# Morphorum

**Create AI images, build camera-driven animations, and export videos on your own computer.**

Morphorum is an open-source, self-hosted image and animation studio with a browser interface. It supports **SDXL, FLUX, and Z-Image** models, a guided animation wizard, 2D/3D Motion Lab, and optional remote control through an authenticated backend API.

**Version:** 0.1.0a1 (early alpha) · **License:** [The Unlicense](LICENSE) · **Platforms:** Windows 10/11 and 64-bit Linux

> [!IMPORTANT]
> Morphorum is early alpha software. It does not include AI model weights. A compatible NVIDIA GPU is strongly recommended, and you should keep backups of your projects and outputs.

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

## What can Morphorum do?

| Feature | What it provides |
| --- | --- |
| Image Generation | Text-to-image and supported image-to-image generation, model-aware presets, seeds, batches and progress |
| Models & LoRAs | Managed Z-Image-Turbo installation, external SDXL/FLUX folders, model-aware LoRA discovery |
| First-Run Setup Wizard | Seven guided installation checks, optional Z-Image download, and two short 3D starter projects |
| New Project Wizard | Seven guided pages from naming and model selection to motion, prompts and saving |
| Motion Lab | Keyframes, 2D/3D camera movement, six-axis camera composer, live motion recording, curves and previews |
| Motion Studio | Analyze project audio; edit beats, independent frequency channels and synchronized camera cues; stage, preview and apply movements |
| Animation & Outputs | Frame rendering, progress monitoring, completed-frame previews, MP4/WebM export with FFmpeg |
| FFmpeg Manager | Auto-detect host FFmpeg/FFprobe, choose a custom executable, or opt in to a verified local managed download, update and removal |
| Import Motion Settings | Compatible Deforum Motion Studio camera schedules, optional soundtrack attachment |
| Interface | Responsive browser layout, built-in console and telemetry, themes: **Midnight Glass**, **Deep Ocean**, **Amethyst Night**, **Slate Graphite** |

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
- **[Motion Studio](docs/MOTION_STUDIO.md)**: audio-driven motion, independent sound channels, recording, presets and synchronized preview
- **[FFmpeg Manager](docs/FFMPEG_MANAGER.md)**: select, verify, install, update or remove local video/audio utilities
- **[Backend-only mode](docs/BACKEND_ONLY.md)**: LAN setup, per-client credentials, connection checks, security
- **[Troubleshooting](docs/TROUBLESHOOTING.md)**: installer, model, CUDA, networking and export problems
- **[Documentation index](docs/README.md)**: all maintained user and contributor guides

## Project information

Morphorum is independent software inspired by Deforum-style creative workflows; it is **not** a copy of Deforum or a guarantee of output compatibility. Some features are experimental, and large renders depend on GPU and model capabilities. Visit [GitHub Issues](https://github.com/merberg-ai/Morphorum/issues) to report bugs or request improvements.

Contributions are welcome: [Contributing](CONTRIBUTING.md) · [License](LICENSE) · [Third-party acknowledgments](THIRD_PARTY.md) · [Notices](NOTICE.md).
