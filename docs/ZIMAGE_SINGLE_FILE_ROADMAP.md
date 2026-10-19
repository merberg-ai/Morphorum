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


### Z2.20b2 Windows physical acceptance (2026-10-18)

**PASS:** `meta_initialized_unverified` on the owner's Windows host. Transformer: 521 parameter tensors, 6,154,908,736 elements; encoder: 398 parameter tensors, 4,022,468,096 elements. All parameters and buffers resided on PyTorch `meta`; `weights_loaded=false`, `cuda_used=false`, `inference_attempted=false`, `loadable=false`. This validates construction of both classes from managed configurations, **not** real CPU weight binding, forward computation or generation. Next phase requires explicit sequential CPU-only weight loading and guards against accidental CUDA allocation; managed files remain immutable.


### Z2.20b3: bounded real CPU scratch tensor materialization

Implemented `backend/morphorum/zimage_cpu_probe.py` with fail-closed tests. After successful b1 schema/config preflight and full scratch integrity hashing, it materializes **one bounded tensor per model family**, sequentially, via `safetensors.safe_open(..., device="cpu")`, checking shape and finite values. Sample size defaults to at most 16 MiB, configurable 1–64 MiB. No production model is created, no whole checkpoint is loaded, no GPU is used, and no model is marked ready. This is deliberately a stepping-stone to actual full CPU model weight loading, *not* that loading itself.

Windows physical test (from Morphorum root on dev-webui):

```powershell
git pull
.\.venv\Scripts\python.exe -m morphorum.zimage_cpu_probe --transformer "D:\Morphorum-z219-test\transformer" --encoder "D:\Morphorum-z219-test\encoder"
```

Expected result: `cpu_samples_verified_nonloadable`, two sample entries, `weights_fully_loaded=false`, `gpu_used=false`, `loadable=false`. This rehashes 18.96 GiB of scratch weights, which is intentional for the first materialization. No code runs on CUDA. Continue to sequential, fully bound CPU model experiments only after physical acceptance, memory telemetry, and CI review.


### Z2.20b3 Windows physical acceptance (2026-10-18)

**PASS:** `cpu_samples_verified_nonloadable`; default hash verification passed and real scratch BF16 tensors materialized on CPU. Transformer sample `layers.0.adaLN_modulation.0.weight`, shape [15360,256], 7,864,320 bytes; encoder sample `model.layers.0.self_attn.k_proj.weight`, shape [1024,2560], 5,242,880 bytes. Both all-finite, no GPU, no full weights or inference, `loadable=false`. Next: explicitly gated *sequential* full CPU binding with memory telemetry, leaving GPU and managed production route unused.


### Z2.20b4: explicitly gated sequential full CPU binding (unverified implementation)

A *separate* CLI module `backend/morphorum/zimage_cpu_binding.py` accepts one `--family` at a time and requires `--execute-cpu-binding`. Preconditions: Z2.20b1 schema/config match, full scratch SHA-256 verification, CUDA masked using `CUDA_VISIBLE_DEVICES=-1` before Python imports Torch, Torch confirms CUDA unavailable, and available system RAM at least twice the chosen artifact size plus 12 GiB. Only then does a local-files-only model class `from_pretrained` load the explicitly selected scratch BF16 weights with a managed reference config. No generation, GPU inference or production model registry wiring. Successful import is `cpu_weights_bound_unverified` and is not a runtime verification. This may fail due to Diffusers/Transformers API differences; the failure details are valuable physical test evidence. CI and Windows test remain pending.

Run transformer first *in its own PowerShell process*, with Morphorum/ComfyUI image jobs stopped to preserve memory:

```powershell
git pull
$env:CUDA_VISIBLE_DEVICES="-1"
.\.venv\Scripts\python.exe -m morphorum.zimage_cpu_binding --transformer "D:\Morphorum-z219-test\transformer" --encoder "D:\Morphorum-z219-test\encoder" --family transformer --execute-cpu-binding
Remove-Item Env:CUDA_VISIBLE_DEVICES
```

