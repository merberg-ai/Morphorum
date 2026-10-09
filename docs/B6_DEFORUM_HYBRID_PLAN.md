# B6: Deforum compatibility and hybrid animation workflows

## Branching and acceptance baseline

- **B6 branch:** `feature/deforum-compatibility-hybrid-b6`.
- **B5.5 GPU-verified checkpoint:** `checkpoint/b5-5-performance-stability-gpu-verified-20261008` at `e9ea6d0491b8ad57f1bc7539514fe8cb9c7063d3`.
- **B5.4 backup:** `checkpoint/b5-4-video-export-windows-verified-20261008` at `f5db57cab8173c5a8038762a20bb5cc5650f2bd7`.
- Baseline: 75-frame Windows SDXL / three-prompt LoRA animation completed, 25 cadence-3 diffusion anchors, average diffusion ~7.49s, CUDA `native-gpu`, peak observed allocated ~14.41 GiB, three resident LoRAs, bounded conditioning cache. Pause/resume/cancel and performance telemetry confirmed by user.
- **Nonregression:** B6 work cannot rewrite existing native Morphorum project semantics, GPU scheduling, cadence, LoRA application, depth projection, temporal refinement, stored renders, or FFmpeg exports without a separate gate.

## Current compatibility surfaces (code audit)

Morphorum already has:
1. `animation_projects.py`: schema 2 projects, canonical `tracks`, legacy-compatible mirrored fields, atomic persistence and forward-compatible unknown-field handling.
2. `animation_timeline.py`: structured prompt and numeric tracks, including 2D angle/zoom/x/y, 3D translation/rotation/FOV, strength, noise, steps, guidance, and diffusion cadence.
3. `schedules.py`: a constrained, expression-aware frame schedule parser; **never** use Python `eval` on input from imported presets.
4. `animation_resolution.py`: resolved project frames with existing validation and LoRA prompt tag resolution.
5. `animation_render.py`: 2D/3D camera transforms, cadence, LoRA-aware img2img, temporal future-anchor refinement, resume and frame manifests.
6. `animation_video.py`: FFmpeg MP4/WebM output assembled from completed PNGs.

Morphorum now has a B6.1 Deforum settings importer that translates legacy JSON/JSON-serialized TXT into native Morphorum projects. It still does **not** have a hybrid video-frame source/compositor. Legacy Deforum settings remain a translation/compatibility layer, not a parallel render engine.

## Implementation status — automated checkpoint `d982a32`

As of this checkpoint:

- **B6.1 implemented, automated gate passed:** safe size/depth-bounded JSON parser; explicit rejection of executable/non-JSON TXT; mapping preview; unsupported/unmapped passive metadata; imported checkpoint paths ignored; explicit indexed-model selection; new-project-only persistence; browser-local file selection; golden 2D/3D fixtures; save/reopen and timeline/resolved-frame agreement tests.
- **B6.0-P diagnostics implemented, automated gate passed:** allocator backend/current/peak/active/inactive statistics, allocation retry/OOM counters, per-frame phase samples without forced synchronization, `GET /api/system/gpu-memory`, on-demand Windows WDDM process dedicated/shared counters, and an advisory confirmation above the physically verified 512×512 pixel count.
- **First opt-in memory strategy implemented:** `performance.sdxl_vae_tiling`, default **false**. It only changes SDXL when explicitly enabled and records `native-gpu+vae-tiling` when active.
- **CI at `d982a32`:** 273 Python tests passed, 17 browser tests passed, Morphorum self-test passed.
- **Not physically accepted yet:** B6.1 Windows UI/short render, WDDM counter readings on the target machine, native 768/1024 SDXL, and SDXL VAE tiling A/B quality/performance.
- **Not implemented:** B6.2 hybrid video upload/extraction and B6.3 hybrid compositing/masks.

The exact physical procedure is in `docs/B6_PHYSICAL_ACCEPTANCE.md`. Do not create a B6.1 GPU/UI checkpoint until that gate passes.

## B6.0-P: High-resolution GPU memory investigation (code-side prep complete; physical gate pending)

