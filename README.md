# Morphorum

**Create AI images, build camera-driven animations, and export videos on your own computer.**

Morphorum is an open-source, self-hosted image and animation studio with a browser interface. It supports **SDXL, FLUX, and Z-Image** models, a guided animation wizard, 2D/3D Motion Lab, an optional opt-in Civitai Hub for model discovery and downloads, and remote control through an authenticated backend API.

**Version:** 0.1.0a1 (early alpha) · **License:** [The Unlicense](LICENSE) · **Platforms:** Windows 10/11 and 64-bit Linux

> [!IMPORTANT]
> Morphorum is early alpha software. It does not include AI model weights. A compatible NVIDIA GPU is strongly recommended, and you should keep backups of your projects and outputs.

## Civitai Model Hub

Enable **Civitai Hub** under **Settings** to search, inspect, and download compatible SDXL, FLUX, and Z-Image checkpoints and LoRAs directly in Morphorum. The Hub is disabled by default; optional API token authentication supports restricted downloads. Download destinations come from your configured model libraries. Model files are never silently replaced.

You can identify installed files by exact SHA-256, check Civitai for newer versions, synchronize metadata/preview images and LoRA trigger words, and run bulk actions on selected models. Verified installed models can be selected for **Image** or the **Project Editor / Motion Lab**, and LoRAs can be inserted into prompts with synced trigger words. Network lookups and metadata synchronization require deliberate actions; no automatic model updates occur.

See the [Civitai Hub guide](docs/CIVITAI_MODEL_HUB.md) for configuration, privacy, download resume, and limitations.

## Quick start

### 1. Install

**Windows (recommended):**

