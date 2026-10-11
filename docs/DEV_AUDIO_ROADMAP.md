# DA1 audio sync development plan

Development branch: `dev-audio` (created from `main`). Do not merge until Windows physical acceptance. `main` and `dev-ui` remain untouched.

## DA1.1 implemented: timestamped spectral attack candidates

- `backend/morphorum/audio_events.py` analyzes normalized mono or stereo PCM without referring to project FPS.
- STFT hop defaults to approximately 5 ms; separately detects positive spectral flux in low-frequency kick, mid-frequency snare and high-frequency bands.
- Emits deterministic timestamps, source-sample indices, strength and candidate labels; these **are not** source-separated or guaranteed instrument classifications.
- `event_frame_index` projects preserved timestamps onto a selected frame rate without changing event times.
- Input guardrails: normalized finite PCM, 8–192 kHz, mono/stereo, bounded duration and event count.
- `tests/test_audio_events.py` exercises synthetic kick/snare transients, stereo, silence, malformed PCM, deterministic results and FPS reassignment.

This is a **backend foundation only**, not wired into the audio upload endpoint, Motion Lab UI, persisted audio layers, or rendering. Existing ML3 audio controls remain unchanged.

## Next steps and gates

1. **DA1.1 acceptance**: CI and local signal tests, then evaluate real heavy-metal stems/recordings. Tune timing accuracy and threshold, and establish ground-truth evaluation fixtures before claiming drum classification.
2. **DA1.2**: analyze WAV at high resolution, return versioned source-hashed events alongside existing envelopes; optional audio-length and FPS recommendation (12/24/30/60) with preview. Existing layers/recordings/keyframes must be guarded against silent retiming.
3. **DA2**: downsampled separate L/R waveform overview and zoomable detailed slices, event overlays, playhead and audio-clock synchronization; device pixel ratio and mobile testing.
4. **DA3**: edit/disable/add/move detected hits, optional BPM grid, deterministic persistence with source analysis version and manual override layer.
5. **DA4: Audio Motion Director**: motion cues first, separate from event detection; staged cue model, six-axis presets, optional Find Beats/bulk assignment, deterministic native Motion Lab compilation and physical acceptance.
6. **DA5**: tune heavy-metal double-bass and snare candidates against recordings; optional stem separation only after testing CPU methods.
7. **DA6**: integration tests, 30 FPS render, soundtrack mux and Windows RTX 4080 SUPER physical gate.

Do not modify `main` or `dev-ui`. Stop before merging.
## DA1.2 API increment implemented (not yet physically accepted)

The existing project WAV analysis endpoint now adds `analysis.events` with high-resolution candidate hit timestamps (seconds and original sample index), label and strength. The original `values` and `bands` remain intact for legacy audio-motion UI and rendering. An `analysis.fps_recommendations` object lists duration-matched frame counts for 12/24/30/60 FPS and indicates which respect the 3000-frame limit. This is a **proposal only**: FPS and max_frames are never changed by analysis, because recorded/keyframed content may be invalidated by retiming. A future UI must require explicit confirmation and reject/retime existing motion safely. Unit tests exercise the API helper and WAV analysis.

**Gate:** verify backend tests and that old audio motion still behaves as before. A Windows WAV analysis response should contain events and recommendations. Stereo waveform and user-facing FPS selection come in DA2 / UI wiring.

## DA3.2 marker persistence (Windows physical testing pending)

- Project-owned `motion_lab_audio/<source_sha256>.markers.json` stores explicitly saved marker edits separately from immutable detector outputs. Schema version 1, strict validation, bounded events, duration and source hash.
- `GET /api/animation/projects/{id}/motion-lab/audio-markers/{sha256}` returns saved edits or null; `PUT /api/animation/projects/{id}/motion-lab/audio-markers` validates ownership of the referenced WAV and atomically saves.
- The Audio Motion marker editor now has **Save marker edits**. Re-analyzing the same WAV for the same project restores saved edits. Switching to a different WAV does not import old markers. Re-open the project and reselect/reanalyze the WAV to restore them; audio is still selected with the browser file picker.
- Edits do not affect the existing composer, native camera tracks or output rendering. Re-analysis creates the detector baseline, and Reset returns to that baseline locally until Save is clicked.
- **Windows acceptance:** change/disable/add markers, Save, reload/reopen and reanalyze same WAV; confirm edits restore. Reanalyze a different WAV and confirm marker sets do not mix. Test Reset + Save, missing marker sidecar, mobile editing, normal Pulse & Return audio layers and MP4 soundtrack export. No main/dev-ui merge.