The B5.5 verified run succeeded for 75 SDXL frames at 512x512 with
cadence 3, three resident LoRAs, CUDA `native-gpu`, 14.41 GiB
maximum *observed live* allocation, 15.36 GiB process maximum tensor
allocation, and 16.43 GiB process maximum reserved allocator statistic
on a 15.99-GiB physical device. It did not exhibit slow-anchor warnings.
This establishes correct GPU inference at 512px; it **does not**
demonstrate that 768, 1024, or higher resolutions fit.

**Critical interpretation:** `torch.cuda.max_memory_reserved()` is a
process-lifetime caching allocator high-water statistic, not an
unambiguous readout of simultaneous physical VRAM residency. PyTorch
documents that under `cudaMallocAsync` the maximum may conservatively
sum peaks from separate pools observed at different times. Windows
WDDM also uses GPU virtual memory and manages residency; possible
shared-memory oversubscription must be corroborated using Windows
dedicated/shared GPU memory counters. Do not present a single >16GiB
peak as proof of paging or a GPU leak.

### B6.0-P plan and physical gate

1. **Metrics correctness:** log allocator backend (`native` vs
   `cudaMallocAsync`), `mem_get_info()`, current/peak
   allocated/reserved, PyTorch `memory_stats()` categories and actual
   Windows dedicated/shared GPU residency where available. Keep
   per-frame diagnostics low-overhead. Ensure clear differentiation
   between *current* memory, *cumulative peak*, cached blocks, and
   Windows memory. Add before/after phase checkpoints around
   model+LoRA load, text conditioning, UNet, VAE encode/decode,
   3D depth and export. No forced synchronization inside the hot loop.
2. **Baseline reproducibility:** identical SDXL model, 512x512,
   one then three LoRAs, one image and short cadence-3 animation.
   Capture latency and memory before testing alternative memory modes.
3. **Targeted opt-in strategies:** assess SDXL VAE tiling and decode
   allocations first; assess memory-efficient attention backend;
   consider preencoding/offloading text encoders while keeping the
   UNet on CUDA and preserving scheduled LoRA/text-encoder behavior.
   Only use model-level CPU offload as an explicit memory-constrained
   fallback, and never silently enable slow sequential offload.
   Validate interactions with `from_pipe()`, cached adapters,
   dynamic LoRA weights and `encode_prompt()`.
4. **Safe, stepped resolution matrix:** 512x512, 768x768, 896x1152,
   1024x1024, 1216x832, 1536x1024, then 1536x1536 or
   2048x2048 only if headroom and measured performance permit.
   Start with single-image GPU tests, progress to 3-frame runs,
   then longer 3D cadence renders. 1024x1024 contains **4x** as
   many pixels as 512x512; 1536x1536 contains **9x**.
   These ratios are not predictions of exact total VRAM.
5. **OOM behavior:** detect likely insufficient headroom before
   queueing extreme settings; provide a **warning/confirmation** and
   alternatives, not an invented fixed hardware maximum. A failed
   CUDA attempt must cleanly unload/restore its partial pipeline,
   preserve checkpoints, and never silently switch to CPU or corrupt
   the render. Protect other user workloads on a shared 16GiB GPU.
6. **Acceptance:** 768 and 1024 tests with visually verified SDXL
   LoRA influence, working 3D depth/temporal cadence, exports, and
   cancel/resume. Compare native/tiling/offload modes with
   repeatable metrics. No physical high-resolution result has been
   established yet; gate each mode and leave verified B5 untouched.

This investigation can progress alongside B6.1 import UI work. Any
memory-mode code should live behind explicit settings and regression
tests; avoid entangling importer correctness with GPU experiments.

## B6.1: Safe legacy Deforum JSON/TXT import

**Implementation is present and automated-test gated at `d982a32`; Windows UI/short-render acceptance is still pending.** Parsing, translation/compatibility warnings, browser preview, explicit model binding and new-project persistence are separate stages.

### Input and safety

- Accept common Deforum settings JSON and a documented subset of text-serialized settings. Parse with JSON, or explicitly reject unsupported TXT variants with actionable diagnostics. Do not execute/import embedded Python.
- Restrict payload size and nesting/keyframe counts; reject non-object roots and malformed schedules. Input is untrusted.
- Show a **preview before save** with importable fields, original source values, mapped values, warnings and unsupported fields.
- Preserve original source metadata and unmapped settings under a namespaced, passive compatibility section for audit and future re-import; avoid silently inventing equivalences.
- Never trust imported absolute model names or local filesystem paths. Users must choose a known indexed Morphorum checkpoint, and missing LoRAs must be resolved with the existing LoRA catalog.
- A failed import must leave existing projects unchanged. Save creates a **new native project** via existing normalization/persistence.

