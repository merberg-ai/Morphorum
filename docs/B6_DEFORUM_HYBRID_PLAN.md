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

Morphorum does **not** yet have a Deforum settings importer or hybrid video-frame source/compositor. Legacy Deforum JSON must translate into the native Morphorum project, not become a new parallel render engine.

## B6.1: Safe legacy Deforum JSON/TXT import

**First implementation milestone.** Separate parsing, translation/compatibility warnings, and persistence.

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
- The B6 branch is initially a **planning/audit baseline**; no Deforum input is accepted until B6.1 parser, translation, tests and UI are implemented.
