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
- [ ] P1.5: Streamline tool navigation without duplicating existing controls.
- [x] P1.6: Reusable contextual help (?) for selected Editor/Composer controls, saved Appearance toggle, keyboard/touch support; future passes broaden coverage.

## P6 early safety

- [x] Optional depth-service discovery failures no longer prevent project loading.
- [ ] Add last-successful projected-coverage and resolved camera diagnostics to 3D warp failure messages.

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
