"""Manual ArcPy smoke test for the generated integration schema."""

import os
from pathlib import Path
import sys
import tempfile

import arcpy

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from indoors_demo_generator.preflight import validate_indoors_source
from indoors_demo_generator.schema import create_asset_management_schema


temporary_directory = tempfile.mkdtemp(prefix="indoors_demo_schema_")
geodatabase = arcpy.management.CreateFileGDB(temporary_directory, "fixture.gdb").getOutput(0)
indoor = os.path.join(geodatabase, "Indoor")
arcpy.management.CreateFeatureDataset(geodatabase, "Indoor", arcpy.SpatialReference(3857))
for name in ("Facilities", "Levels", "Units"):
    arcpy.management.CreateFeatureclass(indoor, name, "POLYGON")
arcpy.management.AddGlobalIDs(os.path.join(indoor, "Facilities"))
arcpy.management.AddGlobalIDs(os.path.join(indoor, "Levels"))
arcpy.management.AddField(os.path.join(indoor, "Units"), "USE_TYPE", "TEXT", field_length=64)
arcpy.management.AddGlobalIDs(os.path.join(indoor, "Units"))

schema = create_asset_management_schema(arcpy, geodatabase, validate_indoors_source(arcpy, geodatabase))
artifacts = (
    schema.indoor_asset_locations,
    schema.exterior_asset_points,
    schema.asset_lifecycle,
    schema.inspections,
    schema.repairs,
    schema.work_orders,
    schema.external_references,
    schema.field_work_links,
    schema.media_references,
    os.path.join(geodatabase, "Units_IndoorAssetLocations"),
    os.path.join(geodatabase, "IndoorLocations_AssetLifecycle"),
    os.path.join(geodatabase, "AssetLifecycle_Inspections"),
    os.path.join(geodatabase, "AssetLifecycle_Repairs"),
    os.path.join(geodatabase, "AssetLifecycle_WorkOrders"),
    os.path.join(geodatabase, "IndoorLocations_Inspections"),
    os.path.join(geodatabase, "IndoorLocations_Repairs"),
    os.path.join(geodatabase, "IndoorLocations_WorkOrders"),
    os.path.join(geodatabase, "Facilities_ExteriorAssetPoints"),
    os.path.join(geodatabase, "AssetLifecycle_ExternalReferences"),
    os.path.join(geodatabase, "AssetLifecycle_FieldWorkLinks"),
    os.path.join(geodatabase, "AssetLifecycle_MediaReferences"),
)
assert all(arcpy.Exists(artifact) for artifact in artifacts)
assert len(arcpy.da.ListContingentValues(schema.asset_lifecycle)) == 30
assert len(arcpy.Describe(schema.asset_lifecycle).attributeRules) == 1
print(f"Created {len(artifacts)} schema artifacts in {geodatabase}")