from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "build_organizational_asset_catalog.py"
SCRIPT_SPEC = spec_from_file_location("catalog_builder", SCRIPT_PATH)
assert SCRIPT_SPEC is not None and SCRIPT_SPEC.loader is not None
catalog_builder = module_from_spec(SCRIPT_SPEC)
SCRIPT_SPEC.loader.exec_module(catalog_builder)


class _SearchCursor:
    def __init__(self, fields):
        self.fields = fields

    def __enter__(self):
        return iter([("VMC", json.dumps({"rings": [[[0, 0], [1, 0], [0, 0]]] }))])

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class _ArcPyStub:
    def __init__(self):
        self.requested_fields = None
        self.da = SimpleNamespace(SearchCursor=self._search_cursor)

    def ListFields(self, dataset):
        return [SimpleNamespace(name="FACILITY_ID", type="String", editable=True, required=False)]

    def _search_cursor(self, dataset, fields):
        self.requested_fields = fields
        return _SearchCursor(fields)

    def AsShape(self, geometry, esri_json):
        return ("detached", geometry, esri_json)


class CatalogBuilderTests(unittest.TestCase):
    def test_read_features_detaches_cursor_geometry_from_json(self):
        arcpy_stub = _ArcPyStub()

        with patch.object(catalog_builder, "arcpy", arcpy_stub):
            records = catalog_builder._read_features("Facilities")

        self.assertEqual(arcpy_stub.requested_fields, ["FACILITY_ID", "SHAPE@JSON"])
        self.assertEqual(records[0]["FACILITY_ID"], "VMC")
        self.assertEqual(records[0]["SHAPE@"][0], "detached")
        self.assertTrue(records[0]["SHAPE@"][2])


if __name__ == "__main__":
    unittest.main()
