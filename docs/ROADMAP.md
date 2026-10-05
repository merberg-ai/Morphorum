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

- initial SD 1.x inference adapter
- single-file checkpoint loading
- LoRA parsing/loading with `<lora:name:weight>`
- txt2img first-frame generation
- img2img subsequent-frame generation
- PNG frame output
- render job manager
- WebSocket progress events
- live preview/progress/ETA/logs
- resumable render manifest

## 0.3.0-alpha.1 — classic motion

- 2D transforms
- border modes
- strength/noise/CFG/step schedules
- prompt transitions
- motion preview without diffusion
- camera/keyframe timeline UI
- pause/resume/cancel/crash recovery polish

## 0.4.0-alpha.1 — multi-model

- SDXL adapter
- Flux adapter(s)
- Z-Image adapter(s)
- capability-driven model configuration UI
- architecture-specific CFG/guidance controls
- model profiles/presets
- LoRA family compatibility detection
- precision/offload/memory profiles

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

## Non-negotiable compatibility targets

Throughout development:

- do not break classic `<lora:name:weight>` prompt syntax
- do not discard unknown legacy JSON fields
- do not couple rendering to a browser session
- do not make desktop-only UI decisions that render mobile unusable
- do not force all architectures through SD-style settings
- do not copy GPL/AGPL implementation source into the Unlicensed core
