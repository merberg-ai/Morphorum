# Installing and maintaining Morphorum

**New user?** Start with the [README quick start](../README.md#get-started-in-three-steps). This guide explains the installer in more detail, including custom installation folders, server ports, models, updates, and how to recover from problems.

> [!IMPORTANT]
> Morphorum is **early alpha software**. The installer can configure the application and its Python environment, but it **does not download AI models automatically**. Back up important projects before updating or changing Git branches.

## Before installing

| Item | What to know |
| --- | --- |
| **Operating system** | Windows 10/11 or 64-bit Linux. Scripts are provided for both. |
| **GPU** | An NVIDIA GPU with CUDA is recommended for practical local image/video generation. Availability and speed depend on the model and hardware. |
| **Free space** | The installer checks for **8 GiB** to bootstrap the runtime. Models need substantially more: managed **Z-Image-Turbo is about 33 GB** by itself. Plan additional space for caches and outputs. |
| **Internet** | Required to fetch source, Python packages, and any models you choose to download. |
| **Git and Python** | Install scripts arrange Git where supported, a managed Python **3.12** runtime, and Morphorum's private environment. You do not need to create a Python virtual environment manually. |
| **FFmpeg** | Required for video encoding/export and some video-source operations. Windows may install it with `winget`; Linux users may need a distribution package. |

The frontend is included in the repository. **Node.js is not required** just to use the app.

## Windows installation

### Option A: Download and run the installer

1. Download **[bootstrap.bat](https://raw.githubusercontent.com/merberg-ai/Morphorum/main/bootstrap.bat)**.
2. Double-click `bootstrap.bat` or run it in a Command Prompt/PowerShell terminal.
3. When asked for the **installation directory**, press Enter for `C:\Morphorum`, or type another location such as `D:\Morphorum`.
4. When asked for the **server port**, press Enter for `7865`, or enter a free port from 1 through 65535.
5. Let the colored setup window finish downloading dependencies, checking CUDA where relevant, and running its self-test.
6. When complete, the installer displays the location of `run.bat`.

> [!TIP]
> The first installation may take a while. Morphorum downloads the Python runtime and GPU-aware PyTorch dependencies. The **33 GB Z-Image model is an optional separate download** from the Models page after startup.

### Option B: PowerShell installation

Open PowerShell where you want to keep the downloaded installer and run:

```powershell
curl.exe -fL -o bootstrap.bat https://raw.githubusercontent.com/merberg-ai/Morphorum/main/bootstrap.bat
.\bootstrap.bat
```

To choose a folder and port without answering the prompts:

```powershell
.\bootstrap.bat -InstallDir "D:\Morphorum" -Port 8080
```

The bootstrap also accepts `-Branch dev-ui` for development installations. For the published main build, **omit `-Branch`**. Installing into an existing managed checkout invokes the guarded updater rather than discarding your files.

### Launch on Windows

Open PowerShell, change to the installation folder, and run:

```powershell
cd C:\Morphorum
.\run.bat
```

Open **http://127.0.0.1:7865** in a browser, or replace `7865` with the port you selected. Keep the PowerShell window open. Press **Ctrl+C** to stop the server.

To run on a different port for a single session:

```powershell
.\run.bat -Port 8080
```

This override **does not alter** the default port you chose during setup. Windows stores that preference at `data\server-port.txt`.

## Linux installation

The installer supports common 64-bit Linux distributions. It attempts to provision Git on several common package-manager families; system packages may require `sudo`.

Default location, `~/Morphorum`:

```bash
curl -fsSL https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.sh | bash
```

Custom install location:

```bash
curl -fsSL https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.sh | bash -s -- "$HOME/Apps/Morphorum"
```

Alternatively, set `MORPHORUM_HOME` in the environment. The precedence is **explicit path → environment variable → default location**.

The installer provisions the local Python runtime and dependencies. If FFmpeg is missing, install it through your Linux distribution's package manager.

### Launch on Linux

```bash
cd ~/Morphorum
./run.sh
```

Open **http://127.0.0.1:7865** in your browser. Linux uses `7865` by default and supports a launch-time environment override:

```bash
MORPHORUM_PORT_OVERRIDE=8080 ./run.sh
```

Linux does **not** currently use the Windows port-prompt/file mechanism. Its run script uses `MORPHORUM_PORT_OVERRIDE` when supplied.

## Local access versus LAN access

**Local mode** (default) binds the server to `127.0.0.1` so only the host computer can open it:

| Platform | Command |
| --- | --- |
| Windows | `.\run.bat` |
| Linux | `./run.sh` |

**LAN mode** lets other devices on your private network connect:

| Platform | Command |
| --- | --- |
| Windows | `.\run-lan.bat` |
| Linux | `./run-lan.sh` |

Windows also supports `.\run-lan.bat -Port 8080`. The Windows launcher lists detected local IPv4 URLs. On Linux, read the host computer's LAN IPv4 address and use `http://HOST_IP:7865` or your configured override.

> [!WARNING]
> **Do not expose Morphorum directly to the internet.** The LAN server is **not password-protected**. Restrict it to a network you trust, and do not forward its listening port through your router. If a device cannot connect, check the operating system's firewall and that both devices are on the same local network.

## First-run example project and AI models

A clean installation with an empty project library gets a **Default** animation project containing 3D settings, 120 frames at 24 FPS, 1024 × 1024 resolution, and two prompt keyframes. Its source is `config/example-project.json`.

The installer **does not replace existing projects** during repair or update. Open **Motion Lab → Project Manager → Default**, choose **Open in Editor**, and select a model before rendering.

For a first model, open **Models** and use the managed **Z-Image-Turbo** download. It is an approximately **33 GB** model package and supports both txt2img and img2img. Existing compatible SDXL and FLUX checkpoints can be indexed from folders selected under **Settings**. See [Getting started](GETTING_STARTED.md#2-download-or-locate-an-image-model).

## Updating Morphorum

Before any update, stop the running server and save your work.

From the installation folder:

| Goal | Windows | Linux |
| --- | --- | --- |
| Update the current Git branch | `.\update.bat` | `./update.sh` |
| Switch to the published main branch | `.\update.bat main` | `./update.sh main` |
| Switch to development (advanced) | `.\update.bat dev-ui` | `./update.sh dev-ui` |

The updater checks for **uncommitted modifications to Git-tracked files**, backs up configuration and top-level database files, uses **fast-forward-only Git pulls**, refreshes dependencies, and runs verification. It can attempt to roll back its source/runtime changes if the update fails.

> [!NOTE]
> An update is **not** a substitute for a full backup. Back up your `projects/`, `outputs/`, and `data/` folders separately if the work matters to you. The updater's backup focuses on configuration and selected database files; it does not duplicate every model or rendered video.

### Updating an older installation without branch-aware scripts

Very early installations may not accept a branch name on the command line. In that case, stop Morphorum, open a terminal in the installation directory, and use Git to switch to an existing main tracking branch, then update:

```powershell
git fetch origin
git switch main
.\update.bat
```

If `main` does not exist locally, use `git switch --track origin/main`. **Do not use `git reset --hard` to fix errors:** it can discard local tracked modifications. See [Troubleshooting](TROUBLESHOOTING.md#updater-refuses-to-run-because-of-local-changes).

## Repair, diagnostics, and logs

Run these from the installed Morphorum folder:

| Task | Windows | Linux |
| --- | --- | --- |
| Repair runtime/dependencies and diagnose | `.\repair.bat` | `./repair.sh` |
| Start and inspect console messages | `.\run.bat` | `./run.sh` |

Repair refreshes the managed environment and invokes Morphorum's **doctor** checks (Python, Git, FFmpeg, runtime directories, available disk space, GPU/CUDA where present, and related dependencies).

Useful locations:

| Path (inside the installation folder) | What it contains | What updates do |
| --- | --- | --- |
| `data/` | User settings (`config.yaml`), selected port on Windows (`server-port.txt`), and runtime state | Preserve |
| `projects/` | Animation projects and project-managed source files | Preserve |
| `outputs/` | Generated images, frames, and video output | Preserve |
| `cache/` | Download/cache data | Preserve (unless manually cleaned) |
| `logs/` | Installer, repair, update, and runtime logs | Preserve |
| `backups/` | Update backup and rollback metadata | Preserve |
| `.runtime/` | Installer-owned `uv`, Python, and package cache | May repair/update |
| `.venv/` | Installer-owned Python environment | May repair/update |
| `config/example-project.json` | Bundled example template in source | Updated with source; not your saved project |

The installer writes logs under `logs/`, including `install.log`, `update.log`, and `repair.log`. You can also run `.\run.bat` or `./run.sh` from a terminal and read the errors there.

### Dependency versions and advanced development

Morphorum uses `pyproject.toml` to define Python requirements, including **Python 3.12**, and `uv` for installation. The installer manages a local PyTorch build appropriate to available hardware. There is **no separate Node frontend build step for users**.

For developer-oriented details see [Architecture](ARCHITECTURE.md), [Testing](TESTING.md), and [Contributing](../CONTRIBUTING.md).

## Troubleshooting

Problems starting the app, downloading a model, accessing from a phone, using CUDA, or exporting video? Start with the [troubleshooting guide](TROUBLESHOOTING.md). If that doesn't resolve it, include the exact error, your OS, GPU, command, and relevant log lines in a [GitHub issue](https://github.com/merberg-ai/Morphorum/issues).
