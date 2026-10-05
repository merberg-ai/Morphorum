# Morphorum architecture baseline

This document records the initial architectural contract for Morphorum. It should change deliberately, not accidentally.

## 1. Product shape

Morphorum is a standalone local AI animation studio with a browser UI. The default server binds to localhost; LAN access is opt-in/configurable. The UI must work well on desktop and mobile browsers.

Planned high-level stack:

- Python backend with FastAPI-style HTTP APIs and WebSocket/event streaming
- React + TypeScript + Vite-style frontend
- FFmpeg media/encoding layer
- SQLite for local indexes/job/project metadata where persistence is useful
- swappable inference/model adapters

The frontend must never own a render job. A browser may disconnect and reconnect while rendering continues server-side.

## 2. Licensing strategy

Morphorum's core is a clean-room implementation released under the Unlicense.

Compatibility with Deforum means preserving useful file formats, prompt conventions, schedule semantics, and observable behavior. It does not mean copying GPL/AGPL implementation source. If the project later chooses to incorporate covered source, that requires an explicit project licensing decision first.

## 3. Legacy project compatibility

Classic Deforum JSON/TXT settings are a first-class input format.

Principles:

- Preserve familiar flat settings where possible.
- Preserve prompt syntax such as `<lora:name:weight>`.
- Preserve old schedule expression syntax and interpolation behavior as closely as practical.
- Preserve unknown imported fields rather than deleting them.
- Keep the original imported document available for diagnostics/migration.
- Resolve old checkpoint/LoRA names against configured model directories and remembered mappings.
- Never silently reinterpret an SD-specific parameter as a different architecture's parameter.

Morphorum-specific additions should be namespaced (for example `_morphorum`) so legacy data remains recognizable.

## 4. Deforum-style animation engine

The animation/orchestration layer owns:

- prompt/keyframe scheduling
- numeric/expression schedule resolution
- seeds
- 2D transforms
- 3D/depth transforms
- cadence and intermediate-frame logic
- masks/init images
- color/coherence processing
- optical-flow/hybrid/video workflows
- frame manifests and resumability

It produces a resolved `FrameContext` for inference instead of calling a model implementation directly.

## 5. Model adapter system

Inference is architecture-specific and lives behind adapters.

Initial supported families:

- SDXL
- Flux variants
- Z-Image variants

The enabled family list is a backend registry consumed by Settings and the model library. New modern families should be added through that registry plus an adapter/capability definition rather than hard-coded separately across UI surfaces.

Stable Diffusion 1.x/2.x are not runtime-supported model families. Legacy project imports may preserve their original fields and model references for provenance/migration, but Morphorum must require an explicit model-family migration or replacement rather than pretending those projects can render unchanged.

Adapters own model-specific behavior such as:

- loading model bundles/single-file checkpoints
- txt2img/img2img invocation
- CFG/guidance/true-CFG/shift semantics
- supported negative prompts
- samplers/schedulers
- steps and recommended ranges
- precision/quantization/offload strategy
- token/text-encoder limits
- VAE handling
- LoRA application
- architecture-specific validation

The animation engine must not assume all models expose classic CFG.

## 6. Capability-driven UI

A versioned model capability manifest defines which controls a selected model exposes, their ranges/defaults, whether they are schedulable, and validation rules.

Configuration precedence:

1. engine defaults
2. family defaults
3. model/variant defaults
4. checkpoint profile/metadata
5. user preset
6. project settings

Project settings win. User-requested incompatible values should produce warnings rather than mysterious silent changes.

Simple mode presents model-appropriate concepts such as quality/creativity. Advanced mode exposes real architecture-specific parameters.

## 7. Model library

Users may configure multiple recursive directories for:

- checkpoints/model bundles
- LoRAs
- VAEs
- embeddings/textual inversion
- ControlNet assets

Morphorum indexes external files; it does not require copying them into the application directory.

The index should cache path, size, mtime, hashes when needed, architecture/family, metadata, previews, aliases, and compatibility. It should avoid hashing hundreds of gigabytes on every launch.

LoRA lookup must support legacy `<lora:name:weight>` syntax, extensionless names, relative/nested names, aliases, collision reporting, and architecture compatibility checks.

## 8. Model lifecycle and performance

Models have explicit lifecycle states such as unloaded/loading/ready/busy/unloading/error.

Plan for:

- keep-loaded/idle-unload policies
- BF16/FP16/FP8/quantized variants where supported
- CPU/model offload strategies
- VAE tiling and architecture-specific memory controls
- observed VRAM peak tracking and future VRAM estimates
- model/checkpoint profiles storing preferred settings without editing model files

## 9. Render manager

Rendering is a server-side job system with queue support.

Required state/event concepts:

- preparing project
- resolving/loading model
- loading LoRAs/components
- rendering frame N / total
- diffusion step N / total when available
- post-processing
- interpolation
- audio
- video encoding
- finalization
- completed/failed/paused/cancelled

The UI consumes events over WebSocket or an equivalent persistent event channel.

Required UX:

- live completed-frame preview
- optional diagnostic preview modes (warped source/depth/flow/etc.)
- overall progress
- current-frame progress
- rolling ETA/estimated finish time
- elapsed time and frame rate
- GPU/VRAM telemetry when available
- collapsible logs
- pause after current safe unit of work
- cancel while retaining resumable output
- crash/interruption recovery from persistent render manifests
- browser reconnect from desktop/mobile without stopping jobs

## 10. UI / theming / mobile

The default theme is `Midnight Glass`: dark, restrained, translucent panels/cards, blur where supported, rounded surfaces, readable contrast, and touch-friendly controls.

The theme system is token/data driven and switchable live from Settings. Planned themes include Midnight Glass, OLED Black, conventional Dark, Light, and additional community themes.

