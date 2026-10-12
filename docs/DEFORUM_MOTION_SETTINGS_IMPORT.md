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

## DMI2 browser workspace (physical test pending)

- Audio Motion's left sidebar and visible tab are replaced by **Import Motion Settings**. The legacy Audio Motion card, state and all underlying handlers remain mounted inside a hidden workspace to avoid removal/regression; historical saved `audio` tab preferences redirect to importer.
- The new page accepts a .txt/.json settings file and calls the read-only `POST /api/animation/projects/{project_id}/motion-import/preview` endpoint. Displays source/project FPS and frame counts, duration, cadence, warnings, axis selector and sampled camera velocity graph.
- The optional WAV picker provides a local-browser audio player, Web Audio decoded waveform overview, seek/playhead and adjustable audio-time offset. No WAV is uploaded or saved in DMI2. The external machine soundtrack path is never accessed.
- There is **no Apply button** yet. DMI2 never changes camera tracks, animation timings or project audio. DMI3 will add explicit guarded project apply and soundtrack integration.
- Frontend tests in `tests/frontend_deforum_motion_workspace.test.cjs` and navigation expectations cover the new entry and preserved legacy DOM. The physical desktop/mobile browser gate should test open 3D project, choose an exported DMS .txt, inspect graph for six axes, verify mismatch diagnostics, load a WAV, seek and adjust offset, confirm no project changes or upload, then test the mobile layout and original editor/preview.

## DMI2 follow-up: soundtrack path from exported Deforum settings (2026-10-11)

- Importer preview includes `source.soundtrack_path` from the JSON export, alongside `source.soundtrack_filename`. A path is metadata only: the server **does not access** the file or use it as an upload path.
- New **Referenced soundtrack path** display, **Copy path**, and **Copy folder** controls on the Import Motion Settings page. The copied folder can be pasted into the Windows file chooser's address bar.
- The browser's normal `<input type=file>` does not permit pre-setting a native file-picker directory from an arbitrary imported Windows pathname, for privacy/security reasons. No claim of automatic default-directory selection. If a future desktop/file-system integration provides an explicitly user-granted directory handle, it could optionally be used as a picker hint.
- File chooser now accepts WAV/MP3/OGG/FLAC where the browser supports decoding, because the user-supplied `deforum_motion_settings.txt` references `TEST_METAL.mp3`; all audio remains browser-local and preview-only.
- Regression tests assert source path metadata and UI controls. No WAV upload or project modification. The example export was inspected to verify `add_soundtrack=File`, `fps=24`, `max_frames=296`, `diffusion_cadence=3`, and the MP3 soundtrack reference.

## DMI3 guarded motion-only apply, first acceptance gate

Implementation: `prepare_motion_import` validates a copy of the existing 3D project after substituting six imported camera schedules; it **refuses** mismatched FPS, max frames, cadence, missing axes, projects with existing Motion Lab layers/applied snapshots, malformed numeric schedules or invalid project schedule validation. It leaves every other project field unchanged (model, prompts, seed, LoRAs, cadence, audio, generation controls).

- `POST /api/animation/projects/{project_id}/motion-import/prepare` performs read-only validation and returns the imported source's SHA-256 hash, a SHA-256 fingerprint of the current project, warnings and list of axes. It does not save.
- `POST /api/animation/projects/{project_id}/motion-import/apply` requires both hashes match the content and latest saved project; otherwise refuses stale source or intervening project changes. It saves via the canonical project API with `prefer_tracks=True` only when safe.
- The Import Motion Settings UI has **Review safe import** and **Apply camera motion** actions. The latter stays disabled until successful review and prompts an additional confirmation. Unsaved Editor changes must be saved or discarded before review.
- **Scope restriction**: This stage replaces six camera schedules only; it does NOT yet associate uploaded soundtrack/audio offset with the saved project. WAV/MP3 waveform and offset remain browser-local diagnostics. Cross-FPS resampling and timing adoption remain intentionally blocked.
- Regression tests cover non-mutating preparation, source/timing mismatch and existing Motion Lab guards, plus preview/apply frontend wiring.
- **Windows physical gate**: Use a fresh 3D test project with matching source FPS (24), max frames (296), cadence (3); test read-only review, apply with confirmation, Editor camera schedules, Motion Curves, short preview/render, save/reload. Confirm model, prompts, LoRAs and other configuration do not change; verify an existing Motion Lab project is correctly blocked, and FPS/cadence mismatch cannot apply. Avoid production projects until accepted. Confirm imported soundtrack path remains reference only.
- Next incremental DMI3 work, only after this gate: explicit project-owned soundtrack attachment and offset persistence/export, safe recovery/backups, additional compatibility/retiming options and finalized DMI4 polish.

## DMI3 continuation: theme integration, toasts, explicit soundtrack attachment

