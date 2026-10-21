# WebUI polish plan and historical development record

> **Release reconciliation (2026-10-21):** The completed WebUI improvements described in this historical roadmap are on the published `main` branch. [PR #51](https://github.com/merberg-ai/Morphorum/pull/51) promoted subsequent About, cached-artwork and managed Z-Image LoRA changes after Backend, Syntax and Installer checks passed. P5.3–P5.5 and dedicated physical mobile acceptance remain open; not every unchecked roadmap item is implemented or tested. References below to not merging, future gates and specific historical dev commits describe the status **at the original milestone**, not a current embargo on already-released features. [Current status](CURRENT_STATUS.md) | [Prompt Studio plan](PROMPT_STUDIO_ROADMAP.md).

Original development backlog for Morphorum's polish cycle.
Preserve projects, models, settings, outputs and render behavior.

**Acceptance update · 2026-10-16:** User reported the combined changes
through **P3.3 working as expected**, after the green frontend and backend
CI runs on `dev-webui` (P3.3 head: `50101b146c3d502a61a59caba0f037438632268e`).
Treat P1–P3 as **user-accepted at milestone level**. Exact browser/device
coverage and individual edge-case checklist items were not separately
reported; do not fabricate their results. Earlier "deferred/pending"
notes below document the historical development checkpoint and are
superseded by the later acceptance and release history. **At this original
checkpoint, a separate merge authorization was still required; that release
gate has since been satisfied.** The next phase at that point was P4.

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

## P5 · Next implementation milestone

**Plan:** [P5 Motion Lab Workflow Plan](P5_MOTION_LAB_WORKFLOW_PLAN.md) on `dev-webui`. The planned sequence is **P5.1 project/motion summary → P5.2 preview/apply/render clarity → P5.3 soundtrack reuse/export provenance → P5.4 units and navigation → P5.5 regression, docs and owner signoff**.

**Gate:** UX5 Windows/GPU acceptance was reported as PASS and Syntax, Backend and Installer CI were green at the verified checkpoint. **Physical mobile testing has been explicitly deferred by the owner** and is tracked as remaining work, not a failed or passed test; this does not block P5 implementation. Keep `main` unchanged without explicit merge authorization.

## Pre-P5 UX organization: Motion Studio and Project Editor

**Branch:** `dev-webui` (rebased/fast-forwarded to the approved WebUI+FFmpeg release, with dev-only acceptance notes restored). Do not promote these unfinished changes to `main` without a separate owner acceptance and CI gate.

### UX1 + UX2 · Motion Studio flow and navigation

- [x] Originally replaced the long mixed-card stack with five focused stages.
  **Current shipped workflow adds dedicated Assign Motion to Beats**, making
  six stages: Load Audio → Analyze WAV → Detect Beats → Assign Motion to Beats
  → Create Motion → Preview & Apply. See [Motion Studio](MOTION_STUDIO.md).
- [x] The Create Motion stage offers four authoring modes: **Beat Cues**,
  **Sound Channels**, **Continuous Motion**, and **Single-Band Pulse**.
  Continuous presets remain usable without an audio source.
- [x] Reparent **original DOM controls**, the waveform, marker editor, cue
  director, channel card and continuous motion card. Never clone controls,
  reset a file selection, discard marker/cue drafts or change backend APIs
  just to navigate.
- [x] Move length matching to audio selection, transient/level band,
  sensitivity and threshold to detection, and pulse axis/distance/attack/
  release to response settings, selected by **stable input IDs** instead of
  fragile child positions.
- [x] Add accessible keyboard-operated stage and author-mode tabs,
  persistent browser-only stage/mode preferences, current-stage statuses,
  Previous/Next controls and responsive compact/mobile styling.
- [x] Add frontend regression tests and update Motion Studio documentation.
- [x] **UX2.1 Windows feedback regression fix (2026-10-16):** owner confirmed
  overall stage layout is better, but reported Analyze WAV appeared inert,
  no beat-action button was visible, and Additional envelope diagnostics was
  blank. Moved live analysis feedback out of hidden Single-Band Pulse panel,
  added explicit progress/errors/blocked-state hints near Analyze, a
  **View Detected Beats** action in Step 2, **Show Detected Beats** in Step 3,
  and a Continue-to-Analyze action in Step 1. The analyzer already produces
  event candidates; viewing them does not re-run a destructive detector.
  Envelope diagnostics now explain missing/misaligned data and show the graph
  when aligned, while the empty preview placeholder is explicitly hidden
  after analysis. Added simulated success/failure/no-source and SVG regression
  tests. **Owner must retest before closing UX1/UX2.**
- [x] **UX2.2 owner screenshot follow-up (2026-10-16):** owner reported analysis was blocked with one existing draft layer when the optional Match project length checkbox was selected, a duplicated/oversized status column squeezed the waveform, and Preview Matches always displayed zero. Source fixes on dev-webui: analysis now skips blocked optional resizing while retaining the existing layer and old analyzed state until a valid replacement; only one status message is visible; Analyze step uses full-width vertical flow; matching falls back to analyzed events when no marker override exists, diagnoses excluded hits and resets obsolete time range on WAV change. Added scenario-based regression tests. **Physical Windows retest is required.**
- [x] **UX2.3 dedicated beat assignment (2026-10-16):** owner reported that Kick/Snare/Highs → movement preset → batch assignment became buried after stage reorganization. Added a dedicated **Assign Motion to Beats** stage between Detect Beats and Create Motion, surfaced the existing director there, opened beat matching by default, and clarified **Assign All Matching Beats**. Retained manual cue editing, preview, save and apply actions; added source regression assertions. Commits `6f228496a7cb` and `318d52a2472b`. **Browser and CI acceptance remain pending.**
- [ ] **Owner Windows physical acceptance:** fresh WAV Analyze, saved-project
  soundtrack restoration, waveform Seek/Zoom/Play, marker drag/add/save,
  cue editing/Find Beats/save, independent channels, continuous preset without
  audio, single-band pulses, motion stage/preview/apply, switching active
  sections without data loss, laptop/phone/200% zoom, keyboard navigation.
- [ ] **CI verification:** syntax/frontend and backend workflows on current
  dev head; do not equate a source-level test with physical browser acceptance.

### UX2.4 · Promote project workspaces to main navigation

- [ ] Move **Project Manager**, **New Project Wizard**, and **Project Editor** out of the Motion Lab submenu and expose them as first-class main-menu destinations. Leave Motion Lab / Motion Studio focused on camera motion and audio-driven animation.
- [ ] Retain the existing project selection, unsaved-edit prompts, wizard progress, project restore, deep links, back navigation, keyboard/phone access, and setup shortcuts. Move/reparent existing workspaces instead of cloning form controls or modifying project data.
- [ ] Update labels, wayfinding and documentation so users can go directly to project creation and management without entering Motion Lab. Regression-check open projects, draft edits, active renders, and navigation on desktop and mobile.

**UX2.4 implementation checkpoint (2026-10-16):** Primary navigation now links directly to Project Manager, New Project Wizard and Project Editor, with those entries removed from the Motion Lab sidebar and tool-card launcher. All three retain the original panels and handlers; Motion Lab primary entry opens its Overview. Focused source regression tests added in `tests/frontend_project_navigation.test.cjs`. **Automated CI and physical Windows/mobile acceptance are pending**; do not mark UX2.4 fully accepted yet.

**UX2.4 routing hotfix (2026-10-16):** owner Windows test found that all three promoted top-level project links opened Motion Lab Overview rather than their workspaces. Root cause: the main-menu click handler still targeted `#animation-tab-*`, but UX2.4 removed those DOM buttons. Restored the real workspace dispatch buttons as programmatically clickable, visually hidden elements; no duplicate panels or visible Motion Lab menu entries. Added targeted regression coverage (`7db2f6db`, `6e22a880`). **Windows retest and automated CI still required.**

### UX2.5 · Safe bulk project trash (Project Manager)

- [ ] Add accessible multi-select (checkboxes), **Select All Visible**, **Clear Selection**, and a selected-count action bar with **Move Selected to Trash**. Filters/search/pagination must not silently include hidden projects; use stable project IDs rather than row positions.
- [ ] Reuse existing single-project trash semantics and backend safeguards. Batch operation must **move to trash, not permanently delete**. Clearly distinguish active/current projects, in-progress renders, unsaved edits and already-trashed items; exclude or explain blocked selections.
- [ ] Show one confirmation with exact selected count and names (or a concise preview for large batches). Display per-project success/failure, partial results and updated selection. Do not claim all succeeded when any failed.
- [ ] Provide trash restore via the existing workflow where supported. Define atomicity/rate limits and safe retry/idempotency before implementation; never delete on selection alone.
- [ ] Test filtered and paginated selections, mixed permitted/blocked items, failed requests, network interruption, active project, keyboard/mobile layout, and restore. No permanent-delete endpoint may be invoked by the bulk action.

**Sequencing:** implement UX2.4 navigation and UX2.5 bulk trash before UX3 Editor grouping; then complete UX4/UX5 and resume P5. These are roadmap additions only, not implemented or accepted.

**UX2.5 implementation checkpoint (2026-10-16):** Added checkbox multi-selection in Project Manager, Select All Visible (respecting current search), Clear Selection, selection count, confirmed Move Selected to Trash, per-item failure reporting, and preservation of unsuccessful selections. Reuses the existing managed project DELETE-to-`.trash` endpoint; completed renders and exports remain separate. Motion Studio was moved immediately below Overview in the Motion Lab sidebar. Added responsive styling and source regression assertions. **CI, physical Windows/mobile acceptance and recovery behavior remain pending; do not merge to main.**

**UX2.5 + Motion Studio follow-up (2026-10-16):** Windows owner reported checkboxes selectable but bulk count stuck at zero and the only visible trash button remained single-project. Corrected wrong-function selection toolbar placement (was in prompt editor); status now reflects Project Manager selections and enables the separate bulk action. Motion Studio WAV analysis now attaches its source as the single active project export soundtrack for **future** renders (confirmation if replacing a different soundtrack, with visible failure warning); entering Motion Studio restores/analyzes a saved soundtrack automatically where there is no existing analyzed Motion Lab WAV. The canonical soundtrack attachment remains distinct from archived Motion Lab WAV analyses; existing files and previous render snapshots are not automatically deleted or rewritten. Added source regression assertions. **Windows/CI verification pending; verify on disposable projects and confirm re-rendered exports include audio before signoff.**

**UX2.5 unified Trash action (2026-10-16):** Owner confirmed soundtrack attachment works and requested a single Project Manager Trash button. Removed the separate bulk-toolbar trash button. Existing detail-pane **Move to Trash** now uses the original exact-name confirmation for zero or one checked selection (one checked project takes precedence over the highlighted detail project), and switches its label to **Move N Selected to Trash** with a batch confirmation when multiple checkboxes are checked. Selection count, Select All Visible, Clear Selection, partial-failure handling, and existing trash safeguards remain. Source regression assertions updated. Windows/browser and CI acceptance pending.

### UX3–UX5 · next after acceptance

- [ ] **UX3:** Split Project Editor into Setup, Sources & Media,
  Timeline & Prompts, Camera & Motion, Generation Settings.
- [ ] **UX4:** Persistent project/save status, mobile navigation, context
  indicators, clean keyboard flow and responsive details.
- [ ] **UX5:** Combined regression tests, updated public docs and user
  acceptance before any release PR merge.

**UX5 audit started:** See [UX5_ACCEPTANCE_PLAN.md](UX5_ACCEPTANCE_PLAN.md) for the full release gate. At UX4.2 head the Syntax workflow failed 12/236 frontend assertions, Backend failed 1 test involving manual keyframe clipping, and Installer passed. A targeted backend safeguard correction preserves explicitly authored keyframe/recording axes, but CI must rerun. No release merge or blanket acceptance is authorized.

**UX3 layout hotfix:** First owner Windows screenshot exposed a severe collapsed single-column card caused by nesting new section wrappers inside the pre-existing two-column Editor grid. Patched the Editor layout to use a full-width single-track outer grid and full-width cards, with CSS sizing regression assertions. Commit `467b980`; browser acceptance remains pending. No saved project data was changed.

**UX3 Windows feedback:** Owner confirmed the full-width layout hotfix was much better. Treat that as a visual layout pass, not a complete save/generation/mobile regression signoff.

**UX4.1 implementation checkpoint:** Added a compact Project Editor identity/save-status strip, using the existing `state.dirty` and actual save/clear transitions rather than a separate inferred save flag. Responsive styling and source regression assertions were added. Further UX4 mobile/keyboard navigation polish and full physical/CI acceptance are still pending. No automatic saves or changes to project serialization.

**Motion Lab generated-camera safety follow-up (2026-10-16):** Owner reported an automatically created `camera_3d.translation_x` schedule of +0.8 scene units/frame triggering render preflight on frame 6. The Motion Lab compiler already enforced configurable limits, but projects could raise those limits well above cautious render-safe values. Added an independent 0.08 scene-units/frame bound for *generated* X/Y/Z translation, respecting pre-existing hand-authored base camera schedules rather than silently rewriting them. Diagnostics report affected axes; regression tests cover raised limits and manual-base preservation. Already saved schedules are not automatically altered, and geometry/depth can still generate coverage warnings; use Camera Preview. CI and Windows physical acceptance pending. Commits `e0c7676`, `befff4e`.

**Motion Studio cue cleanup (2026-10-16):** Added checkbox multi-select to manually assigned camera/beat cues, Select All, Clear Selection, confirmed bulk deletion, Clear All and one-step Undo. Deletion modifies only unsaved cue state until Save Cues. Selection is reset on project audio reset. Frontend source assertions added; Windows verification and CI remain pending.\n\n**UX4.2 implementation checkpoint (2026-10-16):** Project Editor five-section navigation now supports Left/Right/Home/End keyboard keys with focused destination, exposes a compact mobile section picker at widths up to 600 CSS px, synchronizes selection and browser-persisted section state, and adds visible focus styling and source regression assertions. Uses existing editor section selection without implicit save or changes to project data. **CI and real mobile/Windows physical acceptance remain pending.**

**UX5 CI remediation verified (2026-10-16):** Fixed stale primary-navigation tests and browser VM harnesses for Motion Studio soundtrack attachment and cue-selection restoration. At source commit `25eafd2`, GitHub Actions **Syntax checks PASS**, **Backend tests PASS**, **Installer checks PASS**. UX5 still needs physical Windows/mobile/GPU regression acceptance and final public-doc review before release. See `docs/UX5_ACCEPTANCE_PLAN.md`.

**UX5 owner acceptance (2026-10-16): Windows PASS.** User reports successful combined test and supplied an exported H.264 832×1216 24-fps MP4 containing AAC audio (9.875 seconds). Frontend, Backend and Installer CI passed at `25eafd2`. Dedicated physical mobile acceptance and final public docs review are not yet independently verified. Continue planning P5 on `dev-webui`; no main merge authorized.

### UX3 implementation checkpoint (2026-10-16)

- [x] Add five directly navigable Project Editor sections: **Setup**, **Sources & Media**, **Timeline & Prompts**, **Camera & Motion**, **Generation Settings**.
- [x] Reparent the original card elements and preserve control IDs, input state and existing event listeners; keep the separate Motion Lab workspaces unchanged.
- [x] Remember section locally, provide mobile-friendly button wrapping and guard hidden groups in CSS.
- [x] Add source-level regression assertions for navigation and card preservation.
- [ ] Run frontend/backend CI on current `dev-webui` and physically test Windows and mobile/zoom layouts.
- [ ] Verify live editor load/save, switching sections with unsaved edits, prompt timeline, 2D/3D camera controls, cadence and rendering. **Not yet owner-accepted.**

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

### P4.4.4 Windows acceptance defect and repair, 2026-10-16

- Physical test on `D:\\Morphorum-test` downloaded the BtbN Windows x64
  release package but failed during encoder verification with
  `name 'subprocess' is not defined`. The new `_validate_encoders`
  function used `subprocess.run()` without importing the module.
  No managed installation was promoted from the failed staging directory.
- Fixed the missing `import subprocess` on `dev-webui`. Managed install
  transitions and errors now publish stage-specific Runtime Console events,
  including a bounded failure reason. They are emitted on stage changes rather
  than every download progress event to avoid Console spam.
- Added a Python regression explicitly checking the subprocess dependency
  and a failed background installation reaching the Runtime Console.
  **These tests still need a verified CI/pytest result.**
- **Windows retest passed, user-reported 2026-10-16:** The corrected managed
  FFmpeg installer completed successfully in `D:\\Morphorum-test`, and the
  user ran `scripts/ffmpeg_acceptance.py --mode managed` and reported all
  tests passing: MP4/H.264/AAC, WebM/VP9/Opus, FFprobe, hybrid frame
  extraction and MP3/OGG/FLAC conversion. The original import failure is
  resolved; other recovery, alternate-mode, Linux install and CI checks remain.

#### Outstanding P4.4 physical acceptance (must not mark complete before testing)

- [x] Windows managed installation and media acceptance (user-reported
  2026-10-16): install succeeded on `D:\\Morphorum-test`, and
  `scripts/ffmpeg_acceptance.py --mode managed` passed all checks.
  Restart persistence and lifecycle edge cases remain on the checklist.
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
