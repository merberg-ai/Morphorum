# Morphorum: current features and development status

**Build version:** `0.1.0a1` (early alpha)  
**Baseline:** `dev-ui` merge `aebb87e28a64ee8c2d131ae13c453bf742e1a01a` (PR [#20](https://github.com/merberg-ai/Morphorum/pull/20))  
**Status reviewed:** 2026-10-10

> [!NOTE]
> This page summarizes the current implementation and physical-test history. Some documents under `docs/` contain **historical plans, research, and acceptance notes**; headings such as "not yet implemented" in an old roadmap should not be treated as a current feature list. For setup, use the [README](../README.md) and [Getting started](GETTING_STARTED.md).

## Available now

| Area | Implemented features |
| --- | --- |
| **Install and updates** | Windows standalone `bootstrap.bat` with directory and port prompts; Linux bootstrap; managed Python 3.12 environment; repair, diagnostics, and guarded branch-aware updates. |
| **Models** | SDXL, FLUX, and Z-Image image generation; external checkpoint indexing and managed Z-Image-Turbo downloading; model-aware controls and recommended resolutions. |
| **LoRAs** | Local LoRA indexing, metadata/trigger word inspection, prompt insertion, and compatible model-aware LoRA application and scheduling. |
| **Image Generation** | Positive/negative prompts as supported; seed modes, batch count, resolution selection, progress and results. |
| **Project Manager** | Project list, search/sort, summaries, open/create/rename, and name-confirmed Move to Trash. Existing saved renders are kept separate. |
| **Motion Lab** | 2D and depth-aware 3D camera motion; six-axis composer; layers/presets; edit/view curves and camera path; frame-aware preview and rendering workflow. |
| **Motion recording** | Keyboard/mobile touch controls, optional browser gamepad, deterministic recorded layers and take handling. |
| **Audio Motion** | Audio import/analysis, frequency filtering and synchronized camera-motion mapping, waveform controls and supported soundtrack export. |
| **Animation rendering** | Frame scheduling, temporal cadence, depth/warp transforms, image-to-image frame generation, render monitoring, pause/resume/cancel as supported, video export including MP4/WebM. |
| **Deforum and video input** | Selected legacy Deforum JSON/TXT settings import with mapping diagnostics; upload/inspect/extract video-source frames for supported hybrid experiments. |
| **Appearance** | Four dark themes (Midnight Glass, Deep Ocean, Amethyst Night, Slate Graphite) and independent interface/console font choices, responsive desktop and mobile layouts. |
| **Diagnostics** | On-screen console, hardware/VRAM reporting when available, job progress, installer self-test and doctor commands. |

## Verified testing and current caveats

- The desktop Motion Lab layout, Project Manager, live controls and themes were iteratively tested on Windows during the `feature/desktop-ux-foundation` development cycle and merged into `dev-ui` in PR #20.
- PR #20 passed the repository's **Syntax**, **Backend**, and **Installer** workflows before and after the `dev-ui` integration.
- Z-Image-Turbo uses the official full **Tongyi-MAI/Z-Image-Turbo** Diffusers package for both txt2img and img2img, with component/shard validation. A user-confirmed Windows generation test followed.
- Several Motion Lab and audio/synchronization operations were accepted on Windows after targeted UI and render testing. Hardware and checkpoint differences can still affect performance.
- **Alpha limitations:** Large-resolution SDXL animation performance is hardware-dependent; a universal high-resolution benchmark has not been established. Video-source hybrid compositing/mask workflows and legacy Deforum feature coverage still need targeted compatibility and physical tests. Optical-flow/RAFT interpolation, unrestricted model support, and a general plugin SDK should **not** be assumed available.
- Some Linux workflows are covered by CI/syntax checks but do not have the same breadth of reported physical GPU testing as the Windows configuration used during development.
- Morphorum's local/LAN web server currently has **no built-in login/authentication**. Never expose its port to the public internet.

## Development workflow and recovery checkpoints

- `main` is the published/stable source branch.
- `dev-ui` is the integration branch used to collect and test features before promotion to `main`.
- New development normally starts on a **feature branch based on `dev-ui`**, with PR and CI checks prior to merging.
- Desktop UX + Motion Lab checkpoint: `checkpoint/desktop-ux-motion-lab-themes-verified-20261010` at `c58d4571b2daf2c64b0b6702cac12ad8ae77d5b1`.
- Pre-release main snapshot: `checkpoint/main-before-desktop-motionlab-promotion-20261010` at `4bc996be29104590a78ae84759a837a8a29a5135`.
- Earlier B5/B6 and Motion Lab checkpoints remain in Git history. Do not delete them as part of a release.

For historical milestones see [Roadmap](ROADMAP.md), [Motion Lab implementation notes](MOTION_LAB_ROADMAP.md), and [B6 physical acceptance](B6_PHYSICAL_ACCEPTANCE.md). For the actual functionality and status of an API or model capability, the current source and automated tests take priority over older planning prose.

## Next development areas

- More desktop and mobile UX refinement; expanded theme/font physical checks.
- Additional per-model performance and stability testing, especially higher resolution and long animations.
- Further compatibility/hybrid composition and mask-workflow validation.
- More first-run installation, model download/recovery, and documented Linux physical acceptance.

**See also:** [Installation](INSTALLATION.md) · [Getting started](GETTING_STARTED.md) · [Troubleshooting](TROUBLESHOOTING.md) · [Docs index](README.md)
