# Indoors Demo Data Generator

An ArcGIS Pro 3.7.2 project for creating deterministic synthetic asset-management data from an ArcGIS Indoors geodatabase. It can enrich the supplied Vertex Medical Center data or build a validated six-facility catalog for dashboards, related-record workflows, and knowledge-graph demonstrations.

Start with [Catalog and Enrichment Guide](docs/catalog_and_enrichment_guide.md). It explains the three geodatabases, what enrichment adds, how Vertex is preserved, how the other facilities are generated, how relationships work, and how to run and validate each workflow.

All generated records are demonstration data, not an asserted facility inventory.

## Choose an output

| Goal | Input | Output | Recommended runner |
| --- | --- | --- | --- |
| Enrich Vertex only | Read-only `Vertex_Assets.gdb` | `Vertex_Assets_Enriched.gdb` | `scripts/enrich_vertex_asset_history_in_arcgis_pro.ipynb` |
| Build the full organization | Reviewed `Vertex_Assets_Enriched.gdb` plus facility profiles | `Organizational_Asset_Catalog.gdb` | `scripts/run_llm_asset_enrichment_in_arcgis_pro.ipynb` |

The Vertex output contains one facility and 1,003 enriched indoor assets. The organization catalog imports that reviewed Vertex slice and adds Point Place, Line Lake, Node North, Rohdran Cove, and Admin HQ using deterministic procedural floor plans. The promoted catalog contains 6 Sites, 6 Facilities, 32 Levels, 1,025 Units, 4,852 lifecycle assets, and 72 exterior assets with zero orphan references.

The original `Vertex_Assets.gdb` is never modified.

## Prerequisites

- ArcGIS Pro 3.7.2 with its managed Python environment and ArcPy.
- Access to the source `Vertex_Assets.gdb`.
- Ollama and `mistral` only when local-LLM narratives are wanted. Authoritative generation does not depend on model output, and failures use deterministic text.
- Production schema and catalog runs must use the ArcGIS Pro notebook kernel on the validated workstation; standalone ArcPy can terminate during schema creation.

## Repository and local data

The GitHub repository contains source code, profiles, notebooks, tests, and documentation. It does not contain file geodatabases, model weights, credentials, local logs, or generated manifests.

After cloning, place the source geodatabase in an approved local data directory and update `REPOSITORY` and `SOURCE_GDB` in the input cell of the notebook you intend to run. The one-off organization builder also declares its workstation paths near the top of `scripts/build_organizational_asset_catalog.py`; the combined notebook verifies that its paths and the builder paths agree before writing. Keep outputs outside the repository.

## Current scope

- Versioned Hospital, Vertex medical-facility, and Government Office room-use asset profiles
- Seeded, reproducible asset allocation
- Stable business-key generation that does not depend on rebuild-specific GlobalIDs
- Asset records with lifecycle attributes and system dependencies
- ArcGIS Pro toolbox with a read-only Indoors inspection report
- Deterministic indoor asset points, lifecycle records, and Facility-related exterior or attached asset points in a copied geodatabase
- Dependency-free procedural floor plans for non-Vertex catalog facilities
- Optional localhost narrative generation with strict JSON validation and deterministic fallback
- Staged catalog validation and lock-safe atomic promotion

The generated schema includes indoor Unit assets plus exterior and building-attached point assets related to the Indoors Facility. It creates coded-value domains, a contingent-value field group, and a lifecycle Arcade constraint rule through ArcPy. Utility-network assets are excluded from the current scope.

`Units.USE_TYPE` selects the applicable profile. The rules engine normalizes capitalization, spaces, and hyphens, then checks only explicit aliases in the selected profile. An unmapped or blank value is skipped and reported; it is never assigned an inferred asset set. Profiles cover room-specific operations assets plus shared locations including hallways, electrical rooms, telecom rooms, mechanical rooms, janitorial rooms, stairwells, entrances, and building exteriors.

Run `Inspect Indoors Geodatabase` before copying a source. Its JSON report starts with a compatibility decision, a Unit and `USE_TYPE` summary, mapped and unmapped values, and a recommended action; exhaustive inventories are retained under `technical_details`. Preflight requires the complete Site-to-Unit hierarchy and its business-key parent fields. Select the same facility profile in `Generate Demo Assets` and provide that report to verify the source workspace and profile version before generating. Generation always revalidates the live source geodatabase before writing, so a stale report cannot bypass safety checks.

The proposed source, generated, external enterprise, ArcGIS field-work, and media relationships are documented in [docs/schema.md](docs/schema.md). The exact additions and intentionally empty fields in the single-facility Vertex output are documented in [docs/vertex_assets_gdb_delta.md](docs/vertex_assets_gdb_delta.md). `AssetMediaReference` links a lifecycle asset to oriented imagery, 360 panoramas, photos, or documents without storing image binaries, credentials, or making network calls.

The multi-facility catalog's synthetic value ranges, lifecycle distribution, representative records, and validation contract are documented in [docs/organizational_catalog_data.md](docs/organizational_catalog_data.md).

