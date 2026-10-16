# WebUI polish plan (dev-webui)

Working development backlog for the next Morphorum polish cycle.
Preserve projects, models, settings, outputs and render behavior.

**Acceptance update · 2026-10-16:** User reported the combined changes
through **P3.3 working as expected**, after the green frontend and backend
CI runs on `dev-webui` (P3.3 head: `50101b146c3d502a61a59caba0f037438632268e`).
Treat P1–P3 as **user-accepted at milestone level**. Exact browser/device
coverage and individual edge-case checklist items were not separately
reported; do not fabricate their results. Earlier "deferred/pending"
notes below document the historical development checkpoint and are
superseded by this acceptance update. **Do not merge to `main` without
separate, explicit authorization.** Next development phase: P4.

| Pass | Scope | Acceptance |
| --- | --- | --- |
| P1 | Editor empty states, disabled-control guidance, current project and last-opened restore, navigation, context-sensitive help | Users can unlock Editor without guessing; help works on touch, mouse and keyboard |
| P2 | Live model index updates, compatibility, generation help, pre-render checks, 3D camera-motion warnings | New models appear without refreshing; warnings never silently change schedules |
| P3 | Responsive layout, controls, overflow, themes and accessibility | Verified from 360–1440 CSS px plus enlarged scaling |
| P4 | Progress, feedback, toasts, loading state and actionable errors | Every operation signals its state and identifies failures clearly |
| P4.4 | FFmpeg Manager: system detection, custom executable, local managed download | Safe verified FFmpeg/FFprobe selection across supported Windows/Linux hosts |
| P5 | Motion Lab project summary, preview/apply/render clarity, audio reuse, units, navigation | No loss of unsaved work or saved media |
| P6 | Startup fault isolation, refresh/reconnect, version/cache, sanitized diagnostics, regression tests, 3D warp error detail | Optional services cannot block the basic editor |
| P7 | Portable project ZIP import/export including media, integrity manifest, optional large files and model remapping | Projects move between hosts without overwriting existing data |

## P1 acceptance

- [x] P1.1: Clear Project Editor empty state, Project Manager and wizard shortcuts.
- [x] P1.2 initial: Explain disabled model selection and absent checkpoints.
- [x] P1.3 initial: Show current project, model and saved/unsaved status.
- [x] P1.4: Restore last opened project if available, fall back safely, clear on deletion.
- [x] P1.5: A project-aware Motion Lab wayfinder gives active workspace, project/save status, safe adjacent tool shortcuts and empty-project recovery without duplicating controls.
- [x] P1.6: Reusable contextual help (?) for selected Editor/Composer controls, saved Appearance toggle, keyboard/touch support; future passes broaden coverage.

## P2 implementation / acceptance

- [x] P2.1: Subscribe the Project Editor and Deforum importer to Model Manager's indexed-model update event without a forced page refresh.
- [x] P2.1 safety: Preserve unsaved checkpoint and sampler choices, including a deliberately cleared model; keep missing checkpoint IDs and reject stale fetches.
- [x] P2.2 initial: Clarify separate still-image and project-specific animation checkpoint selectors.
- [x] P2.3: Read-only indexed checkpoint/family/variant/sampler/resolution compatibility summary with missing-model guidance and navigation to Model Manager; preserve unsupported saved samplers for explicit repair.
- [x] P2.4: Add optional contextual help to Image Generation and remaining animation, cadence and camera controls; show pixels, degrees and frame units plus an inline schedule example.
- [x] P2.5: Add read-only backend preflight endpoint, Check Render results, first-issue navigation, and automatic preflight before render submit; block errors and explicitly review warnings without modifying project data.
- [x] P2.6: Advisory risk analysis of sampled per-frame/cumulative 3D motion and narrow FOV; improved diagnostics for failed projections including real last-successful coverage.

## P6 early safety

- [x] Optional depth-service discovery failures no longer prevent project loading.
- [x] Add last-successful projected-coverage and resolved camera diagnostics to 3D warp failure messages.

