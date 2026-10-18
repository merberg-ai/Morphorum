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

### Z2.12: exact FP8 tensor accounting and encoder report

The latest Windows diagnostic confirmed 209 FP8 transformer tensors, 208 paired scalar `.scale_weight` tensors, no unmatched `.weight` tensors. Diagnostics now list FP8 tensor keys **not ending in `.weight`** separately so no model tensor is silently omitted from the accounting. Encoder diagnostics now surface the existing unverified Qwen-like layer and scale-pair evidence. Diagnostic version is `z2.12`. No tensor payload reads or GPU loads.

Managed component reuse and FP8 dequantization semantics remain unverified and deliberately inactive; inspecting component file presence does not establish compatibility. The latest prior CI fix at `961399e` passed both backend and syntax workflows (920 passed, 1 skipped). Z2.12 test results are tracked separately.

### Z2.13: bounded FP8 scalar probes and managed auxiliary inventory

Added `zimage_fp8_evidence.py`: after the independent safetensors structural check, it reads at most eight ordinary F16/F32/F64 scalar values from `.scale_weight` entries and checks the `scaled_fp8` marker shape/dtype and small scalar value where supported. It does **not** read any FP8 matrix, reconstruct weights, infer the scale direction, or authorize loading. Diagnostic endpoint returns this evidence for the external checkpoint and indexed encoder files.

The same report inventories required tokenizer, VAE and scheduler files in the existing managed Z-Image-Turbo installation **without creating or modifying files**. File presence is not architectural compatibility and does not authorize component reuse. Any unrecognized BF16 scalar and quantization convention stays unverified. FP8 conversion, runtime GPU loading and automatic auxiliary reuse remain disabled.

### Z2.14: FP8 marker semantics, numerical references, managed configuration evidence

Read-only diagnostics now interpret the exact `scaled_fp8` marker **shape convention**, following upstream ComfyUI `comfy/utils.py:convert_old_quants`: a two-element marker sets `full_precision_matrix_mult`, while a zero-element marker does not. Values are not treated as a load authorization. At most two raw marker bytes are returned as hexadecimal with exploratory E4M3FN numeric decoding. Each checkpoint can also yield up to four samples of four FP8 weight bytes with matching F32 scale and a CPU-only reference multiplication. This follows the open-source `comfy_kitchen/backends/eager/quantization.py:dequantize_per_tensor_fp8` operation (`weight_float * scale`). Samples help independently verify our decoder; they are **not** whole-model conversion or evidence of generation correctness.

Managed Z-Image-Turbo diagnostics now read only bounded, selected fields from the installed `model_index.json`, tokenizer config, VAE config, scheduler config and text-encoder config. They compare component class labels against the official Z-Image package roles without copying, mutating or automatically selecting any component. Even a matching class name is not standalone checkpoint compatibility. Raw tokenizer vocabulary and huge weight files are never read.

References: https://github.com/Comfy-Org/ComfyUI/blob/master/comfy/utils.py and https://github.com/Comfy-Org/comfy-kitchen/blob/main/comfy_kitchen/backends/eager/quantization.py ; official pipeline roles https://huggingface.co/Tongyi-MAI/Z-Image-Turbo/blob/main/model_index.json . FP8 production conversion, standalone text-encoder loading, reusing managed parts at runtime and UI activation remain disabled until an isolated Windows physical test establishes compatibility.

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

### Z2.15: full FP8 pairing validation and independent CPU reference tests

Added backend/morphorum/zimage_fp8_validation.py. The diagnostic checker requires one matching F32 scalar .scale_weight for every F8_E4M3 .weight, no unexpected FP8 tensor apart from scaled_fp8, an approved [0] or [2] marker shape, and finite positive values for every scale (bounded at 4096 pairs). It samples up to eight weights with up to sixteen FP8 elements each, and compares our E4M3FN decoder and multiplied values against CPU PyTorch without reading full matrices. The result is fail-closed when torch is unavailable or comparisons fail. Tests include all 256 possible FP8 byte patterns and corruption cases.

The existing /api/models/{model_id}/zimage-diagnostics endpoint now reports diagnostic_version z2.15, transformer fp8_validation, and auxiliary encoder fp8_validation. Managed reuse assessment additionally compares actual encoder embedding, vocab, MLP, attention input and layer dimension evidence with the installed managed Qwen3 config. All are read-only evidence: compatible=false, reuse_enabled=false, conversion_enabled=false and loadable=false, irrespective of successful validation.

