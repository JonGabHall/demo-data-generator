# Project Worklog

Last updated: 2026-09-30

This is the continuation anchor for the project. Read this file before searching the repository or conversation history. Update it whenever a task, decision, path, command, or validation result changes. Keep completed history concise.

## Objective

Build deterministic ArcGIS Indoors demonstration data for Vertex Medical Center, four additional hospitals, and Admin HQ. Support ArcGIS Dashboard and related-table workflows, with optional local-LLM narrative enrichment that cannot alter authoritative asset facts.

## Current State

- The multisite organizational catalog builder is implemented in `scripts/build_organizational_asset_catalog.py`.
- The catalog now requires `Vertex_Assets_Enriched.gdb` and imports its exact 1,003-asset Vertex slice, including all history and narratives. Unit, facility, asset-point, and lifecycle GUID relationships are remapped inside the catalog; the other five facilities are generated separately.
- Facilities are Vertex Medical Center, Point Place, Line Lake, Node North, Rohdran Cove, and Admin HQ.
- The current builder preserves Vertex's 286 Units, then creates procedural plans with 114 Point Place rooms, 114 Line Lake rooms, 120 Node North rooms, 128 Rohdran Cove rooms, and 263 Admin HQ rooms. The resulting organization has 1,025 Units across 32 Levels.
- The promoted catalog contains 4,852 indoor lifecycle assets and 72 exterior assets. Its manifest records 1,025 Units, 20,376 inspections, 922 repairs, 1,913 work orders, 6,590 system dependencies, and zero orphan references.
- The Vertex source contains 286 Units, 5 Levels, 1 Facility, 1,003 lifecycle rows, 10 exterior asset points, and empty inspection, repair, work-order, integration, and media tables.
- Vertex deterministic lifecycle/history planning is implemented in `src/indoors_demo_generator/enrichment.py`.
- Every planned Vertex asset now includes deterministic vendor, purchase, warranty, maintenance-cost, and risk metadata.
- Optional localhost narrative generation is implemented in `src/indoors_demo_generator/narratives.py`.
- Local-LLM preflight is implemented in `scripts/check_local_llm.py`; run manifests record accepted, budget-fallback, invalid-response, and transport-fallback counts.
- `scripts/run_llm_asset_enrichment_in_arcgis_pro.ipynb` orchestrates preflight, Vertex enrichment, and the scaled organizational catalog from ArcGIS Pro.
- The combined notebook currently defaults to `RUN_VERTEX = False`, `RUN_CATALOG = True`, and `ALLOW_OVERWRITE = True`, resolves Ollama from its standard Windows path when `PATH` is stale, and uses a 120-second model timeout.
- The combined notebook now clears cached `indoors_demo_generator` modules before loading workflow scripts, preventing a long-lived ArcGIS Pro kernel from pairing a current writer with an older schema factory.
- The standalone Vertex notebook now requires explicit overwrite consent and removes partial output and manifest files after any workflow failure.
- The catalog schema-test notebook preserves an existing catalog unless `FORCE_REBUILD = True`; an output without its manifest now fails closed.
- The multi-facility builder now accepts the shared narrator and limits model candidates to latest inspections, repairs, and work orders; Vertex also limits inspection candidates to latest records.
- Non-Vertex facilities now use dependency-free procedural corridor-and-room plans. Generated hospitals use `hospital-v1.json`; Admin HQ uses `government-office-v1.json`. No manual room data, CAD/BIM input, new library, or additional software is required.
- Generated indoor assets use `Facility_ID|Level_ID|Unit_ID` as their deterministic generation identity; exterior assets use `Facility_ID`. Current GlobalIDs remain authoritative relationship keys but no longer change asset allocation across rebuilds.
- Catalog validation now checks exact Site and Facility identities, `VMC` to `MMC` parentage, every Level and Unit parent, planned room names and use types, geometry containment, and asset business-key continuity in addition to relationship GUIDs and counts.
- Generated hierarchy rows explicitly replace Vertex template metadata: Facilities receive generated hours, height, level counts, and cleared image URLs; Units receive room-program capacities and amenities instead of inherited Exam Room flags.
- The combined notebook validates its enriched-Vertex dependency before writing, builds to `Organizational_Asset_Catalog_building.gdb`, and preserves or restores the previous catalog if build promotion fails.
- Local service setup and the ArcGIS `SequenceToSequence` DLPK decision are documented in `docs/llm_integration.md`.
- Ollama 0.34.4 is installed and serving on `127.0.0.1:11434`; `mistral:latest` is installed as a 7.2B Q4_K_M model.
- The Vertex ArcPy writer is `scripts/enrich_vertex_asset_history.py`.
- The supported workstation execution path is `scripts/enrich_vertex_asset_history_in_arcgis_pro.ipynb`.
- Notebook responsibilities, output scopes, recommended run paths, and ArcGIS Indoors relationships are documented in `docs/arcgis_pro_notebook_workflows.md`.
- `Vertex_Assets_Enriched.gdb` and its manifest currently exist. Live inspection found 1,003 indoor assets, 10 exterior assets, 4,154 inspections, 271 repairs, and 501 work orders.
- The live catalog run exposed a managed-kernel `ValueError` from retained ArcPy cursor geometry proxies. Hierarchy templates now read `SHAPE@JSON` and immediately reconstruct independent geometries; import/facility checkpoints and full builder tracebacks identify any remaining failure before cleanup.
- The repaired live run completed generation, history population, and validation with 1,025 Units, 4,852 lifecycle assets, 72 exterior assets, and zero orphan references. Promotion then exposed a lock in the prior canonical catalog. The notebook now uses atomic directory renames, recognizes incomplete-promotion state, preserves the complete prior copy, and reuses the complete validated staging catalog without another 27-minute build.
- The recovery run reused the validated staging catalog and successfully promoted it to `Organizational_Asset_Catalog.gdb`; staging and backup workspaces were removed.
- Generated Indoors business-key fields now inherit source field lengths. The live source uses 255 characters for `Levels.LEVEL_ID` and `Units.UNIT_ID`, preventing ArcGIS Pro's floor-awareness length warning in newly built outputs.
- Inspection, repair, and work-order rows now carry both lifecycle and asset-point GUIDs. Direct `IndoorAssetLocation` relationship classes support related history in asset map popups while retaining lifecycle-centered relationships.
- The original `Vertex_Assets.gdb` was verified unchanged; all six child tables remain empty.

