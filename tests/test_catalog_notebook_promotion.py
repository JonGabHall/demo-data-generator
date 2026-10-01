import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest


REPOSITORY = Path(__file__).parents[1]
NOTEBOOK_PATH = REPOSITORY / "scripts" / "run_llm_asset_enrichment_in_arcgis_pro.ipynb"


class _ManagementStub:
    @staticmethod
    def ClearWorkspaceCache():
        return None

    @staticmethod
    def Delete(path):
        shutil.rmtree(path)


class _ArcPyStub:
    class ExecuteError(Exception):
        pass

    management = _ManagementStub()

    @staticmethod
    def Exists(path):
        return Path(path).exists()


class _CatalogBuilderStub:
    def __init__(self, root):
        self.SOURCE_GDB = root / "Vertex_Assets.gdb"
        self.VERTEX_ENRICHED_GDB = root / "Vertex_Assets_Enriched.gdb"
        self.OUTPUT_GDB = root / "Organizational_Asset_Catalog.gdb"
        self.MANIFEST_PATH = root / "Organizational_Asset_Catalog_manifest.json"
        self.LOG_PATH = root / "Organizational_Asset_Catalog_build.log"

    @staticmethod
    def validate_indoors_source(arcpy, workspace):
        return None

    @staticmethod
    def _schema(workspace):
        root = Path(workspace)
        return SimpleNamespace(
            indoor_asset_locations=root / "AssetManagement" / "IndoorAssetLocation",
            exterior_asset_points=root / "AssetManagement" / "ExteriorAssetPoints",
            asset_lifecycle=root / "AssetLifecycle",
            inspections=root / "AssetInspection",
            repairs=root / "AssetRepair",
            work_orders=root / "AssetWorkOrder",
        )

    @staticmethod
    def main(narrator):
        raise AssertionError("A validated staged catalog should be reused.")


def _create_complete_catalog(path):
    required = (
        path / "Indoors" / "Sites",
        path / "Indoors" / "Facilities",
        path / "Indoors" / "Levels",
        path / "Indoors" / "Units",
        path / "AssetManagement" / "IndoorAssetLocation",
        path / "AssetManagement" / "ExteriorAssetPoints",
        path / "AssetLifecycle",
        path / "AssetInspection",
        path / "AssetRepair",
        path / "AssetWorkOrder",
    )
    for dataset in required:
        dataset.mkdir(parents=True, exist_ok=True)


def _run_catalog_function():
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    return "".join(
        next(
            cell["source"]
            for cell in notebook["cells"]
            if cell["cell_type"] == "code" and "def run_catalog():" in "".join(cell["source"])
        )
    )


class CatalogNotebookPromotionTests(unittest.TestCase):
    def test_notebook_defaults_to_existing_catalog_retrofit(self):
        notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
        code_cells = [
            "".join(cell["source"])
            for cell in notebook["cells"]
            if cell["cell_type"] == "code"
        ]
        all_code = "\n".join(code_cells)

        self.assertIn("RUN_CATALOG = False", all_code)
        self.assertIn("RUN_METADATA_RETROFIT = True", all_code)
        self.assertIn("def run_metadata_retrofit():", all_code)
        self.assertIn("catalog_builder.retrofit_asset_metadata(", all_code)
        self.assertIn("if generation_requested and not LLM_READY:", all_code)

    def test_recovers_incomplete_promotion_without_rebuilding(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            builder = _CatalogBuilderStub(root)
            arcpy = _ArcPyStub()
            builder.SOURCE_GDB.mkdir()
            _create_complete_catalog(builder.VERTEX_ENRICHED_GDB)

            output = builder.OUTPUT_GDB
            build_output = root / "Organizational_Asset_Catalog_building.gdb"
            backup_output = root / "Organizational_Asset_Catalog_previous.gdb"
            output.mkdir()
            (output / "partial-copy").write_text("incomplete", encoding="utf-8")
            _create_complete_catalog(build_output)
            _create_complete_catalog(backup_output)
            (build_output / "promoted-marker").write_text("new", encoding="utf-8")

            validation = {
                "sites": 6,
                "facilities": 6,
                "levels": 32,
                "units": 1025,
                "indoor_assets": 4852,
                "exterior_assets": 72,
                "lifecycle_assets": 4852,
                "orphan_references": 0,
                "preserved_vertex_assets": 1003,
            }
            build_manifest = root / "Organizational_Asset_Catalog_manifest_building.json"
            build_manifest.write_text(json.dumps({"validation": validation}), encoding="utf-8")
            builder.MANIFEST_PATH.write_text(json.dumps({"old": True}), encoding="utf-8")
            build_log = root / "Organizational_Asset_Catalog_build_building.log"
            build_log.write_text("new log", encoding="utf-8")
            builder.LOG_PATH.write_text("old log", encoding="utf-8")

            namespace = {
                "arcpy": arcpy,
                "json": json,
                "Path": Path,
                "catalog_builder": builder,
                "LocalJsonNarrator": object,
                "RUN_CATALOG": True,
                "ALLOW_OVERWRITE": True,
                "SOURCE_GDB": builder.SOURCE_GDB,
                "VERTEX_OUTPUT": builder.VERTEX_ENRICHED_GDB,
                "CATALOG_OUTPUT": builder.OUTPUT_GDB,
                "LLM_ENDPOINT": "unused",
                "LLM_MODEL": "unused",
                "LLM_TIMEOUT_SECONDS": 1,
                "CATALOG_LLM_MAX_REQUESTS": 0,
            }
            exec(compile(_run_catalog_function(), str(NOTEBOOK_PATH), "exec"), namespace)

            result = namespace["run_catalog"]()

            self.assertEqual(result["validation"], validation)
            self.assertTrue((output / "promoted-marker").exists())
            self.assertFalse((output / "partial-copy").exists())
            self.assertFalse(build_output.exists())
            self.assertFalse(backup_output.exists())
            self.assertFalse((root / "Organizational_Asset_Catalog_failed_promotion.gdb").exists())
            self.assertEqual(
                json.loads(builder.MANIFEST_PATH.read_text(encoding="utf-8"))["validation"],
                validation,
            )
            self.assertEqual(builder.LOG_PATH.read_text(encoding="utf-8"), "new log")


if __name__ == "__main__":
    unittest.main()
