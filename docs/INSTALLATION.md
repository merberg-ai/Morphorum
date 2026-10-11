# Morphorum installation and maintenance

Morphorum is designed so normal users do not need to manage Python environments, pip packages, Node.js, or frontend build tooling.

## What the installer owns

Inside the selected Morphorum install directory, the installer manages:

- `.runtime/uv/` — Morphorum-owned `uv` runtime manager
- `.runtime/python/` — managed Python 3.12 runtime
- `.runtime/uv-cache/` — installer/runtime package cache
- `.venv/` — Morphorum Python environment
- application source files tracked by Git

These may be repaired or replaced by Morphorum maintenance scripts.

## User data that updates must preserve

The following are user/runtime state and are intentionally ignored by Git:

- `data/` — user configuration, indexes, databases, install metadata
- `projects/` — Morphorum projects
- `outputs/` — generated images/video
- `cache/` — application caches
- `logs/` — install/update/runtime logs
- `backups/` — update backups and recovery information

External checkpoint and LoRA directories are never copied into Morphorum unless the user explicitly chooses to do so in a future workflow.

## Windows

### Interactive Windows install

Download [`bootstrap.bat`](https://raw.githubusercontent.com/merberg-ai/Morphorum/main/bootstrap.bat) and run it. It prints the Morphorum banner, checks prerequisites, and prompts for the installation folder. **The default is `C:\\Morphorum`**. Press Enter to accept it, or enter a custom folder such as `D:\\Morphorum`.

PowerShell download/launch example:

```powershell
curl.exe -fL -o bootstrap.bat https://raw.githubusercontent.com/merberg-ai/Morphorum/main/bootstrap.bat
.\\bootstrap.bat
```

Noninteractive install with an explicit location:

```powershell
.\\bootstrap.bat -InstallDir 'D:\\Morphorum'
```

The new installer asks which **server port** to use (default `7865`). This is stored in `data/server-port.txt` and preserved by updates or repairs. To preselect a port, add `-Port 8080` to `bootstrap.bat` or `install.bat`. Normal launches load that preference, and you can override it temporarily:

```powershell
.\\run.bat -Port 8080
.\\run-lan.bat -Port 8080
```

The bootstrap also supports `-Branch` for testing an alternate Git branch. If you already have an installation at the requested path, it uses the guarded updater instead of overwriting your data.

The existing PowerShell bootstrap remains supported:

```powershell
irm https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.ps1 | iex
```

Selection precedence is an explicit `-InstallDir`, then `MORPHORUM_HOME`, then the interactive prompt defaulting to `C:\\Morphorum`. In an existing checkout, `install.bat` prepares that checkout in place. Use `bootstrap.bat` to choose a fresh location, not `install.bat` from a different directory.

The Windows bootstrap installs Git with `winget` when necessary, clones Morphorum, and hands off to `install.bat`. `run.bat`, `run-lan.bat`, and `update.bat` use the same colorized console UI.

The installer then:

1. creates runtime/user directories;
2. checks free disk space;
3. installs a Morphorum-owned copy of `uv`;
4. installs/manages Python 3.12 through `uv`;
5. creates `.venv`;
6. installs Morphorum and its Python dependencies;
7. creates `data/config.yaml` from defaults if no user config exists;
8. detects the NVIDIA driver/GPU when available;
9. installs FFmpeg through `winget` when it is missing and `winget` is available;
10. runs the Morphorum API self-test;
11. writes installation metadata to `data/install.json`;
12. seeds `projects/default-a070c78c/project.json` from `config/example-project.json` **only on a fresh install with no other projects**. Repair and update never create or overwrite project data.

### Launch

Local-only:

```text
run.bat
```

LAN-accessible:

```text
run-lan.bat
```

Default port: `7865`.

LAN mode is intended only for trusted networks. The Windows run script displays detected IPv4 URLs and explains that the local web server is not password-protected.

## Linux

### Default location

```bash
curl -fsSL https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.sh | bash
```

Default: `$HOME/Morphorum`

### Custom location

```bash
curl -fsSL https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.sh | bash -s -- /home/foo/bar
```

You may also pass the location through `MORPHORUM_HOME`.

The Linux bootstrap attempts to install Git when it is missing on Debian/Ubuntu, Fedora, Arch, and openSUSE-family systems. It may request `sudo` permission for that system package operation.

The Morphorum installer itself does not silently install system-wide FFmpeg packages. If FFmpeg is missing, it prints the appropriate command for common distributions. The rest of the Morphorum Python runtime remains self-contained inside the install directory.

### Launch

Local-only:

```bash
./run.sh
```

LAN-accessible:

```bash
./run-lan.sh
```

## Updating

Windows:

```text
update.bat
```

Linux:

```bash
./update.sh
```

With no argument, the updater keeps the currently checked-out branch and updates it.

To switch to and update a specific remote branch:

```text
update.bat feature/timeline-alpha-a3
```

or on Linux:

```bash
./update.sh feature/timeline-alpha-a3
```

The same command can return a test installation to the stable branch:

```text
update.bat main
```

```bash
./update.sh main
```

When a branch is requested, the updater fetches remote branch information, verifies
`origin/<branch>` exists, switches or creates the matching local tracking branch, and
then performs the normal guarded update.

The updater:

1. refuses to overwrite modified tracked source files;
2. records the current Git branch and commit;
3. backs up `data/config.yaml` and top-level Morphorum databases;
4. optionally switches to the requested remote branch;
5. pulls that branch with fast-forward-only Git semantics;
6. reinstalls/updates runtime dependencies;
7. runs the API self-test;
8. automatically attempts to restore the previous branch, commit, and runtime dependencies if the new install/self-test fails.

Update backups are stored under `backups/update-<timestamp>/` and include
`previous_branch.txt` plus `previous_commit.txt`.

### First switch from an older installation

Installations created before branch-aware updating do not understand the branch argument
yet. For the first switch only, use Git directly, then run the updater from the new
branch.

Windows PowerShell:

```powershell
cd D:\Morphorum-test
git fetch origin
git switch --track -c feature/timeline-alpha-a3 origin/feature/timeline-alpha-a3
.\update.bat
```

If the local branch already exists, use:

```powershell
git switch feature/timeline-alpha-a3
.\update.bat
```

After that first switch, branch-aware updating is available normally.

## Repair / diagnostics

Windows:

```text
repair.bat
```

Linux:

```bash
./repair.sh
```

Repair re-runs the installer in repair mode, then runs `morphorum doctor`.

The doctor currently checks items including:

- Python 3.12 runtime
- Git
- FFmpeg
- Morphorum runtime directories
- free disk space
- FastAPI/Uvicorn availability
- NVIDIA GPU/driver information when `nvidia-smi` is present
- PyTorch/CUDA status once PyTorch becomes part of the installed model backend

Installer/update/repair logs are stored in `logs/`.

## Runtime check

The installer provisions a managed Python and PyTorch runtime, checks the configured CUDA backend where applicable, and runs the Morphorum self-test. Opening `http://127.0.0.1:7865/` shows the actual app, including Image Generation and Motion Lab. `http://127.0.0.1:7865/api/health` exposes its health endpoint.

### First-run Default project

The bundled file `config/example-project.json` is the provided 3D example: 120 frames at 24 FPS, 1024×1024, with two cat prompt keyframes (frames 0 and 30), motion/generation schedules and the Deforum-style track data. The example has **no selected checkpoint**, so choose a compatible image model before rendering.

The install seeds this template only when the projects library is empty. The seed command is idempotent (`.venv\\Scripts\\python.exe -m morphorum seed-example`): running it again leaves existing projects alone. Existing user data under `projects/`, including modified starter projects, is preserved by install/repair/update.

## Dependency locking

During the initial installer bring-up, Python dependencies are constrained by `pyproject.toml` and installed through `uv`. A committed `uv.lock` will be added after the first successful Windows/Linux install test validates the dependency graph. From that point onward production-style installs should use the committed lockfile for reproducibility.
