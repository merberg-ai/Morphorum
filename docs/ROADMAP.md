# Morphorum roadmap

This roadmap is intentionally milestone-oriented. Version numbers may move as reality applies its usual corrections.

## 0.1.0-alpha.0 — repository foundation

- project/license/contribution documents
- clean-room compatibility policy
- architecture baseline
- install/run/update/repair wrappers
- one-line Windows/Linux bootstrap scripts
- default configuration and Midnight Glass theme tokens

## 0.1.0-alpha.1 — compatibility shell

- backend/frontend application skeleton
- settings and first-run foundations
- responsive Midnight Glass UI shell
- project create/open/save/autosave
- legacy Deforum JSON/TXT importer
- original-source preservation and migration report
- classic schedule parser/evaluator
- frame-resolution inspector
- configurable model/LoRA/VAE/embedding directories
- persistent model index
- initial architecture detection
- model capability registry/adapter interfaces

Success criterion: import representative legacy projects and resolve schedule values frame-for-frame without running diffusion.

## 0.2.0-alpha.1 — first real rendering

- initial SDXL inference adapter
- single-file checkpoint loading
- LoRA parsing/loading with `<lora:name:weight>`
- first-class Single Image/still-image workspace
- model-aware prompt/negative-prompt controls
- steps/CFG/sampler/scheduler controls driven by the active adapter
- WebUI-style seed controls: fixed, random, incrementing, configurable increment step, randomize, and reuse-last-seed
- multiple-image generation from one prompt/job with explicit per-image resolved seeds
- batch count/images control plus advanced batch-size control where supported
- variation/subseed controls where the backend/model supports them
- easy resolution picker with aspect-ratio presets, exact custom dimensions, orientation swap, divisibility validation, and megapixel feedback
- image-generation progress, preview, batch status, ETA where meaningful, and lightweight session history
- per-image metadata including resolved seed, model, LoRAs, dimensions, sampler/scheduler, and guidance settings
- send generated image/settings into animation as a starting point
- txt2img first-frame generation
- img2img subsequent-frame generation
- PNG frame output
- render job manager
- WebSocket progress events
- live preview/progress/ETA/logs
- resumable render manifest

## Animation foundation — Phase 1 complete

- native animation project schema v1
- per-project `projects/<id>/project.json` persistence with atomic writes
- timeline dimensions, FPS, and frame-count state
- stable model-index references
- positive/negative prompt keyframe storage
- raw Deforum-style 2D motion schedule storage
- raw strength/noise/steps/guidance schedule storage
- seed/sampler state
- responsive Animation workspace with create/load/save/reload controls
- forward-compatible preservation of unknown project fields

Physical acceptance target: create, edit, save, reload, and switch animation projects from desktop/mobile without losing state. Schedule evaluation intentionally begins in Phase 2.

## Schedule engine — Phase 2 implemented

- clean-room Deforum-style numeric keyframe parser
- linear numeric interpolation
- continuously evaluated math expressions using `t` / `max_f`
- expression-based frame positions such as `max_f-1`
- safe restricted expression evaluator with common math functions
- blend/hold prompt-transition state
- project-wide schedule validation with warnings/errors
- renderer-facing resolved frame-state contract
- deterministic fixed/incrementing seed resolution
- random-at-render seed state
- live Resolved Frame Inspector in the Animation workspace
- schedule curve preview without diffusion
- live validation styling for motion/generation schedules
- APIs for unsaved-project frame resolution, validation, and curve sampling

Physical acceptance target: edit schedules on mobile, scrub frames, verify known interpolated values and prompt weights, validate expression schedules, and confirm malformed schedules are reported without corrupting the project.

## Motion preview — Phase 3 implemented

- project-owned starting-image upload/replace/clear workflow
- RGB PNG source normalization with original filename metadata
- cumulative center-based 2D affine transform engine
- angle, zoom, translation X, and translation Y schedule application
- classic replicate/wrap border modes
- project-resolution translation scaling into preview resolution
- matrix accumulation without repeated source-image degradation
- evenly sampled preview rasterization for long animations
- animated GIF output with project-timing-aware frame durations
- serialized background preview jobs with browser progress
- responsive mobile source/preview workspace
- no diffusion/GPU model load required