## P7 package policy (proposal, not implemented)

Include project.json and a versioned manifest with relative paths, SHA-256
checksums and format compatibility; attached start image; imported soundtrack
and offset; Motion Lab WAVs, cues and marker overrides; optional hybrid video.
Completed renders are opt-in. Exclude model weights, credentials, machine paths,
temporary caches and unlisted external files.

Import should preview content, verify checksums and resource limits, reject
archive path traversal, absolute paths, links and decompression bombs, assign
a fresh project ID, never overwrite another project, remap unavailable models
by compatible family and roll back an incomplete import.

## Physical acceptance

For this initial P1 pass test empty libraries, existing projects, stale remembered
IDs, missing checkpoints, rename/unsaved status, Project Manager and New Project
Wizard shortcuts, a failing optional depth endpoint, desktop/mobile layouts,
browser refresh, and actual image/animation generation. Run Node/frontend CI;
a green CI result does not replace a physical GPU test.

## P1.6 acceptance notes

Contextual help icons use trusted static text, real buttons beside form labels, and a shared dismissible tooltip. Mouse hover, focus, Enter/Space, tap, Escape, outside click, and mobile viewport layout must be checked. Settings → Appearance → Contextual Help persists on the backend; unsaved changes should revert on Settings reload. Hiding optional hints must never suppress warnings or errors. The code has not been physically GPU-tested yet.

## P1.5 navigation acceptance

- The wayfinder stays outside the twelve dedicated workspace panels and does not clone tool controls.
- With no project open it routes to Project Manager or New Project Wizard, not a disabled editor.
- For an open project it suggests relevant workspaces and shows unsaved Editor state.
- Route buttons only call the existing workspace switcher. They never save, apply motion, switch projects or start rendering; existing unsaved-edit confirmations remain authoritative.
- Leaving active Live Recording through navigation uses the existing safe stop behavior.
- Test desktop, tablet and narrow phones; verify the shortcuts on each workspace, model-setting edits remain dirty, and jobs continue through workspace navigation.

## P2.3 acceptance

- Model type/family/variant come from the indexed checkpoint and backend family capabilities, not inferred filenames.
- Compatible sampler lists and divisibility (SDXL 8px, Flux and Z-Image 16px), bounds (64–4096), and memory caution appear beside the editor checkpoint selector.
- A missing checkpoint retains its saved ID; a saved sampler that is no longer supported is displayed, not silently replaced. Unsupported or unavailable capabilities are reported as warnings rather than an invented compatible status.
- Model Manager shortcut, Choose Sampler and Edit Resolution focus/navigation are advisory. This pass does **not** disable render buttons, revalidate the full timeline, or automatically modify project settings; P2.5 handles pre-render validation.
- Check both 2D/3D projects, supported/missing/unsupported models, Flux Schnell variant, blank checkpoint, large/custom dimensions, saved incompatible sampler, Model Manager scans and unsaved form state on Windows and phone.

## P2.5 acceptance

- Checking a render never saves a project, changes its schedules, allocates GPU work, starts an export, or writes output folders.
- Backend preflight checks indexed and on-disk checkpoint availability, model family, supported adapter file format, sampler compatibility, output size and alignment, required start image, existing schedule and LoRA checks, hybrid opacity, plus sampled steps/guidance range and first-frame positive prompt.
- Errors block the UI render action. Warnings require an explicit Render Anyway confirmation. The server render endpoint still performs its own authoritative existing validation.
- The submitted render freezes the same collected browser draft that was checked. If the project changes during the async check/dialog, submission is canceled and the user must check again.
- In large projects, per-frame generation-parameter checking samples up to 500 frames and prominently warns that remaining frames are checked during generation. GPU/model-inference health and cumulative camera projection are not guaranteed by preflight.
- Test source-image versus prompt start, missing or incomplete checkpoints, incompatible sampler, alignment, invalid schedules, missing prompt, unsaved edits, navigation, warnings and cancellations, desktop and mobile. Physical Windows GPU acceptance required before merge.

