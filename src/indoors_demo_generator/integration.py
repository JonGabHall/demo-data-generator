"""Safely integrate generated assets into a copied target Indoors geodatabase."""

from __future__ import annotations

from dataclasses import dataclass
import ntpath
from typing import Any

from .preflight import IndoorsSource, PreflightError, validate_indoors_source
from .schema import AssetManagementSchema, create_asset_management_schema


@dataclass(frozen=True)
class IntegrationResult:
    output_geodatabase: str
    indoor_asset_count: int
    exterior_asset_count: int
    lifecycle_count: int


def integrate_generated_assets(
    arcpy: Any, target_gdb: str, generated_gdb: str, output_gdb: str
) -> IntegrationResult:
    """Create a validated integrated copy without changing either input geodatabase."""
    target = validate_indoors_source(arcpy, target_gdb)
    generated = validate_indoors_source(arcpy, generated_gdb)
    if _same_path(target_gdb, generated_gdb):
        raise PreflightError("Target and generated geodatabases must be different workspaces.")
    if arcpy.Exists(output_gdb):
        raise PreflightError(f"Integrated output geodatabase already exists: {output_gdb}")

    generated_schema = _schema_paths(generated_gdb)
    _require_generated_schema(arcpy, generated_schema)
    _validate_parent_references(arcpy, target, generated_schema)

    output_created = False
    try:
        arcpy.management.Copy(target_gdb, output_gdb)
        output_created = True
        output_source = validate_indoors_source(arcpy, output_gdb)
        output_schema = create_asset_management_schema(arcpy, output_gdb, output_source)
        _transfer_generated_records(arcpy, generated_schema, output_schema)
        _validate_integrated_output(arcpy, output_source, output_schema)
    except Exception:
        if output_created and arcpy.Exists(output_gdb):
            arcpy.management.Delete(output_gdb)
        raise

    return IntegrationResult(
        output_geodatabase=output_gdb,
        indoor_asset_count=_row_count(arcpy, output_schema.indoor_asset_locations),
        exterior_asset_count=_row_count(arcpy, output_schema.exterior_asset_points),
        lifecycle_count=_row_count(arcpy, output_schema.asset_lifecycle),
    )


def _schema_paths(workspace: str) -> AssetManagementSchema:
    feature_dataset = ntpath.join(workspace, "AssetManagement")
    return AssetManagementSchema(
        feature_dataset=feature_dataset,
        indoor_asset_locations=ntpath.join(feature_dataset, "IndoorAssetLocation"),
        exterior_asset_points=ntpath.join(feature_dataset, "ExteriorAssetPoints"),
        asset_lifecycle=ntpath.join(workspace, "AssetLifecycle"),
        inspections=ntpath.join(workspace, "AssetInspection"),
        repairs=ntpath.join(workspace, "AssetRepair"),
        work_orders=ntpath.join(workspace, "AssetWorkOrder"),
        external_references=ntpath.join(workspace, "AssetExternalReference"),
        field_work_links=ntpath.join(workspace, "AssetFieldWorkLink"),
        media_references=ntpath.join(workspace, "AssetMediaReference"),
    )


def _require_generated_schema(arcpy: Any, schema: AssetManagementSchema) -> None:
    missing = [path for path in _datasets(schema) if not arcpy.Exists(path)]
    if missing:
        raise PreflightError(
            "Generated geodatabase is missing the required generated schema: " + ", ".join(missing)
        )


def _validate_parent_references(arcpy: Any, target: IndoorsSource, generated: AssetManagementSchema) -> None:
    _require_references(
        arcpy,
        generated.indoor_asset_locations,
        "SourceUnitGlobalID",
        target.feature_classes["units"],
        target.unit_global_id_field,
        "Units",
    )
    _require_references(
        arcpy,
        generated.exterior_asset_points,
        "SourceFacilityGlobalID",
        target.feature_classes["facilities"],
        target.facility_global_id_field,
        "Facilities",
    )


def _transfer_generated_records(
    arcpy: Any, generated: AssetManagementSchema, output: AssetManagementSchema
) -> None:
    _copy_rows(arcpy, generated.indoor_asset_locations, output.indoor_asset_locations)
    point_ids = _global_id_map(arcpy, generated.indoor_asset_locations, "Asset_ID")
    output_point_ids = _global_id_map(arcpy, output.indoor_asset_locations, "Asset_ID")
    _copy_rows(
        arcpy,
        generated.asset_lifecycle,
        output.asset_lifecycle,
        {"AssetPointGlobalID": _translate_ids(point_ids, output_point_ids)},
    )
    lifecycle_ids = _global_id_map(arcpy, generated.asset_lifecycle, "Asset_ID")
    output_lifecycle_ids = _global_id_map(arcpy, output.asset_lifecycle, "Asset_ID")
    lifecycle_id_map = _translate_ids(lifecycle_ids, output_lifecycle_ids)
    point_id_map = _translate_ids(point_ids, output_point_ids)
    _copy_rows(arcpy, generated.exterior_asset_points, output.exterior_asset_points)
    for generated_path, output_path, id_remaps in (
        (
            generated.inspections,
            output.inspections,
            {
                "AssetLifecycleGlobalID": lifecycle_id_map,
                "AssetPointGlobalID": point_id_map,
            },
        ),
        (
            generated.repairs,
            output.repairs,
            {
                "AssetLifecycleGlobalID": lifecycle_id_map,
                "AssetPointGlobalID": point_id_map,
            },
        ),
        (
            generated.work_orders,
            output.work_orders,
            {
                "AssetLifecycleGlobalID": lifecycle_id_map,
                "AssetPointGlobalID": point_id_map,
            },
        ),
        (generated.external_references, output.external_references, {"AssetGlobalID": lifecycle_id_map}),
        (generated.field_work_links, output.field_work_links, {"AssetGlobalID": lifecycle_id_map}),
        (
            generated.media_references,
            output.media_references,
            {"AssetLifecycleGlobalID": lifecycle_id_map},
        ),
    ):
        _copy_rows(arcpy, generated_path, output_path, id_remaps)