Windows acceptance: update dev-webui, restart, open the existing diagnostic URL, confirm both FP8 validation statuses are reference_matched and counts are 208 and 252, review managed_reuse_assessment checks. Keep standalone generation disabled pending a separately reviewed runtime plan and hardware acceptance.

### Z2.16: safe isolated FP8-to-BF16 sample conversion (not a loader)

Implemented `backend/morphorum/zimage_fp8_prototype.py` for the ComfyUI-style `F8_E4M3` checkpoints already checked by Z2.15. It chooses at most two representative source weights and emits **at most four windows** of **64 FP8 elements** each. For a rank-2 fused QKV weight, three windows come from the Q, K and V thirds independently, with explicit source offsets and target name hints. These target names are **only hints**, not a verified complete Diffusers state-dict mapping. The standalone Qwen encoder samples q_proj and down_proj separately. A read-only diagnostic plan is exposed under `checkpoint.experimental_bf16_plan` and `auxiliary_encoders[].header.experimental_bf16_plan`. Neither of these paths writes files or changes model loading.

The optional manual CLI `python -m morphorum.zimage_fp8_prototype --checkpoint <file>` is read-only by default; adding `--export --output <new-experimental-directory>` explicitly creates a small non-loadable `samples.safetensors` and `manifest.json` **outside checkpoint and managed directories**, using an exclusive reservation, temporary staging, atomic rename and manifest/hash checks. The output contains one-dimensional sample windows rather than full model tensors. CPU PyTorch performs FP8-to-BF16 using the upstream BF16 reference order: cast the FP8 values and scalar to BF16 **before** multiplication, then compare the result to a separate CPU-decoded reference. No GPU or model inference is invoked. Experimental output never modifies original files or managed components; production `plan_conversion` still rejects FP8. Do **not** point Image or Motion Lab at this sample file.

`managed_auxiliary_binding_plan` in the existing diagnostic response identifies managed tokenizer, VAE, and scheduler as **candidates only**, with external encoder and transformer still explicitly unverified. Even when all evidence checks match, `runtime_binding_enabled=false`, `loadable=false`, and `ready=false`.

Windows acceptance: restart a `dev-webui` checkout and inspect the existing external Z-Image diagnostic URL. Expect `diagnostic_version=z2.16`, transformer BF16 plan with separate Q/K/V regions, encoder plan with ordinary weight windows, and nonbinding managed auxiliary candidates. Review GitHub backend and syntax CI. A manual sample export is optional and should be done only in a new, separate scratch directory, never inside the model or managed installation. No production inference until full state-dict mapping and GPU/runtime compatibility are validated.

### Z2.17: exhaustive header-only tensor schema reconciliation

Added backend/morphorum/zimage_schema_validation.py to compare every mapped **name and shape** in standalone scaled-FP8 Z-Image transformer and Qwen3 encoder checkpoints against the **actual managed package** tensor schema. It reads the managed transformer and text-encoder sharded safetensors **index JSON + bounded shard headers only** (not weight payloads), checks all index entries, safe shard names, header/payload byte lengths, overlaps, missing or unindexed tensors, then constructs an independent reference schema.

The original transformer mapping reproduces the upstream Diffusers Z-Image renames, drops upstream-excluded norm_final.weight, splits all fused QKV weights into equal Q/K/V shapes, and checks agreement with Morphorum's earlier complete-source mapping gate. The Qwen encoder is checked separately using its native model.* tensor names and shapes. Only the legacy quantization metadata scaled_fp8 and corresponding .scale_weight scalar entries are excluded from the full name/shape comparison. All other parameters, including F32 and BF16 biases, norms and embeddings, must match.

Read-only diagnostics include checkpoint.schema_validation and auxiliary_encoders[].header.schema_validation, with diagnostic_version z2.17. Results are schema_matches, schema_mismatch, or blocked. Mismatches return exact aggregate counts for missing/extra/shape-disagreeing tensors plus up to 16 examples in each category. Even schema_verified=true means schema evidence only, **not** identical trained weights, verified FP8 conversion, loadability or GPU runtime.

Safety: no full weight read, cache publication, FP8 production conversion, runtime component reuse, GPU load, or mutation of either managed or external model files. Z2.15 and Z2.16 compatibility gates and false readiness flags remain unchanged. In particular, do not invoke the existing full conversion path on FP8 sources.

