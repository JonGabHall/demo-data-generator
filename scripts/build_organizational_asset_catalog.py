"""One-off builder for the organizational asset geo-catalog demo geodatabase."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime as DateTime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import sys
import traceback
from typing import Any, Iterable

import arcpy


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

from indoors_demo_generator.generation import (  # noqa: E402
    SourceFacilityRecord,
    SourceUnitRecord,
    _insert_asset_locations,
    _insert_exterior_asset_locations,
    _insert_lifecycle_records,
    allocate_exterior_assets,
    allocate_indoor_assets_with_summary,
    deterministic_run_id,
)
from indoors_demo_generator.floorplans import (  # noqa: E402
    FacilityFloorPlan,
    Rectangle,
    create_facility_floor_plan,
    unit_program_attributes,
)
from indoors_demo_generator.narratives import (  # noqa: E402
    LocalJsonNarrator,
    narrative_run_metadata,
)
from indoors_demo_generator.rules import load_facility_profile  # noqa: E402
from indoors_demo_generator.preflight import validate_indoors_source  # noqa: E402
from indoors_demo_generator.schema import (  # noqa: E402
    AssetManagementSchema,
    create_asset_management_schema,
)


SOURCE_GDB = Path(
    r"c:\Workspace\Sandbox\data\ILM_asset_gen\Medical Indoors_3141f0\GDBs\Vertex_Assets.gdb"
)
VERTEX_ENRICHED_GDB = SOURCE_GDB.with_name("Vertex_Assets_Enriched.gdb")
OUTPUT_GDB = SOURCE_GDB.parent / "Organizational_Asset_Catalog.gdb"
MANIFEST_PATH = SOURCE_GDB.parent / "Organizational_Asset_Catalog_manifest.json"
LOG_PATH = SOURCE_GDB.parent / "Organizational_Asset_Catalog_build.log"
REFERENCE_DATE = date(2026, 9, 28)
INSPECTION_START = date(2021, 9, 28)
INSPECTION_END = date(2026, 3, 28)
BASE_SEED = 3141

HOSPITALS = (
    ("PP", "Point Place", "Seattle", "WA", -122.3321, 47.6062),
    ("LL", "Line Lake", "Chicago", "IL", -87.6298, 41.8781),
    ("NN", "Node North", "New York", "NY", -73.9352, 40.7306),
    ("RC", "Rohdran Cove", "Miami", "FL", -80.1918, 25.7617),
)
ADMIN = ("AHQ", "Admin HQ", "Denver", "CO", -104.9903, 39.7392)

EXPECTED_LIFE_RANGES = {
    "Building Services": (15, 25),
    "Clinical Equipment": (8, 12),
    "Communications Equipment": (6, 10),
    "Diagnostic Equipment": (8, 12),
    "Electrical Equipment": (20, 30),
    "Fire and Life Safety": (12, 20),
    "Furniture": (10, 15),
    "IT Equipment": (4, 8),
    "Plumbing Equipment": (20, 30),
    "Security Equipment": (7, 12),
}

FACILITY_METADATA = {
    "VMC": ("Vertex Medical Center", "Hospital", "Meridian", "Reference"),
    **{
        code: (name, "Hospital", city, region)
        for code, name, city, region, _, _ in HOSPITALS
    },
    ADMIN[0]: (ADMIN[1], "Business Center", ADMIN[2], ADMIN[3]),
}

FACILITY_LIFECYCLE_BIAS = {
    "VMC": 0.12,
    "PP": 0.02,
    "LL": 0.08,
    "NN": -0.04,
    "RC": 0.16,
    "AHQ": -0.18,
}

REPLACEMENT_COST_RANGES = {
    "Building Services": (8_000, 180_000),
    "Clinical Equipment": (2_500, 95_000),
    "Communications Equipment": (800, 18_000),
    "Diagnostic Equipment": (12_000, 350_000),
    "Electrical Equipment": (1_200, 125_000),
    "Fire and Life Safety": (500, 28_000),
    "Furniture": (250, 6_000),
    "IT Equipment": (700, 14_000),
    "Plumbing Equipment": (600, 22_000),
    "Security Equipment": (450, 16_000),
}

MANUFACTURERS = {
    "Building Services": ("Trane", "Carrier", "Johnson Controls"),
    "Clinical Equipment": ("GE HealthCare", "Philips", "Stryker"),
    "Communications Equipment": ("Cisco", "Poly", "Motorola Solutions"),
    "Diagnostic Equipment": ("Siemens Healthineers", "Canon Medical", "Abbott"),
    "Electrical Equipment": ("Eaton", "Schneider Electric", "Siemens"),
    "Fire and Life Safety": ("Honeywell", "Simplex", "Siemens"),
    "Furniture": ("Steelcase", "Herman Miller", "Haworth"),
    "IT Equipment": ("Dell", "HP", "Lenovo"),
    "Plumbing Equipment": ("Kohler", "Sloan", "Zurn"),
    "Security Equipment": ("Axis", "Bosch", "HID Global"),
}

INSPECTORS = {
    "VMC": ("Avery Morgan", "Jordan Lee"),
    "PP": ("Taylor Brooks", "Morgan Diaz"),
    "LL": ("Casey Patel", "Jamie Wilson"),
    "NN": ("Riley Chen", "Drew Carter"),
    "RC": ("Alex Rivera", "Sam Bennett"),
    "AHQ": ("Cameron Price", "Parker Shah"),
}

SERVICE_PROVIDERS = {
    "VMC": ("Vertex Clinical Engineering", "Meridian Facilities"),
    "PP": ("Cascade Medical Service", "Point Facilities"),
    "LL": ("Lakeshore Technical", "Line Lake Operations"),
    "NN": ("Northeast Clinical Systems", "Node Facilities"),
    "RC": ("Coastal Medical Service", "Rohdran Operations"),
    "AHQ": ("Front Range Building Systems", "Admin Workplace Services"),
}


def _checkpoint(message: str) -> None:
    timestamp = DateTime.now().isoformat(timespec="seconds")
    line = f"{timestamp} {message}"
    with LOG_PATH.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")
    print(line, flush=True)


def _create_minimal_catalog() -> None:
    arcpy.management.CreateFileGDB(str(OUTPUT_GDB.parent), OUTPUT_GDB.name)
    source_indoors = SOURCE_GDB / "Indoors"
    source_units = source_indoors / "Units"
    spatial_reference = arcpy.Describe(str(source_units)).spatialReference
    target_indoors = OUTPUT_GDB / "Indoors"
    arcpy.management.CreateFeatureDataset(str(OUTPUT_GDB), "Indoors", spatial_reference)
    for name in ("Sites", "Facilities", "Levels", "Units"):
        target = str(target_indoors / name)
        arcpy.management.CopyFeatures(str(source_indoors / name), target)
        arcpy.management.AddGlobalIDs(target)


def _create_catalog_extensions(
    output_gdb: str, schema: AssetManagementSchema
) -> tuple[str, str]:
    for name, field_type, length in (
        ("LifecycleStage", "TEXT", 32),
        ("ExpectedLifeYears", "SHORT", None),
        ("AssetAgeYears", "DOUBLE", None),
        ("RemainingLifeYears", "DOUBLE", None),
        ("ReplacementDueDate", "DATE", None),
        ("ReplacementYear", "SHORT", None),
        ("LastInspectionDate", "DATE", None),
        ("OverdueDays", "LONG", None),
        ("EstimatedReplacementCost", "DOUBLE", None),
        ("Vendor", "TEXT", 128),
        ("PurchaseDate", "DATE", None),
        ("PurchaseCost", "DOUBLE", None),
        ("WarrantyExpirationDate", "DATE", None),
        ("WarrantyStatus", "TEXT", 16),
        ("MaintenanceIntervalDays", "LONG", None),
        ("AnnualMaintenanceCost", "DOUBLE", None),
        ("RiskScore", "SHORT", None),
        ("RiskLevel", "TEXT", 16),
        ("Facility_Name", "TEXT", 255),
        ("Organization_Type", "TEXT", 32),
        ("City", "TEXT", 64),
        ("Region", "TEXT", 32),
        ("Department", "TEXT", 128),
    ):
        _add_field(schema.asset_lifecycle, name, field_type, length)

    facility_catalog = os.path.join(output_gdb, "FacilityCatalog")
    arcpy.management.CreateTable(output_gdb, "FacilityCatalog")
    for name, field_type, length in (
        ("FacilityGlobalID", "GUID", None),
        ("Facility_ID", "TEXT", 64),
        ("Facility_Name", "TEXT", 255),
        ("Organization_Type", "TEXT", 32),
        ("City", "TEXT", 64),
        ("Region", "TEXT", 32),
        ("Longitude", "DOUBLE", None),
        ("Latitude", "DOUBLE", None),
    ):
        _add_field(facility_catalog, name, field_type, length)
    arcpy.management.AddGlobalIDs(facility_catalog)
    arcpy.management.AddIndex(facility_catalog, "FacilityGlobalID", "IX_FacilityCatalog_Facility")
    arcpy.management.CreateRelationshipClass(
        os.path.join(output_gdb, "Indoors", "Facilities"),
        facility_catalog,
        os.path.join(output_gdb, "Facilities_FacilityCatalog"),
        "SIMPLE",
        "Catalog metadata",
        "Indoors facility",
        "NONE",
        "ONE_TO_ONE",
        "NONE",
        "GlobalID",
        "FacilityGlobalID",
    )

    dependencies = os.path.join(output_gdb, "AssetSystemDependency")
    arcpy.management.CreateTable(output_gdb, "AssetSystemDependency")
    for name, field_type, length in (
        ("AssetLifecycleGlobalID", "GUID", None),
        ("Asset_ID", "TEXT", 64),
        ("SystemName", "TEXT", 64),
    ):
        _add_field(dependencies, name, field_type, length)
    arcpy.management.AddGlobalIDs(dependencies)
    arcpy.management.AddIndex(dependencies, "AssetLifecycleGlobalID", "IX_Dependency_Asset")
    arcpy.management.CreateRelationshipClass(
        schema.asset_lifecycle,
        dependencies,
        os.path.join(output_gdb, "AssetLifecycle_SystemDependencies"),
        "SIMPLE",
        "Required system",
        "Asset lifecycle record",
        "NONE",
        "ONE_TO_MANY",
        "NONE",
        "GlobalID",
        "AssetLifecycleGlobalID",
    )
    return facility_catalog, dependencies


def _populate_facility_catalog(output_gdb: str, facility_catalog: str) -> None:
    facilities = os.path.join(output_gdb, "Indoors", "Facilities")
    facility_ids = _key_guid_map(facilities, "FACILITY_ID")
    coordinates = {
        code: (longitude, latitude)
        for code, _, _, _, longitude, latitude in HOSPITALS
    }
    coordinates[ADMIN[0]] = (ADMIN[4], ADMIN[5])
    source_geometry = next(
        geometry for facility_id, geometry in arcpy.da.SearchCursor(
            facilities, ["FACILITY_ID", "SHAPE@"]
        ) if str(facility_id) == "VMC"
    )
    source_label = arcpy.PointGeometry(
        source_geometry.labelPoint, source_geometry.spatialReference
    )
    source_wgs84 = source_label.projectAs(arcpy.SpatialReference(4326))
    coordinates["VMC"] = (source_wgs84.firstPoint.X, source_wgs84.firstPoint.Y)
    fields = [
        "FacilityGlobalID", "Facility_ID", "Facility_Name", "Organization_Type",
        "City", "Region", "Longitude", "Latitude",
    ]
    with arcpy.da.InsertCursor(facility_catalog, fields) as cursor:
        for facility_id, (name, organization_type, city, region) in FACILITY_METADATA.items():
            longitude, latitude = coordinates[facility_id]
            cursor.insertRow(
                (facility_ids[facility_id], facility_id, name, organization_type,
                 city, region, longitude, latitude)
            )


def _dependency_map() -> dict[str, tuple[str, ...]]:
    dependencies: dict[str, set[str]] = defaultdict(set)
    for profile_name in (
        "vertex-v1.json",
        "hospital-v1.json",
        "government-office-v1.json",
    ):
        profile = load_facility_profile(REPOSITORY / "profiles" / profile_name)
        for templates in profile.room_uses.values():
            for template in templates:
                dependencies[template.identifier].update(template.dependencies)
    return {asset_type: tuple(sorted(values)) for asset_type, values in dependencies.items()}


def _schema(workspace: str) -> AssetManagementSchema:
    feature_dataset = os.path.join(workspace, "AssetManagement")
    return AssetManagementSchema(
        feature_dataset=feature_dataset,
        indoor_asset_locations=os.path.join(feature_dataset, "IndoorAssetLocation"),
        exterior_asset_points=os.path.join(feature_dataset, "ExteriorAssetPoints"),
        asset_lifecycle=os.path.join(workspace, "AssetLifecycle"),
        inspections=os.path.join(workspace, "AssetInspection"),
        repairs=os.path.join(workspace, "AssetRepair"),
        work_orders=os.path.join(workspace, "AssetWorkOrder"),
        external_references=os.path.join(workspace, "AssetExternalReference"),
        field_work_links=os.path.join(workspace, "AssetFieldWorkLink"),
        media_references=os.path.join(workspace, "AssetMediaReference"),
    )


def _date_time(value: date) -> DateTime:
    return DateTime.combine(value, DateTime.min.time())


def _normalized_guid(value: Any) -> str:
    return str(value).strip().strip("{}").upper()


def _stable_number(value: str, modulo: int) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], 16) % modulo


def _editable_fields(dataset: str) -> list[str]:
    ignored_types = {"OID", "GlobalID", "Geometry"}
    return [
        field.name
        for field in arcpy.ListFields(dataset)
        if field.type not in ignored_types and field.editable and not field.required
    ]


def _read_features(dataset: str) -> list[dict[str, Any]]:
    fields = _editable_fields(dataset)
    records: list[dict[str, Any]] = []
    with arcpy.da.SearchCursor(dataset, fields + ["SHAPE@JSON"]) as cursor:
        for row in cursor:
            record = dict(zip(fields, row[:-1]))
            record["SHAPE@"] = arcpy.AsShape(json.loads(row[-1]), True)
            records.append(record)
    return records


def _insert_features(dataset: str, records: Iterable[dict[str, Any]]) -> None:
    fields = _editable_fields(dataset) + ["SHAPE@"]
    with arcpy.da.InsertCursor(dataset, fields) as cursor:
        for record in records:
            cursor.insertRow([record.get(field) for field in fields])


def _transform_geometry(
    geometry: Any,
    shift_x: float,
    shift_y: float,
    origin_x: float,
    origin_y: float,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    local_x: float = 0.0,
) -> Any:
    data = json.loads(geometry.JSON)

    def transform_point(point: list[Any]) -> None:
        point[0] = origin_x + (point[0] - origin_x) * scale_x + shift_x + local_x
        point[1] = origin_y + (point[1] - origin_y) * scale_y + shift_y

    def visit(value: Any) -> None:
        if not isinstance(value, list):
            return
        if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            transform_point(value)
            return
        for item in value:
            visit(item)

    if "x" in data and "y" in data:
        point = [data["x"], data["y"]]
        transform_point(point)
        data["x"], data["y"] = point
    for key in ("rings", "paths", "points"):
        if key in data:
            visit(data[key])
    return arcpy.AsShape(data, True)


def _target_shift(
    longitude: float, latitude: float, spatial_reference: Any, origin_x: float, origin_y: float
) -> tuple[float, float]:
    target = arcpy.PointGeometry(
        arcpy.Point(longitude, latitude), arcpy.SpatialReference(4326)
    ).projectAs(spatial_reference)
    return target.firstPoint.X - origin_x, target.firstPoint.Y - origin_y


def _key_guid_map(dataset: str, key_field: str) -> dict[str, str]:
    identifiers: dict[str, str] = {}
    with arcpy.da.SearchCursor(dataset, [key_field, "GlobalID"]) as cursor:
        identifiers.update(
            (str(key), str(global_id)) for key, global_id in cursor
        )
    return identifiers


def _add_field(dataset: str, name: str, field_type: str, length: int | None = None) -> None:
    if name.upper() in {field.name.upper() for field in arcpy.ListFields(dataset)}:
        return
    arguments: list[Any] = [dataset, name, field_type]
    if length is not None:
        arguments.extend([None, None, length])
    arcpy.management.AddField(*arguments)


def _guid_translation(
    source_ids: dict[str, str], target_ids: dict[str, str], identity_name: str
) -> dict[str, str]:
    if source_ids.keys() != target_ids.keys():
        raise RuntimeError(f"Enriched Vertex {identity_name} identities do not match the catalog.")
    return {
        _normalized_guid(source_ids[key]): target_ids[key]
        for key in source_ids
    }


def _copy_common_rows(
    source: str,
    target: str,
    guid_remaps: dict[str, dict[str, str]] | None = None,
) -> None:
    source_fields = {
        field.name.upper(): field.name for field in arcpy.ListFields(source)
    }
    target_fields = _editable_fields(target)
    fields = [field for field in target_fields if field.upper() in source_fields]
    source_cursor_fields = [source_fields[field.upper()] for field in fields]
    if getattr(arcpy.Describe(source), "shapeType", None):
        fields.append("SHAPE@")
        source_cursor_fields.append("SHAPE@")
    with arcpy.da.SearchCursor(source, source_cursor_fields) as reader, arcpy.da.InsertCursor(
        target, fields
    ) as writer:
        for source_row in reader:
            row = list(source_row)
            for field_name, replacements in (guid_remaps or {}).items():
                if field_name not in fields:
                    continue
                index = fields.index(field_name)
                if row[index] is not None:
                    normalized = _normalized_guid(row[index])
                    try:
                        row[index] = replacements[normalized]
                    except KeyError as error:
                        raise RuntimeError(
                            f"{os.path.basename(source)} contains an unresolved {field_name}."
                        ) from error
            writer.insertRow(row)


def _import_enriched_vertex(
    output_gdb: str, target_schema: AssetManagementSchema
) -> tuple[set[str], dict[str, int]]:
    if not arcpy.Exists(str(VERTEX_ENRICHED_GDB)):
        raise FileNotFoundError(
            "The organization catalog requires the reviewed Vertex enrichment output: "
            f"{VERTEX_ENRICHED_GDB}"
        )
    source_schema = _schema(str(VERTEX_ENRICHED_GDB))
    source_datasets = (
        source_schema.indoor_asset_locations,
        source_schema.exterior_asset_points,
        source_schema.asset_lifecycle,
        source_schema.inspections,
        source_schema.repairs,
        source_schema.work_orders,
        source_schema.external_references,
        source_schema.field_work_links,
        source_schema.media_references,
    )
    missing = [dataset for dataset in source_datasets if not arcpy.Exists(dataset)]
    if missing:
        raise RuntimeError(
            "Vertex enrichment output is incomplete: "
            + ", ".join(os.path.basename(dataset) for dataset in missing)
        )

    source_indoors = VERTEX_ENRICHED_GDB / "Indoors"
    target_indoors = Path(output_gdb) / "Indoors"
    unit_ids = _guid_translation(
        _key_guid_map(str(source_indoors / "Units"), "UNIT_ID"),
        _key_guid_map(str(target_indoors / "Units"), "UNIT_ID"),
        "Unit",
    )
    facility_ids = _guid_translation(
        _key_guid_map(str(source_indoors / "Facilities"), "FACILITY_ID"),
        _key_guid_map(str(target_indoors / "Facilities"), "FACILITY_ID"),
        "Facility",
    )

    _copy_common_rows(
        source_schema.indoor_asset_locations,
        target_schema.indoor_asset_locations,
        {"SourceUnitGlobalID": unit_ids},
    )
    point_ids = _guid_translation(
        _key_guid_map(source_schema.indoor_asset_locations, "Asset_ID"),
        _key_guid_map(target_schema.indoor_asset_locations, "Asset_ID"),
        "asset-point",
    )
    _copy_common_rows(
        source_schema.asset_lifecycle,
        target_schema.asset_lifecycle,
        {
            "AssetPointGlobalID": point_ids,
            "SourceUnitGlobalID": unit_ids,
        },
    )
    lifecycle_ids = _guid_translation(
        _key_guid_map(source_schema.asset_lifecycle, "Asset_ID"),
        _key_guid_map(target_schema.asset_lifecycle, "Asset_ID"),
        "lifecycle",
    )
    _copy_common_rows(
        source_schema.exterior_asset_points,
        target_schema.exterior_asset_points,
        {"SourceFacilityGlobalID": facility_ids},
    )
    for source, target, remaps in (
        (
            source_schema.inspections,
            target_schema.inspections,
            {
                "AssetLifecycleGlobalID": lifecycle_ids,
                "AssetPointGlobalID": point_ids,
            },
        ),
        (
            source_schema.repairs,
            target_schema.repairs,
            {
                "AssetLifecycleGlobalID": lifecycle_ids,
                "AssetPointGlobalID": point_ids,
            },
        ),
        (
            source_schema.work_orders,
            target_schema.work_orders,
            {
                "AssetLifecycleGlobalID": lifecycle_ids,
                "AssetPointGlobalID": point_ids,
            },
        ),
        (
            source_schema.external_references,
            target_schema.external_references,
            {"AssetGlobalID": lifecycle_ids},
        ),
        (
            source_schema.field_work_links,
            target_schema.field_work_links,
            {"AssetGlobalID": lifecycle_ids},
        ),
        (
            source_schema.media_references,
            target_schema.media_references,
            {"AssetLifecycleGlobalID": lifecycle_ids},
        ),
    ):
        _copy_common_rows(source, target, remaps)

    asset_ids = set(_key_guid_map(source_schema.asset_lifecycle, "Asset_ID"))
    counts = {
        "indoor_assets": _row_count(source_schema.indoor_asset_locations),
        "exterior_assets": _row_count(source_schema.exterior_asset_points),
        "lifecycle_assets": _row_count(source_schema.asset_lifecycle),
        "inspections": _row_count(source_schema.inspections),
        "repairs": _row_count(source_schema.repairs),
        "work_orders": _row_count(source_schema.work_orders),
    }
    return asset_ids, counts


def _rectangle_geometry(
    rectangle: Rectangle,
    center_x: float,
    center_y: float,
    rotation_degrees: float,
    scale: float,
    spatial_reference: Any,
) -> Any:
    angle = math.radians(rotation_degrees)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    coordinates = []
    for local_x, local_y in (
        (rectangle.xmin, rectangle.ymin),
        (rectangle.xmax, rectangle.ymin),
        (rectangle.xmax, rectangle.ymax),
        (rectangle.xmin, rectangle.ymax),
        (rectangle.xmin, rectangle.ymin),
    ):
        scaled_x = local_x * scale
        scaled_y = local_y * scale
        coordinates.append(
            arcpy.Point(
                center_x + scaled_x * cosine - scaled_y * sine,
                center_y + scaled_x * sine + scaled_y * cosine,
            )
        )
    return arcpy.Polygon(arcpy.Array(coordinates), spatial_reference)


def _set_if_present(record: dict[str, Any], field: str, value: Any) -> None:
    if field in record:
        record[field] = value


def _unit_capacity(use_type: str) -> int:
    capacities = {
        "EXAM_ROOM": 2,
        "MEETING_ROOM": 8,
        "OFFICE": 1,
        "OPERATING_ROOM": 8,
        "PATIENT_ROOM": 2,
        "PUBLIC_SERVICE_COUNTER": 4,
        "RECEPTION": 10,
        "STAFF_SUPPORT": 6,
    }
    return capacities.get(use_type, 0)


def _apply_unit_program_attributes(record: dict[str, Any], use_type: str) -> None:
    for field, value in unit_program_attributes(use_type).items():
        _set_if_present(record, field, value)


def _fit_plan_scale(
    plan: FacilityFloorPlan,
    source_facility: Any,
    target_site: Any,
    center_x: float,
    center_y: float,
    spatial_reference: Any,
) -> tuple[float, Any]:
    source_extent = source_facility.extent
    scale = 0.8 * min(
        source_extent.width / plan.footprint.width,
        source_extent.height / plan.footprint.height,
    )
    for _ in range(20):
        geometry = _rectangle_geometry(
            plan.footprint,
            center_x,
            center_y,
            plan.rotation_degrees,
            scale,
            spatial_reference,
        )
        if target_site.contains(geometry):
            return scale, geometry
        scale *= 0.9
    raise RuntimeError(f"Unable to fit {plan.facility_id} within its generated Site.")


def _create_synthetic_hierarchy(
    output_gdb: str,
    templates: dict[str, list[dict[str, Any]]],
    code: str,
    name: str,
    facility_kind: str,
    shift_x: float,
    shift_y: float,
    origin_x: float,
    origin_y: float,
) -> tuple[list[dict[str, Any]], Any]:
    site_template = next(
        item for item in templates["sites"] if str(item["SITE_ID"]) == "MMC"
    )
    facility_template = next(
        item for item in templates["facilities"] if str(item["FACILITY_ID"]) == "VMC"
    )
    level_template = next(
        item for item in templates["levels"] if str(item["FACILITY_ID"]) == "VMC"
    )
    unit_template = next(iter(templates["units"]))
    plan = create_facility_floor_plan(code, name, facility_kind)
    center_x = origin_x + shift_x
    center_y = origin_y + shift_y
    spatial_reference = facility_template["SHAPE@"].spatialReference

    site = dict(site_template)
    site["SITE_ID"] = code
    site["NAME"] = f"{name} Campus" if facility_kind == "hospital" else name
    site["NAME_LONG"] = site["NAME"]
    site["SHAPE@"] = _transform_geometry(
        site["SHAPE@"], shift_x, shift_y, origin_x, origin_y
    )
    _insert_features(os.path.join(output_gdb, "Indoors", "Sites"), [site])

    scale, facility_geometry = _fit_plan_scale(
        plan,
        facility_template["SHAPE@"],
        site["SHAPE@"],
        center_x,
        center_y,
        spatial_reference,
    )
    facility = dict(facility_template)
    facility["FACILITY_ID"] = code
    facility["SITE_ID"] = code
    facility["NAME"] = name
    facility["NAME_LONG"] = name
    _, _, city, region = FACILITY_METADATA[code]
    facility["Address"] = (
        f"100 Catalog Way, {city}, {region}"
        if facility_kind == "hospital"
        else f"1 Administration Plaza, {city}, {region}"
    )
    levels_above_ground = sum(
        bool(level.units) and level.vertical_order >= 0 for level in plan.levels
    )
    has_roof = any(not level.units and level.short_name == "Roof" for level in plan.levels)
    _set_if_present(facility, "LEVELS_ABOVE_GROUND", levels_above_ground)
    _set_if_present(
        facility,
        "LEVELS_BELOW_GROUND",
        sum(level.vertical_order < 0 for level in plan.levels),
    )
    _set_if_present(
        facility,
        "HEIGHT_RELATIVE",
        levels_above_ground * 4.5 + (2.5 if has_roof else 0.0),
    )
    _set_if_present(
        facility,
        "Hours",
        "Open 24 hours" if facility_kind == "hospital" else "Monday-Friday, 7:00 AM-7:00 PM",
    )
    for image_field in ("image_url_1", "image_url_2", "image_url_3"):
        _set_if_present(facility, image_field, None)
    _set_if_present(facility, "AREA_GROSS", facility_geometry.area)
    facility["SHAPE@"] = facility_geometry
    _insert_features(os.path.join(output_gdb, "Indoors", "Facilities"), [facility])

    level_records: list[dict[str, Any]] = []
    unit_records: list[dict[str, Any]] = []
    for planned_level in plan.levels:
        level_geometry = _rectangle_geometry(
            planned_level.rectangle,
            center_x,
            center_y,
            plan.rotation_degrees,
            scale,
            spatial_reference,
        )
        target_level = dict(level_template)
        target_level["LEVEL_ID"] = planned_level.level_id
        target_level["FACILITY_ID"] = code
        target_level["NAME"] = planned_level.name
        target_level["NAME_SHORT"] = planned_level.short_name
        target_level["LEVEL_NUMBER"] = planned_level.level_number
        target_level["VERTICAL_ORDER"] = planned_level.vertical_order
        _set_if_present(target_level, "SITE_ID", code)
        _set_if_present(target_level, "AREA_GROSS", level_geometry.area)
        _set_if_present(target_level, "HEIGHT_RELATIVE", 4.5)
        target_level["SHAPE@"] = level_geometry
        level_records.append(target_level)

        for planned_unit in planned_level.units:
            unit_geometry = _rectangle_geometry(
                planned_unit.rectangle,
                center_x,
                center_y,
                plan.rotation_degrees,
                scale,
                spatial_reference,
            )
            target_unit = dict(unit_template)
            target_unit["UNIT_ID"] = planned_unit.unit_id
            target_unit["LEVEL_ID"] = planned_unit.level_id
            target_unit["USE_TYPE"] = planned_unit.use_type
            target_unit["NAME"] = planned_unit.name
            target_unit["NAME_LONG"] = f"{name} {planned_level.name} {planned_unit.name}"
            _set_if_present(target_unit, "FACILITY_ID", code)
            _set_if_present(target_unit, "SITE_ID", code)
            _set_if_present(target_unit, "CAPACITY", _unit_capacity(planned_unit.use_type))
            _set_if_present(target_unit, "AREA_GROSS", unit_geometry.area)
            _set_if_present(target_unit, "AREA_NET", unit_geometry.area)
            _apply_unit_program_attributes(target_unit, planned_unit.use_type)
            target_unit["SHAPE@"] = unit_geometry
            unit_records.append(target_unit)

    _insert_features(os.path.join(output_gdb, "Indoors", "Levels"), level_records)
    _insert_features(os.path.join(output_gdb, "Indoors", "Units"), unit_records)
    return unit_records, facility_geometry


def _materialize_assets(
    output_gdb: str,
    schema: AssetManagementSchema,
    unit_rows: list[dict[str, Any]],
    facility_id: str,
    site_id: str,
    facility_geometry: Any,
    profile_path: Path,
    seed: int,
) -> tuple[int, int]:
    profile = load_facility_profile(profile_path)
    units_path = os.path.join(output_gdb, "Indoors", "Units")
    facilities_path = os.path.join(output_gdb, "Indoors", "Facilities")
    unit_global_ids = _key_guid_map(units_path, "UNIT_ID")
    facility_global_ids = _key_guid_map(facilities_path, "FACILITY_ID")
    source_units = [
        SourceUnitRecord(
            global_id=unit_global_ids[str(row["UNIT_ID"])],
            use_type=str(row["USE_TYPE"]),
            geometry=row["SHAPE@"],
            unit_id=str(row["UNIT_ID"]),
            level_id=str(row["LEVEL_ID"]),
            facility_id=facility_id,
            site_id=site_id,
            generation_key=f"{facility_id}|{row['LEVEL_ID']}|{row['UNIT_ID']}",
        )
        for row in unit_rows
    ]
    indoor_records, skip_summary = allocate_indoor_assets_with_summary(profile, source_units, seed)
    if skip_summary.skipped_unit_count:
        raise RuntimeError(
            f"{facility_id} skipped {skip_summary.skipped_unit_count} mapped Units during asset allocation."
        )
    run_id = deterministic_run_id(profile, seed)
    _insert_asset_locations(arcpy, schema, indoor_records, run_id)
    _insert_lifecycle_records(arcpy, schema, indoor_records, run_id)

    source_facility = SourceFacilityRecord(
        global_id=facility_global_ids[facility_id],
        geometry=facility_geometry,
        generation_key=facility_id,
    )
    exterior_records, skipped = allocate_exterior_assets(profile, [source_facility], seed)
    if skipped:
        raise RuntimeError(f"{facility_id} exterior asset allocation failed.")
    _insert_exterior_asset_locations(arcpy, schema, exterior_records, run_id)
    return len(indoor_records), len(exterior_records)


def _maintenance_intervals() -> dict[str, int]:
    intervals: dict[str, int] = {}
    for profile_name in (
        "vertex-v1.json",
        "hospital-v1.json",
        "government-office-v1.json",
    ):
        profile = load_facility_profile(REPOSITORY / "profiles" / profile_name)
        for templates in profile.room_uses.values():
            for template in templates:
                intervals[template.identifier] = template.maintenance_interval_days
    return intervals


def _enrich_lifecycle(
    schema: AssetManagementSchema,
    units_path: str,
    preserved_asset_ids: set[str],
) -> dict[str, dict[str, Any]]:
    unit_departments = {
        str(unit_id): str(use_type).replace("_", " ").title()
        for unit_id, use_type in arcpy.da.SearchCursor(units_path, ["UNIT_ID", "USE_TYPE"])
    }
    asset_facilities = [
        (str(asset_id), str(facility_id))
        for asset_id, facility_id in arcpy.da.SearchCursor(
            schema.asset_lifecycle, ["Asset_ID", "Facility_ID"]
        )
    ]
    preserved_stages = Counter(
        str(stage)
        for asset_id, stage in arcpy.da.SearchCursor(
            schema.asset_lifecycle, ["Asset_ID", "LifecycleStage"]
        )
        if str(asset_id) in preserved_asset_ids
    )
    recent_count = (
        round(len(asset_facilities) * 0.20)
        - preserved_stages["Recently Installed"]
    )
    replacement_count = (
        round(len(asset_facilities) * 0.30)
        - preserved_stages["Retrofit/Replacement"]
    )
    generated_assets = [
        item for item in asset_facilities if item[0] not in preserved_asset_ids
    ]
    if recent_count < 0 or replacement_count < 0:
        raise RuntimeError("Preserved Vertex lifecycle cohorts exceed organization targets.")
    if recent_count + replacement_count > len(generated_assets):
        raise RuntimeError("Not enough generated assets remain to satisfy lifecycle cohorts.")

    def cohort_score(asset_id: str, facility_id: str, label: str) -> float:
        base = _stable_number(f"{label}|{asset_id}", 1_000_000) / 1_000_000
        bias = FACILITY_LIFECYCLE_BIAS[facility_id]
        return base + (bias if label == "replacement" else -bias)

    replacement_ranked = sorted(
        generated_assets,
        key=lambda item: cohort_score(item[0], item[1], "replacement"),
        reverse=True,
    )
    replacement_ids = {asset_id for asset_id, _ in replacement_ranked[:replacement_count]}
    recent_ranked = sorted(
        (item for item in generated_assets if item[0] not in replacement_ids),
        key=lambda item: cohort_score(item[0], item[1], "recent"),
        reverse=True,
    )
    recent_ids = {asset_id for asset_id, _ in recent_ranked[:recent_count]}
    stage_by_id = {
        asset_id: (
            "Retrofit/Replacement" if asset_id in replacement_ids
            else "Recently Installed" if asset_id in recent_ids
            else "Within Service Life"
        )
        for asset_id, _ in asset_facilities
    }

    intervals = _maintenance_intervals()
    fields = [
        "Asset_ID", "AssetType", "AssetClass", "Facility_ID", "Unit_ID", "Criticality",
        "Condition", "CommissioningDate", "NextMaintenanceDate", "Make", "Model", "Serial",
        "Owner", "LifecycleStage", "ExpectedLifeYears", "AssetAgeYears",
        "RemainingLifeYears", "ReplacementDueDate", "ReplacementYear", "LastInspectionDate",
        "OverdueDays", "EstimatedReplacementCost", "Facility_Name", "Organization_Type",
        "City", "Region", "Department",
    ]
    assets: dict[str, dict[str, Any]] = {}
    with arcpy.da.UpdateCursor(schema.asset_lifecycle, fields) as cursor:
        for row in cursor:
            asset_id = str(row[0])
            asset_type = str(row[1])
            asset_class = str(row[2])
            facility_id = str(row[3])
            unit_id = str(row[4])
            criticality = str(row[5])
            facility_name, organization_type, city, region = FACILITY_METADATA[facility_id]
            department = unit_departments.get(unit_id, "Building Exterior")
            if asset_id in preserved_asset_ids:
                row[22:] = [
                    facility_name,
                    organization_type,
                    city,
                    region,
                    department,
                ]
                cursor.updateRow(row)
                assets[asset_id] = {
                    "asset_type": asset_type,
                    "asset_class": asset_class,
                    "facility_id": facility_id,
                    "facility_name": facility_name,
                    "organization_type": organization_type,
                    "condition": str(row[6]),
                    "criticality": criticality,
                    "stage": str(row[13]),
                    "commissioning": row[7].date(),
                    "last_inspection": row[19].date(),
                    "maintenance_interval": intervals.get(asset_type, 365),
                    "replacement_cost": float(row[21]),
                }
                continue
            stage = stage_by_id[asset_id]
            randomizer = random.Random(f"lifecycle|{BASE_SEED}|{asset_id}")
            life_min, life_max = EXPECTED_LIFE_RANGES[asset_class]
            life_years = randomizer.randint(life_min, life_max)
            life_days = round(life_years * 365.25)
            if stage == "Recently Installed":
                age_days = randomizer.randint(184, min(730, round(life_days * 0.25)))
            elif stage == "Within Service Life":
                age_days = randomizer.randint(round(life_days * 0.20), round(life_days * 0.75))
            else:
                age_days = randomizer.randint(round(life_days * 0.80), round(life_days * 1.05))
            commissioning = REFERENCE_DATE - timedelta(days=age_days)
            replacement_due = commissioning + timedelta(days=life_days)
            maintenance_interval = intervals.get(asset_type, 365)
            inspection_lower = max(INSPECTION_START, commissioning)
            inspection_span = (INSPECTION_END - inspection_lower).days
            recency_window = min(inspection_span, maintenance_interval * 2)
            last_inspection = INSPECTION_END - timedelta(
                days=randomizer.randint(0, recency_window)
            )
            if last_inspection < inspection_lower:
                last_inspection = inspection_lower
            next_maintenance = last_inspection + timedelta(days=maintenance_interval)
            overdue_days = max(0, (REFERENCE_DATE - next_maintenance).days)

            condition_roll = randomizer.randrange(100)
            if stage == "Retrofit/Replacement":
                condition = (
                    "Operational" if condition_roll < 58
                    else "Maintenance Due" if condition_roll < 90
                    else "Offline Repair"
                )
            elif stage == "Within Service Life":
                condition = (
                    "Operational" if condition_roll < 88
                    else "Maintenance Due" if condition_roll < 97
                    else "Offline Repair"
                )
            else:
                condition = "Operational" if condition_roll < 96 else "Maintenance Due"
            if overdue_days > maintenance_interval and condition == "Operational" and condition_roll % 3 == 0:
                condition = "Maintenance Due"

            cost_min, cost_max = REPLACEMENT_COST_RANGES[asset_class]
            replacement_cost = float(randomizer.randint(cost_min, cost_max))
            manufacturers = MANUFACTURERS[asset_class]
            manufacturer = manufacturers[randomizer.randrange(len(manufacturers))]
            model = f"{asset_type[:18]}-{100 + randomizer.randrange(900)}"
            serial = hashlib.sha256(f"serial|{asset_id}".encode()).hexdigest()[:16].upper()
            owner = (
                "Clinical Engineering" if asset_class in {"Clinical Equipment", "Diagnostic Equipment"}
                else "Digital Infrastructure" if asset_class in {"IT Equipment", "Communications Equipment", "Security Equipment"}
                else "Workplace Services" if asset_class == "Furniture"
                else "Facilities Engineering"
            )
            age_years = round(age_days / 365.25, 1)
            remaining_years = round((replacement_due - REFERENCE_DATE).days / 365.25, 1)
            row[6:] = [
                condition, _date_time(commissioning), _date_time(next_maintenance), manufacturer,
                model, serial, owner, stage, life_years, age_years, remaining_years,
                _date_time(replacement_due), replacement_due.year, _date_time(last_inspection),
                overdue_days, replacement_cost, facility_name, organization_type, city, region,
                department,
            ]
            cursor.updateRow(row)
            assets[asset_id] = {
                "asset_type": asset_type,
                "asset_class": asset_class,
                "facility_id": facility_id,
                "facility_name": facility_name,
                "organization_type": organization_type,
                "condition": condition,
                "criticality": criticality,
                "stage": stage,
                "commissioning": commissioning,
                "last_inspection": last_inspection,
                "maintenance_interval": maintenance_interval,
                "replacement_cost": replacement_cost,
            }

    with arcpy.da.UpdateCursor(schema.indoor_asset_locations, ["Asset_ID", "Condition"]) as cursor:
        for asset_id, _ in cursor:
            cursor.updateRow((asset_id, assets[str(asset_id)]["condition"]))
    return assets


def _populate_related_tables(
    schema: AssetManagementSchema,
    dependencies_table: str,
    assets: dict[str, dict[str, Any]],
    preserved_asset_ids: set[str],
    narrator: LocalJsonNarrator | None = None,
) -> dict[str, int]:
    lifecycle_ids = {
        str(asset_id): str(global_id)
        for asset_id, global_id in arcpy.da.SearchCursor(
            schema.asset_lifecycle, ["Asset_ID", "GlobalID"]
        )
    }
    point_ids = {
        str(asset_id): str(global_id)
        for asset_id, global_id in arcpy.da.SearchCursor(
            schema.indoor_asset_locations, ["Asset_ID", "GlobalID"]
        )
    }
    inspection_fields = [
        "AssetLifecycleGlobalID",
        "AssetPointGlobalID",
        "Asset_ID",
        "Asset_Type",
        "Inspection_Date",
        "Inspector",
        "Condition_Rating",
        "Repair_Needed",
        "Notes",
        "Estimated_Repair_Cost",
        "Repair_Type",
    ]
    with arcpy.da.InsertCursor(schema.inspections, inspection_fields) as cursor:
        for asset_id, asset in assets.items():
            if asset_id in preserved_asset_ids:
                continue
            stable = _stable_number(asset_id, 10_000)
            inspectors = INSPECTORS[asset["facility_id"]]
            cadence = asset["maintenance_interval"]
            if asset["criticality"] in {"High", "Critical"}:
                cadence = max(90, cadence // 2)
            inspection_date = asset["last_inspection"]
            history_index = 0
            while inspection_date >= max(INSPECTION_START, asset["commissioning"]):
                is_latest = history_index == 0
                condition_rating = (
                    {
                        "Operational": "Good" if stable % 5 else "Excellent",
                        "Maintenance Due": "Fair",
                        "Offline Repair": "Poor",
                    }[asset["condition"]]
                    if is_latest else "Good"
                )
                repair_needed = (
                    "Y" if is_latest and asset["condition"] != "Operational" else "N"
                )
                estimated_cost = (
                    round(asset["replacement_cost"] * (0.02 + (stable % 7) / 100), 2)
                    if repair_needed == "Y" else None
                )
                fallback = (
                    f"Condition inspection for {asset['stage'].lower()} asset."
                    if is_latest else "Scheduled preventive inspection completed."
                )
                notes = (
                    narrator.narrate(
                        "inspection",
                        _narrative_facts(
                            asset,
                            condition_rating=condition_rating,
                            repair_needed=repair_needed,
                        ),
                        fallback,
                    )
                    if narrator is not None and is_latest
                    else fallback
                )
                cursor.insertRow(
                    (
                        lifecycle_ids[asset_id],
                        point_ids[asset_id],
                        asset_id,
                        asset["asset_type"],
                        _date_time(inspection_date),
                        inspectors[(stable + history_index) % len(inspectors)],
                        condition_rating,
                        repair_needed,
                        notes,
                        estimated_cost,
                        "Corrective" if repair_needed == "Y" else "Preventive",
                    )
                )
                history_index += 1
                if history_index >= 6:
                    break
                jitter = _stable_number(f"inspection|{asset_id}|{history_index}", 61) - 30
                inspection_date -= timedelta(days=max(60, cadence + jitter))

    repair_fields = [
        "AssetLifecycleGlobalID",
        "AssetPointGlobalID",
        "Asset_ID",
        "Asset_Type",
        "Repair_Date",
        "Technician",
        "Repair_Type",
        "Notes",
        "Repair_Cost",
    ]
    repaired_assets: set[str] = set()
    with arcpy.da.InsertCursor(schema.repairs, repair_fields) as cursor:
        for asset_id, asset in assets.items():
            if asset_id in preserved_asset_ids:
                continue
            stable = _stable_number(f"repair|{asset_id}", 10_000)
            should_repair = (
                asset["stage"] == "Retrofit/Replacement" and stable % 100 < 45
            ) or (asset["stage"] == "Within Service Life" and stable % 100 < 8)
            if not should_repair:
                continue
            providers = SERVICE_PROVIDERS[asset["facility_id"]]
            repair_date = min(
                REFERENCE_DATE,
                asset["last_inspection"] + timedelta(days=7 + stable % 75),
            )
            repair_type = (
                "Corrective Repair"
                if asset["condition"] != "Operational"
                else "Preventive Service"
            )
            repair_notes = (
                narrator.narrate(
                    "repair",
                    _narrative_facts(asset, repair_type=repair_type),
                    "Condition-based lifecycle service completed.",
                )
                if narrator is not None
                else "Condition-based lifecycle service completed."
            )
            cursor.insertRow(
                (
                    lifecycle_ids[asset_id],
                    point_ids[asset_id],
                    asset_id,
                    asset["asset_type"],
                    _date_time(repair_date),
                    providers[stable % len(providers)],
                    repair_type,
                    repair_notes,
                    round(asset["replacement_cost"] * (0.01 + (stable % 8) / 100), 2),
                )
            )
            repaired_assets.add(asset_id)

    work_order_fields = [
        "AssetLifecycleGlobalID",
        "AssetPointGlobalID",
        "Work_Order_ID",
        "Request_Type",
        "Request_Date",
        "Description_of_Issue",
        "Asset_ID",
        "Asset_Type",
        "Unit_ID",
        "Level_ID",
        "Facility_ID",
        "Facility_Name",
        "Assignee",
        "Status",
    ]
    location_data = {
        str(asset_id): (unit_id, level_id)
        for asset_id, unit_id, level_id in arcpy.da.SearchCursor(
            schema.asset_lifecycle, ["Asset_ID", "Unit_ID", "Level_ID"]
        )
    }
    with arcpy.da.InsertCursor(schema.work_orders, work_order_fields) as cursor:
        for asset_id, asset in assets.items():
            if asset_id in preserved_asset_ids:
                continue
            stable = _stable_number(f"work|{asset_id}", 10_000)
            active = asset["condition"] != "Operational"
            if not active and asset_id not in repaired_assets:
                continue
            unit_id, level_id = location_data[asset_id]
            providers = SERVICE_PROVIDERS[asset["facility_id"]]
            request_date = asset["last_inspection"] + timedelta(days=1 + stable % 60)
            request_date = min(request_date, REFERENCE_DATE)
            status = ("Open", "Assigned", "In Progress", "On Hold")[stable % 4] if active else "Completed"
            request_type = (
                "Corrective Maintenance" if active else "Completed Lifecycle Service"
            )
            description = (
                narrator.narrate(
                    "work_order",
                    _narrative_facts(
                        asset,
                        request_type=request_type,
                        status=status,
                    ),
                    "Condition-based maintenance action generated from the synthetic inspection history.",
                )
                if narrator is not None
                else "Condition-based maintenance action generated from the synthetic inspection history."
            )
            cursor.insertRow(
                (
                    lifecycle_ids[asset_id],
                    point_ids[asset_id],
                    f"WO-{hashlib.sha1(asset_id.encode()).hexdigest()[:12].upper()}",
                    request_type,
                    _date_time(request_date),
                    description,
                    asset_id,
                    asset["asset_type"],
                    unit_id,
                    level_id,
                    asset["facility_id"],
                    asset["facility_name"],
                    providers[stable % len(providers)],
                    status,
                )
            )

    dependency_fields = ["AssetLifecycleGlobalID", "Asset_ID", "SystemName"]
    dependencies_by_type = _dependency_map()
    with arcpy.da.InsertCursor(dependencies_table, dependency_fields) as cursor:
        for asset_id, asset in assets.items():
            for system_name in dependencies_by_type.get(asset["asset_type"], ()):
                cursor.insertRow((lifecycle_ids[asset_id], asset_id, system_name))

    return {
        "inspections": _row_count(schema.inspections),
        "repairs": _row_count(schema.repairs),
        "work_orders": _row_count(schema.work_orders),
        "external_references": _row_count(schema.external_references),
        "field_work_links": _row_count(schema.field_work_links),
        "media_references": _row_count(schema.media_references),
        "system_dependencies": _row_count(dependencies_table),
    }


def _narrative_facts(asset: dict[str, Any], **details: object) -> dict[str, object]:
    facts: dict[str, object] = {
        "asset_type": asset["asset_type"],
        "asset_class": asset["asset_class"],
        "facility_name": asset["facility_name"],
        "organization_type": asset["organization_type"],
        "condition": asset["condition"],
        "criticality": asset["criticality"],
        "lifecycle_stage": asset["stage"],
    }
    facts.update(details)
    return facts


def _row_count(dataset: str) -> int:
    return int(arcpy.management.GetCount(dataset)[0])


def _assert_vertex_preserved(
    target_schema: AssetManagementSchema, preserved_asset_ids: set[str]
) -> None:
    source_schema = _schema(str(VERTEX_ENRICHED_GDB))
    relationship_fields = {
        "ASSETGLOBALID",
        "ASSETLIFECYCLEGLOBALID",
        "ASSETPOINTGLOBALID",
        "SOURCEFACILITYGLOBALID",
        "SOURCEUNITGLOBALID",
    }
    comparisons = (
        (source_schema.indoor_asset_locations, target_schema.indoor_asset_locations, True),
        (source_schema.asset_lifecycle, target_schema.asset_lifecycle, False),
        (source_schema.inspections, target_schema.inspections, False),
        (source_schema.repairs, target_schema.repairs, False),
        (source_schema.work_orders, target_schema.work_orders, False),
    )
    for source, target, include_geometry in comparisons:
        source_fields = {
            field.name.upper(): field.name
            for field in arcpy.ListFields(source)
            if field.type not in {"OID", "GlobalID", "GUID", "Geometry"}
            and field.name.upper() not in relationship_fields
        }
        target_fields = {
            field.name.upper(): field.name
            for field in arcpy.ListFields(target)
            if field.type not in {"OID", "GlobalID", "GUID", "Geometry"}
            and field.name.upper() not in relationship_fields
        }
        common_names = sorted(source_fields.keys() & target_fields.keys())
        source_cursor_fields = [source_fields[name] for name in common_names]
        target_cursor_fields = [target_fields[name] for name in common_names]
        asset_index = common_names.index("ASSET_ID")
        expected = Counter(
            tuple(row) for row in arcpy.da.SearchCursor(source, source_cursor_fields)
        )
        actual = Counter(
            tuple(row)
            for row in arcpy.da.SearchCursor(target, target_cursor_fields)
            if str(row[asset_index]) in preserved_asset_ids
        )
        if actual != expected:
            raise RuntimeError(
                f"Catalog did not preserve enriched Vertex rows in {os.path.basename(source)}."
            )
        if include_geometry:
            source_geometry = {
                str(asset_id): geometry
                for asset_id, geometry in arcpy.da.SearchCursor(
                    source, [source_fields["ASSET_ID"], "SHAPE@"]
                )
            }
            target_geometry = {
                str(asset_id): geometry
                for asset_id, geometry in arcpy.da.SearchCursor(
                    target, [target_fields["ASSET_ID"], "SHAPE@"]
                )
                if str(asset_id) in preserved_asset_ids
            }
            if source_geometry.keys() != target_geometry.keys() or any(
                not geometry.equals(target_geometry[asset_id])
                for asset_id, geometry in source_geometry.items()
            ):
                raise RuntimeError("Catalog did not preserve enriched Vertex asset geometry.")


def _validate(
    schema: AssetManagementSchema,
    facility_catalog: str,
    dependencies_table: str,
    preserved_asset_ids: set[str],
) -> dict[str, Any]:
    output_gdb = str(OUTPUT_GDB)
    sites = os.path.join(output_gdb, "Indoors", "Sites")
    facilities = os.path.join(output_gdb, "Indoors", "Facilities")
    levels = os.path.join(output_gdb, "Indoors", "Levels")
    units = os.path.join(output_gdb, "Indoors", "Units")
    generated_plans = {
        code: create_facility_floor_plan(code, name, "hospital")
        for code, name, *_ in HOSPITALS
    }
    generated_plans[ADMIN[0]] = create_facility_floor_plan(
        ADMIN[0], ADMIN[1], "office"
    )

    expected_site_ids = {"MMC", *generated_plans}
    site_rows = list(arcpy.da.SearchCursor(sites, ["SITE_ID", "SHAPE@"]))
    site_geometries = {str(site_id): geometry for site_id, geometry in site_rows}
    if len(site_rows) != len(site_geometries) or set(site_geometries) != expected_site_ids:
        raise RuntimeError(f"Site identities do not match the requested catalog: {sorted(site_geometries)}")

    expected_facility_sites = {"VMC": "MMC", **{code: code for code in generated_plans}}
    facility_rows = list(
        arcpy.da.SearchCursor(facilities, ["FACILITY_ID", "SITE_ID", "SHAPE@"])
    )
    facility_sites = {
        str(facility_id): str(site_id)
        for facility_id, site_id, _ in facility_rows
    }
    facility_geometries = {
        str(facility_id): geometry
        for facility_id, _, geometry in facility_rows
    }
    if len(facility_rows) != len(facility_sites) or facility_sites != expected_facility_sites:
        raise RuntimeError(f"Facility-to-Site hierarchy is invalid: {facility_sites}")

    level_rows = list(
        arcpy.da.SearchCursor(levels, ["LEVEL_ID", "FACILITY_ID", "SHAPE@"])
    )
    level_facilities = {
        str(level_id): str(facility_id)
        for level_id, facility_id, _ in level_rows
    }
    level_geometries = {str(level_id): geometry for level_id, _, geometry in level_rows}
    if len(level_rows) != len(level_facilities):
        raise RuntimeError("Levels contains duplicate LEVEL_ID values.")
    orphan_levels = {
        level_id: facility_id
        for level_id, facility_id in level_facilities.items()
        if facility_id not in facility_sites
    }
    if orphan_levels:
        raise RuntimeError(f"Levels contains orphan FACILITY_ID values: {orphan_levels}")

    unit_rows = list(
        arcpy.da.SearchCursor(units, ["UNIT_ID", "LEVEL_ID", "USE_TYPE", "NAME", "SHAPE@"])
    )
    unit_levels = {str(unit_id): str(level_id) for unit_id, level_id, *_ in unit_rows}
    if len(unit_rows) != len(unit_levels):
        raise RuntimeError("Units contains duplicate UNIT_ID values.")
    orphan_units = {
        unit_id: level_id
        for unit_id, level_id in unit_levels.items()
        if level_id not in level_facilities
    }
    if orphan_units:
        raise RuntimeError(f"Units contains orphan LEVEL_ID values: {orphan_units}")

    expected_generated_levels = {
        level.level_id: code
        for code, plan in generated_plans.items()
        for level in plan.levels
    }
    actual_generated_levels = {
        level_id: facility_id
        for level_id, facility_id in level_facilities.items()
        if facility_id in generated_plans
    }
    if actual_generated_levels != expected_generated_levels:
        raise RuntimeError("Generated Level identities or Facility parents are inconsistent.")

    expected_generated_units = {
        unit.unit_id: (unit.level_id, unit.use_type, unit.name)
        for plan in generated_plans.values()
        for unit in plan.units
    }
    actual_generated_units = {
        str(unit_id): (str(level_id), str(use_type), str(name))
        for unit_id, level_id, use_type, name, _ in unit_rows
        if str(level_id) in expected_generated_levels
    }
    if actual_generated_units != expected_generated_units:
        raise RuntimeError("Generated Unit identities, names, room uses, or Level parents are inconsistent.")

    if any(geometry is None for geometry in site_geometries.values()):
        raise RuntimeError("Sites contains null geometry.")
    if any(geometry is None for geometry in facility_geometries.values()):
        raise RuntimeError("Facilities contains null geometry.")
    if any(geometry is None for geometry in level_geometries.values()):
        raise RuntimeError("Levels contains null geometry.")
    unit_geometries = {str(unit_id): geometry for unit_id, *_, geometry in unit_rows}
    if any(geometry is None for geometry in unit_geometries.values()):
        raise RuntimeError("Units contains null geometry.")

    for facility_id in generated_plans:
        if not site_geometries[facility_id].contains(facility_geometries[facility_id]):
            raise RuntimeError(f"{facility_id} Facility geometry extends outside its Site.")
    for level_id, facility_id in expected_generated_levels.items():
        parent = facility_geometries[facility_id]
        geometry = level_geometries[level_id]
        if not (parent.contains(geometry) or parent.equals(geometry)):
            raise RuntimeError(f"{level_id} geometry extends outside {facility_id}.")
    for unit_id, (level_id, _, _) in expected_generated_units.items():
        if not level_geometries[level_id].contains(unit_geometries[unit_id]):
            raise RuntimeError(f"{unit_id} geometry extends outside {level_id}.")

    expected_names = {metadata[0] for metadata in FACILITY_METADATA.values()}
    actual_names = {str(row[0]) for row in arcpy.da.SearchCursor(facilities, ["NAME"])}
    if actual_names != expected_names:
        raise RuntimeError(f"Facility names do not match the requested catalog: {sorted(actual_names)}")
    expected_counts = {
        "sites": len(expected_site_ids),
        "facilities": len(expected_facility_sites),
        "levels": _row_count(str(SOURCE_GDB / "Indoors" / "Levels"))
        + sum(len(plan.levels) for plan in generated_plans.values()),
        "units": _row_count(str(SOURCE_GDB / "Indoors" / "Units"))
        + sum(len(plan.units) for plan in generated_plans.values()),
    }
    actual_counts = {
        "sites": _row_count(sites),
        "facilities": _row_count(facilities),
        "levels": _row_count(levels),
        "units": _row_count(units),
    }
    if actual_counts != expected_counts:
        raise RuntimeError(f"Hierarchy count mismatch: {actual_counts}, expected {expected_counts}")

    parent_checks = (
        (schema.indoor_asset_locations, "SourceUnitGlobalID", units, "GlobalID"),
        (schema.exterior_asset_points, "SourceFacilityGlobalID", facilities, "GlobalID"),
        (schema.asset_lifecycle, "AssetPointGlobalID", schema.indoor_asset_locations, "GlobalID"),
        (schema.inspections, "AssetLifecycleGlobalID", schema.asset_lifecycle, "GlobalID"),
        (schema.repairs, "AssetLifecycleGlobalID", schema.asset_lifecycle, "GlobalID"),
        (schema.work_orders, "AssetLifecycleGlobalID", schema.asset_lifecycle, "GlobalID"),
        (schema.inspections, "AssetPointGlobalID", schema.indoor_asset_locations, "GlobalID"),
        (schema.repairs, "AssetPointGlobalID", schema.indoor_asset_locations, "GlobalID"),
        (schema.work_orders, "AssetPointGlobalID", schema.indoor_asset_locations, "GlobalID"),
        (schema.external_references, "AssetGlobalID", schema.asset_lifecycle, "GlobalID"),
        (schema.field_work_links, "AssetGlobalID", schema.asset_lifecycle, "GlobalID"),
        (schema.media_references, "AssetLifecycleGlobalID", schema.asset_lifecycle, "GlobalID"),
        (facility_catalog, "FacilityGlobalID", facilities, "GlobalID"),
        (dependencies_table, "AssetLifecycleGlobalID", schema.asset_lifecycle, "GlobalID"),
    )
    for child, foreign_key, parent, parent_key in parent_checks:
        parent_ids = {
            _normalized_guid(row[0])
            for row in arcpy.da.SearchCursor(parent, [parent_key])
            if row[0] is not None
        }
        child_values = [row[0] for row in arcpy.da.SearchCursor(child, [foreign_key])]
        if any(value is None for value in child_values):
            raise RuntimeError(
                f"{os.path.basename(child)} contains null {foreign_key} references."
            )
        child_ids = {_normalized_guid(value) for value in child_values}
        missing = child_ids - parent_ids
        if missing:
            raise RuntimeError(f"{os.path.basename(child)} contains {len(missing)} orphan references.")

    inspection_dates = [
        row[0].date() for row in arcpy.da.SearchCursor(schema.inspections, ["Inspection_Date"])
    ]
    if not inspection_dates or min(inspection_dates) < INSPECTION_START or max(inspection_dates) > INSPECTION_END:
        raise RuntimeError("Inspection dates fall outside the requested five-year to six-month-ago window.")
    latest_by_asset: dict[str, date] = {}
    for asset_id, inspection_date in arcpy.da.SearchCursor(
        schema.inspections, ["Asset_ID", "Inspection_Date"]
    ):
        key = str(asset_id)
        value = inspection_date.date()
        latest_by_asset[key] = max(value, latest_by_asset.get(key, value))
    recorded_latest = {
        str(asset_id): inspection_date.date()
        for asset_id, inspection_date in arcpy.da.SearchCursor(
            schema.asset_lifecycle, ["Asset_ID", "LastInspectionDate"]
        )
    }
    if latest_by_asset != recorded_latest:
        raise RuntimeError("Lifecycle latest-inspection dates do not match inspection history.")
    stages = Counter(
        str(row[0]) for row in arcpy.da.SearchCursor(schema.asset_lifecycle, ["LifecycleStage"])
    )
    lifecycle_count = _row_count(schema.asset_lifecycle)
    expected_stages = {
        "Recently Installed": round(lifecycle_count * 0.20),
        "Retrofit/Replacement": round(lifecycle_count * 0.30),
    }
    expected_stages["Within Service Life"] = lifecycle_count - sum(expected_stages.values())
    if dict(stages) != expected_stages:
        raise RuntimeError(f"Lifecycle cohort mismatch: {dict(stages)}, expected {expected_stages}")

    facility_asset_counts = Counter(
        str(row[0]) for row in arcpy.da.SearchCursor(schema.asset_lifecycle, ["Facility_ID"])
    )
    if set(facility_asset_counts) != set(FACILITY_METADATA):
        raise RuntimeError(f"One or more facilities have no lifecycle assets: {dict(facility_asset_counts)}")

    for dataset in (schema.indoor_asset_locations, schema.asset_lifecycle):
        for asset_id, unit_id, level_id, facility_id, site_id in arcpy.da.SearchCursor(
            dataset, ["Asset_ID", "Unit_ID", "Level_ID", "Facility_ID", "Site_ID"]
        ):
            unit_key = str(unit_id)
            expected_level = unit_levels.get(unit_key)
            expected_facility = level_facilities.get(expected_level or "")
            expected_site = facility_sites.get(expected_facility or "")
            actual = (str(level_id), str(facility_id), str(site_id))
            expected = (expected_level, expected_facility, expected_site)
            if actual != expected:
                raise RuntimeError(
                    f"{os.path.basename(dataset)} asset {asset_id} has inconsistent hierarchy keys: "
                    f"{actual}, expected {expected}."
                )

    admin_room_count = sum(
        1 for unit_id, in arcpy.da.SearchCursor(units, ["UNIT_ID"])
        if str(unit_id).startswith(f"{ADMIN[0]}-U-")
    )
    expected_admin_rooms = len(generated_plans[ADMIN[0]].units)
    if admin_room_count != expected_admin_rooms:
        raise RuntimeError(
            f"Admin HQ contains {admin_room_count} rooms, expected {expected_admin_rooms}."
        )
    if _row_count(facility_catalog) != 6:
        raise RuntimeError("FacilityCatalog does not contain one metadata row per facility.")
    if any(
        _row_count(dataset) != 0
        for dataset in (
            schema.external_references,
            schema.field_work_links,
            schema.media_references,
        )
    ):
        raise RuntimeError("Unconfigured integration or media tables must remain empty.")

    direct_relationships = (
        os.path.join(output_gdb, "IndoorLocations_Inspections"),
        os.path.join(output_gdb, "IndoorLocations_Repairs"),
        os.path.join(output_gdb, "IndoorLocations_WorkOrders"),
    )
    missing_relationships = [
        os.path.basename(path) for path in direct_relationships if not arcpy.Exists(path)
    ]
    if missing_relationships:
        raise RuntimeError(
            "Missing direct asset-history relationships: "
            + ", ".join(missing_relationships)
        )
    _assert_vertex_preserved(schema, preserved_asset_ids)

    return {
        **actual_counts,
        "indoor_assets": _row_count(schema.indoor_asset_locations),
        "exterior_assets": _row_count(schema.exterior_asset_points),
        "lifecycle_assets": lifecycle_count,
        "facility_assets": dict(sorted(facility_asset_counts.items())),
        "lifecycle_stages": dict(stages),
        "inspection_date_min": min(inspection_dates).isoformat(),
        "inspection_date_max": max(inspection_dates).isoformat(),
        "orphan_references": 0,
        "direct_asset_history_relationships": len(direct_relationships),
        "admin_hq_rooms": admin_room_count,
        "preserved_vertex_assets": len(preserved_asset_ids),
    }


def main(narrator: LocalJsonNarrator | None = None) -> None:
    if not SOURCE_GDB.exists():
        raise FileNotFoundError(SOURCE_GDB)
    if OUTPUT_GDB.exists() or arcpy.Exists(str(OUTPUT_GDB)):
        raise FileExistsError(f"Output already exists: {OUTPUT_GDB}")

    LOG_PATH.unlink(missing_ok=True)
    MANIFEST_PATH.unlink(missing_ok=True)
    output_created = False
    try:
        _checkpoint("stage=create_minimal_catalog status=started")
        _create_minimal_catalog()
        output_created = True
        output_gdb = str(OUTPUT_GDB)
        _checkpoint("stage=create_minimal_catalog status=complete")

        source = validate_indoors_source(arcpy, output_gdb)
        _checkpoint("stage=create_asset_schema status=started")
        schema = create_asset_management_schema(arcpy, output_gdb, source)
        facility_catalog, dependencies_table = _create_catalog_extensions(output_gdb, schema)
        _checkpoint("stage=create_asset_schema status=complete")

        facilities_path = os.path.join(output_gdb, "Indoors", "Facilities")
        templates = {
            "sites": _read_features(os.path.join(output_gdb, "Indoors", "Sites")),
            "facilities": _read_features(facilities_path),
            "levels": _read_features(os.path.join(output_gdb, "Indoors", "Levels")),
            "units": _read_features(os.path.join(output_gdb, "Indoors", "Units")),
        }
        vertex_facility = next(
            item for item in templates["facilities"]
            if str(item["FACILITY_ID"]) == "VMC"
        )
        base_facility = vertex_facility["SHAPE@"]
        extent = base_facility.extent
        origin_x = (extent.XMin + extent.XMax) / 2
        origin_y = (extent.YMin + extent.YMax) / 2
        spatial_reference = base_facility.spatialReference
        generated_counts: dict[str, dict[str, int]] = {}

        _checkpoint("stage=generate_hierarchy_and_assets status=started")
        original_facility_id = str(vertex_facility["FACILITY_ID"])
        _checkpoint("stage=import_enriched_vertex status=started")
        preserved_asset_ids, vertex_counts = _import_enriched_vertex(output_gdb, schema)
        _checkpoint("stage=import_enriched_vertex status=complete")
        generated_counts[FACILITY_METADATA[original_facility_id][0]] = {
            "indoor_assets": vertex_counts["indoor_assets"],
            "exterior_assets": vertex_counts["exterior_assets"],
        }

        for index, (code, name, _, _, longitude, latitude) in enumerate(HOSPITALS, start=1):
            _checkpoint(f"stage=generate_facility facility={code} status=started")
            shift_x, shift_y = _target_shift(
                longitude, latitude, spatial_reference, origin_x, origin_y
            )
            unit_rows, facility_geometry = _create_synthetic_hierarchy(
                output_gdb,
                templates,
                code,
                name,
                "hospital",
                shift_x,
                shift_y,
                origin_x,
                origin_y,
            )
            indoor_count, exterior_count = _materialize_assets(
                output_gdb,
                schema,
                unit_rows,
                code,
                code,
                facility_geometry,
                REPOSITORY / "profiles" / "hospital-v1.json",
                BASE_SEED + index,
            )
            generated_counts[name] = {"indoor_assets": indoor_count, "exterior_assets": exterior_count}
            _checkpoint(f"stage=generate_facility facility={code} status=complete")

        code, admin_name, _, _, longitude, latitude = ADMIN
        _checkpoint(f"stage=generate_facility facility={code} status=started")
        shift_x, shift_y = _target_shift(longitude, latitude, spatial_reference, origin_x, origin_y)
        admin_units, admin_geometry = _create_synthetic_hierarchy(
            output_gdb,
            templates,
            code,
            admin_name,
            "office",
            shift_x,
            shift_y,
            origin_x,
            origin_y,
        )
        indoor_count, exterior_count = _materialize_assets(
            output_gdb,
            schema,
            admin_units,
            code,
            code,
            admin_geometry,
            REPOSITORY / "profiles" / "government-office-v1.json",
            BASE_SEED + 100,
        )
        generated_counts[admin_name] = {
            "indoor_assets": indoor_count,
            "exterior_assets": exterior_count,
        }
        _checkpoint(f"stage=generate_facility facility={code} status=complete")
        _checkpoint("stage=generate_hierarchy_and_assets status=complete")

        _checkpoint("stage=populate_catalog_history status=started")
        _populate_facility_catalog(output_gdb, facility_catalog)
        units_path = os.path.join(output_gdb, "Indoors", "Units")
        assets = _enrich_lifecycle(schema, units_path, preserved_asset_ids)
        related_counts = _populate_related_tables(
            schema, dependencies_table, assets, preserved_asset_ids, narrator
        )
        _checkpoint("stage=populate_catalog_history status=complete")

        _checkpoint("stage=validate status=started")
        validation = _validate(
            schema, facility_catalog, dependencies_table, preserved_asset_ids
        )
        _checkpoint("stage=validate status=complete")
        manifest = {
            "created_utc": DateTime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_geodatabase": str(SOURCE_GDB),
            "vertex_enrichment_geodatabase": str(VERTEX_ENRICHED_GDB),
            "output_geodatabase": str(OUTPUT_GDB),
            "purpose": "Synthetic ArcGIS Online Dashboard and asset knowledge-graph catalog",
            "reference_date": REFERENCE_DATE.isoformat(),
            "inspection_window": {
                "start": INSPECTION_START.isoformat(),
                "end": INSPECTION_END.isoformat(),
            },
            "facility_asset_generation": generated_counts,
            "preserved_vertex_history": vertex_counts,
            "related_table_counts": related_counts,
            "narrative_generation": narrative_run_metadata(narrator),
            "validation": validation,
            "synthetic_geographic_anchors": {
                name: {"city": city, "region": region, "longitude": longitude, "latitude": latitude}
                for _, name, city, region, longitude, latitude in (*HOSPITALS, ADMIN)
            },
        }
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        _checkpoint("stage=manifest status=complete")
        print(json.dumps(manifest, indent=2))
    except Exception as error:
        _checkpoint(f"stage=failed error={type(error).__name__}: {error}")
        traceback_text = traceback.format_exc()
        with LOG_PATH.open("a", encoding="utf-8") as stream:
            stream.write(traceback_text)
        print(traceback_text, file=sys.stderr, flush=True)
        if output_created:
            arcpy.ClearWorkspaceCache_management()
            if arcpy.Exists(str(OUTPUT_GDB)):
                try:
                    arcpy.management.Delete(str(OUTPUT_GDB))
                except arcpy.ExecuteError:
                    pass
            if OUTPUT_GDB.exists():
                shutil.rmtree(OUTPUT_GDB, ignore_errors=True)
        raise
    finally:
        arcpy.ClearWorkspaceCache_management()


if __name__ == "__main__":
    main()