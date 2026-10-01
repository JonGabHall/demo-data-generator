"""Backfill taxonomy and type-specific synthetic finance into an existing GDB."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .asset_catalog import (
    PRICE_BASIS,
    PRICE_CURRENCY,
    PRICEBOOK_VERSION,
    build_asset_metadata,
    estimated_repair_cost_for,
    repair_cost_for,
)
from .rules import load_facility_profile


PROFILE_NAMES = ("vertex-v1.json", "hospital-v1.json", "government-office-v1.json")


def _maintenance_intervals(repository: Path) -> dict[str, int]:
    intervals: dict[str, int] = {}
    for profile_name in PROFILE_NAMES:
        profile = load_facility_profile(repository / "profiles" / profile_name)
        for templates in profile.room_uses.values():
            for template in templates:
                intervals[template.identifier] = template.maintenance_interval_days
    return intervals


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ValueError(f"Expected a populated date, received {value!r}.")


def _require_fields(arcpy: Any, dataset: str, expected: tuple[str, ...]) -> None:
    available = {field.name.casefold() for field in arcpy.ListFields(dataset)}
    missing = [name for name in expected if name.casefold() not in available]
    if missing:
        raise ValueError(f"{dataset} is missing required fields: {', '.join(missing)}")


def retrofit_asset_metadata(
    arcpy: Any,
    geodatabase: str | Path,
    *,
    reference_date: date = date(2026, 9, 28),
    repository: Path | None = None,
) -> dict[str, Any]:
    """Backfill categories and deterministic type-based price fields in place.

    This only updates generator-owned lifecycle and history tables. It never
    modifies the source Indoors hierarchy or asset geometries.
    """
    geodatabase = str(geodatabase)
    lifecycle = str(Path(geodatabase) / "AssetLifecycle")
    inspections = str(Path(geodatabase) / "AssetInspection")
    repairs = str(Path(geodatabase) / "AssetRepair")
    if not arcpy.Exists(lifecycle):
        raise FileNotFoundError(f"AssetLifecycle table was not found: {lifecycle}")
    if not arcpy.Exists(inspections) or not arcpy.Exists(repairs):
        raise FileNotFoundError("AssetInspection and AssetRepair tables are required.")

    repository = repository or Path(__file__).resolve().parents[2]
    intervals = _maintenance_intervals(repository)
    lifecycle_fields = (
        "Asset_ID",
        "AssetType",
        "AssetClass",
        "CommissioningDate",
        "Criticality",
        "Condition",
        "LifecycleStage",
        "OverdueDays",
        "MaintenanceIntervalDays",
    )
    _require_fields(arcpy, lifecycle, lifecycle_fields)
    lifecycle_rows: dict[str, dict[str, Any]] = {}
    with arcpy.da.SearchCursor(lifecycle, list(lifecycle_fields)) as cursor:
        for row in cursor:
            asset_id, asset_type, asset_class = map(str, row[:3])
            commissioning = _as_date(row[3])
            criticality = str(row[4])
            condition = str(row[5])
            stage = str(row[6])
            overdue_days = int(row[7] or 0)
            maintenance_interval = intervals.get(asset_type, int(row[8] or 365))
            metadata = build_asset_metadata(
                asset_type,
                asset_class,
                asset_id,
                commissioning,
                criticality,
                condition,
                stage,
                overdue_days,
                maintenance_interval,
                reference_date,
            )
            lifecycle_rows[asset_id] = {
                "metadata": metadata,
                "maintenance_interval": maintenance_interval,
            }

    update_fields = (
        "Asset_ID",
        "Category_Code",
        "Category_Type",
        "Subtype_Code",
        "Category_Subtype",
        "EstimatedReplacementCost",
        "PurchaseDate",
        "PurchaseCost",
        "Vendor",
        "WarrantyExpirationDate",
        "WarrantyStatus",
        "MaintenanceIntervalDays",
        "AnnualMaintenanceCost",
        "RiskScore",
        "RiskLevel",
    )
    _require_fields(arcpy, lifecycle, update_fields)
    inspection_fields = ("Asset_ID", "Repair_Needed", "Estimated_Repair_Cost")
    repair_fields = ("Asset_ID", "Repair_Cost")
    _require_fields(arcpy, inspections, inspection_fields)
    _require_fields(arcpy, repairs, repair_fields)
    with arcpy.da.SearchCursor(inspections, ["Asset_ID", "Repair_Needed"]) as cursor:
        for asset_id, repair_needed in cursor:
            if str(asset_id) not in lifecycle_rows:
                raise ValueError(f"Inspection references an unknown asset ID: {asset_id}.")
            if repair_needed not in (None, "", "Y", "N"):
                raise ValueError(
                    f"Inspection has an unsupported Repair_Needed value: {repair_needed!r}."
                )
    with arcpy.da.SearchCursor(repairs, ["Asset_ID"]) as cursor:
        for (asset_id,) in cursor:
            if str(asset_id) not in lifecycle_rows:
                raise ValueError(f"Repair references an unknown asset ID: {asset_id}.")

    with arcpy.da.UpdateCursor(lifecycle, list(update_fields)) as cursor:
        for row in cursor:
            asset_id = str(row[0])
            values = lifecycle_rows[asset_id]
            metadata = values["metadata"]
            row[1:] = [
                metadata.category_code,
                metadata.category_type,
                metadata.subtype_code,
                metadata.category_subtype,
                metadata.replacement_cost,
                datetime.combine(metadata.purchase_date, datetime.min.time()),
                metadata.purchase_cost,
                metadata.vendor,
                datetime.combine(
                    metadata.warranty_expiration_date, datetime.min.time()
                ),
                metadata.warranty_status,
                values["maintenance_interval"],
                metadata.annual_maintenance_cost,
                metadata.risk_score,
                metadata.risk_level,
            ]
            cursor.updateRow(row)

    inspection_counts: Counter[str] = Counter()
    with arcpy.da.UpdateCursor(
        inspections, ["Asset_ID", "Repair_Needed", "Estimated_Repair_Cost"]
    ) as cursor:
        for row in cursor:
            asset_id = str(row[0])
            needed = str(row[1] or "N").upper() == "Y"
            if needed:
                replacement = lifecycle_rows[asset_id]["metadata"].replacement_cost
                row[2] = estimated_repair_cost_for(replacement, asset_id)
                inspection_counts["with_repair_estimate"] += 1
            else:
                row[2] = None
                inspection_counts["without_repair_estimate"] += 1
            cursor.updateRow(row)

    repair_count = 0
    with arcpy.da.UpdateCursor(repairs, ["Asset_ID", "Repair_Cost"]) as cursor:
        for row in cursor:
            asset_id = str(row[0])
            replacement = lifecycle_rows[asset_id]["metadata"].replacement_cost
            row[1] = repair_cost_for(replacement, asset_id)
            cursor.updateRow(row)
            repair_count += 1

    return {
        "pricebook_version": PRICEBOOK_VERSION,
        "reference_date": reference_date.isoformat(),
        "lifecycle_assets_updated": len(lifecycle_rows),
        "inspections_updated": sum(inspection_counts.values()),
        "inspections_with_repair_estimate": inspection_counts["with_repair_estimate"],
        "inspections_without_repair_estimate": inspection_counts["without_repair_estimate"],
        "repair_rows_updated": repair_count,
        "currency": PRICE_CURRENCY,
        "price_basis": PRICE_BASIS,
    }