Windows acceptance: update dev-webui, restart Morphorum, open the existing diagnostic URL, and inspect z2.17 transformer/encoder schema_validation. Both schema_matches would permit planning an isolated streaming conversion experiment. A schema_mismatch or blocked result must be diagnosed before proceeding. No additional download or standalone inference test is required for this step.

### Z2.17.1: Qwen legacy `.scale_input` reconciliation

The first physical Z2.17 output verified all 521 mapped transformer tensors with 34 fused-QKV splits and no mismatches, but the encoder reported 252 unexpected `*.scale_input` tensors against 398 managed reference parameters. The upstream ComfyUI `comfy/utils.py:convert_old_quants` function drops an old-format `.scale_input` only when its scalar equals **exactly 1.0**; a non-unit value is retained as `input_scale`. Z2.17 therefore now performs bounded scalar payload reads of each input scale and excludes **only** input scales that (a) belong to a matching F8_E4M3 weight, (b) have supported scalar F16/BF16/F32 dtype and shape and (c) equal 1.0 exactly. Non-unit, orphan and malformed input scales fail closed. Result reporting includes `discarded_unit_input_scale_count`, making the decision auditable. This is still read-only and still **not** authorization for full conversion or inference.

Next Windows acceptance: rescan the same diagnostic URL after updating `dev-webui` and restarting. For the provided standalone encoder, expect a `schema_matches` only if all 252 extra `.scale_input` values actually equal one; otherwise inspect the explicit `blocked` reason without overriding it. Validate the transformer remains a 521/521 match. No production model paths or managed components change.

### Z2.17.2: audited FP8 input-scale inventory and separate parameter schema

The owner's Z2.17.1 Windows test retained a clean **521/521 transformer schema match**, but rejected at least one **non-unit** Qwen `.scale_input` tensor. Research of upstream ComfyUI `comfy/utils.py:convert_old_quants`, `comfy/quant_ops.py`, and `QUANTIZATION.md` established that `.scale_input` (renamed `input_scale`) is *activation calibration for FP8 quantized execution*, not a model weight tensor. Values equal to one may be omitted by ComfyUI; non-unit values must be retained for any future FP8 runtime rather than ignored.

The new `backend/morphorum/zimage_input_scales.py` reads each legacy input-scale scalar through a strict bounded header parser without touching model weights. It requires a paired `F8_E4M3` weight and `.scale_weight`; supports F32/F16/BF16 scalar input scales; and rejects orphan, malformed, nonfinite, nonpositive or unbounded inputs. The audit reports **all** counts and dtype distribution, unit and non-unit counts, range, and a bounded set of examples. No file is modified or scales destroyed.

`zimage_schema_validation.py` now separates model *parameter names/shapes* from quantization *metadata*. After passing the complete input-scale audit, the model parameter schema excludes `.scale_input` entries regardless of unit/non-unit value, while retaining **all scale evidence** and an explicit `quantization_compatibility.status=fp8_activation_scale_binding_unverified`. The diagnostic exposes `schema_validation.input_scale_metadata` and `schema_validation.quantization_compatibility`. A `schema_matches` result proves **parameter architecture only**. It does **not** approve an FP8 activation kernel, a model loader, or full conversion. `loadable=false`, `runtime_verified=false`, and `conversion_enabled=false` are unconditional.

For a future *fully dequantized BF16 weight-only path*, calibrated FP8 **activation** scales should not enter BF16 `linear` calls because no FP8 activation quantizer is present. An isolated CPU test checks the weight-dequantization result and BF16 linear computation without input-scale use; a separate fake-quantization sanity check confirms that changing FP8 input calibration can change an FP8-quantized activation. This is **not** a proof of model inference, ComfyUI GPU kernel equivalence, or safe BF16 materialization. Both conversion and runtime activation stay disabled.

**Windows acceptance:** update `dev-webui`, restart Morphorum, open the same diagnostic URL. The transformer should remain `521/521` with 34 QKV splits. The Qwen `schema_validation` can now become `schema_matches` for **398/398** model parameters, while `input_scale_metadata.count` should report **252**, including the actual non-unit ranges and examples. Expect `fp8_runtime_verified=false` regardless of results. Review CI before moving into Z2.18 disk-space/memory planning and an isolated conversion experiment.