## P2.6 acceptance and deferred hardware testing

- A no-GPU, no-depth estimate looks for unusually large single-frame motion, accumulated scene-space translation/rotation, and narrow FOV combined with motion. It returns warnings, **not blockers**.
- Checks are sampled for long schedules and are not actual coverage predictions. Exact pixel coverage depends on the source image, depth estimator, and camera position; Camera Preview remains the visual reference.
- The Project Editor offers **Review 3D Render Safety** to switch to Render Monitor and invoke the existing read-only P2.5 preflight check; it never saves or starts generation.
- Live 3D zero-projection errors include frame, counts of points in front and within image bounds, resolved camera axes, and last successful projected coverage if known. No image pixels, depth, motion schedules, or renderer recovery behavior are altered.
- P2.5 and P2.6 physical tests are **deferred at user request**. Keep main unchanged pending a combined Windows/Android acceptance pass.

## P3 responsive and accessibility milestones

- [x] P3.1: Keep four Render Monitor actions, preflight reports and 3D camera safety controls within small/mobile/zoomed layouts. Buttons have wrapped labels and full-size touch targets.
- [x] P3.2: Fix intrinsic-width overflow in Model Manager, Settings, LoRA Manager and Image Results; add responsive button grids, accessible expanded filenames/paths, and keyboard focus styling. Device/zoom acceptance deferred.
- [x] P3.3: Contain Motion Lab timeline, curve, inspector, 3D camera, previews, and Deforum import dialog at narrow/zoomed widths; make desktop timeline keyboard-scrollable and fit focused phone plots to actual card width. Physical acceptance deferred.

P3.1 was initially a code/style regression checkpoint; the combined P2.5–P3.3
milestone subsequently received user-reported acceptance on 2026-10-16.
Specific device widths and browser zoom checks remain unitemized. Do not
merge to main without separate authorization.

## Combined acceptance test plan

The [COMBINED_POLISH_TEST_PLAN.md](COMBINED_POLISH_TEST_PLAN.md) covers
P2.5–P3.3. The user reported a successful combined test on 2026-10-16.
Unreported individual checks remain unchecked for traceability. No merge
to main is authorized.

## P3.2 code acceptance

- Model Manager search/filters shrink to one column on narrow viewports. Long model paths and managed-model destinations wrap; indexed paths remain behind keyboard-accessible Show full file path disclosure.
- Settings tabs form two rows at phone/zoom widths; all four destinations remain directly accessible. Model path input and Check/Remove controls become separate rows at the narrowest breakpoint.
- LoRA metadata, selected/focused long filenames, tags, and quick-action buttons fit their card. Long text is selectable instead of forcing an oversized page.
- Image Results retain seed details, full-size preview, Save and Reuse seed actions, with stacked layouts at narrow widths.
- CSS-only layout changes do not alter API calls, model selection, downloads, save, prompt tags or generation behavior.
- Desktop 1440px, tablet 720px, phone 360px, light/dark, 200% zoom and keyboard navigation **remain pending physical testing** and are included in the combined checklist.

## P3.3 implementation / physical signoff

- Desktop timeline scale and editable frame positions are unchanged. The scroll region is keyboard focusable, and keyframe buttons retain visible focus outlines.
- Mobile-focused timeline sizing no longer assumes a 300px minimum plot width, which previously clipped the last frames in narrower cards or at 200% zoom.
- Motion Curve and Camera Path SVGs retain their logical coordinates, while their containers, field grids, readouts and action buttons shrink and wrap.
- 3D preset, inspector, camera preview, and Deforum importer keep long filenames, descriptions and mapped fields within their scroll areas. Dialog Close/Cancel/Create actions remain keyboard/touch accessible.
- Layout and accessibility changes do not save or apply motion, move keyframes, modify camera schedules, change model choices or start renders.
- **P3 implementation is complete and user-accepted at the combined milestone level (2026-10-16).** Detailed device/zoom results were not itemized. Leave main unchanged until explicit approval.