Physical acceptance target: upload a source image, preview obvious cumulative camera motion, verify replicate and wrap edges differ as expected, and confirm schedule edits can be previewed without saving or loading a model.

## Diffusion frame loop — Phase 4 implemented

- frozen render-local project/source snapshots
- persistent per-frame seed plan
- previous-frame cumulative 2D transform feedback
- Deforum strength → Diffusers denoise-strength mapping
- deterministic uniform noise schedule application
- SDXL / Flux / Z-Image img2img task wrappers
- loaded-weight reuse via Diffusers `from_pipe()`
- real Blend prompt-conditioning interpolation per architecture
- per-frame PNG metadata
- atomic render manifest after every completed frame
- cancel support
- interrupted/failed/cancelled render resume
- live render history/progress/latest-frame UI
- completed low-resolution GIF render preview
- shared inference lock with still-image generation
- automatic img2img ↔ txt2img task switching

Physical acceptance passed on Z-Image-Turbo with real frame generation plus cancel/resume.

## Phase 4.1 — start-frame and workflow polish implemented

- explicit Generate from Prompt vs Use Starting Image mode
- txt2img-generated frame 0 when no source image is desired
- uploaded image remains available as an optional CPU camera-preview reference
- latest-rendered-frame URLs now track only completed PNGs
- existing stale manifests repair latest-frame URLs from completed results
- Z-Image variable-length prompt embeddings aligned safely for Blend transitions
- clearer Project → Start Frame → Prompts → Motion → Generation → Preview → Render workflow
- embedded favicon removes the stray browser `/favicon.ico` 404

Physical acceptance target: generate frame 0 from prompt with no upload, repeat a multi-prompt Z-Image Blend render, and verify the latest-frame panel advances without 404s.

## 0.3.0-alpha.1 — classic motion

- 2D transforms
- border modes
- strength/noise/CFG/step schedules
- prompt transitions
- motion preview without diffusion
- camera/keyframe timeline UI
- pause/resume/cancel/crash recovery polish

## 0.4.0-alpha.1 — modern multi-model

- initial Flux Dev/Schnell txt2img adapter using local transformer files plus cached shared components
- Flux CUDA model-offload path for consumer GPUs
- initial managed Z-Image-Turbo txt2img adapter with 16 GB-class streamed offload path
- capability-driven model configuration UI shared by Single Image and Animation
- architecture-specific CFG/guidance/true-CFG/shift controls
- model-aware resolution recommendations/presets
- model profiles/presets
- LoRA family compatibility detection
- precision/offload/memory profiles
- single-image support for each enabled model family using the same adapter/capability layer
- seed/batch modes normalized across adapters while preserving architecture-specific limitations

## 0.5.0-alpha.1 — depth and 3D

- depth estimation abstraction
- depth-map diagnostic preview
- 3D camera transform engine
- FOV/near/far schedules
- modern depth backend plus compatibility options

## 0.6.0-alpha.1 — cadence and flow

- classic diffusion cadence
- intermediate frames
- optical-flow abstraction
- RAFT/compatible backend
- cadence/flow diagnostics

## Later milestones

- ControlNet
- Parseq-compatible import/integration concepts
- hybrid/video input workflows
- RIFE/FILM-style interpolation options
- audio handling/reactive schedules
- richer preset browser
- render queue management
- notifications
- plugin/extension SDK
- advanced model-family adapters and modern video-model interpolation/tweening
- camera-path visualization
- richer single-image gallery/history and comparison workflows

## Non-negotiable compatibility targets

Throughout development:

- runtime-supported model families are SDXL, Flux, and Z-Image; preserve legacy SD1/2 import metadata for migration without restoring those inference backends
- do not break classic `<lora:name:weight>` prompt syntax
- do not discard unknown legacy JSON fields
- do not couple rendering to a browser session
- do not make desktop-only UI decisions that render mobile unusable
- do not force all architectures through SD-style settings
- do not maintain separate contradictory model-parameter semantics between Single Image and Animation
- do not hide the actual resolved seed sequence used for multi-image generation
- do not copy GPL/AGPL implementation source into the Unlicensed core
