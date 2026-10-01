from importlib.machinery import SourceFileLoader
from pathlib import Path
import unittest


TOOLBOX_PATH = Path(__file__).parents[1] / "toolbox" / "indoors_demo_generator.pyt"
toolbox = SourceFileLoader("indoors_demo_generator_toolbox", str(TOOLBOX_PATH)).load_module()


class ToolboxPathTests(unittest.TestCase):
    def test_resolves_repository_from_standard_toolbox_path(self):
        toolbox_file = toolbox._toolbox_file_path(TOOLBOX_PATH)

        self.assertEqual(toolbox_file, TOOLBOX_PATH.resolve())
        self.assertEqual(toolbox_file.parent.parent, Path(__file__).parents[1].resolve())

    def test_resolves_repository_from_arcgis_tool_qualified_path(self):
        qualified_path = TOOLBOX_PATH / "InspectIndoorsGeodatabase"
        toolbox_file = toolbox._toolbox_file_path(qualified_path)

        self.assertEqual(toolbox_file, TOOLBOX_PATH.resolve())

    def test_rejects_a_geodatabase_nested_in_another_geodatabase(self):
        with self.assertRaisesRegex(ValueError, "cannot be inside another .gdb"):
            toolbox._validate_output_geodatabase_path(
                r"C:\Workspace\GDBs\Hospital_V1.gdb\Hospital_V1.gdb"
            )

    def test_accepts_a_new_geodatabase_directly_in_a_folder(self):
        toolbox._validate_output_geodatabase_path(r"C:\Workspace\GDBs\Hospital_V1.gdb")

    def test_combines_output_folder_and_geodatabase_name(self):
        output_gdb = toolbox._output_geodatabase_path(r"C:\Workspace\GDBs", "Hospital_V1.gdb")

        self.assertEqual(output_gdb, r"C:\Workspace\GDBs\Hospital_V1.gdb")

    def test_rejects_a_full_path_as_geodatabase_name(self):
        with self.assertRaisesRegex(ValueError, "file name"):
            toolbox._output_geodatabase_path(r"C:\Workspace\GDBs", r"C:\Workspace\GDBs\Hospital_V1.gdb")

    def test_clears_cached_project_modules_before_tool_execution(self):
        import indoors_demo_generator.preflight

        toolbox._reload_project_modules()

        self.assertNotIn("indoors_demo_generator.preflight", __import__("sys").modules)


if __name__ == "__main__":
    unittest.main()