Upstream reference: https://github.com/Comfy-Org/ComfyUI/blob/master/comfy/utils.py ; https://github.com/Comfy-Org/ComfyUI/blob/master/QUANTIZATION.md .


### Z2.18: explicit standalone FP8-to-BF16 scratch conversion, with preflight

Implemented `backend/morphorum/zimage_fp8_stream.py`, an isolated experimental **CPU-only** chunked converter for the exact observed Z-Image original transformer and Qwen3 encoder formats. It consumes the fully validated Z2.17.2 schemas, handles all original-to-Diffusers tensor renames plus every QKV split, and preserves ordinary BF16/F16/F32 weights while independently converting FP8 weight tensors to BF16 using a per-tensor F32 weight scale cast to BF16 before multiplication. Qwen's 252 non-unit `.scale_input` entries are validated as FP8 activation-calibration metadata. They are **not model parameters** and do not enter a fully-dequantized BF16 weight-only linear path; the original FP8 metadata is never changed. FP8 runtime calibration/binding remains unverified.

`python -m morphorum.zimage_fp8_stream --checkpoint <external.safetensors> --managed-root <managed-Z-Image-Turbo-directory> --family transformer` is **read-only by default**. It provides exact converted safetensors byte count, full parameter count, FP8 tensor count, deterministic per-tensor shapes and output dtypes, a bounded 2 MiB input chunk size, an estimated conversion RAM ceiling (16 MiB, excluding process/model runtime), an additional 2 GiB scratch-volume safety reserve, and a warning that this is not 16 GB GPU-runtime acceptance. Use `--scratch <new-absolute-scratch-directory>` without `--export` to preflight available disk space. The normal per-model `/zimage-diagnostics` response now includes separate read-only `checkpoint.z218_stream_preflight` and encoder `header.z218_stream_preflight`; diagnostic version **z2.18**.

**Only explicit CLI `--export --scratch <new-directory>` performs conversion.** The experimental writer refuses destination collisions, source-directory/managed-installation traversal and symlinks; checks free disk before writing; serializes validated safetensors headers and streams small CPU tensors with constant-size chunks; records per-tensor and full-file SHA-256 hashes; stages output into a temporary directory; checks source size/mtime and exported header and size; and publishes with an exclusive reservation and atomic directory rename. Unexpected errors remove only this invocation's temporary directory and release its lock. The resulting artifact is **NON-LOADABLE** and outside Morphorum's managed checkpoint tree. The legacy production FP8 converter remains blocked. No GPU model, VAE, tokenizer, pipeline or inference is invoked.

Run the transformer and encoder export as two separately named scratch destinations if/when the owner explicitly elects a physical conversion test. Disk requirements are cumulative if retaining both artifacts. **Do not** place them under managed models, enable them for generation, or merge until physical validation and a separately reviewed runtime/offloading phase.

### Console > Diagnostics subtab (Z2.18 UX)

The Console page now has two internal subtabs: **Console logs** (unchanged and preserved) and **Diagnostics**. Diagnostics selects an indexed *external Z-Image checkpoint* and retrieves the same-origin `GET /api/models/{id}/zimage-diagnostics` endpoint, without any fixed LAN address or new backend permission. It displays concise schema/count summaries, searchable field paths and values, top-level section and status filters, copy-complete-JSON and copy-filtered-results actions, and a maximum of 350 rendered rows per view for mobile performance. Result values use DOM `textContent`, not unsanitized HTML. Mobile arrangement is owned by `mobile.css`. The UI is read-only: no conversion, generation or model loading button is added.

Windows acceptance sequence: update `dev-webui`, restart Morphorum, open **Console → Diagnostics**, select the indexed external Z-Image transformer, click **Run diagnostics**. Expect schema 521/521, encoder 398/398, 252 audited non-unit input scales, and two `z218_stream_preflight.status=planned` entries. Use section/search/status filters, copy JSON or filtered evidence, and verify Console logs remain intact after switching tabs. Inspect scratch disk estimates before separately authorizing any real conversion. The Windows browser and full artifact export have not been physically verified by CI, which uses small synthetic safetensors fixtures.

Z2.18 publication hardening: a separate read-only `verify_fp8_stream_artifact(directory)` pass reopens each converted tensor after writing, independently checks its header shape/dtype/offset coverage, streams every tensor again to verify its manifest SHA-256, and checks the complete output digest before the atomic rename. Failure leaves no published scratch directory. Tests cover deliberate output corruption, unexpected nonfinite FP8 values mid-stream, cleanup of temporary files and locks, and insufficient free disk. The scratch verifier **never** returns `loadable=true`.


