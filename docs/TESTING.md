# Morphorum installer test checklist

This checklist is for the first real Windows/Linux validation pass. The installer already contains a built-in API self-test; these steps validate the surrounding bootstrap, filesystem, maintenance, and launch behavior.

## Windows clean install

Recommended first target: Windows 10/11 with an NVIDIA GPU.

1. Choose an empty location such as `D:\Morphorum-test`.
2. Run:

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.ps1'))) -InstallDir 'D:\Morphorum-test'
```

3. Confirm the installer reports:
   - Git available;
   - Morphorum-owned `uv` installed;
   - managed Python 3.12 installed;
   - `.venv` created;
   - Morphorum dependencies installed;
   - NVIDIA GPU details when applicable;
   - FFmpeg present or installed;
   - API self-test passed.
4. Confirm these exist:
   - `.runtime/uv/uv.exe`
   - `.runtime/python/`
   - `.venv/Scripts/python.exe`
   - `data/config.yaml`
   - `data/install.json`
   - `logs/install.log`
5. Run `run.bat` and open `http://127.0.0.1:7865/`.
6. Open `http://127.0.0.1:7865/api/health` and confirm JSON reports `status: ok`.
7. Stop the server with Ctrl+C.
8. Run `repair.bat` and confirm the self-test and doctor complete.
9. Run the bootstrap command again against the same directory and confirm it routes through the guarded updater rather than failing or reinstalling destructively.

## Windows path tests

Repeat or spot-check with:

- a path containing spaces, such as `D:\AI Apps\Morphorum`;
- the default `$HOME\Morphorum` path;
- a directory that already contains unrelated files, which should be rejected;
- a drive with insufficient free space, if practical to simulate.

## Linux clean install

Recommended first target: Ubuntu/Debian, followed by another distro when convenient.

1. Choose an empty location such as `/opt/morphorum-test` (with suitable permissions) or `$HOME/Morphorum-test`.
2. Run:

```bash
curl -fsSL https://raw.githubusercontent.com/merberg-ai/Morphorum/main/scripts/bootstrap.sh | bash -s -- "$HOME/Morphorum-test"
```

3. Confirm the same runtime/self-test milestones as Windows.
4. Confirm executable wrappers work:

```bash
./run.sh
./repair.sh
./update.sh
```

5. Confirm `./run-lan.sh` binds to `0.0.0.0` and is reachable from another machine on the LAN when the host firewall permits it.

## Update rollback test

After a known-good install:

1. Note the current commit with `git rev-parse HEAD`.
2. Confirm `update.bat` / `./update.sh` creates a timestamped directory under `backups/`.
3. Confirm `data/config.yaml` survives the update unchanged.
4. Later, once a deliberately broken test branch/release is available, verify that a failed installer/self-test causes the updater to reset to the previous commit and reinstall the previous runtime.

Do not manufacture a broken `main` branch merely for entertainment. There are already enough ways to generate excitement in software development.

## Developer tests

Once the development dependency group has been installed, run:

```bash
uv run --group dev pytest
uv run --group dev ruff check backend tests
```

A committed `uv.lock` should be generated and added after the first successful platform install confirms the selected dependency graph.

## Information to capture on failure

Please preserve:

- the console error;
- `logs/install.log`, `logs/update.log`, or `logs/repair.log` as applicable;
- `data/install.json` if it was created;
- output of `.venv/bin/python -m morphorum doctor` on Linux or `.venv\Scripts\python.exe -m morphorum doctor` on Windows;
- operating system/version;
- GPU model/driver;
- install path used.
