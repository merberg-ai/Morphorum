# Z-Image single-file checkpoint support roadmap (dev-webui)

Status: **Z1 initial inspection complete; Z2.1 dependency inventory and Z2.2 preliminary architecture fingerprint and Z2.3 structural/precision diagnostics and Z2.4 guarded encoder bundle diagnostics implemented. Z2.5 isolated conversion preflight and Z2.6 exact-schema staging and Z2.7 mapping validation/integrity and Z2.8 gated streaming conversion and Z2.9 cache integrity/concurrency protection and Z2.10 read-only diagnostics and Z2.11 real FP8 scale/encoder evidence added. Native loading remains disabled.** Initial bounded, read-only safetensors inspector and synthetic tests committed to dev-webui. Main remains unchanged. No standalone checkpoint is runtime-ready.

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

### Z2.5: isolated conversion preflight and cache planning

Added `backend/morphorum/zimage_conversion.py` with `plan_conversion(checkpoint, cache_root)`. It performs read-only safetensors inspection, requires recognized structural fingerprints and supported ordinary floating dtypes, explicitly blocks FP8/low-bit quantized variants, rejects symlinks, and refuses a conversion cache that overlaps or contains the source checkpoint. It derives a cache identity from the normalized source path, size, mtime and architecture. The planned output location is separate from the original file and managed Z-Image package. It creates **no files**, converts **no tensors**, and always returns `conversion_enabled=false`, `ready=false`, `loadable=false`.

Automated tests in `tests/test_zimage_conversion.py` cover deterministic cache planning, modified-source cache invalidation, FP8/partial checkpoint rejection and unsafe cache locations. The preflight is **not** an implemented converter or loader: future work must establish exact Diffusers state-dict conversion using verified real weights, strengthen cache content checks and atomic writes, resolve the full encoder/tokenizer/VAE/scheduler package, and run Windows GPU validation before enabling model selection.

### Z2.6: exact-schema weight staging primitive

`stage_verified_tensor_copy()` implements the first executable, CPU-only conversion-preparation path for **Diffusers-layout, ordinary floating-point safetensors only**. An independently supplied complete expected tensor-name/shape schema must match exactly: missing, extra or wrong-shaped entries are rejected before any copying. The file is copied into an isolated temporary cache directory, checked for source mutation and size, and then atomically published along with a manifest declaring `runtime_verified=false` and `loadable=false`. Existing destinations are never intentionally overwritten. Source safetensors remain immutable. Synthetic tests verify exact-schema matching, cache publication, non-overwrite and original-layout rejection.

This **does not yet perform tensor-name conversion** of original/ComfyUI-format checkpoints. The full expected tensor schema has not been established from verified actual checkpoint headers, so production conversion cannot safely be activated. FP8/low-bit formats remain blocked; no runtime loading, UI-ready status or managed-model changes were introduced. Next is upstream-verified original-to-Diffusers tensor mapping, validated real checkpoint fixtures, SHA-256 integrity checks and Windows physical testing.

### Z2.7: upstream-aligned tensor mapping and SHA-256 integrity

Added `plan_original_tensor_mapping()`, a **non-executable** full-schema validator following upstream Diffusers Z-Image key renames and fused QKV splitting. It requires a caller-supplied *complete* expected output shape/name schema and rejects mismatches, duplicate destinations, and invalid fused QKV dimensions. Original checkpoint tensors are not read into memory or converted by this function. The existing Diffusers-layout cache stager now hashes both the source and staged file with SHA-256 before atomic publication, recording both digests in the unverified manifest. Synthetic tests cover mapping and integrity. No model is marked ready or loadable.

Still required: authoritative source and target schemas for real Z-Image variants, a memory-safe executable QKV splitting converter, validated FP8 scale handling, component compatibility, cache concurrency hardening and physical Windows RTX 4080 SUPER testing. This stage does not implement full original-format conversion or native generation.

### Z2.8: executable streaming tensor remapping (gated)