## Next development phase: P4

P4 targets clearer operation progress, consistent asynchronous busy/disabled
states, toast notifications and actionable error messages. P4 work is not
started by this acceptance note; begin in `dev-webui` when authorized.

## P4: progress, feedback and notifications

- [x] **P4.1:** Shared, persistent and accessible operation-status ribbon
  with running/success/warning/error states; indeterminate and determinate
  progress, origin navigation, explicit dismiss (without cancellation),
  and out-of-order async response guards.
- [x] **P4.1 integrations:** Settings Reload/Save busy state and actionable
  validation failures; Model Manager scan + post-scan index refresh and
  background managed-model downloads with live bytes/percentage, completion
  and repair guidance. A failed index refresh no longer reports a successful
  scan. No changes to backend generation or download APIs.
- [x] **P4.2:** Extend consistent operation-status and in-flight guards to
  Image Generation submission, history refresh and model unload; Motion Lab
  CPU preview generation, draft preview/apply and render submission. Preserve
  existing detailed job progress and cancellation interfaces; distinguish
  blocked, cancelled, queued, successful and failed operations.
- [x] **P4.3 code complete:** Prioritize failures above background success
  and progress notices; bound/dedupe toast stacks, make alerts accessible and
  progress quiet for screen readers; emit browser-side runtime diagnostics;
  detect repeated status polling failures and announce recovery once; bound
  read-only polling GET requests with aborts that never cancel host jobs.
  Preserve managed download tokens across temporary connectivity failures.
  Targeted P4.1/P4.3 JavaScript regression checks passed (11/11 in an
  isolated V8 harness, 2026-10-16), but full Node CI and physical GPU/browser
  signoff have not been verified.
- [ ] P4 Windows/phone acceptance. Keep `main` unchanged.

### P4.1 acceptance

At desktop and narrow phone sizes: verify Settings Save and Reload show
persistent progress and result; invalid paths yield warnings; failed host
requests remain visible with actions; Model scan shows scanning/index-refresh
states and cannot claim success after refresh fails; managed Z-Image download
shows bytes and percentage and resumes status after browser reload (while
catalog polling is active). Closing a notice does not cancel the operation.
Independent concurrent operations remain tracked without stale responses.
Test reduced-motion preferences and screen reader output.

### P4.2 acceptance

- Image submit reports a non-percentage pending state, rejects duplicate
  submission requests, then yields to the existing generation job monitor;
  errors remain visible with an actionable retry suggestion.
- Refresh Image History has a proper busy button, disabled repeat action
  and explicit success/error feedback. Model Unload cannot race with an
  active or just-submitting image job; failure is reported without clearing
  the loaded state incorrectly.
- CPU Camera Preview updates status and measured progress from the preview
  job, then reports a final success or error. It does not load a diffusion
  model. Preview/apply of Motion Lab layers distinguishes draft-only
  compile, required Editor-save confirmation, rebase confirmation, success,
  failure and user cancellation.
- Render submission reports preflight, warning confirmation, blocked
  validation, cancellation, stale browser edits, queuing and submit errors.
  A failed refresh of render history cannot retroactively mark an accepted
  render as failed. Live frame/GPU progress remains in Render Monitor.
- All feedback uses the P4.1 non-blocking operation ribbon; dismissing
  feedback does not abort the running operation. Operations do not mutate
  project settings beyond the user's explicitly authorized actions.
- Windows GPU/CPU and Android UI testing of P4.2 still required. `main`
  remains unchanged.

### P4.2 follow-up: nonintrusive feedback

Automatic curve editing may trigger dozens of transient server-side preview
recompiles. These keep their existing inline Motion Curves diagnostics but do
not publish a separate persistent banner for every draft change. Clearing
or switching previews also closes its operation notice as "no longer
tracked," without claiming that an already queued CPU backend job was
cancelled. Both behaviors need physical confirmation with P4.2.

## P4.3 implementation / acceptance