### Z2.19: Windows physical-conversion acceptance verifier and Diagnostics JSON export

The owner's first Console > Diagnostics test passed, but **Copy JSON** raised `Cannot read properties of undefined (reading 'writeText')` while browsing Morphorum from an `http://192.168.*` LAN address. Browser Clipboard APIs are generally unavailable in insecure HTTP contexts. The panel now uses optional `navigator.clipboard?.writeText` and, when unavailable/denied, a selected temporary textarea with `document.execCommand('copy')`. Failures produce an actionable message rather than throwing. The new **Download JSON** button produces the **complete**, unfiltered diagnostic result as a UTF-8 `.json` file through a client-side Blob/object URL; it requires no clipboard permissions or new API. The file name includes the selected checkpoint and diagnostic version. Switching checkpoints disables copy/download until new diagnostics are fetched. Console logs and filter behavior remain unchanged.

For the next actual Windows acceptance step, `backend/morphorum/zimage_fp8_stream.py` adds **`--verify-existing`** to inspect a separately exported scratch artifact **without writing**. Verification rechecks every output tensor's SHA-256 and full artifact digest, compares exact model names/dtypes/shapes/offsets against the current original checkpoint and managed reference schema, validates the source file path/size/mtime recorded in the manifest, and independently recalculates **bounded start/middle/end sample windows from the original FP8 source** using CPU BF16 reference conversion. Every output tensor is sampled, including all three fused Q/K/V partitions and the separate Qwen encoder. A self-consistent but maliciously rehashed altered output is rejected if a sampled value differs. No source full SHA-256 or whole-model numerical equivalence is claimed, and **neither verification nor export enables loading or inference**.

Use the Morphorum backend Python environment and a **real existing filename**, not an example placeholder. From `PS D:\\Morphorum-test>` the following example uses the owner's indexed checkpoint location. Run `Test-Path` first and confirm `True`. Choose an entirely new scratch directory outside the external models and managed installation.
```powershell
Test-Path "D:\\models\\Checkpoints\\Z-Image\\zImageTurboQuantized_fp8ScaledE4m3fnKJ.safetensors"

# Read-only conversion/disk preflight:
.\\.venv\\Scripts\\python.exe -m morphorum.zimage_fp8_stream --checkpoint "D:\\models\\Checkpoints\\Z-Image\\zImageTurboQuantized_fp8ScaledE4m3fnKJ.safetensors" --family transformer --scratch "D:\\Morphorum-z219-test\\transformer"

# Only when status=planned and scratch_space_sufficient=true, explicitly export:
.\\.venv\\Scripts\\python.exe -m morphorum.zimage_fp8_stream --checkpoint "D:\\models\\Checkpoints\\Z-Image\\zImageTurboQuantized_fp8ScaledE4m3fnKJ.safetensors" --family transformer --scratch "D:\\Morphorum-z219-test\\transformer" --export

# Check source parity and output hashes after successful export:
.\\.venv\\Scripts\\python.exe -m morphorum.zimage_fp8_stream --checkpoint "D:\\models\\Checkpoints\\Z-Image\\zImageTurboQuantized_fp8ScaledE4m3fnKJ.safetensors" --family transformer --scratch "D:\\Morphorum-z219-test\\transformer" --verify-existing
```
The encoder uses the same three modes but `--family encoder`, its separate FP8 encoder source file, and a **different new scratch directory**. Use the `managed_model_location("zimage") / "Z-Image-Turbo"` path configured by your installation; do not guess its location. Real Windows transformer and encoder scratch exports and independent verifications **passed on 2026-10-18**; see the measured acceptance report below. First validate Download JSON and copy fallback, then share the Z2.18 preflight sizes and disk results; only run exports with sufficient disk space. Keep `dev-webui`, `main`, the original checkpoints and managed Z-Image untouched. Any GPU/offload testing is a distinct, subsequent milestone.

Z2.19 CLI convenience: `--managed-root` is optional for the three physical acceptance commands. When omitted, Morphorum resolves the managed package from its configured `managed_model_location("zimage") / "Z-Image-Turbo"` setting; this avoids guessing the path. You must still supply the real checkpoint, family and scratch directory. The `--verify-existing` mode never creates or overwrites files.

