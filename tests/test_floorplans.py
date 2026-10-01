from pathlib import Path
import unittest

from indoors_demo_generator.floorplans import create_facility_floor_plan, unit_program_attributes
from indoors_demo_generator.rules import generate_assets, load_facility_profile


PROFILE_ROOT = Path(__file__).parents[1] / "profiles"


class FloorPlanTests(unittest.TestCase):
    def test_hospital_plan_is_deterministic_and_has_a_roof(self):
        first = create_facility_floor_plan("PP", "Point Place", "hospital")
        second = create_facility_floor_plan("PP", "Point Place", "hospital")

        self.assertEqual(first, second)
        self.assertEqual(len(first.levels), 5)
        self.assertEqual(first.levels[-1].short_name, "Roof")
        self.assertEqual(first.levels[-1].units, ())
        self.assertGreaterEqual(len(first.units), 100)

    def test_facilities_receive_distinct_dimensions_or_rotation(self):
        plans = [
            create_facility_floor_plan(code, name, "hospital")
            for code, name in (
                ("PP", "Point Place"),
                ("LL", "Line Lake"),
                ("NN", "Node North"),
                ("RC", "Rohdran Cove"),
            )
        ]

        signatures = {
            (plan.footprint.width, plan.footprint.height, plan.rotation_degrees)
            for plan in plans
        }
        self.assertEqual(len(signatures), len(plans))
        self.assertEqual(
            {plan.facility_id: len(plan.units) for plan in plans},
            {"PP": 114, "LL": 114, "NN": 120, "RC": 128},
        )

    def test_rooms_are_unique_contained_and_non_overlapping(self):
        plan = create_facility_floor_plan("AHQ", "Admin HQ", "office")

        self.assertEqual(len(plan.levels), 7)
        self.assertGreaterEqual(len(plan.units), 200)
        self.assertEqual(len({unit.unit_id for unit in plan.units}), len(plan.units))
        for level in plan.levels:
            for unit in level.units:
                self.assertTrue(level.rectangle.contains(unit.rectangle))
            for index, unit in enumerate(level.units):
                self.assertFalse(
                    any(unit.rectangle.overlaps(other.rectangle) for other in level.units[index + 1 :])
                )

    def test_generated_room_uses_are_covered_by_profiles(self):
        hospital = create_facility_floor_plan("PP", "Point Place", "hospital")
        office = create_facility_floor_plan("AHQ", "Admin HQ", "office")
        hospital_profile = load_facility_profile(PROFILE_ROOT / "hospital-v1.json")
        office_profile = load_facility_profile(PROFILE_ROOT / "government-office-v1.json")

        self.assertTrue(
            all(hospital_profile.resolve_room_use(unit.use_type) for unit in hospital.units)
        )
        self.assertTrue(all(office_profile.resolve_room_use(unit.use_type) for unit in office.units))

    def test_room_names_and_ids_are_facility_scoped(self):
        plan = create_facility_floor_plan("NN", "Node North", "hospital")

        self.assertTrue(all(unit.unit_id.startswith("NN-U-") for unit in plan.units))
        self.assertTrue(all(unit.name.startswith(("B ", "L1 ", "L2 ", "L3 ")) for unit in plan.units))
        self.assertTrue(any(unit.use_type == "HALLWAY" for unit in plan.units))
        self.assertTrue(any(unit.use_type == "OPERATING_ROOM" for unit in plan.units))

    def test_asset_ids_are_unique_across_generated_facilities(self):
        specifications = (
            ("PP", "Point Place", "hospital", "hospital-v1.json", 3142),
            ("LL", "Line Lake", "hospital", "hospital-v1.json", 3143),
            ("NN", "Node North", "hospital", "hospital-v1.json", 3144),
            ("RC", "Rohdran Cove", "hospital", "hospital-v1.json", 3145),
            ("AHQ", "Admin HQ", "office", "government-office-v1.json", 3241),
        )
        asset_ids = []
        level_ids = []
        unit_ids = []
        for code, name, kind, profile_name, seed in specifications:
            plan = create_facility_floor_plan(code, name, kind)
            profile = load_facility_profile(PROFILE_ROOT / profile_name)
            level_ids.extend(level.level_id for level in plan.levels)
            unit_ids.extend(unit.unit_id for unit in plan.units)
            facility_asset_ids = [
                asset.asset_id
                for unit in plan.units
                for asset in generate_assets(
                    profile,
                    f"{code}|{unit.level_id}|{unit.unit_id}",
                    unit.use_type,
                    seed,
                )
            ]
            self.assertGreater(len(facility_asset_ids), len(plan.units))
            asset_ids.extend(facility_asset_ids)

        self.assertEqual(len(level_ids), len(set(level_ids)))
        self.assertEqual(len(unit_ids), len(set(unit_ids)))
        self.assertEqual(len(asset_ids), len(set(asset_ids)))

    def test_room_amenities_follow_the_generated_program(self):
        office = unit_program_attributes("OFFICE")
        meeting = unit_program_attributes("MEETING_ROOM")
        exam = unit_program_attributes("EXAM_ROOM")
        hallway = unit_program_attributes("HALLWAY")

        self.assertEqual(office["MacDockingStation"], 1)
        self.assertEqual(office["DualMonitor"], 1)
        self.assertEqual(meeting["VideoConferencing"], 1)
        self.assertEqual(meeting["Projector"], 1)
        self.assertEqual(exam["Whiteboard"], 1)
        self.assertEqual(hallway["TrashCan"], 0)
        self.assertTrue(
            all(
                hallway[field] == 0
                for field in (
                    "MacDockingStation",
                    "DualMonitor",
                    "Locker",
                    "SitStandDesk",
                    "Whiteboard",
                    "VideoConferencing",
                    "WaterCooler",
                    "Projector",
                    "TrashCan",
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
