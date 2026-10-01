"""Create a validated Vertex asset-history geodatabase without modifying the source."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime as DateTime, time, timezone
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Iterable

import arcpy


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

from indoors_demo_generator.enrichment import (  # noqa: E402
    AssetSeed,
    EnrichmentConfig,
    EnrichmentPlan,
    build_enrichment_plan,
)
from indoors_demo_generator.asset_catalog import (  # noqa: E402
    PRICE_BASIS,
    PRICEBOOK_VERSION,
    PRICE_CURRENCY,
)
from indoors_demo_generator.narratives import (  # noqa: E402
    LocalJsonNarrator,
    narrative_run_metadata,
)
from indoors_demo_generator.preflight import validate_indoors_source  # noqa: E402
from indoors_demo_generator.rules import load_facility_profile  # noqa: E402
from indoors_demo_generator.schema import (  # noqa: E402
    AssetManagementSchema,
    create_asset_management_schema,
)


DEFAULT_SOURCE = Path(
    r"c:\Workspace\Sandbox\data\ILM_asset_gen\Medical Indoors_3141f0\GDBs\Vertex_Assets.gdb"
)
DEFAULT_OUTPUT = DEFAULT_SOURCE.with_name("Vertex_Assets_Enriched.gdb")
DEFAULT_REFERENCE_DATE = date(2026, 9, 28)
CHILD_TABLES = (
    "AssetInspection",
    "AssetRepair",
    "AssetWorkOrder",
    "AssetExternalReference",
    "AssetFieldWorkLink",
    "AssetMediaReference",
)
LIFECYCLE_EXTENSION_FIELDS = (
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
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a separately validated Vertex asset lifecycle/history geodatabase."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reference-date", type=date.fromisoformat, default=DEFAULT_REFERENCE_DATE)
    parser.add_argument("--seed", type=int, default=3141)
    parser.add_argument("--llm-endpoint")
    parser.add_argument("--llm-model")
    parser.add_argument("--llm-max-records", type=int, default=100)
    parser.add_argument("--keep-failed-output", action="store_true")
    return parser.parse_args()


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


def _row_count(dataset: str) -> int:
    return int(arcpy.management.GetCount(dataset)[0])


def _normalized_guid(value: object) -> str:
    return str(value).strip().strip("{}").upper()


def _date_time(value: date) -> DateTime:
    return DateTime.combine(value, time.min)


def _add_field(dataset: str, name: str, field_type: str, length: int | None) -> None:
    arguments: list[Any] = [dataset, name, field_type]
    if length is not None:
        arguments.extend([None, None, length])
    arcpy.management.AddField(*arguments)


def _create_minimal_output(source_workspace: str, output_workspace: str) -> None:
    source = validate_indoors_source(arcpy, source_workspace)
    sites = source.feature_classes.get("sites")
    if sites is None:
        raise ValueError("Source is missing the ArcGIS Indoors Sites feature class.")
    output_path = Path(output_workspace)
    arcpy.management.CreateFileGDB(str(output_path.parent), output_path.name)
    spatial_reference = arcpy.Describe(source.feature_classes["units"]).spatialReference
    arcpy.management.CreateFeatureDataset(output_workspace, "Indoors", spatial_reference)
    for name, source_path in (
        ("Sites", sites),
        ("Facilities", source.feature_classes["facilities"]),
        ("Levels", source.feature_classes["levels"]),
        ("Units", source.feature_classes["units"]),
    ):
        target = os.path.join(output_workspace, "Indoors", name)
        arcpy.management.CopyFeatures(source_path, target)
        if not any(field.type == "GlobalID" for field in arcpy.ListFields(target)):
            arcpy.management.AddGlobalIDs(target)


def _ensure_empty_source_children(source_schema: AssetManagementSchema) -> None:
    populated = {
        name: _row_count(os.path.join(Path(source_schema.asset_lifecycle).parent, name))
        for name in CHILD_TABLES
        if arcpy.Exists(os.path.join(Path(source_schema.asset_lifecycle).parent, name))
        and _row_count(os.path.join(Path(source_schema.asset_lifecycle).parent, name))
    }
    if populated:
        raise ValueError(
            "Source child tables contain records and cannot be safely replaced: "
            + ", ".join(f"{name}={count}" for name, count in sorted(populated.items()))
        )


def _key_guid_map(dataset: str, key_field: str) -> dict[str, str]:
    with arcpy.da.SearchCursor(dataset, [key_field, "GlobalID"]) as cursor:
        return {str(key): str(global_id) for key, global_id in cursor}


def _hierarchy(output_workspace: str) -> tuple[dict[str, tuple[str, str, str]], dict[str, str]]:
    indoors = os.path.join(output_workspace, "Indoors")
    facilities = os.path.join(indoors, "Facilities")
    levels = os.path.join(indoors, "Levels")
    units = os.path.join(indoors, "Units")
    facility_data = {
        str(facility_id): (str(site_id), str(name))
        for facility_id, site_id, name in arcpy.da.SearchCursor(
            facilities, ["FACILITY_ID", "SITE_ID", "NAME"]
        )
    }
    level_facilities = {
        str(level_id): str(facility_id)
        for level_id, facility_id in arcpy.da.SearchCursor(
            levels, ["LEVEL_ID", "FACILITY_ID"]
        )
    }
    unit_locations: dict[str, tuple[str, str, str]] = {}
    for unit_id, level_id in arcpy.da.SearchCursor(units, ["UNIT_ID", "LEVEL_ID"]):
        facility_id = level_facilities[str(level_id)]
        site_id, _ = facility_data[facility_id]
        unit_locations[str(unit_id)] = (str(level_id), facility_id, site_id)
    return unit_locations, {key: value[1] for key, value in facility_data.items()}


def _writable_fields(dataset: str) -> list[str]:
    return [
        field.name
        for field in arcpy.ListFields(dataset)
        if field.type not in {"OID", "GlobalID", "Geometry"}
        and field.editable
        and not field.required
    ]


def _copy_asset_schema_rows(
    source_schema: AssetManagementSchema,
    target_schema: AssetManagementSchema,
    output_workspace: str,
) -> None:
    unit_locations, _ = _hierarchy(output_workspace)
    target_units = os.path.join(output_workspace, "Indoors", "Units")
    target_unit_ids = _key_guid_map(target_units, "UNIT_ID")
    source_fields = {field.name.upper() for field in arcpy.ListFields(source_schema.indoor_asset_locations)}
    indoor_fields = [
        field for field in _writable_fields(target_schema.indoor_asset_locations)
        if field.upper() in source_fields
    ]
    with arcpy.da.SearchCursor(
        source_schema.indoor_asset_locations, indoor_fields + ["SHAPE@"]
    ) as source_cursor, arcpy.da.InsertCursor(
        target_schema.indoor_asset_locations, indoor_fields + ["SHAPE@"]
    ) as target_cursor:
        for source_row in source_cursor:
            row = dict(zip(indoor_fields + ["SHAPE@"], source_row))
            unit_id = str(row["Unit_ID"])
            level_id, facility_id, site_id = unit_locations[unit_id]
            row.update(
                {
                    "Level_ID": level_id,
                    "Facility_ID": facility_id,
                    "Site_ID": site_id,
                    "SourceUnitGlobalID": target_unit_ids[unit_id],
                }
            )
            target_cursor.insertRow([row.get(field) for field in indoor_fields + ["SHAPE@"]])

    target_point_ids = _key_guid_map(target_schema.indoor_asset_locations, "Asset_ID")
    lifecycle_source_fields = {
        field.name.upper() for field in arcpy.ListFields(source_schema.asset_lifecycle)
    }
    lifecycle_fields = [
        field for field in _writable_fields(target_schema.asset_lifecycle)
        if field.upper() in lifecycle_source_fields
    ]
    with arcpy.da.SearchCursor(
        source_schema.asset_lifecycle, lifecycle_fields
    ) as source_cursor, arcpy.da.InsertCursor(
        target_schema.asset_lifecycle, lifecycle_fields
    ) as target_cursor:
        for source_row in source_cursor:
            row = dict(zip(lifecycle_fields, source_row))
            asset_id = str(row["Asset_ID"])
            unit_id = str(row["Unit_ID"])
            level_id, facility_id, site_id = unit_locations[unit_id]
            row.update(
                {
                    "Level_ID": level_id,
                    "Facility_ID": facility_id,
                    "Site_ID": site_id,
                    "AssetPointGlobalID": target_point_ids[asset_id],
                    "SourceUnitGlobalID": target_unit_ids[unit_id],
                }
            )
            target_cursor.insertRow([row.get(field) for field in lifecycle_fields])

    source_facilities = os.path.join(str(Path(source_schema.asset_lifecycle).parent), "Indoors", "Facilities")
    target_facilities = os.path.join(output_workspace, "Indoors", "Facilities")
    source_facility_ids = {
        _normalized_guid(global_id): str(facility_id)
        for facility_id, global_id in arcpy.da.SearchCursor(
            source_facilities, ["FACILITY_ID", "GlobalID"]
        )
    }
    target_facility_ids = _key_guid_map(target_facilities, "FACILITY_ID")
    exterior_fields = _writable_fields(target_schema.exterior_asset_points)
    with arcpy.da.SearchCursor(
        source_schema.exterior_asset_points, exterior_fields + ["SHAPE@"]
    ) as source_cursor, arcpy.da.InsertCursor(
        target_schema.exterior_asset_points, exterior_fields + ["SHAPE@"]
    ) as target_cursor:
        for source_row in source_cursor:
            row = dict(zip(exterior_fields + ["SHAPE@"], source_row))
            facility_id = source_facility_ids[_normalized_guid(row["SourceFacilityGlobalID"])]
            row["SourceFacilityGlobalID"] = target_facility_ids[facility_id]
            target_cursor.insertRow([row.get(field) for field in exterior_fields + ["SHAPE@"]])


def _maintenance_intervals() -> dict[str, int]:
    profile = load_facility_profile(REPOSITORY / "profiles" / "vertex-v1.json")
    intervals = {}
    for templates in profile.room_uses.values():
        for template in templates:
            intervals[template.identifier] = template.maintenance_interval_days
    return intervals


def _asset_seeds(schema: AssetManagementSchema) -> list[AssetSeed]:
    intervals = _maintenance_intervals()
    fields = [
        "Asset_ID",
        "GlobalID",
        "AssetType",
        "AssetClass",
        "Criticality",
        "Unit_ID",
        "Level_ID",
        "Facility_ID",
        "Site_ID",
    ]
    assets = []
    with arcpy.da.SearchCursor(schema.asset_lifecycle, fields) as cursor:
        for row in cursor:
            asset_type = str(row[2])
            assets.append(
                AssetSeed(
                    asset_id=str(row[0]),
                    global_id=str(row[1]),
                    asset_type=asset_type,
                    asset_class=str(row[3]),
                    criticality=str(row[4]),
                    unit_id=str(row[5]),
                    level_id=str(row[6]),
                    facility_id=str(row[7]),
                    site_id=str(row[8]),
                    maintenance_interval_days=intervals.get(asset_type, 365),
                )
            )
    return assets


def _apply_plan(schema: AssetManagementSchema, plan: EnrichmentPlan) -> None:
    lifecycle_by_id = {record.asset_id: record for record in plan.lifecycle}
    point_ids = _key_guid_map(schema.indoor_asset_locations, "Asset_ID")
    lifecycle_fields = [
        "Asset_ID",
        "AssetType",
        "AssetClass",
        "Category_Code",
        "Category_Type",
        "Subtype_Code",
        "Category_Subtype",
        "Facility_ID",
        "Site_ID",
        "Condition",
        "CommissioningDate",
        "NextMaintenanceDate",
        "Make",
        "Model",
        "Serial",
        "Owner",
        "LifecycleStage",
        "ExpectedLifeYears",
        "AssetAgeYears",
        "RemainingLifeYears",
        "ReplacementDueDate",
        "ReplacementYear",
        "LastInspectionDate",
        "OverdueDays",
        "EstimatedReplacementCost",
        "Vendor",
        "PurchaseDate",
        "PurchaseCost",
        "WarrantyExpirationDate",
        "WarrantyStatus",
        "MaintenanceIntervalDays",
        "AnnualMaintenanceCost",
        "RiskScore",
        "RiskLevel",
    ]
    with arcpy.da.UpdateCursor(schema.asset_lifecycle, lifecycle_fields) as cursor:
        for row in cursor:
            record = lifecycle_by_id[str(row[0])]
            cursor.updateRow(
                (
                    record.asset_id,
                    record.asset_type,
                    record.asset_class,
                    record.category_code,
                    record.category_type,
                    record.subtype_code,
                    record.category_subtype,
                    record.facility_id,
                    record.site_id,
                    record.condition,
                    _date_time(record.commissioning_date),
                    _date_time(record.next_maintenance_date),
                    record.make,
                    record.model,
                    record.serial,
                    record.owner,
                    record.lifecycle_stage,
                    record.expected_life_years,
                    record.asset_age_years,
                    record.remaining_life_years,
                    _date_time(record.replacement_due_date),
                    record.replacement_year,
                    _date_time(record.last_inspection_date),
                    record.overdue_days,
                    record.estimated_replacement_cost,
                    record.vendor,
                    _date_time(record.purchase_date),
                    record.purchase_cost,
                    _date_time(record.warranty_expiration_date),
                    record.warranty_status,
                    record.maintenance_interval_days,
                    record.annual_maintenance_cost,
                    record.risk_score,
                    record.risk_level,
                )
            )
    with arcpy.da.UpdateCursor(
        schema.indoor_asset_locations, ["Asset_ID", "Condition"]
    ) as cursor:
        for asset_id, _ in cursor:
            cursor.updateRow((asset_id, lifecycle_by_id[str(asset_id)].condition))

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
        for record in plan.inspections:
            cursor.insertRow(
                (
                    record.asset_global_id,
                    point_ids[record.asset_id],
                    record.asset_id,
                    record.asset_type,
                    _date_time(record.inspection_date),
                    record.inspector,
                    record.condition_rating,
                    record.repair_needed,
                    record.notes,
                    record.estimated_repair_cost,
                    record.repair_type,
                )
            )

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
    with arcpy.da.InsertCursor(schema.repairs, repair_fields) as cursor:
        for record in plan.repairs:
            cursor.insertRow(
                (
                    record.asset_global_id,
                    point_ids[record.asset_id],
                    record.asset_id,
                    record.asset_type,
                    _date_time(record.repair_date),
                    record.technician,
                    record.repair_type,
                    record.notes,
                    record.repair_cost,
                )
            )

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
    with arcpy.da.InsertCursor(schema.work_orders, work_order_fields) as cursor:
        for record in plan.work_orders:
            cursor.insertRow(
                (
                    record.asset_global_id,
                    point_ids[record.asset_id],
                    record.work_order_id,
                    record.request_type,
                    _date_time(record.request_date),
                    record.description,
                    record.asset_id,
                    record.asset_type,
                    record.unit_id,
                    record.level_id,
                    record.facility_id,
                    record.facility_name,
                    record.assignee,
                    record.status,
                )
            )


def _validate_output(
    source_workspace: str,
    output_workspace: str,
    schema: AssetManagementSchema,
    config: EnrichmentConfig,
) -> dict[str, Any]:
    source_schema = _schema(source_workspace)
    lifecycle_count = _row_count(schema.asset_lifecycle)
    if lifecycle_count != _row_count(source_schema.asset_lifecycle):
        raise RuntimeError("Output lifecycle count differs from the source.")
    if _row_count(schema.indoor_asset_locations) != _row_count(
        source_schema.indoor_asset_locations
    ):
        raise RuntimeError("Output indoor asset count differs from the source.")
    if _row_count(schema.exterior_asset_points) != _row_count(
        source_schema.exterior_asset_points
    ):
        raise RuntimeError("Output exterior asset count differs from the source.")

    lifecycle_ids = {
        _normalized_guid(global_id)
        for (global_id,) in arcpy.da.SearchCursor(schema.asset_lifecycle, ["GlobalID"])
    }
    point_ids = {
        _normalized_guid(global_id)
        for (global_id,) in arcpy.da.SearchCursor(schema.indoor_asset_locations, ["GlobalID"])
    }
    for child in (schema.inspections, schema.repairs, schema.work_orders):
        parent_ids = {
            _normalized_guid(global_id)
            for (global_id,) in arcpy.da.SearchCursor(child, ["AssetLifecycleGlobalID"])
        }
        missing = parent_ids - lifecycle_ids
        if missing:
            raise RuntimeError(f"{os.path.basename(child)} contains orphan lifecycle references.")
        asset_point_ids = {
            _normalized_guid(global_id)
            for (global_id,) in arcpy.da.SearchCursor(child, ["AssetPointGlobalID"])
        }
        missing = asset_point_ids - point_ids
        if missing:
            raise RuntimeError(f"{os.path.basename(child)} contains orphan asset-point references.")

    stages = Counter(
        str(stage)
        for (stage,) in arcpy.da.SearchCursor(schema.asset_lifecycle, ["LifecycleStage"])
    )
    expected_stages = {
        "Recently Installed": round(lifecycle_count * 0.20),
        "Retrofit/Replacement": round(lifecycle_count * 0.30),
    }
    expected_stages["Within Service Life"] = lifecycle_count - sum(expected_stages.values())
    if stages != Counter(expected_stages):
        raise RuntimeError(f"Lifecycle cohort mismatch: {dict(stages)}")

    lifecycle_dates = {}
    warranty_statuses = Counter()
    risk_levels = Counter()
    profile_fields = [
        "Asset_ID",
        "Facility_ID",
        "Site_ID",
        "CommissioningDate",
        "LastInspectionDate",
        "Vendor",
        "PurchaseDate",
        "PurchaseCost",
        "EstimatedReplacementCost",
        "WarrantyExpirationDate",
        "WarrantyStatus",
        "MaintenanceIntervalDays",
        "AnnualMaintenanceCost",
        "RiskScore",
        "RiskLevel",
    ]
    for row in arcpy.da.SearchCursor(
        schema.asset_lifecycle,
        profile_fields,
    ):
        (
            asset_id,
            facility_id,
            site_id,
            commissioning,
            last_inspection,
            vendor,
            purchase_date,
            purchase_cost,
            replacement_cost,
            warranty_expiration,
            warranty_status,
            maintenance_interval,
            annual_maintenance_cost,
            risk_score,
            risk_level,
        ) = row
        if not facility_id or not site_id:
            raise RuntimeError(f"Lifecycle hierarchy is incomplete for asset {asset_id}.")
        if not vendor or purchase_date >= commissioning:
            raise RuntimeError(f"Acquisition metadata is invalid for asset {asset_id}.")
        if not 0 < purchase_cost < replacement_cost:
            raise RuntimeError(f"Lifecycle costs are invalid for asset {asset_id}.")
        if warranty_expiration <= commissioning or warranty_status not in {"Active", "Expired"}:
            raise RuntimeError(f"Warranty metadata is invalid for asset {asset_id}.")
        if warranty_status != (
            "Active" if warranty_expiration.date() >= config.reference_date else "Expired"
        ):
            raise RuntimeError(f"Warranty status is inconsistent for asset {asset_id}.")
        if maintenance_interval <= 0 or not 0 < annual_maintenance_cost < replacement_cost:
            raise RuntimeError(f"Maintenance metadata is invalid for asset {asset_id}.")
        expected_risk_level = (
            "Critical" if risk_score >= 75
            else "High" if risk_score >= 50
            else "Moderate" if risk_score >= 25
            else "Low"
        )
        if not 0 <= risk_score <= 100 or risk_level != expected_risk_level:
            raise RuntimeError(f"Risk metadata is invalid for asset {asset_id}.")
        warranty_statuses[str(warranty_status)] += 1
        risk_levels[str(risk_level)] += 1
        lifecycle_dates[str(asset_id)] = (commissioning.date(), last_inspection.date())
    latest_inspections = {}
    inspection_assets = set()
    for asset_id, inspection_date in arcpy.da.SearchCursor(
        schema.inspections, ["Asset_ID", "Inspection_Date"]
    ):
        key = str(asset_id)
        value = inspection_date.date()
        commissioning, _ = lifecycle_dates[key]
        if not config.inspection_start <= value <= config.inspection_end:
            raise RuntimeError(f"Inspection date is outside the configured window for {key}.")
        if value < commissioning:
            raise RuntimeError(f"Inspection predates commissioning for {key}.")
        inspection_assets.add(key)
        latest_inspections[key] = max(value, latest_inspections.get(key, value))
    if inspection_assets != set(lifecycle_dates):
        raise RuntimeError("Not every lifecycle asset has inspection history.")
    if any(latest_inspections[key] != values[1] for key, values in lifecycle_dates.items()):
        raise RuntimeError("Lifecycle latest-inspection dates do not match inspection history.")

    repairs = _row_count(schema.repairs)
    expected_repairs = round(lifecycle_count * config.repair_rate)
    if repairs != expected_repairs:
        raise RuntimeError(f"Repair count is {repairs}; expected {expected_repairs}.")
    work_order_statuses = Counter(
        str(status) for (status,) in arcpy.da.SearchCursor(schema.work_orders, ["Status"])
    )
    completed = work_order_statuses["Completed"]
    active = sum(work_order_statuses.values()) - completed
    if completed != round(lifecycle_count * config.historical_work_order_rate):
        raise RuntimeError("Historical work-order coverage does not match the configured rate.")
    if active != round(lifecycle_count * config.active_work_order_rate):
        raise RuntimeError("Active work-order coverage does not match the configured rate.")

    direct_relationships = (
        os.path.join(output_workspace, "IndoorLocations_Inspections"),
        os.path.join(output_workspace, "IndoorLocations_Repairs"),
        os.path.join(output_workspace, "IndoorLocations_WorkOrders"),
    )
    missing_relationships = [
        os.path.basename(path) for path in direct_relationships if not arcpy.Exists(path)
    ]
    if missing_relationships:
        raise RuntimeError(
            "Missing direct asset-history relationships: "
            + ", ".join(missing_relationships)
        )

    source_counts = {name: _row_count(os.path.join(source_workspace, name)) for name in CHILD_TABLES}
    if any(source_counts.values()):
        raise RuntimeError("The source geodatabase changed while enrichment was running.")
    return {
        "lifecycle_assets": lifecycle_count,
        "indoor_asset_points": _row_count(schema.indoor_asset_locations),
        "exterior_asset_points": _row_count(schema.exterior_asset_points),
        "lifecycle_stages": dict(stages),
        "inspections": _row_count(schema.inspections),
        "repairs": repairs,
        "historical_work_orders": completed,
        "active_work_orders": active,
        "orphan_references": 0,
        "direct_asset_history_relationships": len(direct_relationships),
        "inspection_date_min": config.inspection_start.isoformat(),
        "inspection_date_max": config.inspection_end.isoformat(),
        "warranty_statuses": dict(warranty_statuses),
        "risk_levels": dict(risk_levels),
    }


def _manifest_path(output: Path) -> Path:
    return output.with_name(f"{output.stem}_manifest.json")


def _delete_output(output: Path) -> None:
    arcpy.management.ClearWorkspaceCache()
    if arcpy.Exists(str(output)):
        try:
            arcpy.management.Delete(str(output))
            return
        except arcpy.ExecuteError:
            pass
    shutil.rmtree(output, ignore_errors=True)


def main() -> None:
    arguments = _arguments()
    source = arguments.source.resolve()
    output = arguments.output.resolve()
    if source == output:
        raise ValueError("Source and output geodatabases must be different.")
    if not arcpy.Exists(str(source)):
        raise FileNotFoundError(source)
    if output.exists() or arcpy.Exists(str(output)):
        raise FileExistsError(f"Output already exists: {output}")
    if arguments.llm_endpoint and not arguments.llm_model:
        raise ValueError("--llm-model is required when --llm-endpoint is supplied.")

    inspection_start = date(arguments.reference_date.year - 5, arguments.reference_date.month, arguments.reference_date.day)
    inspection_end_month = arguments.reference_date.month - 6
    inspection_end_year = arguments.reference_date.year
    if inspection_end_month <= 0:
        inspection_end_month += 12
        inspection_end_year -= 1
    inspection_end = date(
        inspection_end_year,
        inspection_end_month,
        min(arguments.reference_date.day, 28),
    )
    config = EnrichmentConfig(
        reference_date=arguments.reference_date,
        inspection_start=inspection_start,
        inspection_end=inspection_end,
        seed=arguments.seed,
    )
    source_schema = _schema(str(source))
    _ensure_empty_source_children(source_schema)
    narrator = (
        LocalJsonNarrator(
            arguments.llm_endpoint,
            arguments.llm_model,
            max_requests=arguments.llm_max_records,
        )
        if arguments.llm_endpoint
        else None
    )

    try:
        print(f"Creating minimal output: {output}", flush=True)
        _create_minimal_output(str(source), str(output))
        output_source = validate_indoors_source(arcpy, str(output))
        output_schema = create_asset_management_schema(arcpy, str(output), output_source)
        for field_name, field_type, length in LIFECYCLE_EXTENSION_FIELDS:
            _add_field(output_schema.asset_lifecycle, field_name, field_type, length)

        print("Copying assets and remapping GlobalID relationships", flush=True)
        _copy_asset_schema_rows(source_schema, output_schema, str(output))
        assets = _asset_seeds(output_schema)
        _, facility_names = _hierarchy(str(output))
        facility_name = next(iter(facility_names.values()))
        plan = build_enrichment_plan(assets, config, narrator, facility_name)
        print(
            f"Writing {len(plan.inspections)} inspections, {len(plan.repairs)} repairs, "
            f"and {len(plan.work_orders)} work orders",
            flush=True,
        )
        _apply_plan(output_schema, plan)
        validation = _validate_output(str(source), str(output), output_schema, config)
        manifest = {
            "created_utc": DateTime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_geodatabase": str(source),
            "output_geodatabase": str(output),
            "source_modified": False,
            "reference_date": config.reference_date.isoformat(),
            "inspection_window": {
                "start": config.inspection_start.isoformat(),
                "end": config.inspection_end.isoformat(),
            },
            "seed": config.seed,
            "taxonomy_version": PRICEBOOK_VERSION,
            "synthetic_pricing": {
                "pricebook_version": PRICEBOOK_VERSION,
                "currency": PRICE_CURRENCY,
                "price_basis": PRICE_BASIS,
            },
            "narrative_generation": narrative_run_metadata(narrator),
            "validation": validation,
        }
        manifest_path = _manifest_path(output)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(json.dumps(manifest, indent=2))
        print(f"Manifest: {manifest_path}", flush=True)
    except Exception:
        if not arguments.keep_failed_output:
            _delete_output(output)
        raise
    finally:
        arcpy.management.ClearWorkspaceCache()


if __name__ == "__main__":
    main()