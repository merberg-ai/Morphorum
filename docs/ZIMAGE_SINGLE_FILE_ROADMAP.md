# Z-Image single-file checkpoint support roadmap (dev-webui)

Status: **Z1 initial inspection complete; Z2.1 dependency inventory and Z2.2 preliminary architecture fingerprint and Z2.3 structural/precision diagnostics and Z2.4 guarded encoder bundle diagnostics implemented. Native loading remains disabled.** Initial bounded, read-only safetensors inspector and synthetic tests committed to dev-webui. Main remains unchanged. No standalone checkpoint is runtime-ready.

## Diagnosis: unexpected Wan2GP directory

On October 18, the user's local Civitai manifest recorded a completed Z-Image checkpoint `zImageTurboQuantized_fp8ScaledE4m3fnKJ.safetensors` at `D:\wan2gp\app\ckpts\zImageTurboQuantized_fp8ScaledE4m3fnKJ.safetensors`. The prior downloader used the first value from `settings.models.zimage.checkpoints` when present. Previously the Settings UI hid checkpoint directories for managed Z-Image, while the indexer began scanning that field in the Z-Image indexing patch. This allowed a saved legacy/custom path to control downloads and scanning without appearing on screen, misleadingly displaying “0 model paths.” The provenance of that saved path is **not verified**; inspect `data/config.yaml` under `models: zimage: checkpoints:`. The Civitai manifest records the path used, not who or what configured it.

Dev-webui now exposes Z-Image standalone checkpoint directories in Settings and includes them in save payloads, allowing hidden legacy paths to be removed. The optional default `ckpts/z-image/civitai-checkpoints` is scanned without warnings when absent. The existing official managed Z-Image-Turbo Diffusers package remains separate.

## Non-negotiable guarantees

- Keep the proven managed Diffusers Z-Image-Turbo loader, install state, and model ID intact. A standalone single-file checkpoint must never replace, mutate or masquerade as that managed package.
- Do not mark arbitrary downloaded `.safetensors` as loadable until the architecture is positively recognized and a supported loader has successfully passed verification.
- No filename-based architecture guesses or unsafe pickle deserialization; prefer safetensors, validate structure, paths, file sizes and required auxiliary components.
- Maintain existing image, img2img, Motion Lab, sampler, LoRA, unload, VRAM, error/status and project persistence semantics.
- Build one stage at a time on `dev-webui`; run automated CI and stop for Windows physical tests before merging to `main`.

## Z1: Inspect and classify single-file formats

Initial implementation: `backend/morphorum/zimage_inspect.py` reads only a bounded JSON header, checks dtype/shape/offset consistency and complete payload coverage, and reports conservative statuses (`unsupported`, `needs_components`, `candidate`). All results have `ready=false` and `loadable=false`; no weights are loaded or architecture support claimed. Synthetic tests: `tests/test_zimage_inspect.py`. Still pending: inspect actual representative Z-Image files including FP8 quantized example, establish authoritative tensor signatures, integrate inspection results with model indexing/API/UX, run CI and physical Windows acceptance.

Add bounded safetensors header/metadata inspection that recognizes supported Z-Image full checkpoint formats vs transformer-only exports, quantized and architecture-incompatible weights. Capture tensor naming/shape requirements and the exact auxiliary components needed by each supported class. Surface an explicit reason for Unsupported / Needs components / Candidate status. Inspect actual Civitai sample files, including the user's quantized FP8 example, without assuming its format is directly loadable.

### Z1 auxiliary text encoders (initial implementation)

When a configured external Z-Image checkpoint folder contains a safetensors file with a recognizable Qwen-style token-embedding + attention + MLP tensor signature, scanning indexes it with `kind=components` rather than `kind=checkpoints`. Default model listings and their totals exclude these supporting components. Backend inspection is header-only; files are not executed or loaded into GPU memory. An explicit `kind=components` backend query can find these records for upcoming dependency matching. This is deliberately conservative: it does not prove Qwen version, tokenizer/config presence, or compatibility with any checkpoint. Runtime loader wiring and full compatibility checks belong to Z2. Synthetic regression tests cover index visibility.

## Z2: Separate native loader strategy

Introduce a Z-Image checkpoint loader registered separately from the existing `ManagedModelManager` Diffusers path. Resolve text encoder/tokenizer/scheduler/transformer and verify the expected configuration. Decide whether supported single-file state dictionaries can populate a reusable managed architecture or require conversion; any conversion is explicit and cached under Morphorum control, not written over the original. Reject incomplete weights early.

### Z2.1 implementation: read-only dependency inventory

- Added `backend/morphorum/zimage_standalone.py`, isolated from the managed model loader.
- Resolves a checkpoint's current inspection against separately indexed auxiliary encoder candidates, via `GET /api/models/{model_id}/standalone-dependencies`.
- Uses tensor structure, not filenames, to identify encoder candidates. Compatibility remains unverified; tokenizer, VAE, scheduler and exact transformer mapping are required.
- Exposes `missing_components`, `encoder_candidates`, status and reason. Always `ready=false` and `loadable=false`.
- Existing generation validation still rejects all non-managed Z-Image checkpoints. This is deliberate until actual format mapping and loader tests pass.
- Added isolated synthetic tests `tests/test_zimage_standalone.py`.
- **Next:** inspect real FP8 and other checkpoint headers, positively fingerprint supported architecture, validate component bundles and build verified loader/conversion strategy. Do not turn on Use before Windows tests.

