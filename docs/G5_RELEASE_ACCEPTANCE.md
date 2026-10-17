# G5 SDXL integration: acceptance record and regression checklist

**Release decision (2026-10-17):** The owner reported **G5.5 PASS** on Windows and explicitly approved merging the G1–G5 SDXL changes from `dev-webui` to `main`. The release candidate's Backend, Syntax, and Installer GitHub Actions checks passed. This document preserves a reusable test matrix; individual W1–W11 results were **not provided separately**, so no row is retroactively marked as independently verified. Physical mobile/Linux coverage remains separate from this SDXL Windows acceptance.

## Scope and ground rules

This is the final gate for the SDXL G1–G5 development work: sampler and schedule selection, dual-CLIP chunked prompts, image/animation conditioning, LoRA compatibility/verification, cache efficiency, and accurate diagnostics.

- **Original test branch:** `dev-webui`. **Release branch:** `main`. Use the released `main` branch for normal installations; use `dev-webui` only when intentionally testing ongoing development.
- Test on the existing Windows NVIDIA GPU, with the actual SDXL checkpoint and LoRA files the owner uses. Record the GPU, driver, VRAM, model/LoRA names, and exact commit.
- Keep prompts, seed, resolution, steps, and LoRA weights identical for a meaningful before/after performance comparison.
- Never run destructive cleanup on valuable checkpoints, user projects, outputs, or settings. Back up anything irreplaceable before an update.
- For future regression tests, record **PASS**, **FAIL**, **BLOCKED**, or **NOT TESTED** per row. The owner accepted the overall G5.5 milestone; the original per-row outcomes were not submitted.
- Separate release-blocking regressions from optional or previously deferred hardware/mobile coverage. Report any exceptions explicitly.

## Update a Windows development test installation (historical commands)

Stop active Morphorum generation jobs and close the application server. Open PowerShell in the **existing Morphorum installation folder**:

```powershell
git status --short
.\update.bat dev-webui
git branch --show-current
git rev-parse --short HEAD
.\run.bat
```

Confirm that the active branch is `dev-webui`, and record the resulting SHA. **Do not run `git reset --hard` or delete user data.** The updater rejects modified tracked application files rather than discarding them. If the update fails, stop and investigate; do not force it.

For a genuinely clean-install rehearsal, use a **new empty disposable folder**, the current branch, and `bootstrap.bat -InstallDir "D:\Morphorum-G5-Test" -Branch dev-webui` from a trusted copy of the installer. This is optional unless testing fresh-install behavior is part of the release gate. The public `main` bootstrap link by itself installs `main`, not this development candidate.

## Acceptance matrix

| ID | Windows physical check | Expected observable result | Original row-level record |
| --- | --- | --- | --- |
| W1 | Start Morphorum on `dev-webui`, verify model folders and Settings; open Image Generation | Correct existing project/settings paths; usable responsive controls and model selection | Not individually recorded |
| W2 | SDXL **short** positive/negative prompts, fixed seed, 1 image, no LoRA | Image finishes; **STANDARD** conditioning; no false long-prompt warning | Not individually recorded |
| W3 | SDXL **long** positive prompt and long negative prompt, same settings | Image finishes; **CHUNKED** conditioning with actual CLIP-L/G chunk counts and aligned negative embeddings, when CFG is active | Not individually recorded |
| W4 | SDXL 1–2 LoRAs (prefer previously validated real files), with a long prompt | Image finishes; each adapter is clearly reported as matched, active-not-compared, or UNet-only; no silent checkpoint-value mismatch | Not individually recorded |
| W5 | SDXL sample sampler/schedule combinations: Euler/Normal, DPM++ 2M/Karras, Euler/Trailing; test incompatible DDIM/Karras selection | Supported combinations render; unsupported combination is rejected or prevented, not silently changed | Not individually recorded |
| W6 | SDXL 24–48-frame animation, unchanged long prompt and constant LoRA strengths | Render completes; conditioning remains consistent; later diffusion anchors show cache **hits**; no sustained unexpected VRAM growth | Not individually recorded |
| W7 | SDXL short-to-long prompt keyframe transition with different negative prompts and LoRA strength keyframes | Blend completes with compatible embeddings; prompt/negative telemetry follows frame resolution; cache changes when LoRA settings change | Not individually recorded |
| W8 | Export the saved animation to MP4 with FFmpeg, including audio where available | Export completes; resulting video opens and audio matches the saved soundtrack, if attached | Not individually recorded |
| W9 | Quick FLUX and Z-Image single-image smoke tests **if checkpoints are installed** | Existing non-SDXL workflows still render; no SDXL-specific controls or conditioning injected | Not individually recorded |
| W10 | Inspect Console and the terminal after the LoRA renders | PEFT startup warnings are explained by the subsequent verification result; any actual load failure is visible and actionable | Not individually recorded |
| W11 | Reopen project, reload render history, examine exported performance report | No lost project settings; saved results and render telemetry available after restart | Not individually recorded |

A short test is sufficient for an initial check; no need to run a multi-minute animation to exercise every case. For performance comparisons, the render must use identical relevant generation settings.

### Optional broader release smoke

This branch's SDXL work does not change installers or backend-only authentication, but final public release confidence also benefits from: disposable clean installation, first-run wizard, user model folder verification, update/repair, and backend-only launch with authenticated access. Desktop-sized WebUI acceptance is required for this round; physical mobile testing has been deferred and **must be reported as deferred**, not passed.

## Automated gate

Before requesting a merge, verify GitHub Actions against the *final candidate commit* (including documentation changes). At minimum:

- **Backend tests:** green, including the SDXL G5 integration matrix.
- **Syntax checks:** green, including frontend checks and documentation validation.
- **Installer checks:** green for the draft PR. This workflow runs on pull requests; it is **not** triggered merely by every `dev-webui` push.
- **FFmpeg integration smoke (CPU-only):** record the most recent applicable run (if available) separately from physical MP4 export. Do not claim that an older green run tested the final candidate.

The CPU-based test suite cannot prove GPU speed or image quality. Capture the physical render's settings, exact SHA, errors, and optionally its `performance.jsonl` file for any surprising memory or timing behavior.

## Future release approval and merge gate

For future candidate PRs, leave the PR **draft** while acceptance is ongoing. Before making a future candidate merge-ready, require all of the following:

1. A documented result for every required W1–W11 case; applicable failures fixed and retested, unavailable models clearly marked **BLOCKED**.
2. Confirmed final CI status for the candidate SHA and public-facing docs, including installation/update instructions, SDXL features, and troubleshooting.
3. No unplanned changes to the supported FLUX or Z-Image behaviors.
4. Any deferred mobile/Linux testing, known alpha limits, and remaining risks stated openly.
5. **Explicit owner approval to merge into `main`.** A green CI run or the creation of a draft PR is not that approval.

For the G5 release, the explicit owner approval was received on 2026-10-17. The associated review was [PR #43](https://github.com/merberg-ai/Morphorum/pull/43). After every future merge, check `main` Actions, verify the deployed README and installation docs, and recheck the upgrade path on a disposable installation. Do not change production installation branches automatically.

See [SDXL generation guide](SDXL_GENERATION.md), [Testing](TESTING.md), [Installation](INSTALLATION.md), and [Troubleshooting](TROUBLESHOOTING.md).
