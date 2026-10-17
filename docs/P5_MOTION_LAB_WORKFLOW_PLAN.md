# P5 · Motion Lab Workflow Clarity

**Branch:** `dev-webui`  
**Status:** P5.1 initial frontend implementation committed on `dev-webui`; Windows physical acceptance and CI pending. P5.2–P5.5 remain planned.  
**Prerequisite:** UX5 Windows/GPU owner acceptance and green Syntax, Backend, Installer CI completed. Dedicated mobile physical testing explicitly deferred by owner and is not a P5 start blocker.  
**Safety:** No merge to `main` without owner approval. Never silently save, overwrite, delete, or replace projects, original audio, generated PNGs, or exported videos.

## Goal

Make the path from an opened project to camera preview, applied camera tracks, full animation render, and soundtrack-inclusive video export understandable without hunting between workspaces. Preserve the existing Motion Studio five-stage workflow and Project Editor's five sections; build on their original controls rather than duplicate them.

## P5.1 · Project and motion summary

- Introduce a compact read-only project summary visible from Motion Lab Overview, with project name, render dimensions, FPS, frame count/duration, 2D/3D mode, selected model and save/dirty state.
- Clearly distinguish saved camera schedules, unapplied Motion Lab draft layers, and currently loaded/analyzed audio cues.
- Surface attached export soundtrack filename and synchronization offset separately from Motion Studio's analyzed WAV.
- Add direct links to the existing Project Editor, Motion Studio, Camera Preview, and Render Monitor screens, preserving state.

**Acceptance:** The summary refreshes on project switch/save/apply and never claims a draft is applied or unsaved settings persisted.

## P5.2 · Preview / Apply / Render clarity

- Make **Preview** (temporary inspection), **Apply** (persist or stage real camera changes as currently defined), **Save Project**, **Render Animation**, and **Export Video** visually and verbally distinct.
- Display the precise project, source audio, layer count, camera track origin, and potential unsaved edits before operations that change schedules.
- Provide actionable disabled/loading/error states and return-to-step navigation; avoid duplicating action handlers or bypassing the existing conflict confirmations.
- Retain existing camera safety checks; distinguish gentle generated motion bounds from manually authored keyframes. Do not silently rewrite hand-edited tracks.

**Acceptance:** A user can move from saved cues to preview, apply, save, render, and export without losing drafts or accidentally rendering an older camera schedule.

## P5.3 · Soundtrack reuse and export provenance

- Prefer the attached **single active project soundtrack** when entering Motion Studio, while preserving an explicitly chosen analyzed WAV and any unsaved beat/cue edits.
- Display which audio source drives motion analysis versus which soundtrack is frozen into the render and ultimately muxed into MP4.
- Warn clearly when source differs, audio attachment fails, the render predates attachment, or a silent render cannot inherit newly attached audio.
- Preserve historical analyzed WAV assets; replacing the active soundtrack requires deliberate confirmation. Never delete media automatically.
- Surface exported-video audio inclusion based on actual export metadata, not assumptions.

**Acceptance:** A fresh test render exports MP4 with audio, existing render snapshots stay unchanged, and users can tell why an older export is silent.

## P5.4 · Units, cues, and navigation consistency

- Consistently label scene units/frame, degrees/frame, seconds, FPS, offsets, and slider meaning across camera and audio authoring.
- Keep Motion Studio's beat-assignment selection / bulk-delete / undo and Project Editor navigation reachable without excessive backtracking.
- Tighten context labels, next-action links, focus order, keyboard support, 200% zoom and responsive behavior using the existing CSS architecture.
- Keep errors and warnings next to their relevant controls, with explicit recovery guidance.

**Acceptance:** The UX uses consistent units and never leaves a user guessing whether an edit changes a draft, the project, the preview or the export.

## P5.5 · Verification and closeout

- Add focused frontend behavior tests, backend assertions only where behavior changes, and documentation updates for each phase.
- Run Syntax, Backend and Installer GitHub Actions after integration; fix regressions before owner signoff.
- Owner Windows/GPU smoke: open project → inspect summary → analyze/reuse audio → assign/edit cues → preview → apply → save → render → export → inspect audio inclusion.
- Record mobile-specific physical acceptance as **Deferred by owner**, not PASS. Avoid treating desktop resizing as a substitute.
- Update public documentation after owner Windows acceptance; P5 release or merge still requires separate authorization.

## Suggested sequence

P5.1 → Windows checkpoint → P5.2 → Windows checkpoint → P5.3 → Windows checkpoint → P5.4 → combined P5.5 regression. Keep commits small and reversible; `main` remains unchanged.

## P5.1 implementation checkpoint (2026-10-16)

- Added a read-only Motion Lab Overview grid for current project, Editor save state, live dimensions/FPS/frames/duration, motion mode, checkpoint, and count of unapplied draft layers.
- Added existing navigation shortcuts to Project Editor, Motion Studio, Camera Preview and Render Monitor. No project serialization, render API, applied schedules, or audio files were changed.
- Soundtrack and analyzed WAV provenance are **not yet independently verified** by the overview. P5.3 will connect precise active-soundtrack and analyzed-WAV metadata rather than infer it from draft asset paths.
- Browser/Windows, CI, keyboard, zoom and project-switch acceptance remain pending. Do not mark P5.1 accepted based on source changes alone.