Do not run the encoder in the same process. When ready, launch another fresh CLI invocation with `--family encoder` and the same masked CUDA setting. If the first run is blocked, stop and examine its `reasons`; do not modify managed Z-Image files or weaken guards to force it. Console memory use can spike well beyond file size. `main` unchanged.


### Z2.20b4 Windows first transformer attempt and targeted fix (2026-10-18)

First explicit transformer CPU bind returned `blocked` after successful artifact/integrity and memory gating (`available_ram_gib=50.94`, `required_available_ram_gib=34.93`, `cuda_used=false`): Diffusers `ModelMixin.from_pretrained` searched the intentionally weights-only scratch transformer directory for `config.json`, even though a managed config dict was provided. This is a **loader packaging/API mismatch**, not evidence that the converted weights are invalid.

Corrected the *experimental transformer-only* loading path to instantiate `ZImageTransformer2DModel.from_config(managed_config)` under `torch.device("meta")`, followed by `accelerate.load_checkpoint_and_dispatch` with an explicit scratch `.safetensors` file, `device_map={"": "cpu"}`, `dtype=torch.bfloat16`, and `strict=True`. Encoder loader path and production model handling are unchanged. This is not yet physically verified and might reveal further model-loader compatibility issues. Re-run the same masked-CUDA transformer CLI from the previous section. Do not copy configs into scratch, change managed components, or enable external model selection.


### Z2.20b4 transformer Windows acceptance (2026-10-18)

**PASS for transformer CPU weight binding.** With `CUDA_VISIBLE_DEVICES=-1`, the explicit `accelerate_meta_to_cpu_strict` route successfully bound all **521 parameter tensors / 6,154,908,736 parameter elements** using the converted standalone transformer scratch artifact. Available RAM at start: 50.9 GiB, minimum configured available RAM: 34.93 GiB. The safetensors metadata fallback warning ("Defaulting to 'pt' metadata") was nonfatal. `status=cpu_weights_bound_unverified`, `cuda_used=false`, `inference_attempted=false`, `runtime_verified=false`, `loadable=false`.

**Next physical gate: encoder only**, in a separate fresh CPU-only process. The current encoder loader uses Transformers `Qwen3Model.from_pretrained` with explicit managed `Qwen3Config` and scratch encoder directory. It has not been physically validated and could require the same kind of config/weight-path separation fix as the transformer. Do not infer encoder acceptance from the transformer result or enable application selection.

```powershell
$env:CUDA_VISIBLE_DEVICES="-1"
.\.venv\Scripts\python.exe -m morphorum.zimage_cpu_binding --transformer "D:\Morphorum-z219-test\transformer" --encoder "D:\Morphorum-z219-test\encoder" --family encoder --execute-cpu-binding
Remove-Item Env:CUDA_VISIBLE_DEVICES
```


### Z2.20b4 encoder Windows physical acceptance (2026-10-18)

**PASS for encoder CPU weight binding.** With `CUDA_VISIBLE_DEVICES=-1`, the Transformers `transformers_local_cpu` path bound **398/398 parameter tensors / 4,022,468,096 parameter elements**, loading progress 100%. Starting available RAM 50.91 GiB, minimum available RAM threshold 26.98 GiB. Result `status=cpu_weights_bound_unverified`, `cuda_used=false`, `inference_attempted=false`, `runtime_verified=false`, `loadable=false`. The transformer was independently accepted earlier (521/521, 6,154,908,736 elements). **Z2.20b4 sequential CPU weight-binding acceptance is complete for both components.** This is not evidence that transformer and encoder can coexist with the VAE and activations or execute a forward pass. Follow-on Z2.20c should first measure a guarded single-component forward/pipeline resource plan and reuse immutable managed tokenizer/scheduler/VAE through isolated references; keep production loading disabled and `main` unchanged.


### Z2.20c1: isolated auxiliary-component structural probe

