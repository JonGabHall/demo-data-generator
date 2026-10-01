# Local LLM and ArcGIS DLPK Integration

## Recommended Architecture

Keep deterministic code authoritative and use the LLM only for short inspection, repair, and work-order narratives. The current adapter sends only the supplied asset facts to a localhost endpoint, accepts JSON with exactly one `text` property, normalizes whitespace, rejects text longer than 500 characters, and falls back to deterministic text on any failure.

This service-based route is the recommended first deployment because it:

- Works in the existing ArcGIS Pro notebook without changing the geodatabase schema.
- Keeps model weights and inference dependencies outside ArcGIS Pro's managed Python environment.
- Preserves deterministic IDs, dates, costs, conditions, cohorts, statuses, and relationships.
- Records accepted responses and every fallback category in the output manifest.

## Ollama Setup

Ollama is not included with ArcGIS Pro 3.7.2 or Esri Deep Learning Essentials. The Esri installer supplies libraries such as PyTorch, Transformers, `arcgis`, and `arcgis-dlpk`; Ollama is a separate Windows executable, service, model manager, and runtime.

Do not run `conda install ollama` or `pip install ollama` in an ArcGIS Pro environment. Ollama is not distributed as an executable runtime through the configured Conda channels, and the similarly named Python package is only a client library.