### Initial mapping targets

| Deforum input | Morphorum target | Notes |
| --- | --- | --- |
| `max_frames`, `fps`, `W`, `H` | `animation.max_frames/fps/width/height` | Validate supported bounds |
| `animation_mode` | `animation.mode` | Only explicit 2D/3D; unsupported options flagged |
| `animation_prompts` | `prompts`, `tracks.prompts.positive` | Preserve frame indices and source strings |
| `negative_prompts` (when unambiguous) | `negative_prompts`, `tracks.prompts.negative` | Do not discard global negative content |
| `angle`, `zoom`, `translation_x`, `translation_y` | `motion.*` | Schedule syntax validated |
| `translation_z`, `rotation_3d_x/y/z` | `camera_3d.*` | Confirm coordinate/angle conventions; warn when not equivalent |
| `strength_schedule`, `noise_schedule` | `generation.strength/noise` | Preserve schedule expressions |
| `steps`, `cfg_scale` or `cfg_scale_schedule` | `generation.steps/guidance` | Flat defaults become 0-frame schedules |
| `diffusion_cadence` | `cadence.diffusion` | Validate 1..64, no hidden behavior change |
| `seed`, `seed_behavior` | `generation.seed/seed_behavior` | Map only known values |
| `sampler` | `generation.sampler` | Require supported family/sampler |
| video/hybrid/mask fields | passive compatibility metadata | Until corresponding B6.2+ workflows land |

Where Deforum uses units/signs/coordinate conventions that differ from Morphorum, **warn or defer** rather than pretending a numeric copy will look identical.

### Tests and gate

- Golden fixture imports for 2D and 3D, prompt keyframes, negative prompt formats, schedule interpolation, cadence and seed options.
- Invalid JSON/TXT, unsupported motion options, malicious path strings, unsafe expressions, unknown model and unmapped settings.
- Source JSON must not be mutated; importing must not overwrite prior projects.
- Preview and new-project round-trip must preserve supported data through normalize/save/reopen; visual timeline and resolved-frame APIs must agree.
- Windows **UI gate:** import a known Deforum project, review warnings, bind an installed SDXL checkpoint, verify timeline, perform a short render and compare visually. Only checkpoint B6.1 after this passes.

## B6.2: Hybrid video input and frame extraction

- Upload/select an input video from the **browser**, store under managed per-project assets. No server-side Windows file picker; no access to user-supplied arbitrary host filesystem paths.
- FFmpeg probe and deterministic source-frame extraction, time/fps trim, dimensions, maximum frames and safe path handling; cancel/progress/restart.
- Choose starting frame, frame overlay/reference strength, and fallback for missing source frames.
- Source video is opt-in, and native prompt/source-image B5 modes remain untouched.
- Add source-frame provenance and retention settings to render manifests.

## B6.3: Hybrid compositing and mask tracks

- Configurable blend/composite of warped generated frames with extracted source frames.
- Geometry transforms, masks and source-frame alpha; shape/time alignment and stable per-frame ordering.
- Controls for source-vs-generated content, opacity and temporal stabilization; avoid CPU/GPU memory regressions.
- Save deterministic resolved hybrid state in each frame's manifest and validate resume.

## B6.4: Compatibility polish and delivery

- Missing/unsupported legacy options report, optional native settings export compatible with supported fields (never claim roundtrip equivalence).
- Hybrid preview, project save/load, artifact hygiene and MP4/WebM output tests.
- Long-render stress and visual acceptance on Windows with the RTX 4080 SUPER, including LoRAs, 3D cadence 3, prompt windows and cancel/resume.
- Checkpoint B6 and only then plan the next major phase.

## Working rules

- Implement a milestone completely with unit/browser/regression CI before each physical GPU/UI gate.
- Prefer minimal additive modules and explicit compatibility warnings.
- Keep renderer changes opt-in and preserve the B5.5 checkpoint.
- B6.1 input is now accepted through the safe preview/create importer, but this does not imply full Deforum parity. Unsupported keys remain passive metadata and the Windows visual gate controls checkpoint status.