P4.3 is committed to `dev-webui`, not `main`. Existing P4.2 acceptance
and the final combined P4 Windows/Android signoff remain outstanding.
No behavioral changes to render cancellation, downloads, GPU execution,
project persistence, or video/audio output are intended.

- Operation tracker retains up to twelve settled notices, promotes errors
  above warnings, live work and success, resolves same-priority notices by
  last meaningful event (not start order), ignores stale tokens and allows
  independently dismissing problems without canceling backend jobs.
- Toast stack is capped to four, favors error/warning severity, ignores
  identical messages for thirty seconds, and leaves errors visible longer.
  The persistent operation ribbon is the canonical status of long operations.
- A separate screen-reader live region announces lifecycle transitions,
  not per-frame progress or repeatedly changing percentages. Errors use an
  assertive announcement; normal changes are polite. Dismiss and navigation
  retain their existing accessible buttons and reduced-motion styling.
- Image Generation, Camera Preview, Animation Render, Video Export and
  Managed Model download status checks report **one** warning after three
  consecutive failures, continue retrying, and report recovery once.
  A read-only status request times out after twenty seconds. A missing
  status response does **not** imply a job failed or stopped; users should
  check the Console before submitting a second job.
- Managed model polling keeps accepted download tokens through connectivity
  outages and backs off retry intervals instead of falsely reporting a failed
  download. Browser-side retry warnings/recovery appear in Console → Runtime
  and do not get sent to the server or include raw request payloads/paths.
- The build/runtime offline label refreshes when telemetry fails and the
  backend health endpoint is checked. Telemetry failure alone is **not**
  treated as proof that the host or GPU job is down.
- Automated checks: `node --test tests/frontend_p4_operation_feedback.test.cjs tests/frontend_p43_feedback.test.cjs`
  (targeted tests passed in a V8 test harness; this is **not** a claim of a
  successful repository-wide CI run).

### Remaining physical P4.3 checks

- [ ] With an image or animation actively rendering, temporarily stop/restart
  the backend or disconnect the browser network. Verify one warning after
  repeated status errors, no duplicate toasts, continued retry and recovery
  without another render being submitted.
- [ ] Test a deliberately stalled read-only status GET; after the bounded
  timeout, confirm no backend cancel and an eventual recovery or warning.
- [ ] Verify the managed Z-Image download can recover after lost catalog
  connectivity without resetting the accepted download or claiming success.
- [ ] Test concurrent Settings Save, model scan and render notifications;
  prioritize failures, dismiss a notice without interrupting work, and
  inspect the browser's Runtime Console events.
- [ ] Check mobile/desktop, keyboard navigation, light/dark themes, screen
  readers, reduced motion and 200% zoom. Confirm live-progress updates do not
  repeatedly announce frames or percentages.
- [ ] Run repository-wide CI and ordinary image/animation/video regression
  work on Windows. P4.2 and P4.3 physical acceptance required before
  promotion to `main`.

## P4.4: FFmpeg Manager (scheduled immediately after P4.3)

User request, 2026-10-16: in **Settings**, offer three FFmpeg source modes:
**Auto-detect installed FFmpeg**, **Custom executable path**, and **Morphorum-managed local FFmpeg** downloaded under the Morphorum installation (proposed: `tools/ffmpeg/`).
This is a dedicated P4.4 milestone because downloader integrity, Windows/Linux packaging,
FFprobe pairing, safe extraction, Settings persistence and video/audio integration
are too large to bundle into P4.3's notification and reliability audit.
No implementation or physical verification is implied by this planning entry.

### P4.4 implementation sequence

- [x] **P4.4.1 / Resolver and validation (implemented; physical tests pending):** Introduce a single backend-owned
  FFmpeg/FFprobe resolver for `animation_video`, `animation_hybrid_source`,
  `animation_hybrid_extract` and `project_soundtrack_motion`. Preserve
  compatibility with `MORPHORUM_FFMPEG` and existing PATH behavior. Define
  explicit selection precedence (saved user mode > legacy environment setting
  > system PATH where applicable). In explicit custom/managed modes, never
  silently run a different binary when selected binaries are missing. Probe
  `-version` with bounded timeout and no shell; require the matching FFprobe
  beside the executable for video source features and report capability gaps.
