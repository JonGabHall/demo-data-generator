"""ArcPy preflight checks for an ArcGIS Indoors source geodatabase."""

from __future__ import annotations

from dataclasses import dataclass
import json
import ntpath
from pathlib import PureWindowsPath
from typing import Any


REQUIRED_CLASSES = ("Sites", "Facilities", "Levels", "Units")
REQUIRED_FIELDS = {
    "sites": ("SITE_ID",),
    "facilities": ("FACILITY_ID", "SITE_ID"),
    "levels": ("LEVEL_ID", "FACILITY_ID"),
    "units": ("UNIT_ID", "LEVEL_ID", "USE_TYPE"),
}
INSPECTION_REPORT_VERSION = 1


@dataclass(frozen=True)
class IndoorsSource:
    workspace: str
    feature_classes: dict[str, str]
    facility_global_id_field: str
    unit_use_field: str
    unit_global_id_field: str


class PreflightError(ValueError):
    """Raised when a workspace cannot safely be used as an Indoors input."""


def validate_indoors_source(arcpy: Any, workspace: str) -> IndoorsSource:
    """Confirm the minimum Indoors hierarchy and Unit identity fields exist."""
    if not workspace.lower().endswith(".gdb"):
        raise PreflightError("Source workspace must be a file geodatabase (.gdb).")
    if not arcpy.Exists(workspace):
        raise PreflightError(f"Source geodatabase does not exist: {workspace}")

    feature_classes = _find_feature_classes(arcpy, workspace)
    missing = [name for name in REQUIRED_CLASSES if name.lower() not in feature_classes]
    if missing:
        raise PreflightError(
            "Source is missing required ArcGIS Indoors feature classes: " + ", ".join(missing)
        )

    facilities_path = feature_classes["facilities"]
    for class_name, required_fields in REQUIRED_FIELDS.items():
        available = {
            field.name.upper(): field
            for field in arcpy.ListFields(feature_classes[class_name])
        }
        missing_fields = [name for name in required_fields if name not in available]
        if missing_fields:
            raise PreflightError(
                f"{class_name.title()} is missing required fields: "
                + ", ".join(missing_fields)
            )

    facility_global_id_field = _global_id_field(arcpy, facilities_path, "Facilities")
    units_path = feature_classes["units"]
    fields = {field.name.upper(): field for field in arcpy.ListFields(units_path)}
    global_id_field = _global_id_field(arcpy, units_path, "Units")

    return IndoorsSource(
        workspace=workspace,
        feature_classes=feature_classes,
        facility_global_id_field=facility_global_id_field,
        unit_use_field=fields["USE_TYPE"].name,
        unit_global_id_field=global_id_field,
    )


def inspect_indoors_source(
    arcpy: Any,
    workspace: str,
    profile: Any | None = None,
    profile_name: str | None = None,
) -> dict[str, Any]:
    """Return a read-only implementation report for an Indoors workspace."""
    source = validate_indoors_source(arcpy, workspace)
    units_path = source.feature_classes["units"]
    feature_classes = _find_datasets(arcpy, workspace, "FeatureClass")
    tables = _find_datasets(arcpy, workspace, "Table")
    datasets = {**feature_classes, **tables}
    inventories = {
        name: _dataset_inventory(arcpy, path)
        for name, path in sorted(datasets.items())
    }
    with arcpy.da.SearchCursor(units_path, [source.unit_use_field]) as cursor:
        use_types = sorted({value for (value,) in cursor if value not in (None, "")})
    mappings = []
    for use_type in use_types:
        if profile is None:
            mappings.append({"source_use_type": use_type, "profile_use_type": None, "mapped": None})
            continue
        try:
            profile_use = profile.resolve_room_use(use_type)
            mappings.append({"source_use_type": use_type, "profile_use_type": profile_use, "mapped": True})
        except ValueError:
            mappings.append({"source_use_type": use_type, "profile_use_type": None, "mapped": False})

    mapped = [item for item in mappings if item["mapped"] is True]
    unmapped = [item["source_use_type"] for item in mappings if item["mapped"] is False]
    unit_count = int(arcpy.management.GetCount(units_path)[0])
    return {
        "report_format_version": INSPECTION_REPORT_VERSION,
        "inspection": {
            "source_geodatabase": source.workspace,
            "compatible": True,
            "summary": {
                "unit_count": unit_count,
                "distinct_use_type_count": len(use_types),
                "mapped_use_type_count": len(mapped),
                "unmapped_use_type_count": len(unmapped),
                "spatial_reference": _spatial_reference(arcpy, units_path),
            },
            "profile": (
                {"name": profile_name, "version": profile.version} if profile else None
            ),
            "room_use_summary": {
                "mapped": mapped,
                "unmapped": unmapped,
                "not_evaluated": profile is None,
            },
            "recommended_action": _recommended_action(profile, unmapped),
        },
        "technical_details": {
            "feature_classes": {
                name: {"path": path, "fields": [field.name for field in arcpy.ListFields(path)]}
                for name, path in sorted(source.feature_classes.items())
            },
            "datasets": inventories,
            "domains": _domains(arcpy, workspace),
            "relationship_classes": sorted(_find_datasets(arcpy, workspace, "RelationshipClass")),
            "oriented_imagery_candidates": [
                inventory
                for inventory in inventories.values()
                if _is_likely_imagery_source(inventory)
            ],
            "required_identifiers": {
                "facility_global_id_field": source.facility_global_id_field,
                "unit_global_id_field": source.unit_global_id_field,
                "unit_use_field": source.unit_use_field,
            },
        },
    }