Asset categories and subtypes now use a versioned project taxonomy, with stable type-specific USD planning bands across every profile asset. Purchase, maintenance, warranty, inspection-estimate, and repair values are derived deterministically from asset identity and lifecycle context. These values are synthetic planning assumptions, not vendor quotes or authoritative enterprise codes; Vertex financial values remain as reviewed.

The notebook purposes, Vertex-versus-organization scope, output geodatabases, recommended run sequences, and connections to the ArcGIS Indoors hierarchy are mapped in [docs/arcgis_pro_notebook_workflows.md](docs/arcgis_pro_notebook_workflows.md).

`Integrate Generated Assets` creates a new integrated GDB from a generated GDB and a target Indoors GDB. It does not modify either input, verifies every Unit and Facility parent reference, recreates the generator-owned schema, remaps generated GlobalIDs for the output, and validates dependent relationships.

## Vertex lifecycle enrichment

Open [scripts/enrich_vertex_asset_history_in_arcgis_pro.ipynb](scripts/enrich_vertex_asset_history_in_arcgis_pro.ipynb) in ArcGIS Pro 3.7.2 and run its cells in order. The notebook reads `Vertex_Assets.gdb` and creates a separate `Vertex_Assets_Enriched.gdb`; it never modifies the source. Schema creation is intentionally run in the ArcGIS Pro notebook kernel because this ArcPy operation is unstable in a standalone process on the current workstation.

For the 1,003 existing Vertex lifecycle assets, the workflow creates:

- Exact lifecycle cohorts: 501 within service life, 201 recently installed, and 301 near retrofit/replacement
- Inspection history for every asset between September 28, 2021 and March 28, 2026
- 271 assets with repair history
- 451 completed work orders and 50 active work orders
- Deterministic vendor, purchase, warranty, maintenance-cost, and risk metadata for every asset
- Populated Unit, Level, Facility, and Site keys with remapped GlobalID relationships
- A JSON manifest containing parameters, validation results, and warranty/risk distributions

Narrative text is deterministic by default. To use a local model, set `LLM_ENDPOINT`, `LLM_MODEL`, and `LLM_MAX_REQUESTS` in the notebook input cell. The adapter supports Ollama's `/api/generate` endpoint and OpenAI-compatible chat-completion endpoints on `localhost` or `127.0.0.1`. Responses must be JSON with exactly one `text` field; unavailable, malformed, oversized, or out-of-budget responses fall back to deterministic text. The manifest records accepted responses and each fallback category. The model does not determine IDs, dates, costs, conditions, lifecycle cohorts, or relationships.

Run [scripts/check_local_llm.py](scripts/check_local_llm.py) before ArcPy enrichment. Setup commands, telemetry interpretation, and the separate ArcGIS `SequenceToSequence` DLPK option are documented in [docs/llm_integration.md](docs/llm_integration.md).

To run both Vertex and the scaled six-facility catalog from ArcGIS Pro, use [scripts/run_llm_asset_enrichment_in_arcgis_pro.ipynb](scripts/run_llm_asset_enrichment_in_arcgis_pro.ipynb). Ollama checks and the strict response probe run only when Vertex or catalog generation is enabled; the default metadata retrofit is deterministic and skips Ollama.

The catalog keeps Vertex exactly as reviewed and procedurally creates the other four hospitals and Admin HQ from existing profiles. The planner needs no manual room data, CAD/BIM input, third-party geometry package, or new software. The combined notebook builds the catalog in a staging geodatabase and promotes it only after validation. A validated staged build is retained and reused if an ArcGIS lock prevents promotion.

The combined notebook currently defaults to a metadata-only retrofit of the existing organization catalog. It fills the project taxonomy and type-specific synthetic pricing without rebuilding geometry; set `RUN_METADATA_RETROFIT = False` and `RUN_CATALOG = True` when intentionally generating a fresh catalog. The retrofit does not modify the original `Vertex_Assets.gdb`.

The same implementation is available as [scripts/enrich_vertex_asset_history.py](scripts/enrich_vertex_asset_history.py) for ArcPy environments where standalone schema operations are stable.

## Documentation map

- [Catalog and Enrichment Guide](docs/catalog_and_enrichment_guide.md): end-to-end concepts and operator path.
- [Workflow Summary and Report](docs/catalog_workflow_report.md): executive and technical report covering outcomes, workflow, controls, use cases, and next steps.
- [Organizational Catalog Data](docs/organizational_catalog_data.md): validated counts, value ranges, sample records, and catalog contract.
- [Notebook Workflows](docs/arcgis_pro_notebook_workflows.md): notebook responsibilities, flags, promotion, and recovery.
- [Schema](docs/schema.md): datasets, fields, relationships, profiles, and integrity controls.
- [Vertex Assets Geodatabase Delta](docs/vertex_assets_gdb_delta.md): schema added when the base Vertex asset geodatabase was generated.
- [Local LLM Integration](docs/llm_integration.md): Ollama setup, response contract, telemetry, and alternatives.
- [Worklog](docs/worklog.md): implementation history and workstation-specific validation notes.

## Test

Run from the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests -q --ignore=tests/test_schema.py
```

The current non-schema suite contains 66 tests. Run schema validation in ArcGIS Pro because the standalone ArcPy schema boundary is unstable on the validated workstation.
