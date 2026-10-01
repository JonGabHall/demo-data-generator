"""ArcGIS Pro entry point for the Indoors Demo Data Generator."""

import importlib
import sys
from pathlib import Path


def _toolbox_file_path(file_path: str | Path) -> Path:
    path = Path(file_path).resolve()
    while path.suffix.lower() != ".pyt":
        if path.parent == path:
            raise RuntimeError(f"Unable to locate the Python toolbox from {file_path}")
        path = path.parent
    return path


TOOLBOX_FILE = _toolbox_file_path(__file__)
REPOSITORY_DIRECTORY = TOOLBOX_FILE.parent.parent
SOURCE_DIRECTORY = REPOSITORY_DIRECTORY / "src"
PROFILE_PATHS = {
    "Hospital": REPOSITORY_DIRECTORY / "profiles" / "hospital-v1.json",
    "Vertex": REPOSITORY_DIRECTORY / "profiles" / "vertex-v1.json",
    "Government Office": REPOSITORY_DIRECTORY / "profiles" / "government-office-v1.json",
}


def _enable_project_imports() -> None:
    source_directory = str(SOURCE_DIRECTORY)
    if source_directory in sys.path:
        sys.path.remove(source_directory)
    sys.path.insert(0, source_directory)
    importlib.invalidate_caches()


def _reload_project_modules() -> None:
    """Ensure a toolbox reload uses the current project source files."""
    for module_name in tuple(sys.modules):
        if module_name == "indoors_demo_generator" or module_name.startswith(
            "indoors_demo_generator."
        ):
            del sys.modules[module_name]


_enable_project_imports()


def _validate_output_geodatabase_path(output_gdb: str) -> None:
    path = Path(output_gdb)
    if path.suffix.lower() != ".gdb":
        raise ValueError("Output Geodatabase must be a new file geodatabase path ending in .gdb.")
    if any(parent.suffix.lower() == ".gdb" for parent in path.parents):
        raise ValueError(
            "Output Geodatabase cannot be inside another .gdb. Select a folder and enter a path such as "
            r"C:\Workspace\GDBs\Hospital_V1.gdb."
        )


def _output_geodatabase_path(output_folder: str, output_name: str) -> str:
    if not output_name or output_name != Path(output_name).name:
        raise ValueError("Output Geodatabase Name must be a file name, not a folder or full path.")
    return str(Path(output_folder) / output_name)


class Toolbox:
    def __init__(self):
        self.label = "Indoors Demo Data Generator"
        self.alias = "indoorsdemogenerator"
        self.tools = [InspectIndoorsGeodatabase, GenerateDemoAssets, IntegrateGeneratedAssets]


class InspectIndoorsGeodatabase:
    def __init__(self):
        self.label = "Inspect Indoors Geodatabase"
        self.description = "Creates a read-only compatibility and room-use mapping report."
        self.canRunInBackground = False

    def getParameterInfo(self):
        import arcpy

        source_gdb = arcpy.Parameter(
            displayName="Source Indoors Geodatabase",
            name="source_geodatabase",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input",
        )
        profile_name = arcpy.Parameter(
            displayName="Facility Profile",
            name="profile_json",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
        )
        profile_name.filter.type = "ValueList"
        profile_name.filter.list = list(PROFILE_PATHS)
        report_path = arcpy.Parameter(
            displayName="Inspection Report JSON",
            name="inspection_report",
            datatype="DEFile",
            parameterType="Required",
            direction="Output",
        )
        report_path.filter.list = ["json"]
        return [source_gdb, profile_name, report_path]

    def execute(self, parameters, messages):
        import arcpy
        _enable_project_imports()
        _reload_project_modules()
        from indoors_demo_generator.preflight import (
            PreflightError,
            inspect_indoors_source,
            write_inspection_report,
        )
        from indoors_demo_generator.rules import load_facility_profile

        source_gdb = parameters[0].valueAsText
        profile_name = parameters[1].valueAsText
        report_path = parameters[2].valueAsText
        try:
            if profile_name and profile_name not in PROFILE_PATHS:
                raise PreflightError(f"Unknown facility profile: {profile_name}")
            profile = load_facility_profile(PROFILE_PATHS[profile_name]) if profile_name else None
            report = inspect_indoors_source(arcpy, source_gdb, profile, profile_name)
            write_inspection_report(report, report_path)
        except (OSError, PreflightError, ValueError) as error:
            messages.addErrorMessage(str(error))
            raise arcpy.ExecuteError(str(error)) from error

        messages.addMessage(
            f"Inspected {report['inspection']['summary']['unit_count']} Units. "
            f"Unmapped USE_TYPE values: {report['inspection']['summary']['unmapped_use_type_count']}."
        )


