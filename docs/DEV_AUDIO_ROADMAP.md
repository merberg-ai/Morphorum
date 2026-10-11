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
5. **DA4**: independently mapped kick→Depth Z, snare→roll; reusable non-returning Punch Zoom In/2D zoom step and balanced return envelope; millisecond attacks, travel cap and collision policy.
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
- DA4 (next after acceptance): independent kick/snare mappings including cumulative Punch Zoom, unit-safe bounds, render/preview integration and physically testable presets. Do not merge dev-audio until physical acceptance.
