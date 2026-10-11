# Testing Morphorum before release

This checklist is for maintainers and testers. **New users do not need to run the automated tests**; follow [Getting started](GETTING_STARTED.md) instead.

> [!NOTE]
> A successful CI run checks syntax, APIs, and scripted behavior. A real NVIDIA GPU and browser test is still important for validating large model downloads, performance, camera previews, and video export.

## Automated checks

The repository runs three GitHub Actions workflow suites on pull requests and selected branch pushes:

| Workflow | Checks |
| --- | --- |
| **Syntax checks** | Python compilation, browser JavaScript syntax, frontend behavior/regression suites |
| **Backend tests** | Python/pytest model, project, rendering, settings and API tests |
| **Installer checks** | Windows PowerShell parser, Linux shell syntax, actual Windows standalone `bootstrap.bat -Help` download/launch smoke test |

Review them at [GitHub Actions](https://github.com/merberg-ai/Morphorum/actions). Green runs on `dev-ui` are required before proposing promotion to `main`, and the `main` merge should be checked again afterward.

Developers who already have a virtual environment with **pytest** installed can run:

```bash
python -m pytest tests
```

The frontend behavior suites run with Node.js **22**, which is used for development/CI only (not for normal user installation).

## Windows clean-install acceptance

On a Windows 10/11 system with sufficient disk space and ideally an NVIDIA CUDA GPU:

1. Use a **new, disposable directory** such as `D:\Morphorum-test`, not the primary installation.
2. Download a fresh `bootstrap.bat` from the [published main branch](https://raw.githubusercontent.com/merberg-ai/Morphorum/main/bootstrap.bat).
3. Open PowerShell and run the bootstrap with that disposable directory:

   ```powershell
   .\bootstrap.bat -InstallDir "D:\Morphorum-test" -Port 7865
   ```

4. Confirm installer prerequisite checks, managed Python 3.12 and PyTorch, optional Git/FFmpeg setup, and self-test.
5. Confirm these exist after installation: `.venv`, `.runtime`, `data\config.yaml`, `data\server-port.txt`, `logs\install.log`, `projects`.
6. Run `.\run.bat` from the installed folder and open **http://127.0.0.1:7865**.
7. Confirm `http://127.0.0.1:7865/api/health` returns a healthy response.
8. In **Motion Lab → Project Manager**, verify the **Default** starter project appears if the project library was previously empty.
9. Run `.\run.bat -Port 8080` and confirm the URL changes for that session without modifying the port saved by the installer.
10. Run `.\repair.bat` and verify the starter project and any edits remain intact.
11. Run `.\update.bat` and verify the updater protects data and reports a successful self-test.

**Safety:** Do not test deletion/Trash with valuable user projects. Use disposable projects.

## Windows generation and Motion Lab acceptance

1. Open **Models** and check an already installed Z-Image-Turbo package, or download it if storage allows (approximately **33 GB**).
2. Render **one text-to-image** sample and **one image-to-image** frame. Both should reuse the same Z-Image model folder.
3. Open the starter project, choose the model, and confirm prompts, resolution, frame count, and mode.
4. Use Camera Composer, editable Motion Curves, Camera Preview, and the floating quick-action toolbar.
5. Test Live Recording/Stop; verify conflicting controls correctly disable during active operations.
6. Test Audio Motion and soundtrack export with a disposable project/audio source.
7. Render a short animation and confirm progress, preview/monitor, output files, and FFmpeg export.
8. Test each theme and the interface/console font selectors. Save preferences, refresh, and verify persistence.
9. Verify desktop and mobile browser layouts separately.

GPU performance and VRAM usage should be **measured rather than assumed**. Include model name, batch, resolution, steps, driver, and GPU in performance reports.

## Linux acceptance

1. Install to a **new directory** using `scripts/bootstrap.sh`.
2. Verify Git prerequisites, managed Python environment, and `./run.sh`.
3. Confirm the default local URL and a one-run `MORPHORUM_PORT_OVERRIDE=8080 ./run.sh` override.
4. Run `./repair.sh` and `./update.sh`.
5. Check model indexing, one small render, and FFmpeg export with hardware actually available on that system.
6. Check `./run-lan.sh` **only on a trusted private LAN**.

## Release integration checklist

Before promoting `dev-ui` to `main`:

- [ ] Source branch and target are up to date; changes are reviewable and conflict-free.
- [ ] Recovery checkpoint recorded for existing `main`.
- [ ] README, installation, getting-started, troubleshooting, and current-status documentation match the actual scripts/code.
- [ ] All required CI checks pass.
- [ ] Physical Windows/GPU and user-interface acceptance has been recorded for the promoted feature set.
- [ ] PR targets `main` with its expected commit SHA.
- [ ] Post-merge `main` CI is checked.
- [ ] `main` installation URLs and beginner commands work after promotion.
- [ ] Important `checkpoint/*` branches are preserved.

For a bug report, copy the **first relevant error** rather than dumping an entire multi-megabyte log. Include version/branch, GPU, OS, exact reproduction steps, and whether the same problem occurs on `dev-ui` and `main`.
