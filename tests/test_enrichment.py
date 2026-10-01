from collections import Counter
from dataclasses import replace
from datetime import date
import unittest

from indoors_demo_generator.enrichment import (
    AssetSeed,
    EnrichmentConfig,
    build_enrichment_plan,
)
from indoors_demo_generator.asset_catalog import ASSET_TYPE_COST_BANDS


def _assets(count: int = 1003) -> list[AssetSeed]:
    classes = (
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
    )
    assets = []
    for index in range(count):
        asset_class = classes[index % len(classes)]
        asset_types = sorted(ASSET_TYPE_COST_BANDS[asset_class])
        asset_type = asset_types[(index // len(classes)) % len(asset_types)]
        assets.append(
            AssetSeed(
                asset_id=f"asset-{index:04d}",
                global_id=f"{{00000000-0000-0000-0000-{index:012d}}}",
                asset_type=asset_type,
                asset_class=asset_class,
                criticality=("Low", "Medium", "High", "Critical")[index % 4],
                unit_id=f"UNIT-{index % 286:03d}",
                level_id=f"VMC{index % 5 + 1}",
                facility_id="VMC",
                site_id="VMC",
                maintenance_interval_days=(90, 180, 365)[index % 3],
            )
        )
    return assets


class EnrichmentPlanTests(unittest.TestCase):
    def test_builds_exact_cohorts_and_target_history_rates(self):
        assets = _assets()
        plan = build_enrichment_plan(assets)

        stages = Counter(record.lifecycle_stage for record in plan.lifecycle)
        self.assertEqual(
            stages,
            {
                "Within Service Life": 501,
                "Recently Installed": 201,
                "Retrofit/Replacement": 301,
            },
        )
        self.assertEqual(len(plan.repairs), 271)
        completed = [record for record in plan.work_orders if record.status == "Completed"]
        active = [record for record in plan.work_orders if record.status != "Completed"]
        self.assertEqual(len(completed), 451)
        self.assertEqual(len(active), 50)
        self.assertEqual({record.asset_id for record in plan.inspections}, {a.asset_id for a in assets})

    def test_enforces_inspection_window_and_temporal_order(self):
        config = EnrichmentConfig()
        plan = build_enrichment_plan(_assets(100), config)
        lifecycle = {record.asset_id: record for record in plan.lifecycle}

        self.assertTrue(
            all(
                config.inspection_start <= record.inspection_date <= config.inspection_end
                and lifecycle[record.asset_id].commissioning_date <= record.inspection_date
                for record in plan.inspections
            )
        )
        self.assertTrue(
            all(record.commissioning_date < record.next_maintenance_date for record in plan.lifecycle)
        )
        self.assertTrue(all(record.repair_date <= config.reference_date for record in plan.repairs))
        self.assertTrue(all(record.request_date <= config.reference_date for record in plan.work_orders))

    def test_is_deterministic_and_changes_with_seed(self):
        assets = _assets(30)

        first = build_enrichment_plan(assets)
        second = build_enrichment_plan(list(reversed(assets)))
        changed = build_enrichment_plan(assets, replace(EnrichmentConfig(), seed=9001))

        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)

    def test_builds_consistent_asset_profile_metadata(self):
        assets = _assets(100)
        config = EnrichmentConfig()
        plan = build_enrichment_plan(assets, config)
        intervals = {asset.asset_id: asset.maintenance_interval_days for asset in assets}

        for record in plan.lifecycle:
            self.assertLess(record.purchase_date, record.commissioning_date)
            self.assertLess(record.purchase_cost, record.estimated_replacement_cost)
            self.assertGreater(record.purchase_cost, 0)
            self.assertGreater(record.warranty_expiration_date, record.commissioning_date)
            self.assertEqual(
                record.warranty_status,
                "Active" if record.warranty_expiration_date >= config.reference_date else "Expired",
            )
            self.assertEqual(record.maintenance_interval_days, intervals[record.asset_id])
            self.assertGreater(record.annual_maintenance_cost, 0)
            self.assertLess(record.annual_maintenance_cost, record.estimated_replacement_cost)
            self.assertTrue(record.vendor)
            self.assertIn(record.risk_score, range(101))
            expected_level = (
                "Critical" if record.risk_score >= 75
                else "High" if record.risk_score >= 50
                else "Moderate" if record.risk_score >= 25
                else "Low"
            )
            self.assertEqual(record.risk_level, expected_level)

    def test_offers_only_latest_inspections_to_narrator(self):
        class RecordingNarrator:
            def __init__(self):
                self.calls = []

            def narrate(self, record_type, facts, fallback):
                self.calls.append((record_type, facts))
                return fallback

        assets = _assets(20)
        narrator = RecordingNarrator()
        plan = build_enrichment_plan(assets, narrator=narrator)

        inspection_calls = [
            facts for record_type, facts in narrator.calls if record_type == "inspection"
        ]
        self.assertEqual(len(inspection_calls), len(assets))
        self.assertTrue(
            all("condition_rating" in facts and "repair_needed" in facts for facts in inspection_calls)
        )
        self.assertGreater(len(plan.inspections), len(inspection_calls))

    def test_rejects_invalid_window(self):
        with self.assertRaisesRegex(ValueError, "Inspection dates"):
            EnrichmentConfig(
                reference_date=date(2026, 9, 28),
                inspection_start=date(2026, 4, 1),
                inspection_end=date(2026, 3, 28),
            )


if __name__ == "__main__":
    unittest.main()