## DA3.3 integrated editing workspace (browser acceptance pending)

- DA3.3a: Audio source, beat detection and camera-response fields are reparented into accessible accordion groups. The timeline and inspector share the full-width analysis workspace.
- DA3.3b: The interactive timeline defaults to the frame-aligned envelope with editable markers; display selector switches between Envelope, Stereo and Both. Former standalone envelope plot is retained as optional diagnostics.
- DA3.3c: Marker inspector adds bounded in-memory undo/redo (60 steps). Selected markers can be nudged by 10ms with arrow keys or by a frame with Shift+arrow; Delete removes; Ctrl/Cmd+Z and Ctrl/Cmd+Y act when waveform is keyboard-focused. Pointer drag allows moving marker timing while zoomed. Existing explicit Save marker edits persists source-hashed sidecar. Editing never modifies rendered camera tracks.
- **Physical acceptance before DA4:** analyze the existing stereo heavy-metal WAV; confirm envelope is visible immediately despite collapsed diagnostics; stereo/both modes and frame threshold display; scroll/seek/follow; selecting vs seeking; dragging markers in zoom; keyboard undo/redo and fine nudges; Save + reload; responsive Windows desktop and mobile touch browser. Verify existing Motion Lab audio layers and exported audio.
- **DA4 replaces the old direct kick-to-axis plan:** cue-first choreography, with explicit user-assigned motion at song moments; detection is an optional source for cues, not a prerequisite.

## DA4 replacement: Audio Motion Director (approved 2026-10-11)

**User experience acceptance criterion:** load a WAV; seek to a guitar riff's first note and assign **Push Zoom In** without running analysis; locate a kick drum later and assign **Roll Right → Left**; hear audio and preview the two movements together; edit, save, reopen, then render with the existing synchronized soundtrack. Basic authoring must not expose FFT, spectral thresholds, envelopes or manual axis schedules.

### Separation of concerns
- **Audio source**: project-owned WAV with SHA-256 and exact duration. File import/playback/display alone must work without event detection.
- **Audio events**: timestamped, source-bound kick/snare/highs or manual beat markers. Existing detector and `.markers.json` sidecar remain intact and optional. Events mean only "something happened in the audio."
- **Motion cues**: user-owned, project-persisted, source-bound choreography objects: ID, timestamp in seconds, preset, intensity, duration, interpolation/easing, target axes, enabled flag; **manual cue trigger is independent of any detector event**, while optional source_event_id links detector/bulk cues. Multiple cues may trigger simultaneously. Cue times are canonical seconds; frame mapping happens only when compiling.
- **Native compilation**: deterministically turn cue schedules into native six-axis Motion Lab frame motion. Preserve existing base motion/recording layers, additive composition, axis limits, 3000-frame project bound, audio sync and export behavior. Differentiate returning *position offsets* from cumulative forward travel; avoid per-frame drift or surprise return for Punch Zoom In.

### Implementation phases and gates
1. **DA4.1: Cue schema and persistence**. Build versioned validation and project-scoped, source-hashed cue store; support manual cues even when there are zero detected hits; CRUD, ordering and undo-safe transactions; enforce allowed preset names, safe intensity/duration and consistent FPS projection; separate cue data from event sidecars. No renderer change. Test source mismatch, timing bounds, duplicate IDs and backward compatibility.
2. **DA4.2: Cue-first editor UI**. Replace the busy front page with Load WAV / Play / Add Motion Cue / Preview. Large audio timeline with separate colored motion tracks. Selected cue inspector adjacent to timeline. Preset-first controls rather than filter-first controls. Keep existing detector and low-level controls behind **Find Beats** and **Advanced**. Windows and touch testing before modifying rendering.
3. **DA4.3: Presets and timeline editing**. Implement **Push Zoom In (non-returning Z travel)**, **Roll Right → Left**, **Push & Return**, **Roll Left → Right**, **Dolly Out**, **Shake**, **Ripple**, and optionally **Reveal Drift/Fly-through**. Parameterized amplitude, attack, hold, release, ease, axis sign and offset, plus cue overlapping behavior. Drag, split/duplicate, undo/redo, keyboard and touch cue editing; test cue frame conversion at 12/24/30/60 FPS.
4. **DA4.4: Find Beats and bulk assignment**. Optional kick/snare/highs detection, confidence/sensitivity/min-gap, event selection by song range, assign one preset to selected events or alternating presets (every other kick); preview candidates before applying. Preserve raw detections vs user edits; evaluate false triggers and dense double-bass. No requirement for source separation.
5. **DA4.5: Native Motion Lab integration**. Compile cues into six-axis schedules, layer over base movement, support concurrent cues and bounded additive behavior; sync playback and preview; preserve source hash and deterministic output, soundtrack mux and existing legacy audio layers. Include numerical limits, collision/overlap policy and comprehensive CPU tests.
6. **DA4.6: Windows physical acceptance and checkpoint**. Desktop + mobile interaction, audio seek/zoom/drag, two manual cues example, repeated beats, long projects, undo/save/reopen, preview/native generated video with audio, verify no regression to old ML3 and DA1-3 behavior. Checkpoint on `dev-audio` only after tests. No merge without explicit go-ahead.

