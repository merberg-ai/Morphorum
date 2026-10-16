# Combined WebUI polish acceptance: P2.5, P2.6, P3.1

> Status: **DEFERRED at the user's request**. Automated CI is not a
> substitute for a physical Windows/GPU run. Do not merge into main until
> the user reports acceptance.

Use the dedicated Windows test installation with a backed-up/sacrificial
animation project. Do not intentionally corrupt primary model folders,
delete production checkpoints or overwrite existing project results.

## Update and baseline

1. Update the test installation from the `dev-webui` branch using
   `.\update.bat dev-webui`, then restart the backend and browser.
2. Confirm the branch/build marker points to the expected development
   checkpoint. Open a working SDXL, Flux or Z-Image project.
3. Verify ordinary image generation and a **short** animation render still
   succeed. Check that prior saved audio, LoRAs, project drafts, and outputs
   remain accessible.

## P2.5: Render Monitor preflight

- [ ] **Check Render** on a valid project returns a success report without
      starting a job, saving an unsaved edit or modifying output folders.
- [ ] Use a **copy** of a project to deliberately set an unsupported sampler.
      Check should report a blocking error and offer **Fix in Editor**.
- [ ] Try incompatible width such as SDXL 1025 px or Flux 1032 px; check
      again. Restore values after verifying the warning/error.
- [ ] Test invalid frame schedule or out-of-range step/guidance value.
      The issue should identify the specific schedule field and frame when
      available; the job should not start.
- [ ] Test Starting Image mode without an uploaded source image. Use an
      isolated project; source-mode validation must not damage the library.
- [ ] Restore valid settings, press **Render Animation**, and ensure an
      automatic check occurs before queueing.
- [ ] Trigger non-blocking warnings (see P2.6) and verify **Render Anyway**
      requires explicit confirmation. Canceling the prompt must not queue a job.
- [ ] Make an edit during a slow preflight/confirmation and verify stale
      settings cannot be rendered accidentally.
- [ ] A long project should explicitly state that generation ranges were
      sampled rather than claiming every frame was checked.

## P2.6: Camera safety and real coverage

- [ ] In a 3D project open **Project Editor → 3D Camera Schedules**. Read the
      cumulative-motion explanation, then press **Review 3D Render Safety**.
      Confirm navigation to Render Monitor and a read-only check.
- [ ] Compare `0:(0)` with sustained gentle Z motion
      (for example, `0:(0.06)` over 80 frames) on a disposable project.
      The moving version should show a non-blocking cumulative-motion warning.
- [ ] Try an intentionally large per-frame translation and narrow field of
      view. Check for actionable advisory warnings without automatic repairs.
- [ ] Open **Camera Preview** with actual estimated depth. Read projected
      coverage and compare against the heuristics; estimates must **not**
      be described as measured coverage.
- [ ] On a disposable short test, if projection becomes empty, verify the
      render error reports the failing frame, resolved camera values, and
      last successful measured coverage when known.
- [ ] Restore gentle motion, then render successfully and verify frame
      pixels/results are unchanged by the safety-analysis code.

## P3.1: Responsive rendering UI

- [ ] Desktop widescreen and 100–200% browser zoom: Render Monitor
      shows Check Render, Resume, Cancel and Render Animation without clipping.
- [ ] Narrow phone (~360–390 CSS px): actions stack without page-wide
      horizontal scrolling. Render action buttons remain easy to tap.
- [ ] Tablet (~720 CSS px): actions and preflight reports wrap correctly.
- [ ] The 3D motion safety notice and button, project compatibility panel,
      preflight issue list and Fix in Editor work in both light and dark themes.
- [ ] Test keyboard Tab focus, activation, and long multiline diagnostics;
      review any screen-reader announcements if available.

## Regression smoke: P1–P2.4

- [ ] Last-opened project selection and unsaved edits are retained.
- [ ] Motion Lab workspace guide navigates without saving/applying.
- [ ] Appearance help toggle and mouse/touch help explanations behave.
- [ ] Model Manager scans refresh the Editor without dropping unsaved model
      or sampler choices.
- [ ] Checkpoint family, variant and compatibility information is correct.
- [ ] Basic first-run wizard and managed Z-Image availability still work.

## Signoff details

When reporting results, include which areas **PASS** or **FAIL**, the Windows
branch/build SHA, GPU model, desktop browser, Android/browser if used, a
short reproduction for failures, and relevant sanitized Console messages.
Do not share credentials or private filesystem contents.

**Gate:** P2.5, P2.6 and P3.1 remain pending physical signoff. Additional
development passes may be committed to `dev-webui` but `main` must remain
unchanged until the combined acceptance and separately authorized merge.