Following successful physical Z2.20b4 transformer and encoder CPU binding, added `backend/morphorum/zimage_aux_probe.py` and `tests/test_zimage_aux_probe.py` on `dev-webui`. This CLI requires an isolated process with `CUDA_VISIBLE_DEVICES=-1`, reruns the Z2.20b1 scratch/managed configuration gate, tokenizes and decodes a short local sample with managed Qwen2Tokenizer, creates two CPU scheduler timesteps from the managed FlowMatchEulerDiscreteScheduler configuration, and constructs managed AutoencoderKL **on meta only**. No VAE weights are loaded, no image is generated, no scratch transformer/encoder weights are rebound, and no managed files are modified. It returns `auxiliary_components_structurally_verified` when all checks pass, but `loadable=false`, `runtime_verified=false`, `inference_attempted=false`. This does not yet establish compatibility of conditioning tensor semantics or genuine pipeline inference.

Windows physical test (from `D:\Morphorum-test`):

```powershell
git pull
$env:CUDA_VISIBLE_DEVICES="-1"
.\.venv\Scripts\python.exe -m morphorum.zimage_aux_probe --transformer "D:\Morphorum-z219-test\transformer" --encoder "D:\Morphorum-z219-test\encoder"
Remove-Item Env:CUDA_VISIBLE_DEVICES
```

Next only after successful physical acceptance: Z2.20c2 explicitly gated tiny-model forward and real-memory telemetry; Z2.20c3 the isolated minimal image generation smoke test. The production managed pipeline and `main` remain unchanged.


### Z2.20c1 physical Windows acceptance (2026-10-18)

**PASS:** `auxiliary_components_structurally_verified`. Managed Qwen2Tokenizer encoded/decoded a six-token prompt. Managed FlowMatchEulerDiscreteScheduler returned two CPU timesteps (1000.0, 8.928571701049805). Managed AutoencoderKL constructed on meta with 244 parameter tensors and 83,819,683 elements. `cuda_used=false`, `vae_weights_loaded=false`, `inference_attempted=false`, `loadable=false`. This verifies component construction, not the correctness of conditioning embeddings, VAE decoding or an image-generation pipeline.

Z2.20c2 should begin with isolated, explicitly CPU-only low-memory scheduler numerical stepping (real finite tensors and read-only RSS telemetry) before full multi-billion-parameter model forward passes. Later full forward tests require bounded dimensions, limited timesteps and deliberate GPU-offload planning.


### Z2.20c2a: isolated numerical scheduler step (physical test pending)

Added `backend/morphorum/zimage_scheduler_step_probe.py` and gated tests. This is a *real CPU numerical computation* using the existing managed FlowMatchEulerDiscreteScheduler. It operates on a tiny (1,16,8,8) synthetic float32 latent, performs two scheduler steps with bounded synthetic predictions, checks shape/finiteness, and records process RSS before/after. It requires masked CUDA and passing scratch/managed config preflight. It loads **no transformer, encoder or VAE weights**, executes **no neural-network forward pass**, and does not generate images or enable standalone loading.

From `D:\Morphorum-test` on `dev-webui`:

```powershell
git pull
$env:CUDA_VISIBLE_DEVICES="-1"
.\.venv\Scripts\python.exe -m morphorum.zimage_scheduler_step_probe --transformer "D:\Morphorum-z219-test\transformer" --encoder "D:\Morphorum-z219-test\encoder"
Remove-Item Env:CUDA_VISIBLE_DEVICES
```

Success status `cpu_scheduler_steps_verified`; inspect two-step numerical and RSS report. CI and physical validation pending. Z2.20c2b will be a distinct, explicitly gated neural forward experiment after accepting this step. Keep `main` and managed Z-Image untouched.


### Z2.20c2a Windows physical acceptance (2026-10-18)

**PASS:** `cpu_scheduler_steps_verified`; managed FlowMatchEulerDiscreteScheduler performed two numerical steps on a CPU float32 tensor of shape [1,16,8,8] with finite output. Process RSS before 675.01 MiB, after 676.94 MiB (delta +1.93 MiB). `cuda_used=false`, `inference_attempted=false`, `transformer_forward_attempted=false`, `loadable=false`. This is not a network forward pass or image generation. Proceed to separately guarded Z2.20c2b CPU VAE smoke tests, then larger components as justified by physical results.


