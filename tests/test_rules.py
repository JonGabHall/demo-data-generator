from datetime import date
from pathlib import Path
import unittest

from indoors_demo_generator.rules import UnmappedRoomUseError, generate_assets, load_facility_profile


PROFILE_PATH = Path(__file__).parents[1] / "profiles" / "hospital-v1.json"
VERTEX_PROFILE_PATH = Path(__file__).parents[1] / "profiles" / "vertex-v1.json"
UNIT_GLOBAL_ID = "{77E57187-59B0-49A0-97D1-ED47C49D1D04}"


class HospitalRuleTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_facility_profile(PROFILE_PATH)

    def test_same_seed_produces_same_assets(self):
        first = generate_assets(self.profile, UNIT_GLOBAL_ID, "OPERATING_ROOM", 42)
        second = generate_assets(self.profile, UNIT_GLOBAL_ID, "OPERATING_ROOM", 42)
        self.assertEqual(first, second)

    def test_generated_operating_room_assets_are_consistent(self):
        assets = generate_assets(self.profile, UNIT_GLOBAL_ID, "OPERATING_ROOM", 42)
        self.assertTrue(assets)
        self.assertTrue(all(asset.room_use == "OPERATING_ROOM" for asset in assets))
        self.assertTrue(all(asset.unit_global_id == UNIT_GLOBAL_ID for asset in assets))
        self.assertTrue(all(asset.commissioning_date <= date(2026, 1, 1) for asset in assets))
        self.assertTrue(all(asset.next_maintenance_date > asset.commissioning_date for asset in assets))
        self.assertTrue(all("Electrical" in asset.system_dependencies for asset in assets))

    def test_hallway_profile_includes_life_safety_and_infrastructure_assets(self):
        assets = generate_assets(self.profile, UNIT_GLOBAL_ID, "HALLWAY", 42)

        self.assertTrue(any(asset.asset_class == "Fire and Life Safety" for asset in assets))
        self.assertTrue(any(asset.asset_class == "Electrical Equipment" for asset in assets))
        self.assertTrue(any(asset.template_id == "SECURITY_CAMERA" for asset in assets))

    def test_unsupported_room_use_fails_without_fallback(self):
        with self.assertRaisesRegex(UnmappedRoomUseError, "Unmapped facility room use"):
            generate_assets(self.profile, UNIT_GLOBAL_ID, "UNKNOWN_USE", 42)

    def test_profile_aliases_normalize_source_unit_use_types(self):
        assets = generate_assets(self.profile, UNIT_GLOBAL_ID, "patient bedroom", 42)

        self.assertTrue(assets)
        self.assertTrue(all(asset.room_use == "PATIENT_ROOM" for asset in assets))

    def test_source_synonyms_resolve_to_existing_room_use_templates(self):
        expected_room_uses = {
            "Stairway": "STAIRWELL",
            "Entry Lobby": "RECEPTION",
            "Janitor Closet": "JANITORIAL_ROOM",
            "Telecommunications Room": "TELECOM_ROOM",
        }

        resolved = {
            source_use: self.profile.resolve_room_use(source_use)
            for source_use in expected_room_uses
        }

        self.assertEqual(resolved, expected_room_uses)

    def test_source_medical_indoor_unit_types_resolve_to_reviewed_profiles(self):
        exam_assets = generate_assets(self.profile, UNIT_GLOBAL_ID, "Exam Room", 42)
        shaft_assets = generate_assets(self.profile, UNIT_GLOBAL_ID, "A/C Duct Shaft", 42)

        self.assertTrue(any(asset.template_id == "EXAM_TABLE" for asset in exam_assets))
        self.assertTrue(any(asset.template_id == "FIRE_DAMPER" for asset in shaft_assets))

    def test_hospital_exterior_profile_declares_placement_types(self):
        assets = generate_assets(self.profile, UNIT_GLOBAL_ID, "BUILDING_EXTERIOR", 42)

        self.assertTrue(assets)
        self.assertTrue(all(asset.placement_type in {"Exterior", "Attached"} for asset in assets))


class AdditionalFacilityProfileTests(unittest.TestCase):
    def test_vertex_profile_covers_every_inspected_source_use_type(self):
        profile = load_facility_profile(VERTEX_PROFILE_PATH)
        source_use_types = (
            "A/C Duct Shaft", "Admission", "Billing & Finance", "Break Room", "Cardiology",
            "Copy Room", "Electrical Room", "Elevator", "Endoscopy", "Entry Lobby", "Environmental Services",
            "Exam Room", "Facilities & Engineering", "Fire Closet", "Gym", "Hallway",
            "Human Resources", "Infusion", "Janitor Closet", "Kitchen", "Laboratory",
            "Locker Room/Shower", "Lounge", "Mail Room", "Mechanical Room", "Medical Records",
            "Meeting Room", "Mother's Room", "Nurse Station", "Nutrition", "Office",
            "Office - Doctor", "Open to Below", "Operating Room", "Outdoor Space", "Outpatient",
            "Parking Garage", "Pediatrics", "Pharmacy", "Phone Room", "Post-Op Room", "Postpartum",
            "Pre-Op Room", "Psychiatric", "Radiology", "Rehabilitation", "Restroom", "Stairway",
            "Storage Room", "Telecommunications Room", "Training Room",
        )

        unresolved = [
            source_use for source_use in source_use_types
            if not profile.resolve_room_use(source_use)
        ]

        self.assertEqual(unresolved, [])

    def test_vertex_profile_uses_generic_clinical_assets_for_clinical_spaces(self):
        profile = load_facility_profile(VERTEX_PROFILE_PATH)
        assets = generate_assets(profile, UNIT_GLOBAL_ID, "Pre-Op Room", 42)

        self.assertTrue(assets)
        self.assertTrue(all(asset.asset_class in {"Clinical Equipment", "Plumbing Equipment"} for asset in assets))

    def test_government_office_profile_generates_controlled_assets(self):
        profile = load_facility_profile(Path(__file__).parents[1] / "profiles" / "government-office-v1.json")

        assets = generate_assets(profile, UNIT_GLOBAL_ID, "SECURE_RECORDS_ROOM", 42)

        self.assertTrue(assets)
        self.assertTrue(all(asset.asset_class in {"Security Equipment", "IT Equipment"} for asset in assets))
        self.assertTrue(any("IT Network" in asset.system_dependencies for asset in assets))

    def test_government_profile_generates_exterior_assets(self):
        profile = load_facility_profile(Path(__file__).parents[1] / "profiles" / "government-office-v1.json")

        assets = generate_assets(profile, UNIT_GLOBAL_ID, "BUILDING_EXTERIOR", 42)

        self.assertTrue(assets)
        self.assertTrue(all("Electrical" in asset.system_dependencies for asset in assets))
        self.assertTrue(any(asset.template_id == "EXTERIOR_LIGHT_FIXTURE" for asset in assets))

    def test_government_profile_includes_building_utility_assets(self):
        profile = load_facility_profile(Path(__file__).parents[1] / "profiles" / "government-office-v1.json")

        assets = generate_assets(profile, UNIT_GLOBAL_ID, "ELECTRICAL_ROOM", 42)

        self.assertTrue(any(asset.template_id == "SWITCHGEAR" for asset in assets))
        self.assertTrue(all(asset.asset_class == "Electrical Equipment" for asset in assets))


if __name__ == "__main__":
    unittest.main()