- [x] **P4.4.2 / Settings (implemented; physical tests pending):** Add a responsive FFmpeg Manager under Settings
  showing source mode, editable custom path, effective paths, version,
  architecture, detection/validation outcome, actionable errors and a
  user-triggered Test/Refresh operation. Persist settings using existing
  atomic settings mechanics; never rewrite system PATH or install globally.
**P4.4 checkpoint · 2026-10-16:** Backend FFmpeg/FFprobe selection and
Settings controls are committed on `dev-webui`. Auto-detect honors legacy
`MORPHORUM_FFMPEG` before PATH; Custom/Managed mode never silently falls
back to a different binary. The Settings → Storage → FFmpeg Manager panel
supports source choice, custom path, read-only version tests and persisted
selection. Export/probe/extraction/audio users share one resolver, and Video
Export refreshes after settings reload/save. A missing `ffprobe` leaves FFmpeg
export usable but video import unavailable. P4.4.3 now adds an opt-in managed installer; see its checkpoint below.
Windows/Linux live acceptance and repository CI are not yet verified.
Do not merge into `main`.

- [x] **P4.4.3 / Managed install (implemented; live acceptance pending):** Support vetted downloadable FFmpeg +
  FFprobe bundles for supported Windows and Linux architectures, with a
  versioned local destination under `ROOT/tools/ffmpeg/` (outside Git),
  progress and cancellation through the P4 operation feedback system,
  published provenance/checksum verification, download size limits, safe
  archive extraction, staging + atomic promotion, cleanup/retry, and clear
  replacement/update/removal controls. Avoid privileged/system installation,
  unexpected auto-downloads, and executable bits where inappropriate.
  State unsupported platforms explicitly. Review third-party distribution
  and LGPL/GPL obligations before selecting managed bundle providers.
**P4.4.3 checkpoint · 2026-10-16:** The new `managed_ffmpeg.py`
manager uses BtbN's pinned FFmpeg 8.1 release-family static GPL packages
for Windows x64/ARM64 and Linux x64/ARM64. Release metadata from GitHub's
`releases/tags/latest` is checked for the exact allowlisted artifact name,
URL, bounded archive size and published SHA-256 asset digest. Downloads are
streamed with cancellation and size checks. Extraction accepts **only**
`ffmpeg`/`ffprobe` executables, rejects archive traversal, symlinks,
duplicate names and oversized entries. Both executables are probed in a
private staging directory before promotion to
`tools/ffmpeg/current/bin`. Failed validation leaves the previous
installation intact; replacement is backed up and rolled back if promotion
fails. Install, update/reinstall, cancel, and owned-install removal controls
have progress reporting, recovery polling, responsive layout and are opt-in
under Settings → Storage → FFmpeg Manager. Existing video/audio outputs and
projects are never touched. Installation/removal is refused while tracked
video exports or hybrid extractions are running; already-running subprocesses
and the audio conversion path need final real-world race testing on Windows.

GPL static releases provide x264 encoder support and have different license
obligations than the application's Unlicense. Each local installation has a
notice with provider, package, SHA-256, source URLs and licensing pointers.
No FFmpeg binaries are checked into this repository. The external asset
provider, licenses and source availability must be reevaluated for public
distribution.

**Gate:** Browser-level JS syntax/targeted regression test and Python unit
coverage are prepared; no real download from GitHub nor Windows/Linux
executable smoke test or full CI result has been verified in this turn.
P4.4.4's **physical** acceptance remains open. Do not merge `main`.