### Z2.20c2b: guarded managed VAE CPU neural-network forward (awaiting Windows test)

Added `backend/morphorum/zimage_vae_forward_probe.py` and fail-closed unit guards in `tests/test_zimage_vae_forward_probe.py`. This is the first **actual learned-weight neural-network forward** in this inference program: it constructs a real CPU float32 AutoencoderKL from the *unchanged* managed Z-Image VAE, then decodes a tiny all-zero latent [1, configured_latent_channels, 8, 8], validates RGB output shape/finiteness, and reports process RSS, output min/max and weight tensor count. It enforces an explicit `--execute-vae-forward` opt-in, masked CUDA, passing standalone scratch/managed schema preflight, and at least 12 GiB available RAM. It does not bind the experimental standalone transformer or Qwen3 encoder, run a diffusion pipeline, save an image, or allow production loadability. Network forward success is **not** proof the standalone checkpoint generates a correct image.

Run from `D:\Morphorum-test` with idle AI workloads, and inspect the JSON output:

```powershell
git pull
$env:CUDA_VISIBLE_DEVICES="-1"
.\.venv\Scripts\python.exe -m morphorum.zimage_vae_forward_probe --transformer "D:\Morphorum-z219-test\transformer" --encoder "D:\Morphorum-z219-test\encoder" --execute-vae-forward
Remove-Item Env:CUDA_VISIBLE_DEVICES
```

Expected success: `vae_cpu_forward_verified_nonloadable` with `forward_attempted=true`, `output_finite=true`, `cuda_used=false`, `loadable=false`, `runtime_verified=false`. Windows acceptance and CI are still pending. Subsequent stage: explicitly guarded external encoder/transformer forward with real memory and shape diagnostics before assembling an isolated image-generation pipeline. No changes to `main` or managed model artifacts.


### Z2.20c2b Windows physical acceptance (2026-10-18)

**PASS:** `vae_cpu_forward_verified_nonloadable`. With CUDA masked and 50.75 GiB RAM available, the unchanged managed AutoencoderKL VAE decoded a CPU float32 latent [1,16,8,8] to finite float32 RGB [1,3,64,64] with numerical minimum -0.4819101393 and maximum 0.3444057107. All 244 parameter tensors were bound. Process RSS went from 738.65 MiB before VAE loading to 1096.39 MiB after decode (these readings include model loading and computation; they are **not** an isolated decode-memory delta). `forward_attempted=true`, `inference_attempted=false`, `cuda_used=false`, `loadable=false`. This establishes a managed VAE neural forward, not standalone transformer/encoder conditioning or image generation. Next: isolated experimental Qwen3 encoder forward, then transformer.


### Z2.20c2c: standalone Qwen3 CPU neural forward (Windows test pending)

Added `backend/morphorum/zimage_encoder_forward_probe.py` and guard tests. After exact scratch/schema validation and **full encoder scratch hash verification**, this standalone CLI checks available RAM (2× encoder file bytes + 12 GiB), requires masked CUDA and explicit `--execute-encoder-forward`, loads the standalone BF16 398-tensor Qwen3Model weights using managed config, and performs a single six-ish-token short-prompt CPU forward with `use_cache=False`. It validates finite hidden states, output shape/device and reports RSS before load, after load and after forward. This is **not** end-to-end image inference, transformer execution, or proof of correct prompt conditioning. The managed tokenizer/config are read from their existing directories; no managed files are overwritten.

Windows command from `D:\Morphorum-test`:

```powershell
git pull
$env:CUDA_VISIBLE_DEVICES="-1"
.\.venv\Scripts\python.exe -m morphorum.zimage_encoder_forward_probe --transformer "D:\Morphorum-z219-test\transformer" --encoder "D:\Morphorum-z219-test\encoder" --execute-encoder-forward
Remove-Item Env:CUDA_VISIBLE_DEVICES
```