### Deforum Motion Studio 0.3 comparison, source: github.com/chicodog530/Deforum-Motion-Studio
Inspected upstream `main` on 2026-10-11 (README, motion.py, controller.py, app.py and requirements). Useful transferable **concepts**, reimplement originally against Morphorum interfaces:
- Independent Bass/Snare/Crash sound channels with distinct frequency bands, min gap, timing offset, axis, attack/return and active time range; channels can overlap.
- Filtered RMS at ~100 Hz after bandpass, robust percentile-based normalization, `find_peaks` with prominence/min-distance; compare against Morphorum spectral-flux candidate detection under real test tracks, use user-visible confidence and manual correction.
- **Ripple** decaying oscillation response, **Reveal drift** and **Fly-through** preset concepts.
- Returning pulse is an offset from underlying camera path; apply additive overlap with safety-aware per-axis limits instead of resetting absolute movement; cached PCM reanalysis avoids repeated decoding when changing bands.
- Shared original audio source should remain unchanged. Upstream uses ffmpeg for decoding; Morphorum currently accepts managed WAV, so wider codec support is a separate opt-in dependency/design decision, not a silent change.
- Morphorum differs architecturally: web/mobile UI, project-scoped managed files, native six-axis velocities and render pipeline. Do **not** transplant Tkinter GUI/Deforum export or treat Deforum numeric amplitude as compatible with Morphorum native units.
- Upstream repo has **no declared GitHub license / LICENSE file** as of inspection; friend has granted informal permission as reported by user. Avoid verbatim source copying unless permission terms and attribution are documented for Morphorum's Unlicense repository. Prefer independently implemented ideas and attribute the inspiration in documentation.

**Roadmap supersedes** DA4 direct frequency→axis and unifies DA5 tuning and DA6 render checks under DA4.4-DA4.6. Preserve all prior DA1-DA3 code and test gates. Do not change `main` or `dev-ui`.

### DA4.1 initial backend increment committed (CI/Windows gate pending)

`backend/morphorum/audio_motion_cues.py` implements bounded source-bound motion cue validation, chronological ordering, explicit preset and easing identifiers, cue timestamps in seconds and atomic project-sidecar saving under `motion_lab_audio/<sha256>.cues.json`. New project-scoped read/save API endpoints in `app.py` and `tests/test_audio_motion_cues.py` cover no-detection manual cues, concurrent triggers, invalid source/cue fields and FPS mapping. This is **backend-only groundwork**; no editor UI, preset compilation, frame scheduling or renderer changes have been made in DA4.1 yet. The next task is to run CI, resolve any failure, then add the cue-first editor and controlled Windows test gate.

### DA4.2 first browser acceptance gate (2026-10-11)

The Audio Motion workspace now adds a **Camera motion cues** inspector below the waveform. Manually add a cue at the current audio playhead, choose one of the DA4 preset identifiers, edit its start time/duration/intensity/easing/enabled fields, delete, select from the cue list or select cue rectangles on the waveform, and explicitly Save cues to the source-hashed project sidecar. Reloading and re-analyzing the same managed WAV fetches saved cues. Detection events and marker overrides remain separate.

**Important scope:** This is a cue *authoring and persistence* UI, not yet a motion compositor. No DA4 preset waveform render, native Motion Lab compilation, synchronized camera preview or output integration exists yet. The WAV import currently still uses the original Analyze WAV workflow for the audio waveform; authoring cues does not require selecting or accepting a detected hit. A later DA4.2 polish pass should simplify WAV import and expose a cue-first workspace without detector terminology.

**Windows/browser test stop:** verify Add cue at playhead for riff, pick Push Zoom In, edit values, add Roll Right → Left later, click/select colored cues, Save; restart/reselect/re-analyze same WAV and verify both survive. Test a different WAV, invalid values, deleting a cue and saving, mobile layout and existing event marker workflow. Do not advance to DA4.3/4.5 before this browser gate passes; it needs real pointer/browser testing. Keep `main`/`dev-ui` unchanged.