Added `convert_original_checkpoint()`: requires the complete independently supplied Diffusers target-name/shape schema and the Z2.5 non-quantized preflight. Original-layout tensor names are mapped using Z2.7's validator and contiguous fused QKV weights are split as bounded raw byte ranges along dimension zero. The converter writes a new safetensors header and streams each tensor in 4 MiB chunks to a separate temporary cache folder, verifies the resulting safetensors structure, hashes source/output with SHA-256 and atomically publishes an unverified manifest. The original file is never modified. Failures clean temporary artifacts; existing destination paths refuse overwrite. Synthetic tests cover exact Q/K/V bytes, output tensors, hashes, rejection, and repeat-conversion refusal.

**Not yet production-ready:** real checkpoint target schemas and tensor layouts have not been verified, concurrent cache publication requires stronger locking, and output still says `runtime_verified=false` and `loadable=false`. FP8 remains blocked; no automatic background conversions, UI enablement, runtime model loading or main merge. Physical Windows validation and real representative checkpoints remain necessary.

### Z2.9: cache integrity and concurrency hardening

Added `backend/morphorum/zimage_cache.py` with read-only SHA-256 verification of published staged weights against their manifest, strict unverified/loadable=false checks, and an exclusive cross-process per-destination reservation. Both Z2.6 staging and Z2.8 conversion now use the reservation and independently verify the published cache before returning. Competing writers are rejected; lock files are released after success or ordinary failures. A stale lock is **not** removed automatically, deliberately avoiding interference with another process. Synthetic tests cover cache corruption, competing reservations, and failure cleanup.

Still pending: real model schema and tensor-value verification against reference conversion, robust stale-lock diagnosis/recovery and symlink/reparse-point security audits for parent folders, real checkpoint dependency and FP8 verification, Windows hardware acceptance. Integrity verified means matching the manifest's hash, **not** genuine model authenticity or runtime compatibility. All outputs remain `loadable=false`; managed loader and generation UI are unchanged.

### Z2.10: read-only real-checkpoint diagnostics

Added `backend/morphorum/zimage_diagnostics.py` and the endpoint `GET /api/models/{model_id}/zimage-diagnostics` for indexed external Z-Image checkpoints. It returns bounded header-derived tensor, architecture and precision evidence; up to 64 indexed text-encoder candidates with adjacent Qwen configuration/tokenizer file evidence; outstanding dependencies and conservative conversion strategy. It does **not** read tensor payloads, convert weights, invoke the loader or create caches. Every report retains `ready=false`, `loadable=false`. The original managed Z-Image model is not a valid diagnostic target. Automated tests cover supported-looking and invalid synthetic samples.

On the user's Windows install, first scan Models, find an external Z-Image checkpoint ID, then visit `/api/models/<ID>/zimage-diagnostics` on the local Morphorum server. Save the returned JSON for comparison to the actual FP8 format and downloaded Qwen encoder. The report includes local file paths through the encoder bundle diagnostics; review/redact paths before sharing publicly. Missing tokenizer/config files are reported, not silently accepted.

**Outstanding:** actual FP8 header report and a genuine text-encoder report, authoritative tensor compatibility, runtime load verification, and Z2.9 CI regression repair (the most recent backend run failed; syntax passed). Z2.10 does not bypass the conversion or generation safety gates.

### Z2.11: real FP8 scale and standalone encoder diagnostics

Based on the owner's actual 662-tensor checkpoint (209 `F8_E4M3`) and 903-tensor standalone Qwen-like encoder, inspection now recognizes `.scale_weight` alongside the older scale suffixes. The report exposes a total scale count, count paired with adjacent FP8 `.weight` tensors, unpaired scale count, FP8 weights without a recognized scale and up to 12 sample pairs of header shapes. It also reports Qwen-like encoder layer count and FP8 evidence **without** requiring adjacent HF JSON files for the structural fingerprint. Exact Qwen3 version and tokenizer/config pairing remain unverified. The prior misleading `scale_tensor_count=0` should now be corrected after a fresh scan/API diagnosis.

The managed Z-Image package's existing tokenizer, scheduler and VAE may become reusable auxiliary components, but only after a future read-only verification of component configs and a separate runtime proof. No managed files are modified, moved, copied or automatically selected. FP8 conversion remains blocked until its dequantization semantics are established. Current work is diagnostics only; it does not mark any external model loadable.

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