Expected `encoder_cpu_forward_verified_nonloadable`, `forward_attempted=true`, `finite=true`, `loadable=false`. This is a RAM-intensive isolated experiment; close competing generation workloads beforehand. Stop and diagnose any failure before an experimental transformer forward. CI and physical testing pending; `main` unchanged.


### Z2.20c2c Windows physical acceptance (2026-10-18)

**PASS:** isolated standalone BF16 Qwen3 encoder CPU forward successfully computed finite `torch.bfloat16` hidden states shape [1,6,2560] from a six-token prompt. All 398 parameter tensors bound; scratch full-hash validation passed. Process RSS before load 784.23 MiB, after load 8465.21 MiB, after forward 8477.86 MiB (+12.65 MiB over post-load). Available RAM 50.94 GiB, configured minimum 26.98 GiB. `cuda_used=false`, `loadable=false`, `runtime_verified=false`, `inference_attempted=false`. This is genuine neural computation by converted standalone encoder, but not proof of Z-Image pipeline conditioning semantics, transformer execution or image synthesis. Next phase should verify actual ZImageTransformer2DModel forward API and develop a deliberately gated low-token CPU/GPU experiment, without modifying the managed runtime.


### Z2.20c2d1: standalone transformer forward API contract probe (physical test pending)

Added `backend/morphorum/zimage_transformer_contract_probe.py` and isolation tests. Constructs only a **meta-device** ZImageTransformer2DModel using the existing managed transformer config and inspects its actual installed `forward` signature and selected dimension fields. Requires masked CUDA and passing b1 scratch/schema config inspection. It does not load any weight tensor or execute a forward call, and always reports `weights_loaded=false`, `forward_attempted=false`, `loadable=false`. This intermediate gate is needed to shape a safe, low-token, explicitly bounded **real** standalone transformer forward call for the installed Diffusers version, rather than guessing an API or allocating 11.47 GiB of weights blindly.

Windows command from `D:\Morphorum-test`:

```powershell
git pull
$env:CUDA_VISIBLE_DEVICES="-1"
.\.venv\Scripts\python.exe -m morphorum.zimage_transformer_contract_probe --transformer "D:\Morphorum-z219-test\transformer" --encoder "D:\Morphorum-z219-test\encoder"
Remove-Item Env:CUDA_VISIBLE_DEVICES
```

Expected `transformer_forward_contract_inspected`. Review `forward_parameters` and `config_fields` before developing the separately gated full transformer forward. CI and physical acceptance pending. `main` remains unchanged.


### Z2.20c2d1 Windows acceptance and Z2.20c2d2 transformer CPU forward

**c2d1 PASS (2026-10-18):** `transformer_forward_contract_inspected`; actual installed signature requires `x, t, cap_feats`; config `in_channels=16`, `all_patch_size=[2]`. Meta construction counted 521 parameter tensors and 6,154,908,736 elements. All weights remained unloaded and CUDA masked.

**c2d2 implemented, physical testing pending:** `backend/morphorum/zimage_transformer_forward_probe.py` runs only as an explicitly authorized isolated process. It checks scratch config/schema and the full converted transformer artifact hash, verifies free RAM is at least 2x weight file + 16 GiB, enforces masked CUDA, loads 521 BF16 transformer weights onto CPU using strict Accelerate meta binding (the already physically verified Z2.20b4 method), then calls forward on a minimal synthetic latent `[16,1,4,4]` (C,F,H,W) and a one-token synthetic caption embedding `[1,2560]` using `t=[0.5]`. This is a **mathematical forward test only**; zero captions are not actual prompt conditioning. Inspect return container, finite outputs, expected shape, and process RSS. No pipeline, VAE, generation, GPU offloading, files written, or application loader authorization.

Run on Windows with competing AI jobs stopped:

