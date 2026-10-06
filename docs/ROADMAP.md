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