## Fixed Contracts

- Never modify the original `Vertex_Assets.gdb`.
- Write the result to `Vertex_Assets_Enriched.gdb` and emit `Vertex_Assets_Enriched_manifest.json`.
- Reference date: 2026-09-28.
- Inspection window: 2021-09-28 through 2026-03-28.
- Lifecycle cohorts for 1,003 assets: 501 within service life, 201 recently installed, 301 retrofit/replacement.
- Every asset receives inspection history.
- Repair history: 271 assets (27%).
- Completed work orders: 451 assets (45%).
- Active work orders: 50 assets (5%).
- Derive hierarchy through Unit -> Level -> Facility -> Site.
- Remap all GlobalID/GUID relationships in the new geodatabase.
- LLM output is advisory narrative text only. Deterministic code owns identifiers, dates, costs, conditions, cohorts, statuses, and relationships.
- LLM responses must be local, valid JSON with exactly one `text` field, at most 500 characters; otherwise use deterministic fallback text.
- Purchase dates precede commissioning, purchase costs remain below replacement estimates, warranty status is evaluated at the reference date, and risk scores remain in the 0-100 range.

## LLM Direction

The operational runtime is now Ollama with `mistral:latest`, using the tested localhost adapter. Direct Transformers inference with `Qwen/Qwen2.5-1.5B-Instruct` remains a viable alternative, but no additional runtime change is needed for the current ArcGIS Pro test.

The official GitHub Copilot SDK is a feasible online narrator backend, but it requires authentication and a Copilot subscription or BYOK, consumes metered prompts, and sends supplied facts to a remote provider. GitHub Models cannot be used because its inference service was retired on 2026-07-30.