class GenerateDemoAssets:
    def __init__(self):
        self.label = "Generate Demo Assets"
        self.description = "Creates deterministic synthetic assets in a copied Indoors geodatabase."
        self.canRunInBackground = False

    def getParameterInfo(self):
        import arcpy

        source_gdb = arcpy.Parameter(
            displayName="Source Indoors Geodatabase",
            name="source_geodatabase",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input",
        )
        profile_name = arcpy.Parameter(
            displayName="Facility Profile",
            name="profile_name",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
        )
        profile_name.filter.type = "ValueList"
        profile_name.filter.list = list(PROFILE_PATHS)
        profile_name.value = "Hospital"
        inspection_report = arcpy.Parameter(
            displayName="Inspection Report JSON",
            name="inspection_report",
            datatype="DEFile",
            parameterType="Optional",
            direction="Input",
        )
        inspection_report.filter.list = ["json"]
        output_folder = arcpy.Parameter(
            displayName="Output Folder",
            name="output_folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input",
        )
        output_name = arcpy.Parameter(
            displayName="Output Geodatabase Name",
            name="output_geodatabase_name",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
        )
        output_name.value = "DemoAssets_V1.gdb"
        seed = arcpy.Parameter(
            displayName="Random Seed",
            name="seed",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input",
        )
        seed.filter.type = "Range"
        seed.filter.list = [0, 2147483647]
        seed.value = 42
        return [source_gdb, profile_name, inspection_report, output_folder, output_name, seed]

    def execute(self, parameters, messages):
        import arcpy
        _enable_project_imports()
        _reload_project_modules()
        from indoors_demo_generator.generation import generate_indoor_asset_records
        from indoors_demo_generator.preflight import (
            PreflightError,
            validate_indoors_source,
            validate_inspection_report,
        )
        from indoors_demo_generator.rules import load_facility_profile
        from indoors_demo_generator.schema import create_asset_management_schema

        source_gdb = parameters[0].valueAsText
        profile_name = parameters[1].valueAsText
        inspection_report = parameters[2].valueAsText
        output_folder = parameters[3].valueAsText
        output_name = parameters[4].valueAsText
        seed = int(parameters[5].value or 42)
        output_created = False
        try:
            if profile_name not in PROFILE_PATHS:
                raise PreflightError(f"Unknown facility profile: {profile_name}")
            profile = load_facility_profile(PROFILE_PATHS[profile_name])
            if inspection_report:
                inspection = validate_inspection_report(
                    inspection_report, source_gdb, profile_name, profile
                )
                messages.addMessage(
                    "Using matching inspection report: "
                    f"{inspection['summary']['mapped_use_type_count']} mapped and "
                    f"{inspection['summary']['unmapped_use_type_count']} unmapped USE_TYPE values."
                )
            source = validate_indoors_source(arcpy, source_gdb)
            output_gdb = _output_geodatabase_path(output_folder, output_name)
            _validate_output_geodatabase_path(output_gdb)
            if arcpy.Exists(output_gdb):
                raise PreflightError(f"Output geodatabase already exists: {output_gdb}")
            arcpy.management.Copy(source_gdb, output_gdb)
            output_created = True
            output_source = validate_indoors_source(arcpy, output_gdb)
            schema = create_asset_management_schema(arcpy, output_gdb, output_source)
            result = generate_indoor_asset_records(arcpy, output_source, schema, profile, seed)
        except Exception as error:
            if output_created and arcpy.Exists(output_gdb):
                try:
                    arcpy.management.Delete(output_gdb)
                except Exception as cleanup_error:
                    messages.addWarningMessage(
                        f"Generation failed and could not remove {output_gdb}: {cleanup_error}"
                    )
            messages.addErrorMessage(str(error))
            raise arcpy.ExecuteError(str(error)) from error

        messages.addMessage(
            f"Created {result.indoor_asset_count} indoor and {result.exterior_asset_count} "
            f"exterior or attached deterministic {profile_name} assets in {output_gdb} using seed {seed}."
        )
        if result.skipped_unit_count:
            messages.addWarningMessage(
                f"Skipped {result.skipped_unit_count} Units; see the following reason summary."
            )
            skip_summary = result.unit_skip_summary
            if skip_summary.missing_geometry_count:
                messages.addWarningMessage(
                    f"Skipped {skip_summary.missing_geometry_count} Units with no geometry."
                )
            if skip_summary.blank_use_type_count:
                messages.addWarningMessage(
                    f"Skipped {skip_summary.blank_use_type_count} Units with blank USE_TYPE values."
                )
            if skip_summary.unmapped_use_type_counts:
                unmapped = "; ".join(
                    f"{use_type!r}: {count}"
                    for use_type, count in sorted(skip_summary.unmapped_use_type_counts.items())
                )
                messages.addWarningMessage(
                    "Skipped Units with unmapped USE_TYPE values (value: Unit count): " + unmapped
                )
        if result.skipped_facility_count:
            messages.addWarningMessage(
                f"Skipped {result.skipped_facility_count} Facilities without usable geometry."
            )


