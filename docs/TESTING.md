# Testing and validation

This page is for contributors and maintainers. **You do not need to run automated tests to install or use Morphorum.** For that, follow [Getting started](GETTING_STARTED.md).

## GitHub Actions

The repository runs four complementary checks:

| Workflow | Purpose |
| --- | --- |
| Backend tests | Python `pytest` API, models, projects and render-related behavior, plus an internal self-test |
| Syntax checks | Python compilation, browser JavaScript syntax and frontend regression tests |
| Installer checks | PowerShell and Bash syntax and a standalone Windows bootstrap smoke check |
| FFmpeg integration smoke (CPU-only) | Windows/Linux system-FFmpeg MP4/WebM/audio/hybrid media fixtures plus resolver/managed-download unit regressions; actual managed downloads require separate host testing |

See the current results under [Actions](https://github.com/merberg-ai/Morphorum/actions). Passing CI does not replace physical GPU, browser, and remote-network testing for affected features.

**SDXL G5 release history:** On 2026-10-17 the owner reported G5.5 Windows acceptance passed and explicitly approved merging the G1–G5 SDXL improvements. The release candidate's [draft PR #43](https://github.com/merberg-ai/Morphorum/pull/43) passed Backend, Syntax, and Installer checks; the final pre-promotion CI backend run had **848 passed, 1 skipped**. See the [acceptance matrix](G5_RELEASE_ACCEPTANCE.md) for repeatable test cases and known scope limits; individual W1–W11 outcomes were not supplied as separate test records. Passing CI does not prove GPU speed or pixel-level image quality. The [SDXL user guide](SDXL_GENERATION.md) explains expected diagnostics. Installer checks run on pull requests, even if a source-only `dev-webui` push does not trigger them.

## Run tests locally

A normal installed Morphorum has its own Python virtual environment. Install `pytest` in that environment if it is not already available.

**Windows PowerShell (from installation folder):**

~~~powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m morphorum self-test
~~~

**Linux:**

~~~bash
./.venv/bin/python -m pytest
./.venv/bin/python -m morphorum self-test
~~~

The frontend tests run under **Node.js 22** for development/CI, not normal app installation. Follow the scripts referenced by `.github/workflows/syntax.yml` for the current suite.

## Manual release checks

Before promoting an installation, use a disposable directory and test at least the relevant workflows:

1. Install from a fresh checkout and run the standard browser launcher.
2. Confirm a model can be discovered and a small image generated.
3. Open the New Project Wizard, save a small project, preview its camera motion and run a short animation.
4. Confirm results, telemetry, and FFmpeg video export where available.
5. For backend changes, confirm both normal and backend-only launches, authenticated LAN access and client connectivity.
6. Confirm update/repair commands preserve user projects and settings.
7. For **fresh first-run setup**, verify automatic launch only after the installer-provenance handshake. Existing installations should not be re-onboarded; backend-only must have no wizard. Check folder validation and persistence, optional managed Z-Image (confirm/cancel, partial/resume), two 512 × 512 project presets, and completion/Skip/re-entry.
8. Exercise **Create Example & Open Editor** and **Finish Without Example** separately. Verify no downloads, creations or GPU renders on page loads, no duplicate project after retry, no unsaved-editor data loss, mobile sizing and keyboard navigation.
9. Recheck the new GitHub CI results after the merge.

Do not use someone else's valuable model, project or output folder for destructive testing. Record the exact commit, environment, and whether checks were automated or physically tested.

## Verify FFmpeg without a GPU

Follow [FFmpeg Manager](FFMPEG_MANAGER.md#verify-a-managed-installation) for the host-independent media acceptance script. From your Morphorum directory:

~~~powershell
.\.venv\Scripts\python.exe scripts\ffmpeg_acceptance.py --mode managed
~~~

This uses disposable synthetic media to verify both encoders, FFprobe, PNG extraction and common audio conversions. It does not prove every generation/model combination is correct.

**Release acceptance history (2026-10-16):** The owner reported that the corrected managed FFmpeg installation succeeded on Windows and all six media acceptance groups passed. Linux managed installation, forced interruption/recovery scenarios, P4.3 notification resilience, and repository-wide CI status must be tracked independently rather than silently marked passed.

## Reporting failures

Use [GitHub Issues](https://github.com/merberg-ai/Morphorum/issues) for reproducible bugs. Include OS, GPU, checkpoint family, version, relevant commands and the first error. Never publish tokens, credential files or private data.

[Return to documentation index](README.md).

## Experimental Z-Image single-file checkpoint acceptance (dev-webui)

Owner-supplied Windows physical test results through **Z2.20c3c4** show passing converted BF16 scratch model binding, isolated CPU/CUDA neural forwards, native Diffusers prompt processing, two numerical scheduler steps, and a managed VAE output tensor [1,3,32,32]. This does **not** prove image quality, a saved PNG, full-resolution GPU inference, normal model-loader compatibility, or CI health. Converted external checkpoints remain disabled for normal selection. The next step is the [c3c5 diagnostic PNG implementation plan](ZIMAGE_C3C5_IMPLEMENTATION_PLAN.md), which is **documented but not implemented**; follow its opt-in, exclusive-file creation and negative/positive test requirements before hardware testing. Refer to [the full roadmap](ZIMAGE_SINGLE_FILE_ROADMAP.md). Do not treat owner-provided console JSON as a GitHub Actions run.