Esri precedents verified in the public ArcGIS API for Python materials:

- Mistral 7B Instruct through `arcgis.learn.text.EntityRecognizer`.
- On-premises `meta-llama/Meta-Llama-3-8B-Instruct` through Hugging Face Transformers.
- Third-party open and commercial language models packaged as Esri `.dlpk` model extensions for the GeoAI Text Analysis tools.
- GLiNER zero-shot entity recognition through a custom model extension.

The current localhost adapter is the recommended generator integration. A `.dlpk` is feasible as a separate `SequenceToSequence` custom NLP function when the model must appear directly in ArcGIS Pro's Transform Text Using Deep Learning tool. It requires the Esri `.emd`/inference-function contract, an Advanced license, and ArcGIS deep-learning frameworks.

## Validation Record

- Planner tests: 5 passed, including asset-profile temporal, financial, warranty, maintenance, and risk invariants.
- Narrator tests: 5 passed, covering accepted output, malformed output, request budgets, transport failures, and enabled/disabled manifest telemetry.
- Core non-schema suite: 47 passed, 0 failures, 0 errors in `arcgispro-DL37-py3`.
- Current non-schema suite: 59 passed, including geometry detachment and recovery from an incomplete canonical catalog with complete prior and staged copies.
- Procedural floor-plan suite: 7 passed, including deterministic plans, profile coverage, exact per-facility room counts, non-overlap, room-program amenities, and organization-wide Level, Unit, and asset-ID uniqueness.
- Stable-generation regression suite confirms indoor and exterior asset allocation is unchanged when source GlobalIDs change.
- Full 1,003-asset planner sample: 298 active and 705 expired warranties; risk bands contain 86 Low, 346 Moderate, 356 High, and 215 Critical assets across 21 vendors.
- Toolbox path tests: 7 passed.
- All three ArcGIS Pro notebooks pass Jupyter schema validation. Every existing cell has matching `metadata.id` and `metadata.language` values.
- The standalone Vertex notebook has five compiling code cells; its non-writing setup and guarded workflow definition execute successfully.
- The combined LLM notebook contains 18 cells with 11 code cells and saved output from the successful catalog recovery and promotion.
- The combined notebook's exact preflight passes: Ollama 0.34.4 is found, the API is available, `mistral:latest` is installed, and the strict JSON probe records one accepted response with zero fallbacks.
- The catalog schema-test notebook has seven compiling code cells; its non-writing setup executes successfully and its existing catalog/manifest pair is recognized as a safe skip.
- Pylance/workspace diagnostics reported no errors in the new Python files.
- Python-native inference check: Python 3.13.13, PyTorch 2.9.1, Transformers 4.51.3, Accelerate, SentencePiece, and Safetensors are present; CUDA detects an NVIDIA RTX A3000 12 GB Laptop GPU; system RAM is 31.8 GB.
- No generative LLM weights are cached locally. The cache contains BERT and computer-vision models only. `bitsandbytes` 0.49.1 detects CUDA 12.9, so Mistral 7B Instruct v0.3 is viable with 4-bit Transformers loading but not full BF16 loading on the 12 GB GPU.
- Ollama API validation: `/api/tags` returned `mistral:latest`; the project preflight accepted one generated narrative with zero fallbacks. The first cold generation took about 49 seconds, while the immediately following warm request took about 0.22 seconds.
- Live field validation reproduced the floor-awareness warning cause: source `Levels.LEVEL_ID` is length 255 while the existing output's `IndoorAssetLocation.Level_ID` is length 64. Two ArcPy-independent source-length regression tests pass after the schema fix.
- Direct asset-history relationship regression verifies `IndoorAssetLocation.GlobalID` to child `AssetPointGlobalID`; production writers populate both parent GUIDs and validators reject null or orphan references.
- Enriched-Vertex import validation copied all 1,003 assets, 4,154 inspections, 271 repairs, and 501 work orders into a disposable catalog schema. Sampled lifecycle values were equal, and a preservation probe confirmed authoritative condition, commissioning, lifecycle stage, vendor, and risk values remained unchanged during catalog enrichment.
- Clean-runtime ArcPy probes completed original Vertex plus Point Place, Line Lake, Node North, Rohdran Cove, and Admin HQ hierarchy and asset generation. End-to-end catalog generation and validation then completed in the ArcGIS Pro notebook kernel.
- Notebook reload simulation inserted a stale marker into the cached schema module, ran the refresh and loader cells, and verified that the marker was removed and the current `AssetPointGlobalID` schema loaded. All 10 current code cells compile.
- Read-only ArcPy geometry probes fit representative hospital and office plans inside the real Vertex Site template. Pure planning calculates PP 114 rooms/648 assets, LL 114/644, NN 120/658, RC 128/736, and AHQ 263/1,163.
- The full external-process suite terminates at the existing ArcPy schema integration boundary; this is an environment/process failure, not a Python assertion failure.
- Earlier schema creation succeeded inside an ArcGIS Pro notebook kernel.

