# WebUI polish plan (dev-webui)

Working development backlog for the next Morphorum polish cycle.
Keep main unchanged until automated checks and physical Windows/browser
acceptance are complete. Preserve projects, models, settings, outputs and
render behavior.

| Pass | Scope | Acceptance |
| --- | --- | --- |
| P1 | Editor empty states, disabled-control guidance, current project and last-opened restore, navigation, context-sensitive help | Users can unlock Editor without guessing; help works on touch, mouse and keyboard |
| P2 | Live model index updates, compatibility, generation help, pre-render checks, 3D camera-motion warnings | New models appear without refreshing; warnings never silently change schedules |
| P3 | Responsive layout, controls, overflow, themes and accessibility | Verified from 360–1440 CSS px plus enlarged scaling |
| P4 | Progress, feedback, toasts, loading state and actionable errors | Every operation signals its state and identifies failures clearly |
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