Install the Windows application outside the ArcGIS Pro Python environment using the official [Ollama Windows installer](https://ollama.com/download/OllamaSetup.exe). The official download page also provides this normal PowerShell option:

```powershell
irm https://ollama.com/install.ps1 | iex
```

Close and reopen PowerShell and ArcGIS Pro after installation so they receive the updated `PATH`. Verify the runtime, then download the model:

```powershell
ollama --version
ollama pull mistral
ollama list
Invoke-RestMethod http://localhost:11434/api/tags
```

The Windows application normally starts the localhost service. Run `ollama serve` only when the API is unavailable and Ollama is not already running; starting a second service can fail because port `11434` is in use.

In another terminal, test the exact response contract before running ArcPy:

```powershell
& "C:\Users\jon12828\AppData\Local\ESRI\conda\envs\arcgispro-DL37-py3\python.exe" `
  scripts\check_local_llm.py `
  --endpoint http://localhost:11434/api/generate `
  --model mistral
```

Exit code `0` and `"accepted": true` mean the model returned a usable narrative. Exit code `1` means enrichment would safely use deterministic fallback text; inspect `statistics.invalid_response_fallbacks` and `statistics.request_error_fallbacks` to distinguish model-format failures from connection failures.

Then set these values in `scripts/enrich_vertex_asset_history_in_arcgis_pro.ipynb`:

```python
LLM_ENDPOINT = "http://localhost:11434/api/generate"
LLM_MODEL = "mistral"
LLM_MAX_REQUESTS = 100
```

Run the probe while Ollama is already serving. Do not start Ollama from an ArcGIS Pro notebook cell, and do not install Ollama packages into `arcgispro-DL37-py3`.

For the complete project workflow, open `scripts/run_llm_asset_enrichment_in_arcgis_pro.ipynb` in ArcGIS Pro. It preflights the executable, service, installed model, and strict JSON response before creating either the separate Vertex output or the organizational catalog.

## Python-Native Local Inference

Ollama is optional. This workstation's ArcGIS Pro environment already contains Python 3.13.13, PyTorch 2.9.1, Transformers 4.51.3, Accelerate, SentencePiece, and Safetensors. PyTorch detects the NVIDIA RTX A3000 12 GB GPU, and the machine has 31.8 GB of RAM. A `TransformersJsonNarrator` can therefore load a small instruction model directly in the ArcGIS Pro notebook without installing another inference application.

The deep-learning installation provides inference libraries, not a ready-to-run generative model. The current Hugging Face cache contains `bert-base-uncased` and computer-vision models, but no instruction-tuned text-generation model. BERT can encode or classify text; it cannot generate the required inspection and work-order narratives. Esri pretrained model packages from Living Atlas are also separate downloads rather than model weights bundled with the framework installer.

A practical starting model is `Qwen/Qwen2.5-1.5B-Instruct`. Its full-precision weights fit comfortably on the detected GPU. The smaller `Qwen/Qwen2.5-0.5B-Instruct` reduces memory and download size at the cost of narrative quality. Mistral 7B is not the first choice for direct full-precision inference because its weights and runtime overhead can exceed the available 12 GB of VRAM.

`mistralai/Mistral-7B-Instruct-v0.3` can instead run through the installed Transformers stack with 4-bit quantization. Transformers 4.51.3 satisfies the model's 4.42+ requirement, and the installed `bitsandbytes` 0.49.1 backend detects CUDA 12.9. The model weights are not cached and must still be downloaded. Full BF16 loading is unsuitable because approximately 14 GB of weights alone exceed GPU memory; 4-bit loading is the safer configuration. The installed `mistralai` package is a cloud API client, not local Mistral weights or the separate `mistral-inference` runtime.

This route avoids an Ollama installation, but it does not avoid downloading model weights. Transformers downloads the selected model from Hugging Face on first use and stores it in the local cache. For disconnected operation, download and approve the model once, retain its license files, and load it from a controlled local path.

The Python narrator should reuse the existing request budget, telemetry, exact `{"text": "..."}` contract, 500-character limit, fact-only prompt, and deterministic fallback. Transformers generation does not inherently guarantee the JSON contract, so validation remains mandatory.

`llama-cpp-python` is another local Python option and supports GGUF models plus JSON-schema-constrained output. It is less attractive inside the managed ArcGIS environment because installation may require a compatible prebuilt wheel or a Windows C/C++ build toolchain. It also still requires a separate model-weight download.

## GitHub Copilot

Do not automate the VS Code chat interface or treat an editor session as an inference API. The supported programmatic path is the official `github-copilot-sdk` Python package. As of 2026-09-28, the SDK is generally available, bundles Copilot CLI for Python, and communicates with that CLI through a local JSON-RPC server. Standard use requires GitHub authentication and a Copilot subscription; prompts count against Copilot usage. Bring Your Own Key is also supported for selected providers.

A `CopilotJsonNarrator` is technically feasible for this project and would avoid local model weights and Ollama. It would still require the SDK package, internet access, authentication, organization approval for transmitted data, and strict response validation. Disable Copilot's tools for this narrative-only workflow; the model only needs to transform supplied synthetic facts into short text.

Copilot is better suited to interactive or low-volume enrichment than reproducible bulk generation. Results depend on a remote service, account entitlements, model availability, and usage limits. Keep deterministic fallback text authoritative and record the provider, model, accepted responses, and fallbacks in the manifest.

GitHub Models is not an alternative: GitHub retired its playground, catalog, inference API, and BYOK service on July 30, 2026. GitHub directs new model-inference applications to GitHub Copilot or Azure AI Foundry.

## OpenAI-Compatible Local Servers

For a localhost server that implements chat completions, use its local URL instead:

```powershell
& "C:\Users\jon12828\AppData\Local\ESRI\conda\envs\arcgispro-DL37-py3\python.exe" `
  scripts\check_local_llm.py `
  --endpoint http://127.0.0.1:8000/v1/chat/completions `
  --model local-model-name
```

Only `localhost` and `127.0.0.1` endpoints are accepted. The adapter intentionally has no API-key handling because its trust boundary is local-only.

## Manifest Telemetry

Every run writes `narrative_generation.statistics`:

| Counter | Meaning |
| --- | --- |
| `total_calls` | Narrative opportunities encountered by the planner |
| `requests_sent` | Calls sent before the configured request budget was exhausted |
| `accepted_responses` | Model responses that passed the strict JSON and length contract |
| `fallback_responses` | Total deterministic fallbacks |
| `budget_fallbacks` | Calls skipped after `LLM_MAX_REQUESTS` |
| `invalid_response_fallbacks` | Malformed JSON, extra fields, non-text, empty, or oversized output |
| `request_error_fallbacks` | Connection, timeout, or local-server transport failures |

The following invariant should hold:

```text
total_calls = accepted_responses + fallback_responses
fallback_responses = budget_fallbacks + invalid_response_fallbacks + request_error_fallbacks
```

## Can This Become a DLPK?

Yes, but a DLPK is a separate ArcGIS inference interface, not a direct repackaging of `LocalJsonNarrator`.

ArcGIS Pro 3.7's **Transform Text Using Deep Learning** tool accepts `.emd`, `.dlpk`, and hosted `.dlpk_remote` model definitions. Third-party text-generation packages use `"ModelType": "SequenceToSequence"`. The tool requires an ArcGIS Pro Advanced license and the ArcGIS deep-learning frameworks; CPU is supported, while a GPU is recommended for local model weights.

A custom package must contain:

```text
VertexAssetNarratives/
|-- VertexAssetNarratives.emd
`-- VertexAssetNarratives.py
```

The `.emd` needs at least:

```json
{
  "InferenceFunction": "VertexAssetNarratives.py",
  "ModelType": "SequenceToSequence",
  "OutputField": "Narrative"
}
```

The Python inference class must implement:

- `__init__`: describe and initialize the custom NLP function.
- `initialize(**kwargs)`: read the `.emd` path from `kwargs["model"]` and load weights or connection configuration.
- `getParameterInfo()`: expose model arguments such as model name, endpoint, timeout, and prompt mode.
- `getConfiguration(**kwargs)`: validate arguments and return processing configuration including batch size.
- `predict(feature_set, **kwargs)`: read the selected input text field and return an `arcgis.features.FeatureSet` containing the generated output field.

The containing folder name must match the `.emd` filename. Zip the folder and rename the archive from `.zip` to `.dlpk`.

## DLPK Deployment Choices

### Service-backed DLPK

The custom inference class can call Ollama or another web API. Esri explicitly supports external open-source and commercial models accessed through APIs. For this project, retain the localhost restriction and expose no credentials as model arguments.

Advantages: small package, model remains independently updateable, and no large weights are bundled.

Tradeoffs: ArcGIS Pro still depends on the model service, every row incurs an API call unless `predict` batches requests, and package code must independently reproduce strict response validation and deterministic fallback behavior.

### Self-contained DLPK

The package can include or reference local model weights and load them in `initialize`.

Advantages: no model server and a conventional ArcGIS model artifact.

Tradeoffs: large packages, model-license review, substantial RAM/GPU requirements, and Python/deep-learning dependency compatibility with ArcGIS Pro. Do not install or alter those dependencies until a specific model and ArcGIS deep-learning framework version are selected and tested together.

## Recommendation

For the fewest workstation changes, add an in-process Transformers narrator and start with `Qwen/Qwen2.5-1.5B-Instruct`; the required Python runtime and GPU support are already installed. Retain the existing Ollama adapter when process isolation, model management, and a stable localhost API are more important than avoiding an application installation. Use the Copilot SDK only when online inference, account-based access, and usage metering are acceptable.

Build a `SequenceToSequence` DLPK only when users need model inference exposed through ArcGIS Pro's Text Analysis geoprocessing tools or a hosted ArcGIS model item. Treat that as a separate adapter with its own ArcGIS Pro integration tests. A practical DLPK workflow is to create a staging table with deterministic fact text, run **Transform Text Using Deep Learning** into a candidate narrative field, validate the candidate output, and then copy only accepted text into the final notes fields.

## Official References

- [Transform Text Using Deep Learning](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/geoai/transform-text-using-deep-learning.html)
- [Use third party language models with ArcGIS](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/geoai/using-third-party-language-models-with-arcgis.html)
- [Install deep learning frameworks for ArcGIS](https://doc.esri.com/en/arcgis-pro/latest/help/analysis/deep-learning/install-deep-learning-frameworks.html)
- [GitHub Copilot SDK](https://docs.github.com/en/copilot/how-tos/copilot-sdk)
- [GitHub Models retirement](https://docs.github.com/en/rest/models/inference)
- [Transformers Pipeline](https://huggingface.co/docs/transformers/en/pipeline_tutorial)
- [llama-cpp-python](https://github.com/abetlen/llama-cpp-python)