```powershell
git pull
$env:CUDA_VISIBLE_DEVICES="-1"
.\.venv\Scripts\python.exe -m morphorum.zimage_transformer_forward_probe --transformer "D:\Morphorum-z219-test\transformer" --encoder "D:\Morphorum-z219-test\encoder" --execute-transformer-forward
Remove-Item Env:CUDA_VISIBLE_DEVICES
```

Success: `transformer_cpu_forward_verified_nonloadable`, `output_finite=true`, `parameter_tensors_bound=521`, `loadable=false`. If blocked, preserve diagnostics before modifying code or proceeding. CI and physical acceptance remain pending. `main` and the managed Z-Image model remain unchanged.


### Z2.20c2d2 Windows physical acceptance (2026-10-18)

**PASS:** `transformer_cpu_forward_verified_nonloadable`. The converted BF16 standalone transformer loaded and executed a real CPU forward with all 521 parameter tensors bound. Input latent [16,1,4,4], synthetic caption [1,2560], timestep 0.5; finite BF16 output [16,1,4,4]. CPU-only, no image inference. Available RAM 50.9 GiB, required guarded RAM 38.93 GiB. Process RSS before load 733.49 MiB, after load 745.62 MiB, after forward 12503.03 MiB. The small post-load RSS despite 11.466 GiB of weights likely reflects memory mapping or lazy resident-page accounting; these observations do not establish peak RAM usage or GPU offload feasibility. Safetensors missing metadata fallback warning was nonfatal. `loadable=false`, `runtime_verified=false`, `inference_attempted=false`.

**Gate completed:** independent real forward computation now passed for converted external Qwen3 encoder, converted external Z-Image transformer, and unchanged managed VAE. Next is a separate full-pipeline composition and offload compatibility phase, not automatic approval to expose external checkpoints in normal generation or merge to main.


### Z2.20c3a: isolated standalone pipeline assembly (implementation, Windows acceptance pending)

Committed `backend/morphorum/zimage_pipeline_assembly_probe.py` and regression guards to `dev-webui`. Requires explicit `--execute-pipeline-assembly`, a new process with masked CUDA, scratch configuration/schema verification, complete SHA-256 verification for both BF16 artifacts and available RAM at least both weight files plus 18 GiB reserve. Loads existing managed tokenizer/scheduler/VAE read-only and binds both converted scratch models on CPU through the earlier independently accepted techniques; verifies all CPU model parameters and constructs an isolated `ZImagePipeline` object. **No call to the pipeline, no image generation, no saved output, no model registration/UI loader changes.** Status `pipeline_assembled_nonloadable` still means `loadable=false` and `runtime_verified=false`. Full integration and offload require separate physical tests.

On Windows, with Morphorum/ComfyUI jobs idle, run:

```powershell
git pull
$env:CUDA_VISIBLE_DEVICES="-1"
.\.venv\Scripts\python.exe -m morphorum.zimage_pipeline_assembly_probe --transformer "D:\Morphorum-z219-test\transformer" --encoder "D:\Morphorum-z219-test\encoder" --execute-pipeline-assembly
Remove-Item Env:CUDA_VISIBLE_DEVICES
```

CI and Windows physical acceptance pending. Keep `main`, production managed package and original FP8 checkpoints unchanged.


### Z2.20c3a Windows physical acceptance (2026-10-18)

**PASS:** `pipeline_assembled_nonloadable`. Combined isolated CPU `ZImagePipeline` constructed with managed FlowMatchEulerDiscreteScheduler, Qwen2Tokenizer, AutoencoderKL and converted scratch Qwen3Model and ZImageTransformer2DModel. Parameter tensors bound: encoder 398, transformer 521, VAE 244 (total 1,163); available RAM at preflight 50.68 GiB, minimum guarded 36.96 GiB. Process RSS before assembly 738.53 MiB and after 8838.98 MiB. That snapshot likely does not fully capture memory-mapped transformer pages or peak allocations. `cuda_used=false`, `generation_attempted=false`, `loadable=false`, `runtime_verified=false`. Safetensors metadata fallback warning was nonfatal.

