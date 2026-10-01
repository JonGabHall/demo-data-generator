from pathlib import Path
import unittest

from indoors_demo_generator.generation import (
    SourceUnitRecord,
    SourceFacilityRecord,
    allocate_exterior_assets,
    allocate_indoor_assets,
    allocate_indoor_assets_with_summary,
    deterministic_run_id,
)
from indoors_demo_generator.rules import load_facility_profile


PROFILE_PATH = Path(__file__).parents[1] / "profiles" / "hospital-v1.json"


class IndoorAllocationTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_facility_profile(PROFILE_PATH)

    def test_allocates_assets_only_to_explicitly_mapped_units(self):
        records, skipped = allocate_indoor_assets(
            self.profile,
            [
                SourceUnitRecord("{11111111-1111-1111-1111-111111111111}", "Exam Room", object()),
                SourceUnitRecord("{22222222-2222-2222-2222-222222222222}", "Unknown Space", object()),
            ],
            42,
        )

        self.assertTrue(records)
        self.assertEqual(skipped, 1)
        self.assertTrue(all(record.source_unit.use_type == "Exam Room" for record in records))

    def test_run_id_is_stable_for_the_same_profile_and_seed(self):
        self.assertEqual(deterministic_run_id(self.profile, 42), deterministic_run_id(self.profile, 42))
        self.assertNotEqual(deterministic_run_id(self.profile, 42), deterministic_run_id(self.profile, 43))

    def test_business_key_keeps_indoor_assets_stable_when_global_id_changes(self):
        first, _ = allocate_indoor_assets(
            self.profile,
            [
                SourceUnitRecord(
                    "{11111111-1111-1111-1111-111111111111}",
                    "Patient Room",
                    object(),
                    generation_key="PP|PP2|PP-U-0042",
                )
            ],
            42,
        )
        second, _ = allocate_indoor_assets(
            self.profile,
            [
                SourceUnitRecord(
                    "{22222222-2222-2222-2222-222222222222}",
                    "Patient Room",
                    object(),
                    generation_key="PP|PP2|PP-U-0042",
                )
            ],
            42,
        )

        self.assertEqual([record.asset for record in first], [record.asset for record in second])
        self.assertNotEqual(first[0].source_unit.global_id, second[0].source_unit.global_id)

    def test_blank_room_use_is_skipped(self):
        records, skipped = allocate_indoor_assets(
            self.profile,
            [SourceUnitRecord("{33333333-3333-3333-3333-333333333333}", "", None)],
            42,
        )

        self.assertEqual(records, [])
        self.assertEqual(skipped, 1)

    def test_missing_unit_geometry_is_skipped(self):
        records, skipped = allocate_indoor_assets(
            self.profile,
            [SourceUnitRecord("{33333333-3333-3333-3333-333333333333}", "Exam Room", None)],
            42,
        )

        self.assertEqual(records, [])
        self.assertEqual(skipped, 1)

    def test_skip_summary_groups_unmapped_values_and_other_reasons(self):
        records, summary = allocate_indoor_assets_with_summary(
            self.profile,
            [
                SourceUnitRecord("{1}", "Unknown Space", object()),
                SourceUnitRecord("{2}", "Unknown Space", object()),
                SourceUnitRecord("{3}", "", object()),
                SourceUnitRecord("{4}", "Exam Room", None),
            ],
            42,
        )

        self.assertEqual(records, [])
        self.assertEqual(summary.unmapped_use_type_counts, {"Unknown Space": 2})
        self.assertEqual(summary.blank_use_type_count, 1)
        self.assertEqual(summary.missing_geometry_count, 1)
        self.assertEqual(summary.skipped_unit_count, 4)

    def test_allocates_exterior_assets_for_each_valid_facility(self):
        records, skipped = allocate_exterior_assets(
            self.profile,
            [SourceFacilityRecord("{44444444-4444-4444-4444-444444444444}", object())],
            42,
        )

        self.assertTrue(records)
        self.assertEqual(skipped, 0)
        self.assertTrue(all(record.asset.placement_type in {"Exterior", "Attached"} for record in records))

    def test_business_key_keeps_exterior_assets_stable_when_global_id_changes(self):
        first, _ = allocate_exterior_assets(
            self.profile,
            [SourceFacilityRecord("{11111111-1111-1111-1111-111111111111}", object(), "PP")],
            42,
        )
        second, _ = allocate_exterior_assets(
            self.profile,
            [SourceFacilityRecord("{22222222-2222-2222-2222-222222222222}", object(), "PP")],
            42,
        )

        self.assertEqual([record.asset for record in first], [record.asset for record in second])
        self.assertNotEqual(first[0].source_facility.global_id, second[0].source_facility.global_id)


if __name__ == "__main__":
    unittest.main()