class IntegrateGeneratedAssets:
    def __init__(self):
        self.label = "Integrate Generated Assets"
        self.description = (
            "Creates a validated integrated copy of an Indoors geodatabase; neither input is modified."
        )
        self.canRunInBackground = False

    def getParameterInfo(self):
        import arcpy

        generated_gdb = arcpy.Parameter(
            displayName="Generated Demo Geodatabase",
            name="generated_geodatabase",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input",
        )
        target_gdb = arcpy.Parameter(
            displayName="Target Indoors Geodatabase",
            name="target_geodatabase",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input",
        )
        output_folder = arcpy.Parameter(
            displayName="Output Folder",
            name="output_folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input",
        )
        output_name = arcpy.Parameter(
            displayName="Integrated Geodatabase Name",
            name="integrated_geodatabase_name",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
        )
        output_name.value = "IntegratedDemoAssets.gdb"
        return [generated_gdb, target_gdb, output_folder, output_name]

    def execute(self, parameters, messages):
        import arcpy

        _enable_project_imports()
        _reload_project_modules()
        from indoors_demo_generator.integration import integrate_generated_assets

        generated_gdb = parameters[0].valueAsText
        target_gdb = parameters[1].valueAsText
        output_folder = parameters[2].valueAsText
        output_name = parameters[3].valueAsText
        try:
            output_gdb = _output_geodatabase_path(output_folder, output_name)
            _validate_output_geodatabase_path(output_gdb)
            result = integrate_generated_assets(arcpy, target_gdb, generated_gdb, output_gdb)
        except Exception as error:
            messages.addErrorMessage(str(error))
            raise arcpy.ExecuteError(str(error)) from error

        messages.addMessage(
            f"Created {result.output_geodatabase} with {result.indoor_asset_count} indoor, "
            f"{result.exterior_asset_count} exterior or attached, and {result.lifecycle_count} "
            "lifecycle asset records. The generated and target inputs were not modified."
        )
