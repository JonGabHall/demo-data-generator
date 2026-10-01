import json
from datetime import date
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from indoors_demo_generator.asset_catalog import (  # noqa: E402
    ASSET_TYPE_COST_BANDS,
    annual_maintenance_cost_for,
    asset_taxonomy,
    estimated_repair_cost_for,
    purchase_cost_for,
    purchase_date_for,
    repair_cost_for,
    replacement_cost_for,
)


class AssetCatalogTests(unittest.TestCase):
    def test_pricebook_covers_every_profile_type_and_class(self):
        profile_types = set()
        for profile_path in (ROOT / "profiles").glob("*.json"):
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            for templates in profile["room_uses"].values():
                for template in templates:
                    pair = (template["id"], template["asset_class"])
                    asset_taxonomy(*pair)
                    profile_types.add(pair)

        pricebook_types = {
            (asset_type, asset_class)
            for asset_class, entries in ASSET_TYPE_COST_BANDS.items()
            for asset_type in entries
        }
        self.assertEqual(profile_types, pricebook_types)

    def test_asset_values_are_stable_and_within_type_specific_bands(self):
        for asset_class, entries in ASSET_TYPE_COST_BANDS.items():
            for asset_type, (minimum, maximum) in entries.items():
                identity = f"{asset_class}|{asset_type}|sample"
                first = replacement_cost_for(asset_type, asset_class, identity)
                second = replacement_cost_for(asset_type, asset_class, identity)
                taxonomy = asset_taxonomy(asset_type, asset_class)

                self.assertEqual(first, second)
                self.assertGreaterEqual(first, minimum)
                self.assertLessEqual(first, maximum)
                self.assertLessEqual(len(taxonomy["Category_Code"]), 16)
                self.assertLessEqual(len(taxonomy["Subtype_Code"]), 16)
                self.assertTrue(taxonomy["Category_Subtype"])

    def test_pricing_helpers_preserve_temporal_and_cost_order(self):
        commissioning = date(2024, 1, 1)
        replacement = replacement_cost_for(
            "VITAL_SIGNS_MONITOR", "Clinical Equipment", "asset-1"
        )
        purchase_date = purchase_date_for(commissioning, "asset-1")
        purchase_cost = purchase_cost_for(replacement, "asset-1")
        maintenance_cost = annual_maintenance_cost_for(
            replacement, "High", "Within Service Life", "Operational"
        )

        self.assertLess(purchase_date, commissioning)
        self.assertGreater(purchase_cost, 0)
        self.assertLess(purchase_cost, replacement)
        self.assertGreater(maintenance_cost, 0)
        self.assertLess(maintenance_cost, replacement)
        self.assertGreater(estimated_repair_cost_for(replacement, "asset-1"), 0)
        self.assertGreater(repair_cost_for(replacement, "asset-1"), 0)

    def test_unknown_asset_type_is_rejected(self):
        with self.assertRaises(ValueError):
            replacement_cost_for("UNMAPPED_DEVICE", "IT Equipment", "asset-1")


if __name__ == "__main__":
    unittest.main()