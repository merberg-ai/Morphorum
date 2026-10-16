# Testing and validation

This page is for contributors and maintainers. **You do not need to run automated tests to install or use Morphorum.** For that, follow [Getting started](GETTING_STARTED.md).

## GitHub Actions

The repository runs three complementary checks:

| Workflow | Purpose |
| --- | --- |
| Backend tests | Python `pytest` API, models, projects and render-related behavior, plus an internal self-test |
| Syntax checks | Python compilation, browser JavaScript syntax and frontend regression tests |
| Installer checks | PowerShell and Bash syntax and a standalone Windows bootstrap smoke check |

See the current results under [Actions](https://github.com/merberg-ai/Morphorum/actions). Passing CI does not replace physical GPU, browser, and remote-network testing for affected features.

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

## Reporting failures

Use [GitHub Issues](https://github.com/merberg-ai/Morphorum/issues) for reproducible bugs. Include OS, GPU, checkpoint family, version, relevant commands and the first error. Never publish tokens, credential files or private data.

[Return to documentation index](README.md).