- Importer buttons now reuse Morphorum's `secondary-button compact` and `primary-button compact` CSS classes. Loading settings, reviewing import compatibility, applying camera schedules, previewing soundtrack, attaching soundtrack and saving an offset report progress/success/failure through the shared `toast()` system. Inline review/status text remains accessible.
- Added separate project-owned `imported_soundtrack` audio attachment service. WAV, MP3, OGG and FLAC are accepted when bounded to 40 MiB and their file signatures agree with their extension; file bytes are never interpreted from Deforum's embedded host pathname. A file digest names the stored object, and a small JSON sidecar records basename and numeric offset (-30..+30 s). Attachments and offset updates use atomic file replace and do not mutate the project camera or other settings.
- New endpoints: `GET /api/animation/projects/{project_id}/motion-import/soundtrack`, `POST /api/animation/projects/{project_id}/motion-import/soundtrack` (raw file with `X-Audio-Filename` and `X-Audio-Offset-Seconds` headers), and `PUT /api/animation/projects/{project_id}/motion-import/soundtrack-offset`.
- The **Attach selected audio to project** and **Save audio offset** buttons are explicitly separate from **Apply camera motion**. Merely choosing a file keeps it browser-local.
- **Historical gate note:** At this checkpoint the attachment was stored but was *not yet attached to a render manifest or muxed into finished video*. The following increment supersedes that limitation after the Windows attachment gate passed.
- Tests: `tests/test_imported_soundtrack.py`, `tests/frontend_deforum_motion_workspace.test.cjs`.
- **Physical Windows gate:** verify themed buttons in dark/light themes, toast feedback for successful/failed load/review/apply and audio attach, attach exported MP3 under 40 MiB, save a nonzero sync offset, verify sidecar survives reload (GET API). Confirm no change to imported camera schedules from soundtrack actions and no automatic audio export. Verify failing MIME signature, oversize and invalid offset are rejected. Stop before integrating the soundtrack into render output.


## DMI3 continuation: frozen soundtrack render/export integration

The Windows attachment/theme/toast persistence gate above passed on 2026-10-11 and is preserved at `checkpoint/deforum-motion-import-dmi3-soundtrack-attachment-windows-verified-20261011` (commit `3ba41e2db8932a11a7ab86097841020d1617ffa3`).

- When an animation render is submitted, any attached `imported_soundtrack` is checksum-verified and copied into that render directory. The render manifest freezes its basename, format, digest and synchronization offset. Replacing the project's attachment later does not retroactively change an existing render.
- MP4/WebM export selects the render-frozen imported soundtrack when present. Existing Motion Lab WAV export remains supported. A render containing both sources is rejected instead of silently choosing one.
- Offset semantics exactly match the importer preview: `audio_time = motion_time + offset`. Positive offsets trim/seek forward into the soundtrack at video time zero; negative offsets delay soundtrack playback. Audio is padded/truncated to the rendered video duration.
- Audio-bearing exports must use the original render FPS, preserving the existing Motion Lab synchronization rule.
- The importer UI now explains that attachment affects **new renders** only; existing renders keep their prior soundtrack snapshot.
- Regression coverage extends `tests/test_imported_soundtrack.py`, `tests/test_animation_render.py`, `tests/test_animation_video.py` and the importer frontend contract for immutable render snapshots, checksum protection, offset filters and dual-audio conflict refusal.

**Windows physical gate:** attach the imported soundtrack and a clearly nonzero offset, start a fresh animation render, then export both MP4 and WebM at original FPS. Confirm audio is present and offset direction matches the browser preview. Change/re-attach the project soundtrack after the render completes and confirm re-exporting that old render still uses its frozen original track. Also verify a render with Motion Lab audio plus an imported soundtrack is blocked at video export rather than choosing one. Stop before cross-FPS retiming, automatic duration fitting, recovery/undo expansion or DMI4 final polish.


## DMI3 camera unit compatibility (Windows preview gate pending)

Deforum's `anim_frame_warp_3d` applies a 1/200 translation scale and X/Z sign inversion. The earlier importer copied raw Deforum numbers directly into Morphorum's native 3D camera schedules, producing exaggerated camera motion. This increment adds a bounded, explicit conversion at **import preparation**, not inside the native renderer.

- Default `deforum` mode converts X=-X/200, Y=Y/200, Z=-Z/200. Rotation schedules remain in degrees without a unit conversion. This is a source-compatible starting point, not a promise of identical visual output because depth/projection differ.
- `raw` restores original legacy behavior for visual comparison. Separate translation and rotation strength controls accept 0..2 (100% is 1).
- Preparation displays converted schedules and gives the conversion options their own SHA-256 fingerprint. Apply checks that fingerprint, as well as existing source and project fingerprints; changing options requires another review. No non-camera project values are modified.
- Imported JSON is not rewritten. Re-select the same source file to experiment with different settings.
- **Physical gate:** use a disposable matching 3D project, compare a short camera preview with `deforum` 100%, `deforum` 50% translation, and legacy `raw` values. Verify translation direction, depth travel, and pitch/yaw/roll. Re-review after changing any strength. Do not assume perfect Deforum visual parity. Stop for acceptance before adjusting 3D projection geometry or merging.

