# Installation and maintenance

This guide covers the supported Windows and Linux installers, first launch, network access, updates and backups. For the shortest path, follow the [README quick start](../README.md#quick-start).

> [!IMPORTANT]
> Morphorum is early alpha. Models are **not included** and can require substantial downloads. The installer configures a **private Python 3.12 environment** for Morphorum; you do not need to install Python or Node.js manually.

## Requirements

| Requirement | Details |
| --- | --- |
| Operating system | Windows 10/11 or a compatible 64-bit Linux distribution |
| GPU | NVIDIA CUDA GPU strongly recommended; CPU-only generation may be extremely slow |
| Disk space | At least **8 GiB free** for initial runtime checks, plus model weights, caches and outputs; Z-Image-Turbo is approximately **33 GB** |
| Internet | Needed for source, managed runtime/dependencies, and any models you download |
| Git | Installed automatically on supported setups, or install it yourself |
| FFmpeg + FFprobe | Used for video export and source-video/audio conversion; Windows installer may use `winget`, Linux distribution packages. In Settings → Storage → FFmpeg Manager, select auto-detection or supply a custom executable and test it. The managed downloader is a separate, upcoming phase. |

Use the default installation directory if you are not sure. Avoid installing inside a source-controlled project or an existing folder containing unrelated files.

## Windows installation

1. Download [bootstrap.bat](https://raw.githubusercontent.com/merberg-ai/Morphorum/main/bootstrap.bat).
2. Run it from Downloads (or launch from PowerShell). Windows may ask you to confirm running a downloaded script; only run files you trust.
3. Select an installation folder. Press Enter to use **`C:\Morphorum`**; other locations such as `D:\Morphorum` work too.
4. Choose a server port. Press Enter for **7865**.
5. Let setup finish. The installer sets up Git when needed, downloads a managed Python runtime, installs compatible dependencies, checks CUDA when NVIDIA hardware is present, and runs its self-test.

PowerShell alternative:

~~~powershell
curl.exe -fL -o bootstrap.bat https://raw.githubusercontent.com/merberg-ai/Morphorum/main/bootstrap.bat
.\bootstrap.bat
~~~

Noninteractive folder and port selection:

~~~powershell
.\bootstrap.bat -InstallDir "D:\Morphorum" -Port 8080
~~~

The published installer uses the `main` branch by default. `-Branch` is available for advanced testing, but is not needed for a normal installation. The Windows bootstrap accepts `-InstallDir`, `-Port`, and `-Branch`; use `bootstrap.bat -Help` to inspect its arguments. A standalone downloaded `bootstrap.bat` fetches the matching PowerShell bootstrap script from GitHub before proceeding.

### Windows: start the app

Open **PowerShell**:

~~~powershell
cd C:\Morphorum
.\run.bat
~~~

Go to **http://127.0.0.1:7865** in your browser. If you chose another port, use that port. Leave the PowerShell window open; **Ctrl+C** stops the server.

Change the listening port for one launch without overwriting the saved selection:

~~~powershell
.\run.bat -Port 8080
~~~

## Linux installation

From a terminal on 64-bit Linux:

~~~bash
curl -fsSL https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.sh | bash
~~~

This installs into **`~/Morphorum`** and clones the published `main` branch. The bootstrap may ask for `sudo` to install Git using a supported package manager. If preferred, inspect/download the bootstrap script before executing it. If run again against an existing installed checkout, the bootstrap invokes the guarded updater rather than treating it as a fresh installation.

For a custom folder:

~~~bash
curl -fsSL https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.sh | bash -s -- "$HOME/Apps/Morphorum"
~~~

An explicit install path takes priority over the optional `MORPHORUM_HOME` variable. Some Linux systems require FFmpeg to be installed separately. GPU drivers and CUDA support depend on your distribution.

### Linux: start the app

~~~bash
cd ~/Morphorum
./run.sh
~~~

Visit **http://127.0.0.1:7865**. An optional per-launch port override is supported:

~~~bash
MORPHORUM_PORT_OVERRIDE=8080 ./run.sh
~~~

The Linux launcher does not use the Windows saved-port file.

## First launch: guided setup

On a genuinely fresh installation, **First-Run Setup Wizard** appears automatically when you first load the standard local WebUI. Upgrading an existing installation does **not** assume that missing models mean you want onboarding.

The seven screens guide you through:

1. Welcome and host diagnostics (GPU/CUDA and available storage).
2. WebUI (default) versus authenticated backend-only mode. Switching modes requires restarting Morphorum.
3. SDXL and FLUX checkpoint folders on the **host computer**.
4. Optional family-specific LoRA folders.
5. Optional managed Z-Image-Turbo download, with an explicit confirmation and resumable progress.
6. Exactly two **512 × 512, 48-frame, 12 FPS** starter animation choices: *Gentle Dolly In* and *Gentle Dolly Out*.
7. A review page with **Create Example & Open Editor** or **Finish Without Example**.

Opening the wizard never downloads models, renders frames, or creates a project. You can skip and return later from **Settings → Setup Wizard**. The small examples may be opened as editable but **not render-ready** projects if you have not configured a base model. Finishing or skipping onboarding does not erase existing settings or projects.

To manually show setup on the next **WebUI** launch:

| Windows | Linux |
| --- | --- |
| `.\run.bat --setup-wizard` | `./run.sh --setup-wizard` |

Use the command only after stopping an already-running server. The option is incompatible with `--backend-only`, which deliberately has no browser interface. Model directories entered in the wizard refer to the machine running Morphorum, not necessarily the browser device on a LAN.

## After installation: choose a model

1. Open **Models**.
2. Download managed **Z-Image-Turbo** (approximately 33 GB), then choose **Use Model**, **or** specify your existing SDXL/FLUX folders in **Settings**, scan and select an available checkpoint.
3. Use **Image Generation** to make one modest-resolution test image.
4. For animation, choose the first-run Dolly In/Out example or **Motion Lab → New Project Wizard**.

A new installation with no saved projects may include the **Default** example animation: 120 frames at 24 FPS. It does not automatically have a model assigned, and a full 1024 × 1024 animation is not the best first GPU test.

Continue with [Getting started](GETTING_STARTED.md) for the full walkthrough.

## Network access: three choices

| Mode | Windows | Linux | Default port | Access |
| --- | --- | --- | --- | --- |
| Local browser + API | `.\run.bat` | `./run.sh` | 7865 | This computer only |
| Browser + API on trusted LAN | `.\run-lan.bat` | `./run-lan.sh` | 7865 | Other local devices; **no login** |
| Authenticated backend-only API | `.\run.bat --backend-only` | `./run.sh --backend-only` | 7866 | This computer only |

To make backend-only accessible on a trusted LAN, use `.\run.bat --backend-only --lan` on Windows or `./run.sh --backend-only --lan` on Linux. See the dedicated [Backend-only guide](BACKEND_ONLY.md) for authentication and secure client configuration.

> [!WARNING]
> **Neither LAN mode is safe to expose directly to the internet.** Ordinary browser LAN mode is unauthenticated; backend-only bearer authentication does **not encrypt** credentials on plain HTTP. Do not use router port forwarding. Prefer a secure VPN or TLS tunnel for untrusted networks.

The machine running Morphorum is the server. Connecting devices use its **actual private IP address**, for example `http://192.168.1.50:7865`, not `0.0.0.0`. A local firewall may need a narrowly scoped rule for your private network.

## Updates and repairs

**Stop the server before updating.** Back up projects and outputs if they matter to you.

| Task | Windows (from install folder) | Linux (from install folder) |
| --- | --- | --- |
| Update current branch | `.\update.bat` | `./update.sh` |
| Switch/update to published main | `.\update.bat main` | `./update.sh main` |
| Repair and run diagnostics | `.\repair.bat` | `./repair.sh` |

Updates use guarded Git operations and normally preserve the data directories. They may refuse to continue if you have uncommitted changes in Git-tracked files. **Do not run `git reset --hard` just to silence a warning.**

For Windows, the initial port preference lives at `data\server-port.txt` and is used by subsequent normal launches. Linux uses the launcher defaults or environment overrides.

## What to back up

The most important folders inside the installation directory are:

| Folder | Contents |
| --- | --- |
| `projects/` | Animation projects and their managed media |
| `outputs/` | Generated images, frames, videos and exports |
| `data/` | Application settings and state (including sensitive backend credentials) |
| `logs/` | Installer and diagnostic logs |
| `cache/` | Download caches |
| `backups/` | Selected updater backup and rollback information |

**Protect `data/`** because it can contain authentication material. Do not post the entire folder or its contents in bug reports. The updater's own backups are **not** full backups of all projects, renders or checkpoints. Copy important user data somewhere separate before substantial changes.

## Need help?

Read [Troubleshooting](TROUBLESHOOTING.md) for installer failures, GPU/CUDA problems, model scans, ports, missing FFmpeg and update errors. [Open an issue](https://github.com/merberg-ai/Morphorum/issues) with your OS, GPU, version and first relevant error. Redact tokens and private paths.
