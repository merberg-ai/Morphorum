# Morphorum

**Local AI image generation and Deforum-style animation, from one browser-based studio.**

Morphorum is a self-hosted image and motion-graphics application for **Windows and Linux**. Generate still images, build keyframed 2D/3D animations, experiment with audio-reactive camera motion, and export videos without relying on a hosted generation service.

**Release:** `0.1.0a1` (early alpha) · **License:** [The Unlicense](LICENSE) · **Source:** [GitHub](https://github.com/merberg-ai/Morphorum)

> [!IMPORTANT]
> Morphorum is **alpha software**. It has working local generation and animation workflows, but expect large downloads, hardware-dependent performance, and occasional rough edges. Back up important projects before updating. AI checkpoints are **not bundled** with the application.

## Get started in three steps

### 1. Install Morphorum

**Windows 10/11**

1. Download **[bootstrap.bat](https://raw.githubusercontent.com/merberg-ai/Morphorum/main/bootstrap.bat)**.
2. Open your Downloads folder and run `bootstrap.bat`.
3. When prompted, press **Enter** to install to `C:\Morphorum`, or enter another folder such as `D:\Morphorum`.
4. Press **Enter** to use the default server port (**7865**), or choose another number.
5. Let the installer finish. It downloads the required Python runtime and dependencies automatically.

Or use PowerShell to download and launch it:

```powershell
curl.exe -fL -o bootstrap.bat https://raw.githubusercontent.com/merberg-ai/Morphorum/main/bootstrap.bat
.\bootstrap.bat
```

> [!TIP]
> Prefer a different folder and port without being prompted? Run `.\bootstrap.bat -InstallDir "D:\Morphorum" -Port 8080`. The installer can also install Git and FFmpeg through Windows Package Manager when available.

**Linux**

Paste this into a terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.sh | bash
```

The default location is `~/Morphorum`. To choose a different location:

```bash
curl -fsSL https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.sh | bash -s -- "$HOME/Apps/Morphorum"
```

Some Linux systems may need FFmpeg installed separately. See the [full installation guide](docs/INSTALLATION.md#linux).

### 2. Start the application

**Windows** (PowerShell, after installing to the default location):

```powershell
cd C:\Morphorum
.\run.bat
```

**Linux:**

```bash
cd ~/Morphorum
./run.sh
```

Keep the terminal window open while using Morphorum. In your browser, go to:

**[http://127.0.0.1:7865](http://127.0.0.1:7865)**

If you chose a different server port during installation, replace `7865` with that port. Press **Ctrl+C** in the terminal to stop the server.

### 3. Get a model and generate something

1. In Morphorum, open **Models**.
2. Find the managed **Z-Image-Turbo** option, choose **Download**, and wait for it to finish. This is a large download (approximately **33 GB**) and requires additional disk space for the runtime and generated files.
3. Select **Use Model** when it becomes available.
4. Open **Image Generation**, type a prompt, choose a resolution, and generate your first image.

You can also index supported **SDXL** and **FLUX** checkpoints from directories you already have. Z-Image-Turbo uses **one model package** for text-to-image and image-to-image; you do not need two downloads.

See [First steps](docs/GETTING_STARTED.md) for a guided walkthrough of still images, the included animation project, and exporting a video.

## What you can do

| Workspace | Highlights |
| --- | --- |
| **Image Generation** | SDXL, FLUX, and Z-Image generation; model-aware presets, prompts, seeds, batches, progress, and results. |
| **Motion Lab** | Keyframed 2D/3D camera animation, six-axis motion, depth-aware previews, layered presets, and curve/path editing. |
| **New Project Wizard** | Guided seven-step project creation with contextual help, model-specific defaults, prompts/keyframes, motion presets, and a final review and save. |
| **Project Manager** | Search, inspect, create, open, rename, and move animation projects to Trash. |
| **Live Recording** | Record camera movement with keyboard/touch controls and supported browser gamepads. |
| **Audio Motion** | Analyze audio and map rhythm/frequency bands to camera movement; export sound with animation when configured. |
| **Render Monitor / Outputs** | Monitor long renders; preview frames, pause/resume/cancel supported jobs, and export MP4/WebM. |
| **Models / LoRAs** | Scan external model and LoRA folders, inspect metadata, and insert compatible LoRA tags into prompts. A no-model warning provides setup instructions when no checkpoint is available. |
| **Settings / Console** | Choose four dark themes, select UI/monospace fonts, manage model paths, and view diagnostic logs. |

The **version badge** in the top-right corner also links directly to this repository, the checked-out Git branch, and the exact Git commit, making it easier to find the code running on your machine.

**Appearance themes:** **Midnight Glass** (near-black), **Deep Ocean** (dark blue), **Amethyst Night** (dark purple), and **Slate Graphite** (grey). Interface and technical/console fonts can be selected independently in Settings.

Additional functionality includes Deforum-style timeline/schedule controls, selected legacy Deforum settings import, video-source inspection/extraction and hybrid-frame workflows. **Legacy imports are not guaranteed to reproduce every Deforum extension or unsupported setting.**

> [!NOTE]
> **Model availability matters.** Morphorum does not ship SDXL, FLUX, or Z-Image checkpoints. Some advanced workflows need substantial NVIDIA GPU VRAM, disk space, or FFmpeg. A model must be downloaded or indexed before you can render an image or animation.

## First animation: use the New Project Wizard

For a new project, open **Motion Lab → New Project Wizard**. It guides you through **Name → Model → Animation Setup → Prompts & Keyframes → Camera Motion → Generation Settings → Review & Save**, with help hints and Back/Next controls. The wizard uses the same default-project schema as Project Editor, validates schedules, and **does not create a project until you select Save Project & Open Editor**. The final screen introduces optional Audio Motion. See the [complete wizard walkthrough](docs/NEW_PROJECT_WIZARD.md).

If no checkpoints are available, a translucent **No generation models available** banner links to setup instructions for Z-Image-Turbo downloads and SDXL/FLUX/LoRA directories. Your selected model is required to complete the wizard.

### Or explore the included Default project

New installations with an empty project library include a **Default** example animation (3D, **120 frames at 24 FPS**, 1024 × 1024, with two keyframed cat prompts).

1. Open **Motion Lab → Project Manager** and select **Default**.
2. Choose **Open in Editor**, select a compatible model, and review the project settings.
3. Open **Camera Composer** or **Motion Curves & Path** to experiment with movement. Use **Camera Preview** for a quick look.
4. Apply your changes and select **Render Animation**. The **Render Monitor** displays progress.
5. Review your completed work in **Outputs** and export a video.

For the safest first test, use a **short project and a model-supported resolution** rather than immediately rendering all 120 frames at 1024 × 1024.

The starter project is installed **only when no projects exist**. An update or repair will not replace an edited project.

## Running, updating, and repairing

Run these from your **Morphorum installation directory**:

| Task | Windows | Linux |
| --- | --- | --- |
| Start locally | `.\run.bat` | `./run.sh` |
| Allow access from other devices on your LAN | `.\run-lan.bat` | `./run-lan.sh` |
| Update the current branch | `.\update.bat` | `./update.sh` |
| Update to the main branch | `.\update.bat main` | `./update.sh main` |
| Repair / run diagnostics | `.\repair.bat` | `./repair.sh` |

On Windows, the installer remembers your selected port. You can override it for one run with `.\run.bat -Port 8080` or `.\run-lan.bat -Port 8080`, without changing the saved setting.

> [!WARNING]
> **LAN mode is not an internet-facing service.** It binds the application to network interfaces so trusted devices on your local network can connect. Morphorum does **not** currently provide built-in authentication for that server. **Do not** forward its port on your router or expose it directly to the internet.

Updates protect Git-tracked changes and preserve project and configuration directories. For important work, keep a separate backup of your `projects/` and `outputs/` directories.

## Requirements at a glance

- **Windows:** Windows 10/11, a supported 64-bit system, enough disk space, and network access during setup. The installer can provision its own Python 3.12 environment.
- **Linux:** 64-bit Linux, common shell utilities, Git, and internet access for setup. Git can be installed automatically on several supported distributions.
- **AI generation:** A supported **NVIDIA GPU with CUDA** is strongly recommended for practical local generation. CPU fallback, where available, can be extremely slow.
- **Disk space:** The installer checks for at least **8 GiB free** for the base runtime, **not** for checkpoints. Plan **tens of gigabytes more** per model; managed Z-Image-Turbo advertises approximately **33 GB**.
- **Video:** FFmpeg is required for video encoding/export and certain source-video workflows.

For detailed system preparation, troubleshooting, and an explanation of what the installer changes, see [Installation & maintenance](docs/INSTALLATION.md).

## Documentation

| Guide | Start here for |
| --- | --- |
| **[Getting started](docs/GETTING_STARTED.md)** | Your first image, animation, model, and export |
| **[New Project Wizard](docs/NEW_PROJECT_WIZARD.md)** | Step-by-step project setup, motion presets, hints, validation, and saving |
| **[Installation & maintenance](docs/INSTALLATION.md)** | Windows/Linux install, ports, update, repair, paths, logs |
| **[Troubleshooting](docs/TROUBLESHOOTING.md)** | Common download, GPU, startup, port, and render problems |
| **[Features & current status](docs/CURRENT_STATUS.md)** | What is implemented, limitations, and development branches |
| **[Developer docs index](docs/README.md)** | Architecture, project formats, schedule/render internals, roadmap |

## Development and contributions

Morphorum is an independent, clean-room implementation inspired by Deforum workflows. Supported file formats and observable behavior can be studied and reimplemented, but **GPL/AGPL-covered source code must not be copied** into the Unlicensed core.

Development normally proceeds on **feature branches → `dev-ui` → `main`** after review and tests. Earlier milestone notes are historical and may not reflect the current build.

See [Contributing](CONTRIBUTING.md), [the license](LICENSE), [third-party notices](THIRD_PARTY.md), and [additional notices](NOTICE.md).
