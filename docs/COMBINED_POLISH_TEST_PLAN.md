# Combined WebUI polish acceptance: P2.5–P3.3 (historical)

> **Release reconciliation (2026-10-21):** These changes are present in
> published `main`, following later acceptance and promotion. Historical
> "do not merge" language and unmarked tests below refer to earlier
> development gates. The owner reported combined Windows acceptance, but
> dedicated mobile/device-width checks were not individually verified.
>
> **Milestone acceptance recorded · 2026-10-16.** The user reported testing
> the changes through P3.3 and said they are working as expected. The
> development head was `50101b146c3d502a61a59caba0f037438632268e`,
> with frontend/backend CI passing. This is a **user-reported combined PASS**,
> not independent verification that every checklist item and device size
> below was tested. Unspecified checks remain unchecked for traceability.
> **Historical gate only:** merge required authorization at that time;
> the subsequent approved promotion is complete.

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

**Gate update (2026-10-16):** User-reported combined acceptance now covers
P2.5–P3.3. Unreported device/edge-case checks remain unverified.
Further work may continue on `dev-webui`; the original merge gate was
subsequently satisfied. This checklist remains relevant for any deferred
physical device/edge-case verification.

## P3.2: Models, Settings, LoRA Manager, Image Results

- [ ] At 360px, 720px and desktop widths, check Model Manager search,
      both filters, Clear Filters, model family/type pills and Use/Copy Tag.
      Expand **Show full file path** using Tab, Enter and mouse/touch.
      Confirm long Windows/Linux paths wrap within the card.
- [ ] Open Managed Downloads with an installed, downloading or incomplete
      item if available. Check the status badge, progress text, full
      destination path and Download/Use buttons never push page width.
- [ ] In Settings, check the four group tabs are directly visible and
      keyboard-accessible at 360px and 200% browser zoom. Model Paths input,
      Check, Remove, Add Path and Save/Load Settings must remain usable.
- [ ] In LoRA Manager select a LoRA with a long filename and many trigger
      words. Check selected/focused filenames, all metadata fields, snippet
      and Copy/Insert controls, including narrow phone orientation.
- [ ] In Image Generation, generate two safe low-resolution images and
      verify the results gallery, long seed text, Reuse seed, Save,
      recent-job selector, and full-size lightbox close/download.
- [ ] Verify no page-wide horizontal scroll at 360px, 720px, or
      200% browser zoom, and that focus outlines remain visible.
- [ ] Check dark/light theme contrast and mobile touch targets.
- [ ] No data-loss, project changes or media regressions were introduced.

P3.2 was originally deferred with P2.5/P2.6/P3.1. The user subsequently
reported a successful combined test through P3.3; specific device widths
were not itemized. CI and static layout checks alone never certify
browser rendering at every size.

## P3.3: Motion Lab timeline, curves and dialogs

- [ ] At 1440px and 720px CSS widths, open **Visual Timeline** with a
      disposable animation project. Test the desktop horizontal track scroll,
      keyboard Tab focus on the scroll region, arrow-key scrolling, scale
      control, track picker, Playhead and Prev/Next Keyframe buttons.
- [ ] At approximately 360px CSS width and **200% browser zoom**, open the
      same timeline, select the first and final keyframes, use the phone track
      picker, frame scrubber, Add Keyframe, value editor, Apply and Delete on
      a disposable project. Verify no rightmost keyframes are clipped.
- [ ] On mobile, confirm timeline scrolling remains inside the timeline
      region rather than creating page-wide horizontal scroll. Verify the
      scroll region and keyframe chips have visible keyboard focus.
- [ ] Open **Motion Curves & Camera Path** with a draft camera layer:
      verify axes, Blend, Interpolation, Frame and Velocity fields, keyframe
      list, Save/Delete/Remove buttons, charts and playback scrubber all fit
      at 360/720/1440px and at 200% zoom.
- [ ] Test 3D Camera Schedules and Camera Composer presets on a copied
      project: preset select, Apply button, long labels and contextual help
      remain usable. Confirm no camera schedules change just by navigating.
- [ ] Open **Deforum Settings Import** with an example file containing
      unusually long filenames/mapping values. At phone and zoomed widths,
      scroll the dialog vertically, inspect field mapping, use Close,
      Cancel and Create without controls escaping the viewport.
      Do not overwrite an existing project.
- [ ] Check actual CPU Camera Preview, its timeline controls, curve readouts
      and 3D projected-coverage indicators at all three widths.
- [ ] Verify focus outlines, light/dark themes, enlarged UI scale and
      reduced-motion behavior. Recheck saved projects and ongoing jobs are
      unaffected by panel switching.

### Combined P1–P3 signoff

- [ ] Confirm first-run setup, Model Manager index refresh, LoRA insertion,
      image generation, Motion Studio/audio reuse, project drafts, P2.5
      render preflight, P2.6 camera advisories and the P3.1–P3.3 layouts
      all behave on the Windows test installation.
- [x] Record overall combined PASS at the milestone level, reported by the
      user on 2026-10-16 for P1–P3.3. The latest development commit was
      `50101b146c3d502a61a59caba0f037438632268e`; an independently
      observed test-machine SHA and per-case device results were not supplied.
      **No main merge** until separately authorized.
