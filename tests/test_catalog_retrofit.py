from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from indoors_demo_generator.catalog_retrofit import retrofit_asset_metadata  # noqa: E402
from indoors_demo_generator.asset_catalog import (  # noqa: E402
    estimated_repair_cost_for,
    repair_cost_for,
)


class _Cursor:
    def __init__(self, datasets, dataset_name, fields, update=False):
        self.rows = datasets[dataset_name]
        self.fields = fields
        self.update = update
        self.position = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def __iter__(self):
        return self

    def __next__(self):
        if self.position >= len(self.rows):
            raise StopIteration
        self.position += 1
        source = self.rows[self.position - 1]
        return [source.get(field) for field in self.fields]

    def updateRow(self, row):
        target = self.rows[self.position - 1]
        target.update(dict(zip(self.fields, row)))


class _FakeArcPy:
    def __init__(self, datasets):
        self.datasets = datasets
        self.da = SimpleNamespace(
            SearchCursor=lambda path, fields: _Cursor(
                datasets, path.rsplit("\\", 1)[-1], fields
            ),
            UpdateCursor=lambda path, fields: _Cursor(
                datasets, path.rsplit("\\", 1)[-1], fields, update=True
            ),
        )

    def Exists(self, path):
        return path.rsplit("\\", 1)[-1] in self.datasets

    def ListFields(self, path):
        rows = self.datasets[path.rsplit("\\", 1)[-1]]
        return [SimpleNamespace(name=name) for name in rows[0]]


class CatalogRetrofitTests(unittest.TestCase):
    def test_retrofits_lifecycle_and_history_costs(self):
        datasets = {
            "AssetLifecycle": [
                {
                    "Asset_ID": "asset-1",
                    "AssetType": "VITAL_SIGNS_MONITOR",
                    "AssetClass": "Clinical Equipment",
                    "Category_Code": None,
                    "Category_Type": None,
                    "Subtype_Code": None,
                    "Category_Subtype": None,
                    "CommissioningDate": datetime(2020, 1, 1),
                    "Criticality": "High",
                    "Condition": "Maintenance Due",
                    "LifecycleStage": "Within Service Life",
                    "OverdueDays": 90,
                    "MaintenanceIntervalDays": None,
                    "EstimatedReplacementCost": None,
                    "PurchaseDate": None,
                    "PurchaseCost": None,
                    "Vendor": None,
                    "WarrantyExpirationDate": None,
                    "WarrantyStatus": None,
                    "AnnualMaintenanceCost": None,
                    "RiskScore": None,
                    "RiskLevel": None,
                },
                {
                    "Asset_ID": "asset-2",
                    "AssetType": "ERGONOMIC_CHAIR",
                    "AssetClass": "Furniture",
                    "Category_Code": None,
                    "Category_Type": None,
                    "Subtype_Code": None,
                    "Category_Subtype": None,
                    "CommissioningDate": datetime(2025, 1, 1),
                    "Criticality": "Low",
                    "Condition": "Operational",
                    "LifecycleStage": "Recently Installed",
                    "OverdueDays": 0,
                    "MaintenanceIntervalDays": None,
                    "EstimatedReplacementCost": None,
                    "PurchaseDate": None,
                    "PurchaseCost": None,
                    "Vendor": None,
                    "WarrantyExpirationDate": None,
                    "WarrantyStatus": None,
                    "AnnualMaintenanceCost": None,
                    "RiskScore": None,
                    "RiskLevel": None,
                },
            ],
            "AssetInspection": [
                {"Asset_ID": "asset-1", "Repair_Needed": "Y", "Estimated_Repair_Cost": None},
                {"Asset_ID": "asset-2", "Repair_Needed": "N", "Estimated_Repair_Cost": 25.0},
            ],
            "AssetRepair": [
                {"Asset_ID": "asset-1", "Repair_Cost": None},
            ],
        }
        arcpy = _FakeArcPy(datasets)

        result = retrofit_asset_metadata(arcpy, r"C:\fake\catalog.gdb", repository=ROOT)

        first, second = datasets["AssetLifecycle"]
        self.assertEqual(first["Category_Code"], "CLIN")
        self.assertEqual(first["Category_Type"], "Clinical Equipment")
        self.assertTrue(first["Subtype_Code"])
        self.assertEqual(first["Category_Subtype"], "Vital Signs Monitor")
        self.assertGreater(first["EstimatedReplacementCost"], 0)
        self.assertLess(first["PurchaseCost"], first["EstimatedReplacementCost"])
        self.assertEqual(first["WarrantyStatus"], "Expired")
        self.assertGreater(first["AnnualMaintenanceCost"], 0)
        self.assertIsInstance(first["RiskScore"], int)
        self.assertEqual(second["Category_Code"], "FURN")
        self.assertEqual(datasets["AssetInspection"][0]["Estimated_Repair_Cost"], estimated_repair_cost_for(first["EstimatedReplacementCost"], "asset-1"))
        self.assertIsNone(datasets["AssetInspection"][1]["Estimated_Repair_Cost"])
        self.assertEqual(datasets["AssetRepair"][0]["Repair_Cost"], repair_cost_for(first["EstimatedReplacementCost"], "asset-1"))
        self.assertEqual(result["lifecycle_assets_updated"], 2)
        self.assertEqual(result["inspections_with_repair_estimate"], 1)
        self.assertEqual(result["inspections_without_repair_estimate"], 1)
        self.assertEqual(result["repair_rows_updated"], 1)

    def test_unknown_live_type_fails_before_update(self):
        datasets = {
            "AssetLifecycle": [
                {
                    "Asset_ID": "asset-unknown",
                    "AssetType": "UNKNOWN_DEVICE",
                    "AssetClass": "IT Equipment",
                    "Category_Code": None,
                    "Category_Type": None,
                    "Subtype_Code": None,
                    "Category_Subtype": None,
                    "CommissioningDate": datetime(2020, 1, 1),
                    "Criticality": "High",
                    "Condition": "Operational",
                    "LifecycleStage": "Within Service Life",
                    "OverdueDays": 0,
                    "MaintenanceIntervalDays": 365,
                    "EstimatedReplacementCost": None,
                    "PurchaseDate": None,
                    "PurchaseCost": None,
                    "Vendor": None,
                    "WarrantyExpirationDate": None,
                    "WarrantyStatus": None,
                    "AnnualMaintenanceCost": None,
                    "RiskScore": None,
                    "RiskLevel": None,
                }
            ],
            "AssetInspection": [],
            "AssetRepair": [],
        }
        with self.assertRaisesRegex(ValueError, "No taxonomy and pricebook entry"):
            retrofit_asset_metadata(
                _FakeArcPy(datasets), r"C:\fake\catalog.gdb", repository=ROOT
            )
        self.assertIsNone(datasets["AssetLifecycle"][0]["Category_Code"])


if __name__ == "__main__":
    unittest.main()
