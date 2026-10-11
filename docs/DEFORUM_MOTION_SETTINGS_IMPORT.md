# Deforum Motion Studio / Deforum Settings Import

**Status:** approved design; implementation workstream `feature/deforum-motion-import`, independently based on `dev-audio` pause commit `66839acdecd40bb48fa6e9b4bfc6f63bf4c7a352`. The Windows-verified audio-motion checkpoint `checkpoint/audio-motion-director-da4-5-windows-verified-20261011` must not be changed. Do not merge to main/dev-ui without physical acceptance.

## Why
Deforum Motion Studio (chicodog530/Deforum-Motion-Studio) exports an ordinary JSON-encoded Deforum settings .txt. `motion.py:export_config` copies its initial Deforum config, overwrites `max_frames`, `fps` and six camera schedules (`translation_x/y/z`, `rotation_3d_x/y/z`), using error-bounded sparse keyframes. Optional `app.py:export` attaches `add_soundtrack='File'` and `soundtrack_path` pointing to a Windows host file. Original `diffusion_cadence` comes from its underlying config. Morphorum already parses those six schedules in `deforum_import.py`, but its existing user flow creates a **new project**. This feature must import **motion only into an existing project**, without changing model/prompt/seed or other unrelated settings.

## UX plan
1. Hide legacy Audio Motion from the sidebar and workspace tab buttons; retain its code, saved layers and ability to restore it later. New workspace: **Import Motion Settings** with link to the source repository.
2. Choose .txt/.json, parse without executing or trusting embedded paths, show six-axis colored curves and camera path, source FPS/frame count/cadence, duration and audio path basename. The source path is metadata only, never read on the server.
3. User chooses explicit mapping: replace current camera motion or stage as separate additive Motion Lab layer where safe. Clear diagnostics: imported frame count vs current, max 3000 supported, FPS mismatch, cadence mismatch, unsupported keys, coordinate units/signs.
4. Optional WAV upload through managed audio endpoint. Display waveform below motion curves, sync audio playhead with camera frame, offset slider with ± millisecond control; a constant offset aligns *soundtrack relative to motion* without mutating source motion. Persist the WAV association and offset in project-owned settings, preserve soundtrack mux.
5. Explicit review and confirmation before any mutation. Default **keep existing project FPS/frames/cadence**, refuse unsafe mismatch rather than silently retiming schedules. Optional **adopt source timing** only when safe (e.g. project has no preexisting layers, keyframes, recordings, incompatible render state). Otherwise offer a *new project* import workflow. Preview never modifies the active project; Apply only after confirmation, with conflict detection and explicit save.

## Compatibility/technical constraints
- Deforum 3D schedules are per-frame camera increments; do **not** reinterpret as cumulative absolute camera positions or copy unreviewed numbers from Deforum into native axes without visual/unit testing.
- No PNG/video/project files are loaded from embedded export paths. Validate JSON structure limits, schedule length, frame range, numeric finite values and expressions with existing `deforum_import` guards.
- Audio track length and project motion duration may differ; visualize mismatch, optionally trim/pad only with explicit choice. Preserve raw source timing in metadata.
- Existing project import route `/api/animation/import/deforum/create` is not suitable: it creates a new project. Add dedicated non-mutating preview and guarded apply endpoints for **existing project** only, reusing translation/validation code.
- Handle both DMS v0.3 Deforum export .txt and generic Deforum JSON, not `.dms.json` project session serialization.
- New importer work is distinct from paused DA4.6 Motion Director; do not delete or modify old layers in the checkpoint.
- Attribution: inspired by Deforum Motion Studio, authored by chicodog530; reuse export *format*, not unlicensed source code.

## Staged gates
- DMI1 importer backend: extraction + preview of motion-only data and metadata, duration/cadence mismatch report; hostile file/invalid schedule unit tests.
- DMI2 interactive motion visualization, settings file chooser, optional managed WAV and waveform, playhead and offset; browser physical acceptance.
- DMI3 guarded apply into existing project's camera tracks, restore/undo protections, explicit timing choice and soundtrack export; Windows render and synchronization gate.
- DMI4 documentation and polished responsive layout. Checkpoint after Windows confirmation.

## Safety
No default application or overwrite. Never silently retime projects. Model and generation configuration unchanged. Existing Motion Lab and motion-linked audio project data preserved. Do not merge without user approval.

## DMI1 backend increment (2026-10-11)

Implemented `backend/morphorum/deforum_motion_import.py` and read-only endpoint:
`POST /api/animation/projects/{project_id}/motion-import/preview`
with JSON body `{"content":"<the entire JSON .txt/.json file>","filename":"example.txt"}`.
Response: source timing (FPS, max_frames, duration), source cadence, safe soundtrack basename (never open referenced Windows host path), six-axis summaries, at most 241 downsampled numeric preview samples, project-timing comparisons, warnings and conservative `can_apply_unchanged`. The endpoint loads the specified project for comparison but never saves, applies, or changes it. Supports literal numeric `frame:(value)` keyframes exported by Deforum Motion Studio. Formula schedules are deliberately rejected in this motion-only path, and files are bounded by the existing 1 MiB Deforum parser. A full `.dms.json` session file is not supported; export **Export to Deforum** from your friend's app.

Regression file `tests/test_deforum_motion_import.py` covers six axes, frame interpolation, host path privacy, timing mismatches, source >3000 frames, unsafe expressions, malformed cadence, missing axes and side-effect-free preview.

**CI limitation:** existing GitHub Actions workflow triggers appear limited to `dev-audio`/other specified branches, so this new feature branch does not automatically produce workflow runs. Run locally:
`python -m pytest tests/test_deforum_motion_import.py -v` and `python -m pytest tests/test_deforum_import.py -v`. Do not claim CI green without run evidence.

DMI1 does not yet provide UI, WAV uploading, offset correction, timing adoption or project mutation. These remain DMI2/DMI3 work. Audio Motion navigation is deliberately still visible until replacement UI is ready, preventing a dead-end menu.