Next: Z2.20c3b **non-executing** device-placement/offload planning for the 16 GiB RTX 4080 SUPER, followed by a separately gated physical GPU test and only then a standalone inference smoke test. The existing managed pipeline is unchanged.


### Z2.20c3b1: read-only offload strategy preflight (Windows acceptance pending)

Added `backend/morphorum/zimage_offload_plan.py` plus safety tests. It checks existing component/weights manifests and (unless `--skip-hashes`) full scratch SHA-256 using the physically verified Z2.19 verifier, then reports the two BF16 weight footprints versus a user-provided VRAM budget with a 3 GiB *heuristic* reserve. It imports no Torch/CUDA and loads no weights, never exposes a selectable standalone checkpoint and does not run generation. On 16 GiB VRAM it assesses component-at-a-time CPU offload as a *candidate*, not a verified runtime strategy; model hooks, allocator spikes, activation peaks, decoder memory, and numerical correctness remain unverified.

Windows read-only preflight:

```powershell
git pull
.\.venv\Scripts\python.exe -m morphorum.zimage_offload_plan --transformer "D:\Morphorum-z219-test\transformer" --encoder "D:\Morphorum-z219-test\encoder" --vram-gib 16 --ram-gib 63.59
```

Expected `offload_plan_unverified`; `full_pipeline_cuda_resident_safe=false`. Optionally supply `--free-vram-gib` from a separately measured idle GPU reading; do not treat total GPU capacity as simultaneously free. Physical testing and CI pending. Next c3b2 requires separately authorized and monitored GPU placement tests; c3c is an actual image smoke test. Keep `main` and managed installation unchanged.


### Z2.20c3b1 Windows physical acceptance (2026-10-18)

**PASS for static planning only:** `offload_plan_unverified`, both scratch hashes verified. Transformer 11.466 GiB, encoder 7.492 GiB, combined 18.959 GiB. A hypothetical 16 GiB GPU with fixed 3 GiB reserve yields 13.0 GiB weight-only budget; either component's static weights fit separately, but the full pipeline does not. `cuda_initialized=false`, `gpu_weights_loaded=false`, `generation_attempted=false`, `loadable=false`. No *free* VRAM reading supplied (`vram_free_input_gib=null`). This is not an actual CUDA placement acceptance; attention workspaces, activations, transfer spikes and VAE remain unverified.


### Z2.20c3b2: bounded CUDA placement telemetry (Windows test pending)

Implemented `backend/morphorum/zimage_gpu_placement_probe.py` with opt-in and limit regression tests. This separate diagnostic **does not load either Z-Image model or assemble a pipeline**. It requires explicit `--execute-gpu-probe`, checks current free/total VRAM and a configurable reserve (default 3 GiB), transfers 16 MiB of synthetic BF16 data CPU→GPU, performs finite CUDA arithmetic, synchronizes, and reports device, allocator peak and free-memory readings. It limits transfers to 1–64 MiB and rejects processes with CUDA explicitly masked. This tests **CUDA allocation/transfer only**, not layerwise/offload hooks, model execution, transformer fit or successful pipeline inference. A passing result does not authorize normal model selection.

On Windows with heavy GPU jobs idle, from `D:\Morphorum-test`:

```powershell
git pull
.\.venv\Scripts\python.exe -m morphorum.zimage_gpu_placement_probe --execute-gpu-probe --max-mib 16 --reserve-gib 3
```

Expected `bounded_gpu_transfer_verified_nonloadable` with real available GPU memory numbers. Do not set `CUDA_VISIBLE_DEVICES=-1` for this experiment. CI and physical test pending; `main` remains unchanged. Next only after acceptance: genuine model-component GPU/offload path testing before c3c image smoke.


### Z2.20c3b2 Windows physical acceptance (2026-10-18)