def write_inspection_report(report: dict[str, Any], output_path: str) -> None:
    """Write a portable, reviewable report without changing the source geodatabase."""
    with open(output_path, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)


def validate_inspection_report(
    report_path: str,
    source_workspace: str,
    profile_name: str,
    profile: Any,
) -> dict[str, Any]:
    """Confirm an inspection report matches the generation inputs."""
    try:
        with open(report_path, encoding="utf-8") as stream:
            report = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise PreflightError(f"Unable to read inspection report: {error}") from error

    inspection = report.get("inspection", {})
    if report.get("report_format_version") != INSPECTION_REPORT_VERSION:
        raise PreflightError("Inspection report format is unsupported. Run Inspect Indoors Geodatabase again.")
    if not inspection.get("compatible"):
        raise PreflightError("Inspection report does not confirm a compatible Indoors geodatabase.")
    if not _same_workspace(inspection.get("source_geodatabase"), source_workspace):
        raise PreflightError("Inspection report was created for a different source geodatabase.")

    report_profile = inspection.get("profile") or {}
    if report_profile.get("name") != profile_name or report_profile.get("version") != profile.version:
        raise PreflightError("Inspection report was created with a different facility profile or profile version.")
    return inspection


def _find_feature_classes(arcpy: Any, workspace: str) -> dict[str, str]:
    return _find_datasets(arcpy, workspace, "FeatureClass")


def _find_datasets(arcpy: Any, workspace: str, datatype: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for directory, _, names in arcpy.da.Walk(workspace, datatype=datatype):
        for name in names:
            found.setdefault(name.lower(), str(PureWindowsPath(directory) / name))
    return found


def _dataset_inventory(arcpy: Any, path: str) -> dict[str, Any]:
    fields = arcpy.ListFields(path)
    return {
        "path": path,
        "fields": [
            {
                "name": field.name,
                "type": field.type,
                "length": getattr(field, "length", None),
                "domain": getattr(field, "domain", None),
            }
            for field in fields
        ],
        "global_id_fields": [field.name for field in fields if field.type == "GlobalID"],
    }


def _spatial_reference(arcpy: Any, dataset: str) -> str | None:
    spatial_reference = getattr(arcpy.Describe(dataset), "spatialReference", None)
    return getattr(spatial_reference, "name", None)


def _domains(arcpy: Any, workspace: str) -> list[dict[str, str]]:
    list_domains = getattr(arcpy.da, "ListDomains", None)
    if list_domains is None:
        return []
    return [
        {"name": domain.name, "domain_type": domain.domainType, "field_type": domain.type}
        for domain in list_domains(workspace)
    ]


def _is_likely_imagery_source(inventory: dict[str, Any]) -> bool:
    searchable = inventory["path"].lower() + " " + " ".join(
        field["name"].lower() for field in inventory["fields"]
    )
    indicators = ("oriented", "imagery", "panorama", "imageurl", "cameraheading")
    return any(indicator in searchable for indicator in indicators)


def _recommended_action(profile: Any | None, unmapped: list[str]) -> str:
    if profile is None:
        return "Select a facility profile to evaluate USE_TYPE coverage before generating assets."
    if unmapped:
        return "Review unmapped USE_TYPE values; Units with those values will be skipped during generation."
    return "All discovered USE_TYPE values map to the selected profile. Generation can proceed."


def _same_workspace(first: Any, second: str) -> bool:
    return isinstance(first, str) and ntpath.normcase(ntpath.normpath(first)) == ntpath.normcase(ntpath.normpath(second))


def _global_id_field(arcpy: Any, dataset: str, label: str) -> str:
    field = next((item for item in arcpy.ListFields(dataset) if item.type == "GlobalID"), None)
    if field is None:
        raise PreflightError(f"{label} requires a GlobalID field for generated asset relationships.")
    return field.name
