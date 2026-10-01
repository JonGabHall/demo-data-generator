"""Creation of the generator-owned asset-management schema."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .preflight import IndoorsSource


@dataclass(frozen=True)
class AssetManagementSchema:
    feature_dataset: str
    indoor_asset_locations: str
    exterior_asset_points: str
    asset_lifecycle: str
    inspections: str
    repairs: str
    work_orders: str
    external_references: str
    field_work_links: str
    media_references: str


def create_asset_management_schema(
    arcpy: Any, output_gdb: str, source: IndoorsSource
) -> AssetManagementSchema:
    """Create generator-owned datasets without modifying Indoors core classes."""
    feature_dataset = f"{output_gdb}\\AssetManagement"
    indoor_asset_locations = f"{feature_dataset}\\IndoorAssetLocation"
    exterior_asset_points = f"{feature_dataset}\\ExteriorAssetPoints"
    asset_lifecycle = f"{output_gdb}\\AssetLifecycle"
    inspections = f"{output_gdb}\\AssetInspection"
    repairs = f"{output_gdb}\\AssetRepair"
    work_orders = f"{output_gdb}\\AssetWorkOrder"
    external_references = f"{output_gdb}\\AssetExternalReference"
    field_work_links = f"{output_gdb}\\AssetFieldWorkLink"
    media_references = f"{output_gdb}\\AssetMediaReference"
    units = source.feature_classes["units"]
    unit_id_length = _source_text_field_length(arcpy, units, "UNIT_ID", default=128)
    level_id_length = _source_text_field_length(
        arcpy, source.feature_classes["levels"], "LEVEL_ID", default=64
    )
    facility_id_length = _source_text_field_length(
        arcpy, source.feature_classes["facilities"], "FACILITY_ID", default=64
    )
    site_id_length = _source_text_field_length(
        arcpy, source.feature_classes.get("sites"), "SITE_ID", default=64
    )

    if arcpy.Exists(feature_dataset) or arcpy.Exists(asset_lifecycle):
        raise ValueError("Output geodatabase already contains an AssetManagement schema.")

    spatial_reference = arcpy.Describe(units).spatialReference
    arcpy.management.CreateFeatureDataset(output_gdb, "AssetManagement", spatial_reference)
    arcpy.management.CreateFeatureclass(feature_dataset, "IndoorAssetLocation", "POINT")
    arcpy.management.CreateFeatureclass(feature_dataset, "ExteriorAssetPoints", "POINT")
    arcpy.management.CreateTable(output_gdb, "AssetLifecycle")
    arcpy.management.CreateTable(output_gdb, "AssetInspection")
    arcpy.management.CreateTable(output_gdb, "AssetRepair")
    arcpy.management.CreateTable(output_gdb, "AssetWorkOrder")
    arcpy.management.CreateTable(output_gdb, "AssetExternalReference")
    arcpy.management.CreateTable(output_gdb, "AssetFieldWorkLink")
    arcpy.management.CreateTable(output_gdb, "AssetMediaReference")

    _add_fields(
        arcpy,
        indoor_asset_locations,
        [
            ("Asset_ID", "TEXT", 64),
            ("Unit_ID", "TEXT", unit_id_length),
            ("Level_ID", "TEXT", level_id_length),
            ("Facility_ID", "TEXT", facility_id_length),
            ("Site_ID", "TEXT", site_id_length),
            ("Barcode", "TEXT", 64),
            ("Photo_URL", "TEXT", 2048),
            ("Height", "DOUBLE", None),
            ("SourceUnitGlobalID", "GUID", None),
            ("RunID", "GUID", None),
            ("BusinessID", "TEXT", 64),
            ("AssetType", "TEXT", 64),
            ("AssetClass", "TEXT", 48),
            ("Condition", "TEXT", 24),
        ],
    )
    _add_fields(
        arcpy,
        asset_lifecycle,
        [
            ("Asset_ID", "TEXT", 64),
            ("Name", "TEXT", 255),
            ("Description", "TEXT", 2048),
            ("Category_Code", "TEXT", 16),
            ("Category_Type", "TEXT", 128),
            ("Subtype_Code", "TEXT", 16),
            ("Category_Subtype", "TEXT", 128),
            ("Make", "TEXT", 128),
            ("Model", "TEXT", 128),
            ("Serial", "TEXT", 128),
            ("Owner", "TEXT", 64),
            ("Maintainable", "TEXT", 1),
            ("Fixed", "TEXT", 1),
            ("Criticality_Rating", "SHORT", None),
            ("Unit_ID", "TEXT", unit_id_length),
            ("Level_ID", "TEXT", level_id_length),
            ("Facility_ID", "TEXT", facility_id_length),
            ("Site_ID", "TEXT", site_id_length),
            ("Barcode", "TEXT", 64),
            ("Photo_URL", "TEXT", 2048),
            ("Height", "DOUBLE", None),
            ("AssetPointGlobalID", "GUID", None),
            ("SourceUnitGlobalID", "GUID", None),
            ("RunID", "GUID", None),
            ("BusinessID", "TEXT", 64),
            ("AssetType", "TEXT", 64),
            ("AssetClass", "TEXT", 48),
            ("Condition", "TEXT", 24),
            ("Criticality", "TEXT", 16),
            ("CommissioningDate", "DATE", None),
            ("NextMaintenanceDate", "DATE", None),
        ],
    )
    _add_fields(
        arcpy,
        inspections,
        [
            ("AssetLifecycleGlobalID", "GUID", None),
            ("AssetPointGlobalID", "GUID", None),
            ("Asset_ID", "TEXT", 64),
            ("Asset_Type", "TEXT", 64),
            ("Inspection_Date", "DATE", None),
            ("Inspector", "TEXT", 128),
            ("Condition_Rating", "TEXT", 24),
            ("Repair_Needed", "TEXT", 1),
            ("Notes", "TEXT", 2048),
            ("Estimated_Repair_Cost", "DOUBLE", None),
            ("Repair_Type", "TEXT", 64),
        ],
    )
    _add_fields(
        arcpy,
        repairs,
        [
            ("AssetLifecycleGlobalID", "GUID", None),
            ("AssetPointGlobalID", "GUID", None),
            ("Asset_ID", "TEXT", 64),
            ("Asset_Type", "TEXT", 64),
            ("Repair_Date", "DATE", None),
            ("Technician", "TEXT", 128),
            ("Repair_Type", "TEXT", 64),
            ("Notes", "TEXT", 2048),
            ("Repair_Cost", "DOUBLE", None),
        ],
    )
    _add_fields(
        arcpy,
        work_orders,
        [
            ("AssetLifecycleGlobalID", "GUID", None),
            ("AssetPointGlobalID", "GUID", None),
            ("Work_Order_ID", "TEXT", 64),
            ("Request_Type", "TEXT", 64),
            ("Request_Date", "DATE", None),
            ("Description_of_Issue", "TEXT", 2048),
            ("Asset_ID", "TEXT", 64),
            ("Asset_Type", "TEXT", 64),
            ("Unit_ID", "TEXT", unit_id_length),
            ("Level_ID", "TEXT", level_id_length),
            ("Facility_ID", "TEXT", facility_id_length),
            ("Facility_Name", "TEXT", 255),
            ("Assignee", "TEXT", 128),
            ("Status", "TEXT", 24),
        ],
    )
    _add_fields(
        arcpy,
        exterior_asset_points,
        [
            ("SourceFacilityGlobalID", "GUID", None),
            ("RunID", "GUID", None),
            ("BusinessID", "TEXT", 64),
            ("AssetType", "TEXT", 64),
            ("AssetClass", "TEXT", 48),
            ("PlacementType", "TEXT", 16),
            ("Condition", "TEXT", 24),
        ],
    )
    _add_fields(
        arcpy,
        external_references,
        [
            ("AssetGlobalID", "GUID", None),
            ("RunID", "GUID", None),
            ("SystemName", "TEXT", 64),
            ("ExternalRecordID", "TEXT", 128),
            ("ExternalObjectType", "TEXT", 64),
            ("RecordUrl", "TEXT", 2048),
            ("SyncStatus", "TEXT", 24),
            ("LastSyncUTC", "DATE", None),
        ],
    )
    _add_fields(
        arcpy,
        field_work_links,
        [
            ("AssetGlobalID", "GUID", None),
            ("RunID", "GUID", None),
            ("WorkflowType", "TEXT", 32),
            ("PortalItemID", "TEXT", 32),
            ("LayerOrFormID", "TEXT", 128),
            ("RelatedRecordGlobalID", "GUID", None),
            ("RecordUrl", "TEXT", 2048),
            ("Status", "TEXT", 24),
        ],
    )
    _add_fields(
        arcpy,
        media_references,
        [
            ("AssetLifecycleGlobalID", "GUID", None),
            ("MediaType", "TEXT", 32),
            ("OrientedImageryCatalogID", "TEXT", 128),
            ("PortalItemID", "TEXT", 32),
            ("ImageID", "TEXT", 128),
            ("ImageURL", "TEXT", 2048),
            ("CaptureDate", "DATE", None),
            ("CameraHeading", "DOUBLE", None),
            ("CameraPitch", "DOUBLE", None),
            ("CameraRoll", "DOUBLE", None),
            ("LocationAccuracy", "DOUBLE", None),
        ],
    )
    arcpy.management.AddGlobalIDs(indoor_asset_locations)
    arcpy.management.AddGlobalIDs(exterior_asset_points)
    arcpy.management.AddGlobalIDs(asset_lifecycle)
    arcpy.management.AddGlobalIDs(inspections)
    arcpy.management.AddGlobalIDs(repairs)
    arcpy.management.AddGlobalIDs(work_orders)
    arcpy.management.AddGlobalIDs(external_references)
    arcpy.management.AddGlobalIDs(field_work_links)
    arcpy.management.AddGlobalIDs(media_references)
    _create_condition_domain(arcpy, output_gdb)
    _create_asset_class_domain(arcpy, output_gdb)
    arcpy.management.AssignDomainToField(indoor_asset_locations, "Condition", "AssetCondition")
    arcpy.management.AssignDomainToField(asset_lifecycle, "Condition", "AssetCondition")
    arcpy.management.AssignDomainToField(asset_lifecycle, "AssetClass", "AssetClass")
    _create_lifecycle_domains(arcpy, output_gdb)
    arcpy.management.AssignDomainToField(asset_lifecycle, "Maintainable", "YesNo")
    arcpy.management.AssignDomainToField(asset_lifecycle, "Fixed", "YesNo")
    arcpy.management.AssignDomainToField(asset_lifecycle, "Criticality_Rating", "CriticalityRating")
    arcpy.management.AssignDomainToField(inspections, "Condition_Rating", "InspectionCondition")
    arcpy.management.AssignDomainToField(inspections, "Repair_Needed", "YesNo")
    arcpy.management.AssignDomainToField(work_orders, "Status", "WorkOrderStatus")
    _create_placement_domain(arcpy, output_gdb)
    arcpy.management.AssignDomainToField(exterior_asset_points, "PlacementType", "AssetPlacementType")
    arcpy.management.AssignDomainToField(exterior_asset_points, "Condition", "AssetCondition")
    _create_integration_domains(arcpy, output_gdb)
    arcpy.management.AssignDomainToField(external_references, "SystemName", "ExternalSystem")
    arcpy.management.AssignDomainToField(external_references, "SyncStatus", "IntegrationSyncStatus")
    arcpy.management.AssignDomainToField(field_work_links, "WorkflowType", "FieldWorkWorkflow")
    arcpy.management.AssignDomainToField(field_work_links, "Status", "FieldWorkStatus")
    arcpy.management.AssignDomainToField(media_references, "MediaType", "AssetMediaType")
    arcpy.management.AddIndex(indoor_asset_locations, "SourceUnitGlobalID", "IX_IndoorLocations_Unit")
    arcpy.management.AddIndex(asset_lifecycle, "AssetPointGlobalID", "IX_AssetLifecycle_Location")
    arcpy.management.AddIndex(asset_lifecycle, "Asset_ID", "IX_AssetLifecycle_AssetID")
    arcpy.management.AddIndex(inspections, "AssetLifecycleGlobalID", "IX_Inspection_Asset")
    arcpy.management.AddIndex(repairs, "AssetLifecycleGlobalID", "IX_Repair_Asset")
    arcpy.management.AddIndex(work_orders, "AssetLifecycleGlobalID", "IX_WorkOrder_Asset")
    arcpy.management.AddIndex(inspections, "AssetPointGlobalID", "IX_Inspection_AssetPoint")
    arcpy.management.AddIndex(repairs, "AssetPointGlobalID", "IX_Repair_AssetPoint")
    arcpy.management.AddIndex(work_orders, "AssetPointGlobalID", "IX_WorkOrder_AssetPoint")
    arcpy.management.AddIndex(exterior_asset_points, "SourceFacilityGlobalID", "IX_ExtAssets_Facility")
    arcpy.management.AddIndex(external_references, "AssetGlobalID", "IX_ExternalRefs_Asset")
    arcpy.management.AddIndex(external_references, "ExternalRecordID", "IX_ExternalRefs_Record")
    arcpy.management.AddIndex(field_work_links, "AssetGlobalID", "IX_FieldWorkLinks_Asset")
    arcpy.management.AddIndex(media_references, "AssetLifecycleGlobalID", "IX_MediaRefs_Asset")

    arcpy.management.CreateRelationshipClass(
        units,
        indoor_asset_locations,
        f"{output_gdb}\\Units_IndoorAssetLocations",
        "SIMPLE",
        "Indoor asset locations",
        "Source Indoors Unit",
        "NONE",
        "ONE_TO_MANY",
        "NONE",
        source.unit_global_id_field,
        "SourceUnitGlobalID",
    )
    arcpy.management.CreateRelationshipClass(
        indoor_asset_locations,
        asset_lifecycle,
        f"{output_gdb}\\IndoorLocations_AssetLifecycle",
        "SIMPLE",
        "Asset lifecycle record",
        "Asset point",
        "NONE",
        "ONE_TO_ONE",
        "NONE",
        "GlobalID",
        "AssetPointGlobalID",
    )
    _create_asset_child_relationship(
        arcpy, output_gdb, asset_lifecycle, inspections, "AssetLifecycle_Inspections", "Inspection"
    )
    _create_asset_child_relationship(
        arcpy, output_gdb, asset_lifecycle, repairs, "AssetLifecycle_Repairs", "Repair"
    )
    _create_asset_child_relationship(
        arcpy, output_gdb, asset_lifecycle, work_orders, "AssetLifecycle_WorkOrders", "Work order"
    )
    _create_asset_point_child_relationship(
        arcpy,
        output_gdb,
        indoor_asset_locations,
        inspections,
        "IndoorLocations_Inspections",
        "Inspection",
    )
    _create_asset_point_child_relationship(
        arcpy,
        output_gdb,
        indoor_asset_locations,
        repairs,
        "IndoorLocations_Repairs",
        "Repair",
    )
    _create_asset_point_child_relationship(
        arcpy,
        output_gdb,
        indoor_asset_locations,
        work_orders,
        "IndoorLocations_WorkOrders",
        "Work order",
    )
    arcpy.management.CreateRelationshipClass(
        source.feature_classes["facilities"],
        exterior_asset_points,
        f"{output_gdb}\\Facilities_ExteriorAssetPoints",
        "SIMPLE",
        "Exterior and attached assets",
        "Source Indoors Facility",
        "NONE",
        "ONE_TO_MANY",
        "NONE",
        source.facility_global_id_field,
        "SourceFacilityGlobalID",
    )
    arcpy.management.CreateRelationshipClass(
        asset_lifecycle,
        external_references,
        f"{output_gdb}\\AssetLifecycle_ExternalReferences",
        "SIMPLE",
        "External system reference",
        "Asset",
        "NONE",
        "ONE_TO_MANY",
        "NONE",
        "GlobalID",
        "AssetGlobalID",
    )
    _create_asset_child_relationship(
        arcpy,
        output_gdb,
        asset_lifecycle,
        media_references,
        "AssetLifecycle_MediaReferences",
        "Asset media reference",
    )
    arcpy.management.CreateRelationshipClass(
        asset_lifecycle,
        field_work_links,
        f"{output_gdb}\\AssetLifecycle_FieldWorkLinks",
        "SIMPLE",
        "Inspection or Survey123 link",
        "Asset",
        "NONE",
        "ONE_TO_MANY",
        "NONE",
        "GlobalID",
        "AssetGlobalID",
    )
    _create_asset_contingencies(arcpy, asset_lifecycle)
    _create_lifecycle_constraint(arcpy, asset_lifecycle)
    return AssetManagementSchema(
        feature_dataset=feature_dataset,
        indoor_asset_locations=indoor_asset_locations,
        exterior_asset_points=exterior_asset_points,
        asset_lifecycle=asset_lifecycle,
        inspections=inspections,
        repairs=repairs,
        work_orders=work_orders,
        external_references=external_references,
        field_work_links=field_work_links,
        media_references=media_references,
    )


def _source_text_field_length(
    arcpy: Any, dataset: str | None, field_name: str, default: int
) -> int:
    if dataset is None:
        return default
    for field in arcpy.ListFields(dataset):
        if field.name.upper() == field_name.upper() and field.type == "String":
            return field.length or default
    return default


def _add_fields(arcpy: Any, dataset: str, fields: list[tuple[str, str, int | None]]) -> None:
    for name, field_type, length in fields:
        arguments = [dataset, name, field_type]
        if length is not None:
            arguments.extend([None, None, length])
        arcpy.management.AddField(*arguments)


def _create_condition_domain(arcpy: Any, output_gdb: str) -> None:
    arcpy.management.CreateDomain(
        output_gdb,
        "AssetCondition",
        "Synthetic asset operational condition",
        "TEXT",
        "CODED",
    )
    for code in ("Operational", "Maintenance Due", "Offline Repair"):
        arcpy.management.AddCodedValueToDomain(output_gdb, "AssetCondition", code, code)


def _create_placement_domain(arcpy: Any, output_gdb: str) -> None:
    arcpy.management.CreateDomain(
        output_gdb, "AssetPlacementType", "Exterior asset placement type", "TEXT", "CODED"
    )
    for code in ("Exterior", "Attached"):
        arcpy.management.AddCodedValueToDomain(output_gdb, "AssetPlacementType", code, code)


def _create_asset_class_domain(arcpy: Any, output_gdb: str) -> None:
    arcpy.management.CreateDomain(
        output_gdb, "AssetClass", "Synthetic asset class", "TEXT", "CODED"
    )
    for code in (
        "Building Services",
        "Clinical Equipment",
        "Communications Equipment",
        "Diagnostic Equipment",
        "Electrical Equipment",
        "Fire and Life Safety",
        "Furniture",
        "IT Equipment",
        "Plumbing Equipment",
        "Security Equipment",
    ):
        arcpy.management.AddCodedValueToDomain(output_gdb, "AssetClass", code, code)


def _create_asset_contingencies(arcpy: Any, assets: str) -> None:
    arcpy.management.CreateFieldGroup(assets, "AssetClassCondition", ["AssetClass", "Condition"])
    for asset_class in (
        "Building Services",
        "Clinical Equipment",
        "Communications Equipment",
        "Diagnostic Equipment",
        "Electrical Equipment",
        "Fire and Life Safety",
        "Furniture",
        "IT Equipment",
        "Plumbing Equipment",
        "Security Equipment",
    ):
        for condition in ("Operational", "Maintenance Due", "Offline Repair"):
            arcpy.management.AddContingentValue(
                assets,
                "AssetClassCondition",
                [
                    ["AssetClass", "CODED_VALUE", asset_class],
                    ["Condition", "CODED_VALUE", condition],
                ],
            )


def _create_integration_domains(arcpy: Any, output_gdb: str) -> None:
    _create_coded_domain(
        arcpy,
        output_gdb,
        "ExternalSystem",
        "External enterprise system",
        ("Salesforce", "IBM Maximo", "Other"),
    )
    _create_coded_domain(
        arcpy,
        output_gdb,
        "IntegrationSyncStatus",
        "External reference synchronization state",
        ("Not Configured", "Pending", "Synchronized", "Error"),
    )
    _create_coded_domain(
        arcpy,
        output_gdb,
        "FieldWorkWorkflow",
        "ArcGIS field workflow type",
        ("ArcGIS Inspection", "Survey123"),
    )
    _create_coded_domain(
        arcpy,
        output_gdb,
        "FieldWorkStatus",
        "Inspection or form workflow state",
        ("Not Started", "In Progress", "Complete", "Closed"),
    )
    _create_coded_domain(
        arcpy,
        output_gdb,
        "AssetMediaType",
        "Asset reference media type",
        ("OrientedImage", "Panorama360", "Photo", "Document"),
    )


def _create_lifecycle_domains(arcpy: Any, output_gdb: str) -> None:
    _create_coded_domain(arcpy, output_gdb, "YesNo", "Yes or no", ("Y", "N"))
    arcpy.management.CreateDomain(
        output_gdb, "CriticalityRating", "Asset criticality rating", "SHORT", "CODED"
    )
    for rating in range(1, 6):
        arcpy.management.AddCodedValueToDomain(output_gdb, "CriticalityRating", rating, str(rating))
    _create_coded_domain(
        arcpy,
        output_gdb,
        "InspectionCondition",
        "Inspection condition rating",
        ("Excellent", "Good", "Fair", "Poor", "Fail"),
    )
    _create_coded_domain(
        arcpy,
        output_gdb,
        "WorkOrderStatus",
        "Work order status",
        ("Open", "Assigned", "In Progress", "On Hold", "Completed", "Closed"),
    )


def _create_asset_child_relationship(
    arcpy: Any, output_gdb: str, asset_lifecycle: str, child_table: str, name: str, label: str
) -> None:
    arcpy.management.CreateRelationshipClass(
        asset_lifecycle,
        child_table,
        f"{output_gdb}\\{name}",
        "SIMPLE",
        label,
        "Asset lifecycle record",
        "NONE",
        "ONE_TO_MANY",
        "NONE",
        "GlobalID",
        "AssetLifecycleGlobalID",
    )


def _create_asset_point_child_relationship(
    arcpy: Any,
    output_gdb: str,
    indoor_asset_locations: str,
    child_table: str,
    name: str,
    label: str,
) -> None:
    arcpy.management.CreateRelationshipClass(
        indoor_asset_locations,
        child_table,
        f"{output_gdb}\\{name}",
        "SIMPLE",
        label,
        "Indoor asset location",
        "NONE",
        "ONE_TO_MANY",
        "NONE",
        "GlobalID",
        "AssetPointGlobalID",
    )


def _create_coded_domain(
    arcpy: Any, output_gdb: str, name: str, description: str, codes: tuple[str, ...]
) -> None:
    arcpy.management.CreateDomain(output_gdb, name, description, "TEXT", "CODED")
    for code in codes:
        arcpy.management.AddCodedValueToDomain(output_gdb, name, code, code)


def _create_lifecycle_constraint(arcpy: Any, assets: str) -> None:
    arcpy.management.AddAttributeRule(
        assets,
        "AssetLifecycleDateOrder",
        "CONSTRAINT",
        "IsEmpty($feature.CommissioningDate) || IsEmpty($feature.NextMaintenanceDate) || ($feature.CommissioningDate <= Today() && $feature.NextMaintenanceDate > $feature.CommissioningDate)",
        "EDITABLE",
        ["INSERT", "UPDATE"],
        1001,
        "Commissioning date must not be in the future and maintenance must follow commissioning.",
        "Synthetic asset lifecycle date integrity.",
    )
