# Morphorum guides

Welcome! You do not need to know Python or Git to use Morphorum. Start with the public [README](../README.md), then choose the guide for what you want to do.

## Get up and running

| Guide | Use it for |
| --- | --- |
| **[Civitai Model Hub](CIVITAI_MODEL_HUB.md)** | Optional model discovery, download queue, local SHA identification, metadata/preview sync, LoRA trigger words and generation integration |
| **[Installation & maintenance](INSTALLATION.md)** | Set up Windows/Linux, choose a folder and port, update, repair, back up data |
| **[Getting started](GETTING_STARTED.md)** | Download/select a model, generate an image, create an animation, export video |
| **[First-Run Setup](GETTING_STARTED.md#first-run-setup-wizard)** | Initial seven-step setup, checkpoint folders, optional managed-model download and 3D starter projects |
| **[New Project Wizard](NEW_PROJECT_WIZARD.md)** | Guided animation setup and explanations of the seven wizard steps |
| **[Project archives & Save Project As](PROJECT_ARCHIVES.md)** | Portable project ZIP import/export, full-input copies, overwrite recovery and safety limits |
| **[Saved project media](PROJECT_MEDIA.md)** | How start images and soundtrack/Motion Lab WAVs persist and restore |
| **[Motion Studio](MOTION_STUDIO.md)** | Six-stage WAV workflow, beat assignment and cleanup, frequency channels, continuous motion and project camera tracks |
| **[Prompt Studio PS1.4 (dev-webui testing)](PROMPT_STUDIO_PS1_MANUAL.md)** | Manual prompt import, separate lanes, saved drafts, project ZIP portability, diff and safe Apply to Editor |
| **[Prompt Studio PS1.3 (dev-webui testing)](PROMPT_STUDIO_PS1_MANUAL.md)** | Manual keyframe prompt import, independent positive/negative lanes, diff preview and safe Apply to Editor |
| **[FFmpeg Manager](FFMPEG_MANAGER.md)** | Auto-detect, custom paths, verified local install, update/removal, media acceptance test and GPL terms |
| **[Troubleshooting](TROUBLESHOOTING.md)** | Fix browser, installer, model, CUDA, LAN, project and video problems |
| **[SDXL generation](SDXL_GENERATION.md)** | Select SDXL samplers/schedules; understand chunked CLIP prompts, LoRA integrity and render diagnostics |
| **[G5 release acceptance history](G5_RELEASE_ACCEPTANCE.md)** | Owner acceptance summary and reusable Windows SDXL regression checklist (not required for normal users) |
| **[About & branch updates](ABOUT_AND_UPDATES.md)** | Project credits/logo, current Git branch/commit, host-only guarded updates and LAN restrictions |

The October 21, 2026 [main promotion (PR #51)](https://github.com/merberg-ai/Morphorum/pull/51) includes the About/update page, locally cached Civitai model/LoRA previews and the managed Z-Image LoRA stability fix. The dedicated [release details](CURRENT_STATUS.md#october-21-2026-promotion-to-main) distinguish Windows user testing from automated CI; Prompt Studio and Parseq are still roadmap-only.

Project Manager, New Project Wizard and Project Editor are direct main-menu destinations. Motion Lab Overview provides a read-only project summary and guided Preview → Apply → Save → Render → Export navigation. Older renders do not automatically acquire newly attached audio. See [current features and limitations](CURRENT_STATUS.md) for testing boundaries.

## Other workflows

| Guide | Use it for |
| --- | --- |
| **[Backend-only / remote clients](BACKEND_ONLY.md)** | Run Morphorum without its browser UI; authenticate a desktop client securely |
| **[Import Deforum Motion Settings](DEFORUM_MOTION_SETTINGS_IMPORT.md)** | Bring compatible camera schedules into an existing 3D project |
| **[Features & limitations](CURRENT_STATUS.md)** | See supported workflows and current alpha boundaries |

## Planned integrations (not yet supported)

- **[PQ Parseq URL Integration Roadmap](PARSEQ_URL_INTEGRATION_ROADMAP.md)**: proposed phased work to consume Parseq's Auto-uploaded JSON via a saved URL, validate and apply supported per-frame controls, freeze each render's manifest, and retain Morphorum's native backend. **Planning only; not implemented.** Development is gated on owner approval and restricted to `dev-webui`.
- **[PS Prompt Studio PS0–PS9 Roadmap](PROMPT_STUDIO_ROADMAP.md)** and **[PS0 technical contract](PROMPT_STUDIO_PS0_CONTRACT.md)**: planned standalone storyboard and visual keyframe editor, model-aware LoRA/trigger word composer, Ollama/optional managed LLM assistant, non-destructive Apply to Animation and **required PS6 audio-to-storyboard synchronization using Motion Studio beat cues**. **PS1.3 manual editing passed Windows testing; PS1.4 saved draft library and portability is available on `dev-webui` for acceptance; main still has no Prompt Studio runtime. AI authoring, audio storyboard sync and persistent draft storage are still planned.**

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for source contributions and [Testing](TESTING.md) for the public test workflow.

Historical research and internal milestones remain available in the [earlier development archive](https://github.com/merberg-ai/Morphorum/tree/archive/development-notes-pre-public-cleanup-20261014) and the [Motion Studio / first-run release checkpoint](https://github.com/merberg-ai/Morphorum/tree/archive/motion-studio-ms6-pre-main-20261015). These are **not** installation instructions. Public-facing guides in this directory describe the supported user experience.

## Experimental standalone Z-Image research (developers)

- [Z-Image single-file milestone history](ZIMAGE_SINGLE_FILE_ROADMAP.md): physical Windows acceptance through Z2.20c3c4, still non-loadable in production
- [Z2.20c3c5 implementation plan](ZIMAGE_C3C5_IMPLEMENTATION_PLAN.md): next planned strictly gated 32×32 diagnostic PNG, not yet implemented

These are research notes, not user installation or normal model-selection instructions. Managed Z-Image remains unchanged.


## In-app Help

The desktop WebUI's left-hand **Help** entry (phone: **More → Help**) opens the locally bundled `docs/` Markdown guides within the same WebUI. It reads files via restricted, read-only Help endpoints and doesn't redirect to GitHub or replace FastAPI's existing `/docs` API console. Source documentation updates appear after the next `git pull` and app restart. See [WebUI layout architecture](WEBUI_LAYOUT.md) for implementation boundaries.

## Recent editor workflow changes

The Project Editor now supports **+ Keyframe** with automatic even spacing and an explicit **Evenly Space** control; frames start at zero and the last prompt may land on `max_frames - 1`. Existing positive and negative prompt text is preserved. The Image Studio's **Apply Image Settings to Project** copies model, dimensions, steps, sampler, schedule and seed settings to the open project's draft, while deliberately preserving prompts and CFG; **Save Project** persists changes. SDXL LoRA verification is a collapsed-by-default, locally persistent disclosure. The Results progress bar is just above the preview, and the empty-image placeholder has no redundant Settings/Models shortcuts. Expanded phone menus are constrained to the screen, and Help reads these bundled guides within the application. [WebUI layout details](WEBUI_LAYOUT.md) · [Deferred LoRA diagnostics](https://github.com/merberg-ai/Morphorum/blob/main/TODO.MD).

## Portable project settings and media

[Project archive import/export and Save Project As](PROJECT_ARCHIVES.md) explains how to transfer complete project settings and project-owned input media, confirm overwrite while preserving a Trash backup, and exclude generated renders. The owner reported successful Windows acceptance on October 19, 2026.

- **[About Morphorum & Git updates](ABOUT_AND_UPDATES.md)**: project credits, live branch status, host-only apply, restart and logo instructions