def _copy_rows(
    arcpy: Any, source: str, target: str, id_remaps: dict[str, dict[str, str]] | None = None
) -> None:
    fields = _transfer_fields(arcpy, source, target)
    with arcpy.da.SearchCursor(source, fields) as reader, arcpy.da.InsertCursor(target, fields) as writer:
        for source_row in reader:
            row = list(source_row)
            for field_name, replacements in (id_remaps or {}).items():
                index = fields.index(field_name)
                if row[index] is not None:
                    try:
                        row[index] = replacements[_normalized_id(row[index])]
                    except KeyError as error:
                        raise PreflightError(
                            f"Generated {ntpath.basename(source)} contains an unresolved {field_name}."
                        ) from error
            writer.insertRow(row)


def _transfer_fields(arcpy: Any, source: str, target: str) -> list[str]:
    ignored_types = {"OID", "GlobalID", "Geometry"}
    source_fields = {field.name for field in arcpy.ListFields(source) if field.type not in ignored_types}
    target_fields = {field.name for field in arcpy.ListFields(target) if field.type not in ignored_types}
    if source_fields != target_fields:
        raise PreflightError(f"Generated schema does not match target schema for {ntpath.basename(source)}.")
    fields = sorted(source_fields)
    if getattr(arcpy.Describe(source), "shapeType", None):
        fields.append("SHAPE@")
    return fields


def _global_id_map(arcpy: Any, dataset: str, key_field: str) -> dict[str, str]:
    values: dict[str, str] = {}
    with arcpy.da.SearchCursor(dataset, [key_field, "GlobalID"]) as cursor:
        for key, global_id in cursor:
            if key in values:
                raise PreflightError(f"{ntpath.basename(dataset)} has duplicate {key_field} values.")
            values[key] = _normalized_id(global_id)
    return values


def _translate_ids(source: dict[str, str], target: dict[str, str]) -> dict[str, str]:
    if source.keys() != target.keys():
        raise PreflightError("Generated asset identities changed during integration.")
    return {source[key]: target[key] for key in source}


def _validate_integrated_output(arcpy: Any, source: IndoorsSource, schema: AssetManagementSchema) -> None:
    _require_references(
        arcpy, schema.indoor_asset_locations, "SourceUnitGlobalID", source.feature_classes["units"],
        source.unit_global_id_field, "Units"
    )
    _require_references(
        arcpy, schema.exterior_asset_points, "SourceFacilityGlobalID", source.feature_classes["facilities"],
        source.facility_global_id_field, "Facilities"
    )
    _require_references(
        arcpy, schema.asset_lifecycle, "AssetPointGlobalID", schema.indoor_asset_locations, "GlobalID",
        "IndoorAssetLocation"
    )
    for child, foreign_key in (
        (schema.inspections, "AssetLifecycleGlobalID"),
        (schema.repairs, "AssetLifecycleGlobalID"),
        (schema.work_orders, "AssetLifecycleGlobalID"),
        (schema.external_references, "AssetGlobalID"),
        (schema.field_work_links, "AssetGlobalID"),
        (schema.media_references, "AssetLifecycleGlobalID"),
    ):
        _require_references(arcpy, child, foreign_key, schema.asset_lifecycle, "GlobalID", "AssetLifecycle")
    for child in (schema.inspections, schema.repairs, schema.work_orders):
        _require_references(
            arcpy,
            child,
            "AssetPointGlobalID",
            schema.indoor_asset_locations,
            "GlobalID",
            "IndoorAssetLocation",
        )


def _require_references(
    arcpy: Any, child: str, foreign_key: str, parent: str, parent_key: str, parent_name: str
) -> None:
    parent_ids = _ids(arcpy, parent, parent_key)
    with arcpy.da.SearchCursor(child, [foreign_key]) as cursor:
        if any(row[0] is None for row in cursor):
            raise PreflightError(
                f"{ntpath.basename(child)} contains a null {parent_name} reference."
            )
    child_ids = _ids(arcpy, child, foreign_key)
    missing = child_ids - parent_ids
    if missing:
        raise PreflightError(
            f"{ntpath.basename(child)} references {len(missing)} {parent_name} record(s) absent from the target."
        )


def _ids(arcpy: Any, dataset: str, field_name: str) -> set[str]:
    with arcpy.da.SearchCursor(dataset, [field_name]) as cursor:
        return {_normalized_id(row[0]) for row in cursor if row[0] is not None}


def _row_count(arcpy: Any, dataset: str) -> int:
    return int(arcpy.management.GetCount(dataset)[0])


def _datasets(schema: AssetManagementSchema) -> tuple[str, ...]:
    return (
        schema.feature_dataset,
        schema.indoor_asset_locations,
        schema.exterior_asset_points,
        schema.asset_lifecycle,
        schema.inspections,
        schema.repairs,
        schema.work_orders,
        schema.external_references,
        schema.field_work_links,
        schema.media_references,
    )


def _normalized_id(value: Any) -> str:
    return str(value).strip().strip("{}").upper()


def _same_path(first: str, second: str) -> bool:
    return ntpath.normcase(ntpath.normpath(first)) == ntpath.normcase(ntpath.normpath(second))