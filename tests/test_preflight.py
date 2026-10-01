from pathlib import Path
import unittest

from indoors_demo_generator.preflight import (
    PreflightError,
    inspect_indoors_source,
    validate_indoors_source,
    validate_inspection_report,
    write_inspection_report,
)
from indoors_demo_generator.rules import load_facility_profile


class Field:
    def __init__(self, name, field_type):
        self.name = name
        self.type = field_type


class FakeManagement:
    def GetCount(self, _path):
        return ["3"]


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return iter(self._rows)

    def __exit__(self, _type, _value, _traceback):
        return False


class FakeArcPy:
    def __init__(self, feature_classes, fields, use_types=(), exists=True):
        self._feature_classes = feature_classes
        self._fields = fields
        self._exists = exists
        self._use_types = use_types
        self.da = self
        self.management = FakeManagement()

    def Exists(self, _workspace):
        return self._exists

    def Walk(self, _workspace, datatype):
        if datatype == "FeatureClass":
            yield "C:\\demo.gdb\\Indoor", [], self._feature_classes

    def ListFields(self, _path):
        if isinstance(self._fields, dict):
            return self._fields[Path(_path).name.lower()]
        return self._fields

    def SearchCursor(self, _path, _fields):
        return FakeCursor([(use_type,) for use_type in self._use_types])

    def Describe(self, _path):
        return type("Description", (), {"spatialReference": type("SpatialReference", (), {"name": "WGS 1984"})()})()

    def assertEqual(self, first, second):
        if first != second:
            raise AssertionError(f"{first!r} != {second!r}")


class PreflightTests(unittest.TestCase):
    @staticmethod
    def valid_fields(include_unit_global_id=True):
        unit_fields = [Field("UNIT_ID", "String"), Field("LEVEL_ID", "String"), Field("USE_TYPE", "String")]
        if include_unit_global_id:
            unit_fields.append(Field("GlobalID", "GlobalID"))
        return {
            "sites": [Field("SITE_ID", "String")],
            "facilities": [
                Field("FACILITY_ID", "String"),
                Field("SITE_ID", "String"),
                Field("GlobalID", "GlobalID"),
            ],
            "levels": [Field("LEVEL_ID", "String"), Field("FACILITY_ID", "String")],
            "units": unit_fields,
        }

    def test_valid_indoors_source_is_discovered_case_insensitively(self):
        arcpy = FakeArcPy(
            ["Sites", "FACILITIES", "levels", "Units"],
            self.valid_fields(),
        )

        source = validate_indoors_source(arcpy, "C:\\demo.gdb")

        self.assertEqual(source.unit_use_field, "USE_TYPE")
        self.assertEqual(source.unit_global_id_field, "GlobalID")
        self.assertTrue(source.feature_classes["units"].endswith("Units"))

    def test_missing_units_global_id_fails_safely(self):
        arcpy = FakeArcPy(
            ["Sites", "Facilities", "Levels", "Units"],
            self.valid_fields(include_unit_global_id=False),
        )

        with self.assertRaisesRegex(PreflightError, "GlobalID"):
            validate_indoors_source(arcpy, "C:\\demo.gdb")

    def test_missing_sites_fails_safely(self):
        arcpy = FakeArcPy(
            ["Facilities", "Levels", "Units"],
            self.valid_fields(),
        )

        with self.assertRaisesRegex(PreflightError, "Sites"):
            validate_indoors_source(arcpy, "C:\\demo.gdb")

    def test_missing_parent_key_fails_safely(self):
        fields = self.valid_fields()
        fields["levels"] = [Field("LEVEL_ID", "String")]
        arcpy = FakeArcPy(
            ["Sites", "Facilities", "Levels", "Units"],
            fields,
        )

        with self.assertRaisesRegex(PreflightError, "FACILITY_ID"):
            validate_indoors_source(arcpy, "C:\\demo.gdb")

    def test_non_geodatabase_input_fails_safely(self):
        arcpy = FakeArcPy([], [])

        with self.assertRaisesRegex(PreflightError, "file geodatabase"):
            validate_indoors_source(arcpy, "C:\\demo")

    def test_inspection_reports_profile_coverage_without_writing_source(self):
        arcpy = FakeArcPy(
            ["Sites", "Facilities", "Levels", "Units"],
            self.valid_fields(),
            ["Exam Room", "A/C Duct Shaft", "Unmapped Space"],
        )
        profile = load_facility_profile(Path(__file__).parents[1] / "profiles" / "hospital-v1.json")

        report = inspect_indoors_source(arcpy, "C:\\demo.gdb", profile)

        inspection = report["inspection"]
        self.assertEqual(inspection["summary"]["unit_count"], 3)
        self.assertEqual(inspection["summary"]["mapped_use_type_count"], 2)
        self.assertEqual(inspection["summary"]["unmapped_use_type_count"], 1)
        self.assertEqual(inspection["summary"]["spatial_reference"], "WGS 1984")
        self.assertEqual(report["technical_details"]["datasets"]["units"]["global_id_fields"], ["GlobalID"])
        self.assertEqual(inspection["room_use_summary"]["unmapped"], ["Unmapped Space"])

    def test_matching_inspection_report_can_be_used_for_generation(self):
        arcpy = FakeArcPy(
            ["Sites", "Facilities", "Levels", "Units"],
            self.valid_fields(),
            ["Exam Room"],
        )
        profile = load_facility_profile(Path(__file__).parents[1] / "profiles" / "hospital-v1.json")
        report = inspect_indoors_source(arcpy, "C:\\demo.gdb", profile, "Hospital")
        report_path = Path(self._testMethodName + ".json")
        self.addCleanup(report_path.unlink, missing_ok=True)
        write_inspection_report(report, str(report_path))

        inspection = validate_inspection_report(str(report_path), "C:\\demo.gdb", "Hospital", profile)

        self.assertEqual(inspection["summary"]["mapped_use_type_count"], 1)

    def test_inspection_report_rejects_a_different_source(self):
        arcpy = FakeArcPy(
            ["Sites", "Facilities", "Levels", "Units"],
            self.valid_fields(),
        )
        profile = load_facility_profile(Path(__file__).parents[1] / "profiles" / "hospital-v1.json")
        report_path = Path(self._testMethodName + ".json")
        self.addCleanup(report_path.unlink, missing_ok=True)
        write_inspection_report(
            inspect_indoors_source(arcpy, "C:\\first.gdb", profile, "Hospital"), str(report_path)
        )

        with self.assertRaisesRegex(PreflightError, "different source"):
            validate_inspection_report(str(report_path), "C:\\second.gdb", "Hospital", profile)



if __name__ == "__main__":
    unittest.main()