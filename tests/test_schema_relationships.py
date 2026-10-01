import unittest

from indoors_demo_generator.schema import _create_asset_point_child_relationship


class _Management:
    def __init__(self) -> None:
        self.arguments = None

    def CreateRelationshipClass(self, *arguments) -> None:
        self.arguments = arguments


class _ArcPy:
    management = _Management()


class AssetPointRelationshipTests(unittest.TestCase):
    def test_history_relationship_uses_asset_point_global_id(self):
        arcpy = _ArcPy()

        _create_asset_point_child_relationship(
            arcpy,
            "output.gdb",
            "IndoorAssetLocation",
            "AssetInspection",
            "IndoorLocations_Inspections",
            "Inspection",
        )

        self.assertEqual(arcpy.management.arguments[0], "IndoorAssetLocation")
        self.assertEqual(arcpy.management.arguments[1], "AssetInspection")
        self.assertEqual(
            arcpy.management.arguments[2],
            "output.gdb\\IndoorLocations_Inspections",
        )
        self.assertEqual(arcpy.management.arguments[-2:], ("GlobalID", "AssetPointGlobalID"))


if __name__ == "__main__":
    unittest.main()