**PASS:** `bounded_gpu_transfer_verified_nonloadable` on NVIDIA GeForce RTX 4080 SUPER. Total VRAM 15.992 GiB, free before transfer 14.708 GiB, free during test 14.597 GiB; 16 MiB BF16 synthetic transfer and arithmetic finite, PyTorch allocator peak 56.0 MiB (baseline 0). CUDA initialized, no model weights loaded, no generation. These measurements do **not** prove model GPU placement or offloading feasibility. Continue to independent experimental encoder placement after strictly checking free VRAM and reserve.


### Z2.20c3b3: real standalone encoder GPU placement (physical acceptance pending)

Committed `backend/morphorum/zimage_encoder_gpu_probe.py` with opt-in guards. After config/schema and complete encoder scratch SHA-256 validation, it requires available RAM for the CPU load and actual *measured* free CUDA VRAM exceeding the 7.492 GiB encoder file plus 3 GiB reserve (configurable 2–8 GiB). It loads the 398-tensor BF16 external Qwen3Model from scratch on CPU, checks that all parameters are bound, rechecks free VRAM, moves the encoder to GPU, verifies all parameters on CUDA, collects PyTorch CUDA allocated/peak and free VRAM, then attempts to move back to CPU and release CUDA cache. It runs **no text forward, transformer inference or generation**; successful status `encoder_cuda_placement_verified_nonloadable` is only a component placement proof. This remains experimental, not permission to enable standalone models in Morphorum.

From `D:\Morphorum-test` on `dev-webui`, with other GPU jobs stopped:

```powershell
git pull
.\.venv\Scripts\python.exe -m morphorum.zimage_encoder_gpu_probe --transformer "D:\Morphorum-z219-test\transformer" --encoder "D:\Morphorum-z219-test\encoder" --execute-encoder-gpu-placement --reserve-gib 3
```

Do not disable CUDA. Physical Windows test and CI pending. If free VRAM is insufficient or CUDA reports out-of-memory, stop instead of reducing reserve blindly. Subsequent transformer GPU placement/offload is a separate gate. `main` and managed Z-Image untouched.


### Z2.20c3b3 Windows physical acceptance (2026-10-18)

**PASS:** `encoder_cuda_placement_verified_nonloadable`. All 398 standalone Qwen3 encoder parameter tensors placed on RTX 4080 SUPER CUDA; PyTorch allocated/peak 7.545 GiB, GPU free after placement 7.161 GiB, free before 14.708 GiB, total 15.992 GiB, required free including 3 GiB reserve 10.492 GiB. No encoder forward or generation (`forward_attempted=false`, `generation_attempted=false`, `loadable=false`). This establishes single-component placement, not combined pipeline viability or correctly functioning GPU neural inference. Next: independently gated transformer placement with conservative real free VRAM and a larger activation reserve.


### Z2.20c3b4: isolated real transformer CUDA placement (physical test pending)

Added `backend/morphorum/zimage_transformer_gpu_probe.py` and isolated guard tests on `dev-webui`. This CLI explicitly requires `--execute-transformer-gpu-placement`, config/schema validation, complete SHA-256 transformer scratch verification, enough available host RAM, and live CUDA free memory exceeding the 11.466 GiB converted transformer file plus a default 3 GiB reserve. It repeats the free VRAM gate just before transfer, loads all 521 transformer parameters onto CPU using the previously accepted Accelerate strict route, then attempts entire-model CUDA placement **without** forward or image generation. It reports allocated and peak VRAM and leaves cleanup to process termination rather than copying 11.47 GiB back to CPU. This is a *placement-only* test; an allocation success is not proof of sufficient inference activation headroom. If a VRAM gate blocks, stop and report the numbers rather than reducing the reserve.

Windows physical test with Morphorum/other GPU loads idle, from `D:\Morphorum-test`:

```powershell
git pull
.\.venv\Scripts\python.exe -m morphorum.zimage_transformer_gpu_probe --transformer "D:\Morphorum-z219-test\transformer" --encoder "D:\Morphorum-z219-test\encoder" --execute-transformer-gpu-placement --reserve-gib 3
```

CI and physical acceptance remain pending. No changes to `main` or managed package.