UI requirements:

- responsive/mobile-first layouts
- collapsible cards with remembered state
- bottom navigation/appropriate mobile navigation
- large touch targets
- phone-friendly prompt editing
- mobile timeline/keyframe editor designed for narrow screens rather than shrinking a desktop timeline
- Simple and Advanced interface modes on the same project data
- spinners only for truly indeterminate work; real progress bars when measurable

## 11. Installation / maintenance

From the beginning Morphorum ships easy platform wrappers and one-line bootstrap entrypoints.

Windows:

- `install.bat`
- `run.bat`
- `run-lan.bat`
- `update.bat`
- `repair.bat`

Linux:

- `install.sh`
- `run.sh`
- `update.sh`
- `repair.sh`

Install/update/repair logic lives in scripts rather than duplicating complex logic in wrappers.

A future first-run wizard configures model directories, output directory, hardware profile, and basic server settings.

## 12. Security baseline

- Bind localhost by default.
- LAN binding is explicit.
- Plan optional access-token protection for LAN use.
- Do not expose arbitrary server filesystem browsing to unauthenticated remote clients.
- Validate project/import paths and uploaded filenames.
- Keep secrets/tokens out of project files and logs.

## 13. Reproducibility

Each render should save a manifest with enough information to reproduce/debug it, including:

- Morphorum version and git commit
- project/schema version
- model path/identifier and hash when available
- LoRA identifiers/hashes/weights
- resolved architecture adapter and version
- sampler/scheduler/guidance settings
- seeds
- relevant PyTorch/inference-library versions
- GPU/device information
- completed-frame state

## 14. Extensibility

New model families, depth estimators, optical-flow engines, ControlNet implementations, interpolation systems, and future video-model integrations should be attachable without rewriting the core renderer or UI.

## 15. Single Image workspace

Single-image generation is a first-class workspace alongside animation, not a diagnostic afterthought. The name refers to still-image generation as a workflow; a job may generate one image or a batch of images. It uses the same model library, capability manifests, inference adapters, LoRA resolver, presets, job/progress system, and reproducibility metadata as animation.

The selected model drives the available controls. The UI must not show meaningless SD-style controls for architectures that do not use them. Depending on the active model, the workspace may expose:

- positive prompt and model-supported negative prompt controls
- seed with randomize/reuse controls
- steps and model-appropriate recommended ranges
- classic CFG, distilled guidance, true CFG, shift, or other model-specific guidance controls
- compatible sampler and scheduler selections
- checkpoint/model profile
- LoRAs using familiar `<lora:name:weight>` syntax plus a visual LoRA browser
- VAE/text-encoder/component overrides where supported
- precision, quantization, offload, and memory controls in Advanced mode
- batch count, batch size where supported, and variation controls

### Seed and batch behavior

The still-image workspace should preserve the useful A1111/WebUI-style seed workflow while presenting it more clearly.

Seed controls should include:

- explicit fixed seed
- Random mode, choosing a fresh seed for each generated image
- Increment mode, starting from a chosen seed and increasing by a configurable step (default +1) for each image
- Fixed mode, deliberately reusing the same seed for repeated generations when the model/backend permits meaningful comparison
- seed randomize button
- reuse-last-seed button
- copy seed from any image in the history/gallery
- visible resolved seed on every generated image, even when the requested seed was random

Batch controls should separate:

- Images: total number of outputs requested
- Batch size: how many are processed concurrently when the active adapter/device supports it safely

The UI may simplify these to one `Images` control in Simple mode while Advanced mode exposes batch size separately. A batch must never obscure the actual per-image seed sequence used.

Where supported by a model/backend, variation/subseed behavior should be available as an advanced option:

- variation/subseed
- variation strength
- optional seed-resize compatibility controls for imported legacy workflows

Seed mode should be represented explicitly in project/job settings rather than encoded through undocumented magic values. Compatibility import/export layers may still understand legacy conventions such as random-seed sentinels.

Example resolved sequences for four requested images:

- Fixed, seed 12345 → `12345, 12345, 12345, 12345`
- Increment, seed 12345, step 1 → `12345, 12346, 12347, 12348`
- Increment, seed 12345, step 10 → `12345, 12355, 12365, 12375`
- Random → four independently generated seeds, all recorded in output metadata

### Resolution picker

Resolution selection must be easy on desktop and mobile. It should provide:

- named aspect groups such as Square, Landscape, Portrait, Ultrawide, and Custom
- model-aware recommended/native presets rather than one universal list
- common aspect ratios such as 1:1, 4:3, 3:2, 16:9, 9:16, and model-appropriate additional ratios
- width and height fields for exact custom input
- swap-orientation button
- optional aspect-ratio lock
- architecture-required divisibility snapping/validation
- megapixel estimate and a warning when the chosen size is unusually expensive or outside the model's recommended range
- remembered recent/favorite resolutions

Choosing a preset changes ordinary width/height settings; presets are not opaque modes. Advanced users can always enter exact dimensions.

### Generation UX

A single-image job should show the same quality of feedback expected from animation:

- indeterminate spinner while loading models/components
- denoising-step progress when available
- overall progress for batches
- per-image position such as `3 / 8`
- elapsed time and ETA where meaningful
- GPU/VRAM telemetry when available
- clear cancel/error state
- generated image preview as soon as each image completes

The workspace should keep a lightweight session history/gallery showing image, resolved seed, model, LoRAs, resolution, and generation settings. Users should be able to reuse settings/seed, copy prompt metadata, save the image, and send a generated image directly into an animation project as an init/starting image without manually hunting for the file.

Single-image settings and animation inference settings should share underlying schemas wherever semantics truly match, so testing a model in Single Image provides a reliable starting point for animation rather than maintaining two subtly different configuration systems.