1. Download **[bootstrap.bat](https://raw.githubusercontent.com/merberg-ai/Morphorum/main/bootstrap.bat)** from this repository.
2. Run the downloaded file and follow the prompts. Choose the default **`C:\Morphorum`** folder and **7865** port, or enter your own.
3. The installer downloads Morphorum and sets up its own Python environment. It may offer to install Git or FFmpeg through Windows Package Manager.

Prefer PowerShell? Download and run the same installer:

~~~powershell
curl.exe -fL -o bootstrap.bat https://raw.githubusercontent.com/merberg-ai/Morphorum/main/bootstrap.bat
.\bootstrap.bat
~~~

**Linux (64-bit):**

~~~bash
curl -fsSL https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.sh | bash
~~~

The default Linux installation is `~/Morphorum`. The bootstrap may request `sudo` to install Git if it is missing. See [installation options](docs/INSTALLATION.md) for custom directories, supported platforms, and troubleshooting.

> **Space and hardware:** The base installer checks for at least **8 GiB free**, but AI models and generated video need much more. The optional Z-Image-Turbo package is approximately **33 GB** by itself. CUDA-capable NVIDIA hardware is recommended; CPU generation may be extremely slow.

### 2. Start Morphorum

From your installation folder:

| Windows PowerShell | Linux terminal |
| --- | --- |
| `cd C:\Morphorum` then `.\run.bat` | `cd ~/Morphorum` then `./run.sh` |

Open **http://127.0.0.1:7865** in your browser. If you selected a different Windows installation port, use that instead. Keep the terminal open while using Morphorum; press **Ctrl+C** to stop its server.

A **fresh installation** automatically opens the seven-page **First-Run Setup Wizard** on its first WebUI load. It explains WebUI versus backend-only mode, checks model and optional LoRA folders on the host, offers the optional managed Z-Image-Turbo download, and lets you create a tiny **Gentle Dolly In** or **Gentle Dolly Out** sample project (512 × 512, 48 frames, 12 FPS). Nothing downloads, renders, or creates a project until you explicitly choose the action.

You can skip onboarding and configure everything later. For an existing installation, reopen it from **Settings → Setup Wizard**, or launch the WebUI with `.\run.bat --setup-wizard` on Windows / `./run.sh --setup-wizard` on Linux. Backend-only mode does not have a browser wizard. See [First-run setup](docs/GETTING_STARTED.md#first-run-setup-wizard).

### 3. Add a model and make an image

1. Open **Models** in Morphorum.
2. Download the managed **Z-Image-Turbo** model, or go to **Settings** to index your existing SDXL/FLUX model directories.
3. Choose **Use Model** when a model is ready.
4. Open **Image Generation**, enter a prompt, and generate a single test image using a recommended resolution.

The translucent **No generation models available** notice provides setup help if Morphorum cannot find a base checkpoint. LoRAs cannot be used as a replacement for a base model.

For step-by-step screenshots-free guidance, see [Your first image and animation](docs/GETTING_STARTED.md).

## Current Motion Lab and project workflow

The main navigation offers **Project Manager**, **New Project**, and **Project Editor** directly. Project Editor groups controls into **Setup**, **Sources & Media**, **Timeline & Prompts**, **Camera & Motion**, and **Generation Settings**. The Project Manager supports searching, bulk selection, moving projects to Trash with confirmation, **exporting/importing verified project ZIPs**, and **Save Project As** for duplicating a project with its attached input media. Project Editor also offers **Save Project As**. Rendered images and videos are excluded from these portable project copies.

**Motion Lab → Overview** presents a live read-only project summary and a guided **Preview Draft → Apply Motion → Save Project → Render Animation → Export Video** workflow. Previewing does not save or apply camera movement. Applying Motion Lab layers updates the project's camera schedules, and the workflow's Save Project action calls the existing save operation. A render uses the applied project schedule, not an unapplied draft. Check Camera Preview and any preflight warnings before expensive 3D renders.

**Motion Lab → Motion Studio** guides you through **Load Audio → Analyze WAV → Detect Beats → Assign Motion to Beats → Create Motion → Preview & Apply**. Beat-cue selections support bulk cleanup and undo before saving cues. The active project soundtrack may be reused for analysis and attached to future renders, but old render soundtracks are not rewritten; a past silent render must be regenerated to include subsequently attached audio. See [Motion Studio](docs/MOTION_STUDIO.md) for details.

**Release/testing note (October 2026):** Windows owner testing has confirmed successful animation generation and an MP4 with audio, plus acceptance of the G5 SDXL integration milestone (samplers and schedules, chunked prompt conditioning, LoRA verification, and diagnostics). Dedicated physical mobile acceptance is deferred, and remaining P5 work is tracked separately. This remains alpha software. See [SDXL generation](docs/SDXL_GENERATION.md) and [testing history](docs/TESTING.md).

## Local Models & LoRA artwork (available on main)

After explicitly synchronizing a verified installed checkpoint or LoRA using
**Sync Civitai Info**, Morphorum keeps available Civitai still-image thumbnails
with the rest of its cached metadata. The Models manager displays responsive
thumbnail cards, including an opt-in **Sync Selected** action; the LoRA manager
shows library thumbnails and a larger selected-adapter image. Reopening either
manager reads local cached assets only, without an automatic remote Civitai
request. Models with no usable preview display a placeholder. The Civitai Hub
must be enabled and its thumbnail/mature-content preferences still apply.

[Local thumbnail behavior, safety limits and test checklist](docs/CIVITAI_MODEL_HUB.md)

## What can Morphorum do?

| Feature | What it provides |
| --- | --- |
| Image Generation | Text-to-image and supported image-to-image generation, model-aware presets, seeds, batches and progress; SDXL sampler/schedule controls, long positive/negative prompt chunking and conditioning diagnostics |
| Models & LoRAs | Managed Z-Image-Turbo installation, external SDXL/FLUX folders, model-aware LoRA discovery, SDXL adapter integrity checks, explicit Civitai metadata/thumbnail sync and responsive cached preview cards |
| First-Run Setup Wizard | Seven guided installation checks, optional Z-Image download, and two short 3D starter projects |
| New Project Wizard | Seven guided pages from naming and model selection to motion, prompts and saving |
| Motion Lab | Camera authoring, read-only project overview, guided preview/apply/save/render/export flow, six-axis composer, live recording, curves and previews |
| Motion Studio | Guided six-stage WAV workflow, beat detection, batch beat-cue assignments and cleanup, frequency channels, continuous presets, preview and apply |
| Animation & Outputs | Frame rendering, progress monitoring, SDXL long-prompt blending/cache telemetry, completed-frame previews, MP4/WebM export with FFmpeg |
| FFmpeg Manager | Auto-detect host FFmpeg/FFprobe, choose a custom executable, or opt in to a verified local managed download, update and removal |
| Project transfer & duplication | Verified ZIP export/import of full project settings and attached input media; explicit overwrite confirmation and recoverable Trash backup; Save Project As from Manager or Editor |
| Import Motion Settings | Compatible Deforum Motion Studio camera schedules, optional soundtrack attachment |
| Interface | Responsive browser layout, built-in console and telemetry, About page with project credits and current-branch update checks, themes: **Midnight Glass**, **Deep Ocean**, **Amethyst Night**, **Slate Graphite** |

### Video encoding: FFmpeg Manager

Morphorum needs **FFmpeg** for MP4/WebM export and **FFprobe** for source-video inspection. Open **Settings → Storage → FFmpeg Manager** and choose **Auto-detect**, **Custom executable**, or **Morphorum-managed local FFmpeg**.

For a hassle-free setup, choose **Managed → Install managed FFmpeg**, then **Test FFmpeg / FFprobe** and **Save Settings**. The optional download is verified with its upstream SHA-256 and installed only inside your Morphorum folder under `tools/ffmpeg/current/bin`; it does not change the system PATH or install anything globally. Downloads are opt-in. Managed FFmpeg is third-party **GPL software**, separate from Morphorum's Unlicense.

[FFmpeg Manager setup, upgrades, removal, compatibility and licensing](docs/FFMPEG_MANAGER.md) · [CPU-only encoding smoke test](docs/FFMPEG_MANAGER.md#verify-a-managed-installation)

A new installation may include a **Default** example project (120 frames at 24 FPS), created only when the project library is empty. For a first render, reduce the frame count and choose an appropriate model and image size.

[See features and limitations](docs/CURRENT_STATUS.md) · [New Project Wizard](docs/NEW_PROJECT_WIZARD.md) · [Deforum motion import](docs/DEFORUM_MOTION_SETTINGS_IMPORT.md)

## Everyday commands

Run these **from your installed Morphorum directory**, after stopping an active server before updates:

| Action | Windows | Linux |
| --- | --- | --- |
| Local browser app | `.\run.bat` | `./run.sh` |
| Browser app on trusted LAN | `.\run-lan.bat` | `./run-lan.sh` |
| Backend API only, local | `.\run.bat --backend-only` | `./run.sh --backend-only` |
| Backend API only, trusted LAN | `.\run.bat --backend-only --lan` | `./run.sh --backend-only --lan` |
| Update current branch | `.\update.bat` | `./update.sh` |
| Switch/update to public main | `.\update.bat main` | `./update.sh main` |
| Repair environment | `.\repair.bat` | `./repair.sh` |

### Browser mode vs. backend-only mode

The usual launcher provides both a **web interface and generation API**, typically on port **7865**. Backend-only mode provides **just the API**, typically on port **7866**, for clients such as the separate [Morphorum Studio desktop app](https://github.com/merberg-ai/Morphorum-Studio). Backend-only requests require an authorization token; its root browser page is intentionally absent.

**Security matters:** `run-lan` exposes the ordinary, **unauthenticated** browser app to your private network. Backend-only LAN mode requires bearer credentials, **but plain HTTP does not encrypt them**. Neither mode should be directly exposed to the public internet or forwarded through your router. Use secure networking and read [Backend-only setup and client authentication](docs/BACKEND_ONLY.md) before connecting remotely.

## Documentation

- **[Install & maintain](docs/INSTALLATION.md)**: Windows/Linux setup, custom locations, updates, repairs, data backups
- **[Getting started](docs/GETTING_STARTED.md)**: first-run setup, first image, animation and video
- **[SDXL generation](docs/SDXL_GENERATION.md)**: samplers, schedules, long positive/negative prompts, LoRA verification, animation performance
- **[Motion Studio](docs/MOTION_STUDIO.md)**: audio-driven motion, independent sound channels, recording, presets and synchronized preview
- **[FFmpeg Manager](docs/FFMPEG_MANAGER.md)**: select, verify, install, update or remove local video/audio utilities
- **[Backend-only mode](docs/BACKEND_ONLY.md)**: LAN setup, per-client credentials, connection checks, security
- **[Troubleshooting](docs/TROUBLESHOOTING.md)**: installer, model, CUDA, networking and export problems
- **[Documentation index](docs/README.md)**: all maintained user and contributor guides
- **[Planned Prompt Studio](docs/PROMPT_STUDIO_ROADMAP.md)**: PS0–PS9 design, including required audio-to-storyboard synchronization; **not implemented**
- **[Planned Parseq URL integration](docs/PARSEQ_URL_INTEGRATION_ROADMAP.md)**: PQ0–PQ7 hosted JSON workflow; **not implemented**

## About & built-in updater

The **About** page (desktop navigation, or **More → About** on mobile) introduces Morphorum, credits Deforum and SD WebUI Forge plus community members including **chicodog530**, and links the GitHub repository. It also displays your **installed version, checked-out branch and commit**, with an on-demand **Check for updates** action that fetches only the checked-out branch.

When a clean working copy is behind its remote, **Update current branch** runs the existing backup/rollback installer from a browser on the **host computer only**; remote LAN browsers can check but cannot apply updates because the regular WebUI is unauthenticated. Never update while rendering; restart Morphorum afterward. The About page now includes the optimized blue-and-purple Morphorum skull logo, sized to preserve its full artwork on desktop and mobile.

[About and update safeguards](docs/ABOUT_AND_UPDATES.md)

**Managed Z-Image LoRA stability (merged October 21, 2026):** The corrected Z-Image inference context avoids the previously observed inference-tensor/PEFT adapter error while preserving offloading. The owner verified multiple still generations with and without LoRAs and an animation without recurrence. This is not a claim that every LoRA combination was tested. The separate Z-Image animation continuity investigation (ZT1) remains open in [TODO.MD](TODO.MD).

## Project information

Morphorum is independent software inspired by Deforum-style creative workflows; it is **not** a copy of Deforum or a guarantee of output compatibility. Some features are experimental, and large renders depend on GPU and model capabilities. Visit [GitHub Issues](https://github.com/merberg-ai/Morphorum/issues) to report bugs or request improvements.

Contributions are welcome: [Contributing](CONTRIBUTING.md) · [License](LICENSE) · [Third-party acknowledgments](THIRD_PARTY.md) · [Notices](NOTICE.md).

### Experimental standalone Z-Image checkpoints (development only)

The isolated Z-Image single-file research track has **owner-tested the isolated conversion/inference diagnostics through Z2.20c3c4**: converted BF16 transformer and Qwen3 encoder, native prompt encoding, two guarded CUDA denoising steps and CPU VAE numerical decoding to a 32 × 32 RGB tensor. **This does not mean external Z-Image checkpoints are supported for normal generation.** No diagnostic image file has been saved, and the current managed Z-Image-Turbo pipeline remains unchanged. The next step, [Z2.20c3c5 diagnostic PNG](docs/ZIMAGE_C3C5_IMPLEMENTATION_PLAN.md), is **planned, not implemented**. See [the detailed research roadmap](docs/ZIMAGE_SINGLE_FILE_ROADMAP.md). These are contributor-only experiments; do not run them as installation steps.

## Latest WebUI usability improvements

The Image Studio keeps generation progress directly above the Results preview, and the empty preview stays uncluttered until images are generated. The **SDXL LoRA verification** report is collapsed by default, expands on demand, and remembers your preference. In **Image**, **Apply Image Settings to Project** transfers the selected checkpoint, image dimensions, step count, sampler, schedule and seed settings to the currently open animation project's **unsaved editor draft**. It does **not** overwrite either prompt or CFG; press **Save Project** to persist the edits.

Project Editor's **Prompt Keyframes** now offers **+ Keyframe** with automatic even redistribution, alongside **Evenly Space** to redistribute existing prompts. Positive and negative prompt text is retained in order; frame numbers remain manually editable. For a 543-frame animation, five prompts are positioned at 0, 136, 271, 407 and 542. The sidebar's expanding menus have bounded mobile layouts. **Help** opens the installed `docs/` guides within the WebUI, from the desktop sidebar or mobile More menu. See [WebUI layout details](docs/WEBUI_LAYOUT.md).

The SDXL LoRA follow-up diagnostic investigation is deferred in [TODO.MD](https://github.com/merberg-ai/Morphorum/blob/main/TODO.MD); current reports must not be mistaken for independent verification of all UNet scaling factors. Experimental external single-file Z-Image remains unavailable for regular generation.

## Portable animation projects

In **Project Manager**, use **Export ZIP** for saved settings and project-owned inputs (starting image, soundtrack and Motion Lab WAVs). **Import Project ZIP** validates the archive before writing and asks whether to load the imported project. If the same project ID already exists, you must confirm replacement by typing its current name; Morphorum backs up the old project folder to managed Trash. **Save Project As** creates an independent project with the complete configuration and attached input media, leaving the original unchanged. It is also available in Project Editor, where it carries the current unsaved Editor configuration into the **new copy only**.

**No generated images, animation frames, rendered videos, model weights or LoRA files are included.** Archives are currently limited to 256 MiB compressed / 512 MiB expanded. The owner reported successful Windows acceptance of these workflows on October 19, 2026; additional device-specific testing is welcome. [Project archive guide](docs/PROJECT_ARCHIVES.md) · [Project media restoration](docs/PROJECT_MEDIA.md).
