"""Materialize deterministic asset rules into generator-owned Indoors datasets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from uuid import uuid5

from .rules import FacilityProfile, GeneratedAsset, NAMESPACE, UnmappedRoomUseError, generate_assets
from .schema import AssetManagementSchema


@dataclass(frozen=True)
class SourceUnitRecord:
    global_id: str
    use_type: str
    geometry: Any
    unit_id: str | None = None
    level_id: str | None = None
    facility_id: str | None = None
    site_id: str | None = None
    generation_key: str | None = None


@dataclass(frozen=True)
class IndoorAssetRecord:
    source_unit: SourceUnitRecord
    asset: GeneratedAsset


@dataclass(frozen=True)
class SourceFacilityRecord:
    global_id: str
    geometry: Any
    generation_key: str | None = None


@dataclass(frozen=True)
class ExteriorAssetRecord:
    source_facility: SourceFacilityRecord
    asset: GeneratedAsset


@dataclass(frozen=True)
class UnitSkipSummary:
    missing_geometry_count: int
    blank_use_type_count: int
    unmapped_use_type_counts: dict[str, int]

    @property
    def skipped_unit_count(self) -> int:
        return (
            self.missing_geometry_count
            + self.blank_use_type_count
            + sum(self.unmapped_use_type_counts.values())
        )


@dataclass(frozen=True)
class GenerationResult:
    run_id: str
    indoor_asset_count: int
    exterior_asset_count: int
    skipped_unit_count: int
    skipped_facility_count: int
    unit_skip_summary: UnitSkipSummary

    @property
    def generated_asset_count(self) -> int:
        return self.indoor_asset_count + self.exterior_asset_count


def allocate_indoor_assets(
    profile: FacilityProfile, units: Iterable[SourceUnitRecord], seed: int
) -> tuple[list[IndoorAssetRecord], int]:
    """Allocate profile assets to mapped Units without using ArcPy."""
    records, skip_summary = allocate_indoor_assets_with_summary(profile, units, seed)
    return records, skip_summary.skipped_unit_count


def allocate_indoor_assets_with_summary(
    profile: FacilityProfile, units: Iterable[SourceUnitRecord], seed: int
) -> tuple[list[IndoorAssetRecord], UnitSkipSummary]:
    """Allocate assets and retain skipped-Unit reasons for GP reporting."""
    records: list[IndoorAssetRecord] = []
    missing_geometry_count = 0
    blank_use_type_count = 0
    unmapped_use_type_counts: dict[str, int] = {}
    for unit in units:
        if unit.geometry is None:
            missing_geometry_count += 1
            continue
        if not isinstance(unit.use_type, str) or not unit.use_type.strip():
            blank_use_type_count += 1
            continue
        try:
            assets = generate_assets(
                profile, unit.generation_key or unit.global_id, unit.use_type, seed
            )
        except UnmappedRoomUseError:
            unmapped_use_type_counts[unit.use_type] = (
                unmapped_use_type_counts.get(unit.use_type, 0) + 1
            )
            continue
        records.extend(IndoorAssetRecord(source_unit=unit, asset=asset) for asset in assets)
    return records, UnitSkipSummary(
        missing_geometry_count, blank_use_type_count, unmapped_use_type_counts
    )


def deterministic_run_id(profile: FacilityProfile, seed: int) -> str:
    """Return a stable identifier for a profile and seed combination."""
    return "{" + str(uuid5(NAMESPACE, f"run|{profile.version}|{seed}")) + "}"


def allocate_exterior_assets(
    profile: FacilityProfile, facilities: Iterable[SourceFacilityRecord], seed: int
) -> tuple[list[ExteriorAssetRecord], int]:
    """Allocate BUILDING_EXTERIOR profile assets to source Facilities."""
    records: list[ExteriorAssetRecord] = []
    skipped_facility_count = 0
    for facility in facilities:
        if facility.geometry is None:
            skipped_facility_count += 1
            continue
        try:
            assets = generate_assets(
                profile,
                facility.generation_key or facility.global_id,
                "BUILDING_EXTERIOR",
                seed,
            )
        except UnmappedRoomUseError:
            skipped_facility_count += 1
            continue
        records.extend(ExteriorAssetRecord(source_facility=facility, asset=asset) for asset in assets)
    return records, skipped_facility_count


def generate_indoor_asset_records(
    arcpy: Any,
    source: Any,
    schema: AssetManagementSchema,
    profile: FacilityProfile,
    seed: int,
) -> GenerationResult:
    """Create linked indoor locations and lifecycle rows for mapped source Units."""
    units = _read_units(arcpy, source)
    indoor_records, unit_skip_summary = allocate_indoor_assets_with_summary(profile, units, seed)
    facilities = _read_facilities(arcpy, source)
    exterior_records, skipped_facility_count = allocate_exterior_assets(profile, facilities, seed)
    run_id = deterministic_run_id(profile, seed)
    _insert_asset_locations(arcpy, schema, indoor_records, run_id)
    _insert_lifecycle_records(arcpy, schema, indoor_records, run_id)
    _insert_exterior_asset_locations(arcpy, schema, exterior_records, run_id)
    return GenerationResult(
        run_id,
        len(indoor_records),
        len(exterior_records),
        unit_skip_summary.skipped_unit_count,
        skipped_facility_count,
        unit_skip_summary,
    )


def _read_units(arcpy: Any, source: Any) -> list[SourceUnitRecord]:
    units_path = source.feature_classes["units"]
    fields = {field.name.upper(): field.name for field in arcpy.ListFields(units_path)}
    optional_names = ("UNIT_ID", "LEVEL_ID", "FACILITY_ID", "SITE_ID")
    selected = [source.unit_global_id_field, source.unit_use_field]
    selected.extend(fields[name] for name in optional_names if name in fields)
    selected.append("SHAPE@")
    positions = {name.upper(): index for index, name in enumerate(selected)}
    records = []
    with arcpy.da.SearchCursor(units_path, selected) as cursor:
        for row in cursor:
            records.append(
                SourceUnitRecord(
                    global_id=row[positions[source.unit_global_id_field.upper()]],
                    use_type=row[positions[source.unit_use_field.upper()]],
                    geometry=row[positions["SHAPE@"]],
                    unit_id=_value(row, positions, "UNIT_ID"),
                    level_id=_value(row, positions, "LEVEL_ID"),
                    facility_id=_value(row, positions, "FACILITY_ID"),
                    site_id=_value(row, positions, "SITE_ID"),
                    generation_key=_unit_generation_key(row, positions),
                )
            )
    return records


def _unit_generation_key(row: tuple[Any, ...], positions: dict[str, int]) -> str | None:
    unit_id = _value(row, positions, "UNIT_ID")
    if unit_id in (None, ""):
        return None
    facility_id = _value(row, positions, "FACILITY_ID")
    level_id = _value(row, positions, "LEVEL_ID")
    return "|".join(str(value or "") for value in (facility_id, level_id, unit_id))


def _value(row: tuple[Any, ...], positions: dict[str, int], name: str) -> Any:
    position = positions.get(name)
    return row[position] if position is not None else None


def _read_facilities(arcpy: Any, source: Any) -> list[SourceFacilityRecord]:
    facilities_path = source.feature_classes["facilities"]
    available = {field.name.upper(): field.name for field in arcpy.ListFields(facilities_path)}
    fields = [source.facility_global_id_field]
    if "FACILITY_ID" in available:
        fields.append(available["FACILITY_ID"])
    fields.append("SHAPE@")
    with arcpy.da.SearchCursor(facilities_path, fields) as cursor:
        return [
            SourceFacilityRecord(
                global_id=row[0],
                geometry=row[-1],
                generation_key=str(row[1]) if len(fields) == 3 and row[1] not in (None, "") else None,
            )
            for row in cursor
        ]


def _insert_asset_locations(
    arcpy: Any, schema: AssetManagementSchema, records: list[IndoorAssetRecord], run_id: str
) -> None:
    fields = [
        "Asset_ID", "Unit_ID", "Level_ID", "Facility_ID", "Site_ID", "Barcode",
        "SourceUnitGlobalID", "RunID", "BusinessID", "AssetType", "AssetClass", "Condition", "SHAPE@",
    ]
    with arcpy.da.InsertCursor(schema.indoor_asset_locations, fields) as cursor:
        for record in records:
            unit, asset = record.source_unit, record.asset
            cursor.insertRow((
                asset.asset_id, unit.unit_id, unit.level_id, unit.facility_id, unit.site_id, asset.business_id,
                unit.global_id, run_id, asset.business_id, asset.template_id, asset.asset_class,
                asset.condition,
                arcpy.PointGeometry(unit.geometry.labelPoint, unit.geometry.spatialReference),
            ))


def _insert_lifecycle_records(
    arcpy: Any, schema: AssetManagementSchema, records: list[IndoorAssetRecord], run_id: str
) -> None:
    with arcpy.da.SearchCursor(schema.indoor_asset_locations, ["Asset_ID", "GlobalID"]) as cursor:
        point_ids = {asset_id: global_id for asset_id, global_id in cursor}
    fields = [
        "Asset_ID", "Name", "Description", "Maintainable", "Fixed", "Criticality_Rating",
        "Unit_ID", "Level_ID", "Facility_ID", "Site_ID", "Barcode", "AssetPointGlobalID",
        "SourceUnitGlobalID", "RunID", "BusinessID", "AssetType", "AssetClass", "Condition",
        "Criticality", "CommissioningDate", "NextMaintenanceDate",
    ]
    with arcpy.da.InsertCursor(schema.asset_lifecycle, fields) as cursor:
        for record in records:
            unit, asset = record.source_unit, record.asset
            cursor.insertRow((
                asset.asset_id, asset.template_id.replace("_", " ").title(),
                f"Synthetic {asset.template_id.replace('_', ' ').lower()} assigned to {asset.room_use}.",
                "Y", "Y", _criticality_rating(asset.criticality), unit.unit_id, unit.level_id,
                unit.facility_id, unit.site_id, asset.business_id, point_ids[asset.asset_id], unit.global_id,
                run_id, asset.business_id, asset.template_id, asset.asset_class, asset.condition,
                asset.criticality, asset.commissioning_date, asset.next_maintenance_date,
            ))


def _insert_exterior_asset_locations(
    arcpy: Any, schema: AssetManagementSchema, records: list[ExteriorAssetRecord], run_id: str
) -> None:
    fields = [
        "SourceFacilityGlobalID", "RunID", "BusinessID", "AssetType", "AssetClass", "PlacementType",
        "Condition", "SHAPE@",
    ]
    with arcpy.da.InsertCursor(schema.exterior_asset_points, fields) as cursor:
        for record in records:
            asset = record.asset
            cursor.insertRow((
                record.source_facility.global_id, run_id, asset.business_id, asset.template_id,
                asset.asset_class, asset.placement_type or "Exterior", asset.condition,
                _exterior_point(arcpy, record.source_facility.geometry, asset.asset_id, asset.placement_type),
            ))


def _exterior_point(arcpy: Any, geometry: Any, asset_id: str, placement_type: str | None) -> Any:
    boundary = geometry.boundary()
    if placement_type == "Exterior":
        extent = geometry.extent
        offset = max(extent.width, extent.height) * 0.02
        if offset > 0:
            boundary = geometry.buffer(offset).boundary()
    fraction = 0.05 + (int(asset_id[:8], 16) % 9000) / 10000
    return boundary.positionAlongLine(fraction, True)


def _criticality_rating(criticality: str) -> int:
    return {"Low": 1, "Medium": 3, "High": 4, "Critical": 5}[criticality]