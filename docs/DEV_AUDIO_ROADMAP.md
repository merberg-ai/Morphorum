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