### Z2.2: preliminary architecture fingerprint

Inspection now detects two Z-Image transformer tensor-key layouts through independent structural markers: original/ComfyUI form (`x_embedder`, `final_layer`, `cap_embedder`, `noise_refiner`, `context_refiner`, `layers`, including `model.diffusion_model.` prefix), and the Diffusers form (`all_x_embedder`, `all_final_layer` with the same other blocks). Source references: Diffusers `convert_z_image_transformer_checkpoint_to_diffusers` and `ZImageTransformer2DModel`. Diagnostics include `architecture` and `architecture_evidence`. Matching remains a **preliminary fingerprint**, not proof of tensor completeness or supported precision: `ready=false`, `loadable=false`.

Outstanding work: inspect actual sample headers including the owner's FP8 Civitai file, assess required dimensions/layer counts and FP8 quantization scale conventions, validate matching Qwen3 tokenizer/config and Flux AE VAE, select the compatible Diffusers converter/loading API, then run real GPU tests. No real checkpoint bytes were available in this execution environment. The managed pipeline is unchanged.

### Z2.3: structural and quantization diagnostics (initial implementation)

The header-only inspector now reports per-block layer counts, contiguous index checks, zero-sized parameter evidence, quantized dtype inventory, scale tensor count and an explicit unverified quantization convention for FP8/low-bit files. A fingerprint with missing/noncontiguous major block indices is rejected as unsupported. The result **never** enables generation. These checks do not prove exact layer counts, widths, full parameter coverage, per-tensor scale mapping, Qwen3 architecture/version, tokenizer availability, scheduler, VAE or Diffusers converter compatibility. Real downloaded checkpoint headers are still required for authoritative validation; the owner's local files are not available to this GitHub-based workflow.

### Z2.4: guarded auxiliary bundle and conversion planning

The standalone dependency resolver now examines optional adjacent `config.json` and `tokenizer.json` for indexed encoder safetensors files. JSON reads are bounded and disallow symlinks. A Qwen3 model type, Qwen3 architecture identifier, and positive hidden size, layer count, head count and vocabulary size are required before reporting `component_evidence_present`. This is evidence of locally supplied supporting files, **not** validation of the actual transformer/encoder tensors, tokenizer content or runtime loadability. Unsupported configuration is rejected as unverified. It also reports non-executable conversion candidates for recognized floating-point original versus Diffusers-style transformer layouts; quantized layouts remain blocked pending precision mapping. Managed Z-Image and generation validation are unchanged.

Z2.3 CI surfaced a failure in structural layer numbering caused by an over-escaped regex; repaired on dev-webui before Z2.4. Final CI verification remains required. Outstanding before enabling runtime: actual safetensors sample header evidence, exact model dimensions and tensor schema, verified tokenizer/VAE/scheduler pairing, dedicated converter, FP8 handling and Windows GPU validation.

## Z3: Generation runtime integration

Dispatch on verified model source and loader type; preserve the managed path unchanged. Exercise txt2img and img2img, prompt encoding, guidance, inference steps, seed determinism, cancellation, progress reports, GPU memory unloading and source switching on the user's RTX 4080 SUPER 16 GB.

## Z4: LoRA and variants

Prove LoRA injection separately for new Z-Image architectures and supported precision/quantization variants. Validate base compatibility and tensor match; reject unsupported LoRAs without impacting managed adapter state.

## Z5: Settings, Models and generation UX

- Explicitly separate **Managed Z-Image package** from **Standalone Civitai Z-Image checkpoints**.
- Show actual configured scan/download directories, including formerly hidden paths and the effective destination, with safe add/remove/verify controls.
- Indicate Indexed only / Needs components / Supported / Ready, with reasons and links to missing requirements.
- Only enable **Use** in Image and Motion Lab for verified loadable models; surface errors and compatibility summaries before render.
- Incorporate additional owner-requested UI tweaks before implementing the layout stage; details pending.

## Z6: Acceptance and release

Unit tests for each checkpoint class, malformed file, accidental cross-family load, missing dependencies and path migration. Regression tests of managed install and txt2img/img2img plus standalone load, changeovers, VRAM cleanup and project save/reload. Run GitHub CI and physical Windows tests, update README, installation and model documentation. Merge only after owner acceptance.

## Next action

Verify the newly introduced Z1 inspector in CI; inspect representative actual Z-Image checkpoint headers and define positively verified architecture signatures before any loader integration. UI integration and the owner-requested layout tweaks remain future work.

First verify and remove the unexpected Wan2GP entry in Settings if undesired, save, and rescan. It only affects Morphorum's indexing/download choice; removing it does not delete any Wan2GP files. The already-downloaded file stays where it is unless manually moved. Then gather representative checkpoints, refine Z1/Z2 format support, and collect the remaining UI requests.