- [x] **P4.4.4 / Code and Linux-host smoke complete (Windows/managed-package physical acceptance pending):** Regression-test video export (MP4/WebM),
  hybrid-video probing/extraction, soundtrack MP3/OGG/FLAC conversion, missing
  codec handling, PATH/legacy env/custom/managed precedence, invalid paths,
  interrupted/corrupt downloads, Windows paths with spaces, Linux execute
  permissions, restart persistence, offline operation after install, and
  existing video-render jobs while Settings change. Do not mutate projects,
  remove outputs or change an executable already captured for a running job.
  Include automated tests and Windows/Linux physical acceptance; never merge
  `main` without explicit authorization.

### P4.4.4 implementation and validation, 2026-10-16

Code on `dev-webui`:

- Managed FFmpeg 8.1 installer verifies `ffmpeg -hide_banner -encoders`
  contains **libx264, libvpx-vp9, aac, libopus** before replacing
  an existing installation. A successful version check alone is insufficient.
  An unsupported/missing encoder leaves the previously installed version intact.
- Startup status recovers an owned, complete `.previous-<job-id>` folder
  if a process was interrupted after moving the old version aside.
  Ambiguous backups are *not* restored automatically. An explicit Remove
  operation leaves a persistent removal marker to prevent accidentally
  resurrecting a stale backup. Broken-but-owned installs can be repaired
  or removed without being marked ready.
- Hybrid extraction captures its chosen FFmpeg executable at job acceptance
  instead of resolving it later. Video export already captures the binary
  before its worker thread starts. No project/render data was migrated.
- The standalone `scripts/ffmpeg_acceptance.py` produces 8 synthetic 64×64
  PNGs and a 1-second PCM WAV in temporary storage only. It verifies:
  MP4/H.264 + AAC, WebM/VP9 + Opus, FFprobe streams, hybrid PNG extraction,
  and MP3/OGG/FLAC conversion into 16 kHz mono PCM WAV.
  **A direct, equivalent temporary-media smoke run passed all six groups
  against Linux system FFmpeg 7.1.5 on 2026-10-16.** This does *not* prove
  that the managed 8.1 downloads have run on Windows or Linux.
- New fixture tests cover required codecs, interrupted-upgrade recovery,
  deliberate removal, incomplete managed installations, hybrid binary pinning,
  disposable PNG/WAV source generation, and read-only/explicit-action API
  guards. Added CPU-only Windows/Linux GitHub Actions workflow at
  `.github/workflows/ffmpeg-integration.yml` plus existing syntax workflow.
  **Full Python pytest and GitHub Actions run results are not yet verified.**
- No FFmpeg download was performed in this turn, and no live Windows
  execution was available. The updater and `main` remain unchanged.

#### Outstanding P4.4 physical acceptance (must not mark complete before testing)

- [ ] Windows test host: update `dev-webui`, open Settings → Storage →
  FFmpeg Manager, select Managed → Install, verify checksum/progress/FFprobe,
  Save Settings, restart, then run
  `.\.venv\Scripts\python.exe scripts\ffmpeg_acceptance.py --mode managed`.
- [ ] Linux host: install Managed to the local `tools/ffmpeg/current/bin`
  and run `./.venv/bin/python scripts/ffmpeg_acceptance.py --mode managed`.
  BtbN Linux builds require glibc 2.28+ and Linux kernel 4.18+.
- [ ] Exercise custom/system/legacy `MORPHORUM_FFMPEG` precedence,
  Windows executable paths containing spaces, audio imports, video export,
  hybrid extraction, application and browser restarts, and unsupported OS.
- [ ] Deliberately interrupt downloads and the backend, then retry.
  Test corrupt archive/digest fallback, package replacement while video work
  is active, Cancel, Update/Reinstall, Remove, and out-of-disk conditions.
  Verify old managed binaries and existing projects/media remain untouched.
- [ ] Confirm true Windows/Linux GitHub Actions/pytest results and review
  the BtbN GPL source/redistribution requirements for public releases.
  No merge to `main` without explicit user approval.

**Release gates:** Complete P4.3 notification/error polish independently; then
implement and verify P4.4 on `dev-webui`. Existing P4.2 GPU/phone acceptance
is still pending and should not be represented as complete. FFmpeg install is
always opt-in; system and custom installations remain valid alternatives.
