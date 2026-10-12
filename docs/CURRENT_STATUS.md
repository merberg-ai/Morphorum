# Morphorum: current features and development status

**Build version:** `0.1.0a1` (early alpha)  
**Build lineage:** Desktop/Motion Lab PR [#20](https://github.com/merberg-ai/Morphorum/pull/20), first-run onboarding PR [#22](https://github.com/merberg-ai/Morphorum/pull/22) (integrated into `dev-ui` at `661d029a267bc8c9b6fb01995f46a7ab4b323711`).  
**Status reviewed:** 2026-10-11

> [!NOTE]
> This page summarizes the current implementation and physical-test history. Some documents under `docs/` contain **historical plans, research, and acceptance notes**; headings such as "not yet implemented" in an old roadmap should not be treated as a current feature list. For setup, use the [README](../README.md) and [Getting started](GETTING_STARTED.md).

## Available now

| Area | Implemented features |
| --- | --- |
| **Install and updates** | Windows standalone `bootstrap.bat` with directory and port prompts; Linux bootstrap; managed Python 3.12 environment; repair, diagnostics, and guarded branch-aware updates. |
| **Models** | SDXL, FLUX, and Z-Image generation; external checkpoint indexing and managed Z-Image-Turbo downloading; model-aware controls/resolutions and a no-model setup banner/dialog when no checkpoint is available. |
| **LoRAs** | Local LoRA indexing, metadata/trigger word inspection, prompt insertion, and compatible model-aware LoRA application and scheduling. |
| **Image Generation** | Positive/negative prompts as supported; seed modes, batch count, resolution selection, progress and results. |
| **Project Manager** | Project list, search/sort, summaries, open/create/rename, and name-confirmed Move to Trash. Existing saved renders are kept separate. |
| **New Project Wizard** | Seven guided pages for name, model selection, 2D/3D timing/size, prompts, native camera motion presets, generation controls and review/save. Server-backed defaults, hints, browser-session draft recovery and validation. |
| **Motion Lab** | 2D and depth-aware 3D camera motion; six-axis composer; layers/presets; edit/view curves and camera path; frame-aware preview and rendering workflow. |
| **Motion recording** | Keyboard/mobile touch controls, optional browser gamepad, deterministic recorded layers and take handling. |
| **Deforum Motion Settings Import** | Existing 3D project camera-only import, source-timing diagnostics, compatibility conversion and 0–400% translation/rotation strengths; optional project soundtrack attachment with frozen render snapshot and MP4/WebM export. Legacy Audio Motion controls remain stored but are not a visible workspace. |
| **Animation rendering** | Frame scheduling, temporal cadence, depth/warp transforms, image-to-image frame generation, render monitoring, pause/resume/cancel as supported, video export including MP4/WebM. |
| **Deforum and video input** | Selected legacy Deforum JSON/TXT settings-to-new-project import remains available alongside the new existing-project motion-only importer; upload/inspect/extract video-source frames for supported hybrid experiments. |
| **Appearance** | Four dark themes (Midnight Glass, Deep Ocean, Amethyst Night, Slate Graphite), interface/console font choices, responsive layouts, and version popover links to repository/current Git branch/exact commit. |
| **Diagnostics** | On-screen console, hardware/VRAM reporting when available, job progress, installer self-test and doctor commands. |

## Verified testing and current caveats

- The desktop Motion Lab layout, Project Manager, live controls and themes were iteratively tested on Windows during the `feature/desktop-ux-foundation` development cycle and merged into `dev-ui` in PR #20.
- PR #20 passed the repository's **Syntax**, **Backend**, and **Installer** workflows before and after the `dev-ui` integration.
- The first-run onboarding improvements in PR #22 were accepted during Windows browser testing. The New Project Wizard, no-model banner, and GitHub build popup have frontend/backend regression coverage and passed CI before promotion. The wizard creates projects only at the final Save step and validates schedules using the existing API.
- Z-Image-Turbo uses the official full **Tongyi-MAI/Z-Image-Turbo** Diffusers package for both txt2img and img2img, with component/shard validation. A user-confirmed Windows generation test followed.
- Several Motion Lab and audio/synchronization operations were accepted on Windows after targeted UI and render testing. Deforum importer and camera-strength controls passed reported Windows physical testing at checkpoint `checkpoint/deforum-motion-import-camera-strength-percent-windows-verified-20261011` (`abcd9f3a570262ddcc8d9b348f193e48eb06f078`). Hardware and checkpoint differences can still affect performance.
- **Alpha limitations:** Large-resolution SDXL animation performance is hardware-dependent; a universal high-resolution benchmark has not been established. Video-source hybrid compositing/mask workflows and legacy Deforum feature coverage still need targeted compatibility and physical tests. Optical-flow/RAFT interpolation, unrestricted model support, and a general plugin SDK should **not** be assumed available.
- Some Linux workflows are covered by CI/syntax checks but do not have the same breadth of reported physical GPU testing as the Windows configuration used during development.
- Morphorum's local/LAN web server currently has **no built-in login/authentication**. Never expose its port to the public internet.

## Development workflow and recovery checkpoints

- `main` is the published/stable source branch.
- `dev-ui` is the integration branch used to collect and test features before promotion to `main`.
- New development normally starts on a **feature branch based on `dev-ui`**, with PR and CI checks prior to merging.
- Desktop UX + Motion Lab checkpoint: `checkpoint/desktop-ux-motion-lab-themes-verified-20261010` at `c58d4571b2daf2c64b0b6702cac12ad8ae77d5b1`.
- Wizard/first-run onboarding checkpoint: `checkpoint/wizard-windows-accepted-20261010` at `c750c373b53d944133c9be021bd930f954453be8`.
- Main release baseline checkpoint before wizard promotion: `checkpoint/main-before-wizard-promotion-20261010` at `04aa90a09485d71b130aaa3fe1aa8207727f8d90`.
- dev-ui checkpoint before wizard integration: `checkpoint/dev-ui-before-wizard-20261010` at `aebb87e28a64ee8c2d131ae13c453bf742e1a01a`.
- Pre-release main snapshot: `checkpoint/main-before-desktop-motionlab-promotion-20261010` at `4bc996be29104590a78ae84759a837a8a29a5135`.
- Earlier B5/B6 and Motion Lab checkpoints remain in Git history. Do not delete them as part of a release.

For historical milestones see [Roadmap](ROADMAP.md), [Motion Lab implementation notes](MOTION_LAB_ROADMAP.md), and [B6 physical acceptance](B6_PHYSICAL_ACCEPTANCE.md). For the actual functionality and status of an API or model capability, the current source and automated tests take priority over older planning prose.

## Next development areas

- More desktop and mobile UX refinement; expanded theme/font physical checks.
- Additional per-model performance and stability testing, especially higher resolution and long animations.
- Further compatibility/hybrid composition and mask-workflow validation.
- More first-run installation, model download/recovery, and documented Linux physical acceptance. The new wizard and no-model banner improve onboarding but do not replace real GPU and installer testing.

**See also:** [New Project Wizard](NEW_PROJECT_WIZARD.md) · [Installation](INSTALLATION.md) · [Getting started](GETTING_STARTED.md) · [Troubleshooting](TROUBLESHOOTING.md) · [Docs index](README.md)