Z2.19 preflight troubleshooting: Literal documentation placeholders such as `"<transformer.safetensors>"` are not Windows paths. PowerShell sends those characters unchanged, producing `WinError 123` or a misleading general `blocked` status. The CLI now rejects angle-bracket checkpoint placeholders explicitly, suggests `Test-Path` when the file is missing, and surfaces actual `schema_mismatch` counts or lower-level schema reasons instead of collapsing all failures into “Z2.17.2 checks must pass.” These messages are read-only diagnostic improvements; all conversion and runtime safeguards remain unchanged.

### Z2.19 physical acceptance: Windows transformer + Qwen3 encoder (2026-10-18)

**Acceptance: PASS for both exported scratch artifacts.** These are owner-provided Windows outputs from the unmodified production-path sandbox exporter. Original models and managed Z-Image pipeline were not overwritten. Converted results remain explicitly **non-loadable**, with `conversion_enabled=false` and `runtime_verified=false`; this milestone grants **no** inference or application loader approval.

| Metric | Z-Image transformer | Qwen3 text encoder |
|---|---:|---:|
| Original checkpoint size | 6,158,115,074 bytes | 4,411,721,216 bytes |
| Converted BF16 safetensors size | 12,311,963,391 bytes | 8,044,981,765 bytes |
| Managed-schema mapped tensors | 521/521 | 398/398 |
| FP8 converted tensors | 276 | 252 |
| Input activation calibration scales inspected | 0 | 252 |
| Sample windows checked against original FP8 | 1,563 | 1,194 |
| FP8 sample windows checked | 828 | 756 |
| Sample elements checked | 50,016 | 38,208 |
| Sample numerical mismatches | **0** | **0** |
| Full scratch artifact hash verification | **PASS** | **PASS** |
| Source-to-output sample parity | **PASS** | **PASS** |

**Transformer artifact:** `D:\Morphorum-z219-test\transformer\diffusion_pytorch_model.safetensors`  
SHA-256: `960bf96c6095bad51f520a6c343a21b15ebdbb87cb69b961e1b43ddfbf879110`

**Text encoder artifact:** `D:\Morphorum-z219-test\encoder\model.safetensors`  
SHA-256: `fca14c4c9242e38deae2c5205c4be04eed67db99f82d818245b6cde70e1e3a6a`

The encoder `--verify-existing` was run **twice**, with identical passing counts. Together, the outputs contain **20,356,945,156 bytes (18.96 GiB)** of model artifacts, greater than a 16 GiB GPU even before text processing, VAE and activations. This establishes file conversion consistency and source-sampled numerical parity, **not** full source numerical equivalence, source-file SHA-256 equality, runtime component compatibility, or workable inference on 16 GiB VRAM.

**Next milestone (Z2.20 proposal, not implemented by this acceptance record):** design a separate *experimental-only* inference preflight with explicit scratch path/config binding and immutable managed tokenizer, VAE and scheduler inputs. First estimate RAM/VRAM/offloading and ensure independent artifact manifests are verified; then validate strict model initialization and tiny low-resource smoke tests in a non-production execution route. Keep the managed generation pipeline and external model's disabled status unchanged until physical inference acceptance and separately approved integration.


### Z2.20a: isolated inference capacity and artifact preflight (implementation)

Added `backend/morphorum/zimage_inference_preflight.py` and synthetic guard tests in `tests/test_zimage_inference_preflight.py`. This is **read-only and non-executable**: it never imports model weights, creates a pipeline, moves files, changes the managed model, marks a standalone checkpoint ready, or authorizes inference. It checks distinct scratch directories, family-bound immutable Z2.19 manifests, converted weight filenames/sizes, managed tokenizer/VAE/scheduler directory presence, and by default full per-tensor plus artifact SHA-256 through the Z2.18 verifier. It reports a conservative capacity heuristic and whether the exact export hashes were checked. It does **not** verify runtime config compatibility or scheduler semantics.

On the Windows test machine, from `D:\Morphorum-test` on `dev-webui`:

```powershell
git pull
# Determine installed system RAM (GiB), then substitute the reported number below:
[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 2)
.\.venv\Scripts\python.exe -m morphorum.zimage_inference_preflight --transformer "D:\Morphorum-z219-test\transformer" --encoder "D:\Morphorum-z219-test\encoder" --ram-gib 32 --vram-gib 16
```

