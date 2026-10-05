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

### Default location

```powershell
irm https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.ps1 | iex
```

Default: `$HOME\Morphorum`

### Custom location

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.ps1'))) -InstallDir 'D:\Morphorum'
```

You may also set `MORPHORUM_HOME` before running the standard bootstrap command.

The Windows bootstrap installs Git with `winget` when necessary, clones Morphorum, and hands off to `install.bat`.

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
11. writes installation metadata to `data/install.json`.

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

The updater:

1. refuses to overwrite modified tracked source files;
2. records the current Git commit;
3. backs up `data/config.yaml` and top-level Morphorum databases;
4. pulls the update with fast-forward-only Git semantics;
5. reinstalls/updates runtime dependencies;
6. runs the API self-test;
7. automatically attempts to roll the source tree and runtime back to the previous commit if the new install/self-test fails.

Update backups are stored under `backups/update-<timestamp>/`.

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

## Current development status

The installer currently brings up the real Morphorum runtime foundation and API health endpoint. It does **not** yet install the future diffusion/model stack because those adapters are not implemented yet.

After launch, visiting `http://127.0.0.1:7865/` should display the Morphorum runtime placeholder page. `http://127.0.0.1:7865/api/health` should return a small JSON health response.

## Dependency locking

During the initial installer bring-up, Python dependencies are constrained by `pyproject.toml` and installed through `uv`. A committed `uv.lock` will be added after the first successful Windows/Linux install test validates the dependency graph. From that point onward production-style installs should use the committed lockfile for reproducibility.
