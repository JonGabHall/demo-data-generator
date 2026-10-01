import os
from pathlib import Path
import tempfile
import unittest

import arcpy

from indoors_demo_generator.preflight import validate_indoors_source
from indoors_demo_generator.schema import create_asset_management_schema


@unittest.skipUnless(arcpy.ProductInfo() != "NotLicensed", "ArcGIS Pro license is required")
class DemoSchemaIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.gdb = str(Path(self.temporary_directory.name) / "fixture.gdb")
        arcpy.management.CreateFileGDB(self.temporary_directory.name, "fixture.gdb")
        arcpy.management.CreateFeatureDataset(self.gdb, "Indoor", arcpy.SpatialReference(3857))
        indoor = os.path.join(self.gdb, "Indoor")
        for name in ("Sites", "Facilities", "Levels", "Units"):
            arcpy.management.CreateFeatureclass(indoor, name, "POLYGON")
        arcpy.management.AddField(
            os.path.join(indoor, "Sites"), "SITE_ID", "TEXT", field_length=255
        )
        arcpy.management.AddField(
            os.path.join(indoor, "Facilities"), "FACILITY_ID", "TEXT", field_length=255
        )
        arcpy.management.AddField(
            os.path.join(indoor, "Facilities"), "SITE_ID", "TEXT", field_length=255
        )
        arcpy.management.AddField(
            os.path.join(indoor, "Levels"), "LEVEL_ID", "TEXT", field_length=255
        )
        arcpy.management.AddField(
            os.path.join(indoor, "Levels"), "FACILITY_ID", "TEXT", field_length=255
        )
        arcpy.management.AddField(
            os.path.join(indoor, "Units"), "UNIT_ID", "TEXT", field_length=255
        )
        arcpy.management.AddField(
            os.path.join(indoor, "Units"), "LEVEL_ID", "TEXT", field_length=255
        )
        arcpy.management.AddGlobalIDs(os.path.join(indoor, "Facilities"))
        arcpy.management.AddGlobalIDs(os.path.join(indoor, "Levels"))
        arcpy.management.AddField(os.path.join(indoor, "Units"), "USE_TYPE", "TEXT", field_length=64)
        arcpy.management.AddGlobalIDs(os.path.join(indoor, "Units"))

    def tearDown(self):
        arcpy.management.ClearWorkspaceCache()
        self.temporary_directory.cleanup()

    def test_creates_generated_schema_and_relationships(self):
        source = validate_indoors_source(arcpy, self.gdb)
        schema = create_asset_management_schema(arcpy, self.gdb, source)

        self.assertTrue(arcpy.Exists(schema.indoor_asset_locations))
        self.assertTrue(arcpy.Exists(schema.exterior_asset_points))
        self.assertTrue(arcpy.Exists(schema.asset_lifecycle))
        self.assertTrue(arcpy.Exists(schema.inspections))
        self.assertTrue(arcpy.Exists(schema.repairs))
        self.assertTrue(arcpy.Exists(schema.work_orders))
        self.assertTrue(arcpy.Exists(schema.media_references))
        self.assertTrue(arcpy.Exists(schema.external_references))
        self.assertTrue(arcpy.Exists(schema.field_work_links))
        self.assertTrue(arcpy.Exists(os.path.join(self.gdb, "Units_IndoorAssetLocations")))
        self.assertTrue(arcpy.Exists(os.path.join(self.gdb, "IndoorLocations_AssetLifecycle")))
        self.assertTrue(arcpy.Exists(os.path.join(self.gdb, "AssetLifecycle_Inspections")))
        self.assertTrue(arcpy.Exists(os.path.join(self.gdb, "AssetLifecycle_Repairs")))
        self.assertTrue(arcpy.Exists(os.path.join(self.gdb, "AssetLifecycle_WorkOrders")))
        self.assertTrue(arcpy.Exists(os.path.join(self.gdb, "IndoorLocations_Inspections")))
        self.assertTrue(arcpy.Exists(os.path.join(self.gdb, "IndoorLocations_Repairs")))
        self.assertTrue(arcpy.Exists(os.path.join(self.gdb, "IndoorLocations_WorkOrders")))
        self.assertTrue(arcpy.Exists(os.path.join(self.gdb, "AssetLifecycle_MediaReferences")))
        self.assertTrue(arcpy.Exists(os.path.join(self.gdb, "AssetLifecycle_ExternalReferences")))
        self.assertTrue(arcpy.Exists(os.path.join(self.gdb, "AssetLifecycle_FieldWorkLinks")))
        fields = {field.name for field in arcpy.ListFields(schema.asset_lifecycle)}
        self.assertTrue({"GlobalID", "AssetPointGlobalID", "SourceUnitGlobalID"} <= fields)
        for child in (schema.inspections, schema.repairs, schema.work_orders):
            child_fields = {field.name for field in arcpy.ListFields(child)}
            self.assertIn("AssetPointGlobalID", child_fields)
        indoor_fields = {
            field.name: field for field in arcpy.ListFields(schema.indoor_asset_locations)
        }
        self.assertEqual(indoor_fields["Level_ID"].length, 255)
        self.assertEqual(indoor_fields["Unit_ID"].length, 255)


if __name__ == "__main__":
    unittest.main()