**Important:** `--ram-gib 32` is an *example only*; replace with the actual measured RAM value. `--managed-root` can optionally specify the existing managed Z-Image-Turbo directory, otherwise it resolves from settings. This preflight can take time when hashing 18.96 GiB of weights. `--skip-hashes` is a diagnostic speed shortcut that cannot count as integrity acceptance.

A `capacity_candidate_unverified` result means only that weight files fit the very rough RAM/VRAM heuristic with fixed reserves, not that inference can work. `capacity_warning_unverified` indicates likely offload requirements; `blocked` indicates failed inputs or artifact checks. The transformer itself is about 11.47 GiB of BF16 weights, leaving insufficient proven margin for a fully GPU-resident 16 GiB workflow; the preferred *experiment* is sequential Qwen CPU offload and transformer/group offload, subject to physical performance testing. Static reserves of 3 GiB VRAM and 8 GiB RAM are intentionally not a complete activation/allocator model. **Next:** Z2.20b isolated configuration and CPU initialization probes, followed separately by a deliberately gated Z2.20c low-resolution inference smoke test. Neither is implemented here. Keep the production managed loader and `main` unchanged.


### Z2.20a Windows physical acceptance (2026-10-18)

**PASS for read-only memory/integrity preflight.** Owner ran the SHA-256-validating CLI on RTX 4080 SUPER 16 GiB / system RAM 63.59 GiB. Result `capacity_candidate_unverified`, `artifact_hashes_checked=true`, `loadable=false`, `inference_attempted=false`. Weight footprints: transformer 11.466 GiB, Qwen encoder 7.492 GiB, combined 18.959 GiB. Managed installation untouched. This confirms integrity and basic capacity gating only, not model execution or runtime compatibility.

### Z2.20b1: read-only component configuration/schema binding probe

Added `backend/morphorum/zimage_config_probe.py` with separate test coverage. It reads managed `model_index.json`, transformer/encoder/VAE configs, tokenizer_config and scheduler_config; checks explicit component entries, scratch family manifests and expected weight sizes, and compares every converted tensor's name, shape and ordinary float dtype to the managed reference sharded headers. It imports no Torch, loads no model, does not hash the 19 GiB scratch payload and does not enable generation. This phase is a *configuration candidate* check, not CPU initialization or GPU inference.

Physical Windows command from Morphorum root after `git pull`:

```powershell
.\.venv\Scripts\python.exe -m morphorum.zimage_config_probe --transformer "D:\Morphorum-z219-test\transformer" --encoder "D:\Morphorum-z219-test\encoder"
```

Expected success status: `config_shape_candidate_unverified`. If blocked, inspect `reasons` to identify missing/mismatched configs; do not modify managed files to silence the probe. **Next:** Z2.20b2 guarded CPU model-class initialization proof and then Z2.20c minimal inference smoke test. Wait for physical b1 results before enabling either. `main` is unchanged.


### Z2.20b1 Windows physical acceptance (2026-10-18)

**PASS:** `config_shape_candidate_unverified`; managed ZImagePipeline component config bindings: FlowMatchEulerDiscreteScheduler, Qwen3Model, Qwen2Tokenizer, ZImageTransformer2DModel, AutoencoderKL. BF16 scratch tensor schemas: transformer 521, encoder 398. No weights initialized or inference attempted.

### Z2.20b2: experimental meta-only class construction (physical test pending)

Added `backend/morphorum/zimage_meta_probe.py` and a fail-closed regression test. Requires b1 config/schema probe, imports model classes, constructs them on the PyTorch `meta` device using managed configs, checks **all** parameters and buffers remain on `meta`, then discards both model objects. Does not read scratch weights, initialize real CPU/GPU parameters, run forward, enable standalone models, or change managed package. This is a **class-constructor compatibility probe**, not yet the full CPU weight-loading test. Run with Morphorum stopped if possible:

```powershell
git pull
.\.venv\Scripts\python.exe -m morphorum.zimage_meta_probe --transformer "D:\Morphorum-z219-test\transformer" --encoder "D:\Morphorum-z219-test\encoder"
```

Expected: `meta_initialized_unverified`, each component initialized true, `weights_loaded=false`, `cuda_used=false`. Any `blocked` status warrants class/config investigation instead of editing managed files. Next after physical acceptance: separately gated CPU load of actual scratch tensors using explicit offload strategy; no full-GPU inference yet.