Selected interpreter:

```text
C:\Users\jon12828\AppData\Local\ESRI\conda\envs\arcgispro-DL37-py3\python.exe
```

Non-schema test command:

```powershell
$env:PYTHONPATH = "src"
& "C:\Users\jon12828\AppData\Local\ESRI\conda\envs\arcgispro-DL37-py3\python.exe" -m unittest discover -s tests -v
```

Do not rely on the full command above for unattended completion on this workstation because `test_schema.py` can terminate the external ArcPy process. Run schema validation in ArcGIS Pro.

## Next Actions

1. Add the catalog `IndoorAssetLocation` as a floor-aware layer, apply `Facility_ID = 'VMC'`, and confirm related inspections, repairs, and work orders are available in popups.
2. Prepare feature-service publishing and ArcGIS Dashboard or knowledge-graph configuration.
3. Decide whether to expose the enrichment workflow as a Python toolbox tool.

## Known Constraints

- Standalone ArcPy processes on this workstation can terminate during `create_asset_management_schema`; use the ArcGIS Pro notebook kernel.
- Replacing a catalog requires all ArcGIS Pro layers, standalone tables, attribute tables, and Catalog views referencing the old geodatabase to be closed. A lock-safe validated staging build is retained for recovery.
- VS Code does not expose the attached ArcGIS Pro notebook kernel; final catalog rebuild validation must be completed in ArcGIS Pro.
- Do not create or modify another Python environment; use the existing `arcgispro-DL37-py3` environment.
- Existing terminals opened before the Ollama installation may not resolve `ollama` on `PATH`; reopen them or use `C:\Users\jon12828\AppData\Local\Programs\Ollama\ollama.exe`. Do not run a second `ollama serve` process while the desktop application owns port `11434`.

## Key Files

- `src/indoors_demo_generator/enrichment.py`: deterministic planner.
- `src/indoors_demo_generator/floorplans.py`: dependency-free procedural plans for generated facilities.
- `src/indoors_demo_generator/narratives.py`: constrained local-LLM adapter.
- `scripts/check_local_llm.py`: localhost model response-contract probe.
- `scripts/run_llm_asset_enrichment_in_arcgis_pro.ipynb`: combined ArcGIS Pro LLM workflow.
- `docs/arcgis_pro_notebook_workflows.md`: notebook, output-scope, and Indoors relationship guide.
- `docs/llm_integration.md`: Ollama, telemetry, and ArcGIS DLPK integration guide.
- `scripts/enrich_vertex_asset_history.py`: ArcPy output writer and validator.
- `scripts/enrich_vertex_asset_history_in_arcgis_pro.ipynb`: authoritative workstation runner.
- `tests/test_enrichment.py`: cohort, rate, date, and determinism tests.
- `tests/test_narratives.py`: response validation and fallback tests.
- `docs/vertex_assets_gdb_delta.md`: original Vertex schema audit.
- `docs/organizational_catalog_data.md`: multisite catalog data contract.

## Update Template

After continuing work, edit only the affected sections and record:

```text
Last updated: YYYY-MM-DD
Completed: <short result>
Validated: <command/check and outcome>
Next: <first executable action>
Blocker: <only if present>
```