### DA4.3 preset mathematics and marker cleanup increment

- Added `backend/morphorum/audio_motion_presets.py` containing deterministic, frame-aligned *isolated* native motion increments for all nine cue identifiers. Supported movements include non-returning `push_zoom_in`, `dolly_out`, balanced `push_return`, two signed roll oscillations, damped shake/ripple and Reveal Drift/Fly-through. Motion amplitudes derive from Morphorum native per-frame axis scales, not upstream Deforum values.
- Added `tests/test_audio_motion_presets.py` verifying finite six-axis arrays, cumulative direction of pushes, near-zero total for returning cues, overlapping cue additivity and 12/24/30/60 FPS projection. These curves are **not yet connected to preview or renderer**, which is deliberately held for DA4.5.
- Added **Clear all detected markers** to the event editor. Clears detected events while preserving manually authored `manual-` markers and every camera-motion cue; participates in existing Undo and explicit Save Marker Edits, and Reset Detections still restores detector baseline.
- Next: verify backend tests and user browser behavior of Clear All Detected Markers. Build DA4.4 optional Find Beats / bulk assignment and DA4.5 bounded native integration only after this is checked. The first true motion preview/render physical test is DA4.5.

### DA4.4 optional Find Beats implementation (physical testing pending)

A collapsed **Find Beats · Optional batch cues** panel inside Camera Motion Cues filters previously analyzed/edited events by kind (kick/snare/highs), minimum normalized strength, cooldown/minimum gap, song start/end time and every Nth hit. **Preview matches** marks candidate hits with green dots on the waveform. **Assign cues to matches** creates source_event_id-bound camera cues with user-selected preset or alternating right/left rolls. Existing matching event+preset pairs are skipped, cue count is bounded to 3000, and **Undo batch** restores the cue list from before the last batch assignment. **Save cues** explicitly persists additions; manual cues are not removed. Cleared detector markers are excluded, while manual markers remain eligible when selected by type. Saved marker corrections are rehydrated with original detector confidence/provenance so sensitivity remains meaningful after reload. No native camera compilation/render code changed. Current filtering operates on existing uploaded WAV analysis; DA4.5 remains a separate preview/render integration gate.

**Windows test:** analyze music, preview kick candidates and green highlight dots; restrict a range; alternate rolls on every other kick; assign, undo, reassign and Save; reload and verify cue list. Clear detected markers and confirm zero auto candidates but manual markers remain. Test snare/highs, invalid ranges, long audio, click/select cue lane and mobile layout. Do not merge or advance to DA4.5 until the browser test passes.

### DA4.5 native camera integration (Windows GPU/browser acceptance pending)

- New `type:"audio_cues"` Motion Lab layer normalizes a *source-matched*, versioned cue document and compiles the cue preset curves to deterministic, six-axis per-frame increments. Only additive blending is permitted; regular Motion Lab per-axis safety limits and hand-edited-track conflict policy still apply. Other preset, recording and legacy audio layers retain their existing semantics.
- Audio Motion Director now provides **Preview camera cues** and **Apply camera cues** buttons. The cues must be explicitly saved before either action; Preview stages/replaces a single source-keyed layer in the draft and calls existing Motion Lab preview and synchronized frame player; Apply confirms then uses existing rebase/save safeguards. Saving a cue sidecar alone never modifies the camera.
- Existing Motion Lab layer UI recognizes the Director layer, offers navigation back to the Audio tab instead of misleading preset editing, and permits toggling/removal/reordering like ordinary layers.
- Integration tests in `tests/test_audio_director_integration.py` check native motion compilation, forward-only zoom, balanced roll, additive existing preset, deterministic reapply, project serialization, source hash and replace guardrails, and changed-track conflict protection.
- **Required Windows gate before DA4.6**: open 3D animation and WAV, create/save Push Zoom In at first guitar riff and Roll Right → Left on later kick; press Preview and confirm actual six-axis motion and synchronized audio; inspect Curves, make sure existing layers remain; Apply and inspect Editor schedules, render a brief sequence with audio and confirm movement direction and net forward travel; reapply and verify no doubled motion; test cancel/rebase conflict, disabled cues, clipping warnings, saved/reopened project, and other existing audio layers. Verify no preview/runtime or export regressions. Do not merge to main or dev-ui until user acceptance.
