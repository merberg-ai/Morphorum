# Morphorum Motion Lab — implementation roadmap

**Status:** ML0, ML1a, ML1b and the ML1b smoothing/checkbox polish physically accepted on Windows (2026-10-09). Latest protected checkpoint remains `checkpoint/motion-lab-ml1b-smoothing-windows-verified-20261009` at `c0e5f90a692e14e32b48155f71d0a8afc923c6ae`. **ML2.0–ML2.2 are now implemented on `feature/motion-lab` and awaiting Windows/phone physical acceptance; they are not checkpointed or merged.** The ML2 code candidate before documentation updates is `47b614f10993cfae0eb249b94ee94b932d693149`, with Syntax and Backend CI green. ML3 audio is not implemented.
**Branch:** `feature/motion-lab`
**Branch base:** `dev-ui` at `bc40d18d4f5968904afedc798ecd3efdef71761a` (B6.3.2 physical acceptance)
**Existing paused separate work:** `feature/b6-3-3-hybrid-masks` at `c0e9be0aa03472747ba4c2594c128bdcd80318ef`. Do not touch that branch.
**Inspiration:** `chicodog530/Deforum-Motion-Studio` (reviewed version 0.2 of 2026-10-09).
**Review:** user design agreement, short Windows physical tests at each phase, CI gates, then merge to `dev-ui`.

## Goal and integration rule

Build a dedicated **Motion Lab** workspace within Morphorum's existing Animation Studio. Allow creative 2D/3D camera movement using preset motion paths, responsive camera preview, mouse/touch/controller recording, and audio-reactive modulation, while keeping exactly **one authoritative Morphorum renderer**.

Motion Lab is a motion *authoring/composition* tool. It must not launch a second independent diffusion engine, copy the standalone Tk GUI, or replace Morphorum's timeline, motion preview, depth warp, LoRA scheduling, or hybrid-video generation.

The friend's project supplies **behavioral inspiration**: six-axis motion controls, Still/Gentle drift/Wave/Spiral/Figure eight/Rocking/Push/Pull presets, explicit layer add/replace, travel, constrained bass pulses, interactive recording, speed/limits, undo, and Deforum settings export. The friend’s README reports calibrated **flat-depth** geometry preview and 20 automated tests; it does **not** reproduce changing depth maps, AI regeneration, cadence or final video. Morphorum already handles depth-aware warp and diffusion and should use its own existing preview and renderer.

**Source authorization:** The Morphorum maintainer reports that the author of `chicodog530/Deforum-Motion-Studio` gave permission to reuse **any and all of his code** in this project. Reusing adapted source is therefore within the owner's stated authorization, but the public upstream repo still has no formal license declaration. Before publishing copied code under Morphorum's Unlicense, get a short written confirmation that the permission expressly includes redistribution, modification, and release under Unlicense (or ask the author to add an appropriate public license). Retain clear upstream credit and review any third-party material separately. Prefer integrating its tested algorithms, not its independent Tk GUI or parallel rendering system.

## Existing Morphorum extension points (verified against dev-ui)

- `animation_projects.py`: project schema v2; legacy `motion`, `camera_3d`, `tracks`, animation FPS/dimensions.
- `animation_timeline.py`: canonical keyframed 2D and 3D track descriptors and legacy schedule bridge.
- `animation_resolution.py`: one resolved per-frame contract containing `motion`, `camera_3d`, prompts, LoRAs, generation and cadence.
- `animation_motion.py`: 2D sequential camera preview and B5.3 CPU depth-aware 3D motion preview. Current 3D preview caps at 180 frames; do not claim AI/cadence equivalence.
- `animation_3d.py`: actual depth reprojection in **Morphorum scene units**, 3D XYZ rotation and FOV.
- `animation_render.py`: SDXL/Flux/Z-Image animation loop and temporal/cadence motion, unaffected when Motion Lab not applied.
- `frontend/dist/index.html`, `assets/animation.js`, `assets/animation.css`: Animation Editor/Monitor/Media/Outputs workspace navigation and visual timeline.

**Critical parity issue:** Standalone Motion Studio defines per-frame six-axis velocities in its *own* units, converting translation to a flat-depth camera using a 1/200 scale, default FOV 70 and different projection settings. Morphorum uses real pseudo-depth scene units and default FOV 40, while 2D zoom is a *multiplicative per-frame scale*. Never assume the standalone values can be pasted 1:1 into Morphorum. Define sign, axis, units, frame-relative vs absolute semantics; calibrate using a small reference grid, actual Morphorum frame resolution and 2D/3D tests. Build conversion or separate carefully tuned Morphorum-native preset strengths.

## Proposed UX

A prominent **Motion Lab** workspace tab inside Animation Studio (Editor / Motion Lab / Monitor / Outputs). The unfinished Media (hybrid-video import/extract) workspace is intentionally hidden **only on this feature branch** while B6.3.3 is paused. Its DOM, API, data, extraction and saved hybrid project settings are preserved and can be restored later without migration. MP4/WebM video export remains visible in Outputs. The working CPU-only Camera Motion Preview has been moved from Editor into Motion Lab, with navigation shortcuts back to 3D Camera Schedules and Visual Timeline.

**Desktop**
- Left: preset library, range/strength/cycle/fade, mode Add/Replace, travel and limits.
- Center: fast virtual 3D camera/grid/path preview, optionally image-backed; play, seek, loop and comparison of prior/effective motion.
- Bottom/right: six-axis curves, keyframe overlays, per-layer list (base timeline, presets, recorded take, audio-reactive layer), undo/redo, Commit to Timeline.
- Clear status showing which motion is **draft** and which was last **applied** to the render.

**Mobile**
- Stacked preset/preview/curves tabs, scrubber and two thumb joysticks with Z/roll controls, safe touch targets, no hover-only actions or wide modal dialogs.
- Same project-saved motion layers and preview result as desktop.
- Preview must fit portrait phone without overflowing existing header or animation navigation.

**Export/undo**
- Project saves motion authoring layers, options, imported/audio assets through the existing save/reopen flow.
- `Apply to Animation` is an explicit, undoable change to existing camera schedules/tracks. Do not silently rewrite hand-authored schedules on opening or editing a Motion Lab preset.
- Optional Deforum schedule export and preset JSON export after format/calibration tests.

## Single, deterministic six-axis motion contract

Canonical motion data for each frame (relative movement, **not global camera position**):

```json
{
  "frame": 42,
  "translation_x": 0.0,
  "translation_y": 0.0,
  "translation_z": 0.0,
  "rotation_x": 0.0,
  "rotation_y": 0.0,
  "rotation_z": 0.0
}
```

Each layer stores:
- `id`, `type` (`preset`, `recording`, later `audio`), `enabled`, `blend` (`add`/`replace`), `start_frame`/`end_frame`, allowed axes, versioned parameters, and an optional per-axis recorded-take series.
- Stable `fps`, frame count, frame zero still-by-default and explicit behavior when retiming.
- Presets/recordings/audio remain independently editable, with a deterministic composer:

```
authored base motion tracks
    + enabled preset layers (range/fades; additive or selected-axis replace)
    + controller/mouse/touch recorded take
    + continuous travel
    + audio position-derived *returning* pulses (future phase)
    -> per-axis limits + smoothness validation
    -> composed six-axis frame values + diagnostics
    -> existing Morphorum 3D/2D track schedules through explicit Apply
    -> existing resolver, motion preview, img2img, cadence, LoRAs, export
```

Maintain a clear distinction between **base source tracks** and **last compiled/applied tracks** so re-applying layers never doubles additive motion. Persist a baseline version/hash and warn on conflicts when timeline tracks have been edited since the last Apply; provide preserve/overwrite choices.

Initially **compile/bake** to canonical native camera tracks via the existing schedule bridge, not a parallel render-time motion resolver. Preserve frame-by-frame values for high-frequency recordings; compress flat segments and keyframes only with an error-bound; never turn a wave/pulse into an inaccurate 2-keyframe approximation. Subsequent enhancement may support lazy per-frame layer resolution when long schedules become unwieldy.

For 2D projects: start with a 3D camera lab and a clearly disabled/limited 2D mode. Define explicit 2D translation/angle/zoom mapping later. Never treat 3D Z as interchangeable with 2D multiplicative zoom.

## Delivery phases and acceptance gates

### ML0: Architectural foundation and six-axis composer (implemented, Windows acceptance pending)

- Define versioned Motion Lab project sub-schema and non-destructive migration; default `enabled:false`.
- Pure deterministic preset series generator in **Morphorum native units**; support Still, Drift, Wave, Spiral, Figure Eight, Rocking, Push, Pull.
- Numeric range/fade/cycle/strength, signed travel, Add/Replace layer combination, per-axis limits and warnings.
- Map output through native 3D camera schedules with explicit Apply, preserving FOV, generation, cadence, prompts, LoRAs, depth/hybrid settings.
- Unit tests for frame-zero identity, preset timing, layer order, rotation/sign/units, value clipping and no-regression save/reopen.
- **Gate:** Backend/Syntax CI and short 2D/3D frame-resolution parity tests. No new interface required before passing.

### ML1: Motion Lab UI, layer curves, preview

- Add Motion Lab tab; responsive desktop/mobile preset controls, layer enable/order/edit/undo/redo, six-axis graphs, seek/play.
- Browser-rendered geometric camera/grid preview for immediate feedback; mark **geometric preview** (no diffusion or depth).
- Reuse existing CPU depth-aware Motion Preview when user explicitly requests an image/depth-based test. Do not block every slider change on CPU depth estimation.
- Show uncommitted draft vs committed timeline; apply and return to Visual Timeline.
- **Gate:** desktop and phone acceptance of presets, preview, save/reopen, stable existing UI. Validate resolution/FOV/coordinate behavior.

### ML1a: Frame-accurate curves, geometric path and editable layers (implemented; physical test pending)

- New `motion-lab-visual.js` uses the existing ML0 draft preview API to draw six native camera-velocity curves and integrated geometric translation path in the browser. The path is **auto-fitted and approximate**, not a diffusion/depth/FOV preview.
- `compile_motion_lab(include_series=True)` returns full bounded `[0..max_frames-1]` six-axis samples, matching the native `resolve_project_frame` output and preserving the same clipping/seed behavior. Only draft preview requests the series; Apply remains light.
- In-workspace **Update Curves** compiles the current draft without starting expensive CPU depth estimation; **Preview Draft Motion** still invokes the existing real CPU depth-aware Motion Preview as needed.
- Frame scrubber, pointer/keyboard scrubbing, play/pause and loop at project FPS update six-axis values and path marker. No independent render engine and no GPU model load.
- Draft stack supports enable/disable, order Up/Down, inline Edit, remove, Clear, undo/redo (50 history entries). Every edit marks the curves stale and pauses playback until refreshed.
- ML1a physical gate: on Windows 24/60 frames at 12 FPS, layer Spiral + Wave and select Update Curves; confirm two motion-curve panels (translations and degrees/frame), visible normalized path, correct frame readout on drag/touch, smooth 12-FPS playback with Loop off/on. Disable/reorder layers, Undo/Redo and update curves again; verify displayed motion changes, then Preview Draft Motion and Apply to Animation with no lost settings. Repeat on portrait phone. Switch projects and ensure stale plots do not persist.
- CI contract: Python per-frame resolver parity, API sample counts, Node runtime playback/scrub/stale handling and browser structural placement tests.

### ML1b: Direct curve/keyframe and geometric path editing (implemented; Windows acceptance pending)

- Add versioned, native camera-velocity `keyframes` layers to `motion_lab.py`. Each is bound to one of the six native axes with linear, hold, smoothstep, smootherstep, or shape-preserving monotone cubic interpolation, Add/Replace blend, enable state, bounded range, ordered sparse keyframes (max 128 per layer), strict duplicate/frame/value validation, and an unwarped frame-zero anchor. Existing preset layers and projects remain compatible.
- ML1b curve editor is entirely inside Motion Lab → Motion Curves & Camera Path. Select one axis, enter precise frame and per-frame velocity, add/update/delete keyframes, or select **Edit curve by dragging** to create/drag the selected axis keyframes directly in the SVG curve. Full keyboard/numeric fallback supports browsers without pointer dragging. Keyframe layers appear alongside presets and use ML1a reorder/toggle/undo/redo.
- Select **Edit path X/Y by dragging** to grab a point on the auto-fit geometric path. Its pixel displacement is converted to native X/Y *per-frame velocity* offsets at that frame, saved as an atomic pair of ordinary manual curve layers. Because camera travel is an integral, later path positions will also change; this does not assert absolute spatial positioning, calibrated physical units, or depth-aware occlusion. The existing CPU depth motion preview remains the authoritative visual check for warping.
- Editing a curve or a path automatically recomputes curves through the non-mutating existing preview API (no new GPU models); the user explicitly selects Apply to Animation to persist the compiled tracks. Manual Editor schedule edits continue to use ML0 conflict protection and explicit camera rebase authorization.
- Safety: no frame-zero movement, no arbitrary expression execution, finite values, max 24 layers / 128 keyframes each / 3000-frame preview, existing native per-axis clipping diagnostics, project save/reopen, stable frame mapping and interpolation after reload. Changing project stops and resets the visualizer; avoid editing while a compose request is pending.
- **Windows ML1b physical gate:**
  1. Update `feature/motion-lab`, choose a saved 3D project, 48 frames / 12 FPS, use the default calibration grid.
  2. In Motion Lab → Motion Curves & Camera Path (not Editor), select Translation X. Add keys `0→0`, `12→0.06`, `24→-0.04`; Update Curves, scrub to frames 6, 12, 18, 24 and inspect linear slopes. Switch interpolation to Hold, confirm staircase steps, and undo/redo.
  3. Enable **Edit curve by dragging**, drag frame-12 keyframe to frame 18 and a different value. Confirm the keyframe list and curve update; drag a new keyframe. Frame 0 must remain fixed.
  4. Add Spiral and Push In presets; reorder the manual X keyframe layer around them, compare Add vs Replace. Confirm RGB/geometry CPU Preview Draft Motion still works, and saved animation is untouched until Apply.
  5. Enable **Edit path X/Y by dragging** and drag a highlighted geometric path point (not start frame). Confirm X/Y manual curve changes, undo once to reverse the paired edit, and recompute the projected path. This is incremental velocity editing, not absolute XYZ point placement.
  6. Apply to Animation, save/reopen, verify keyframe layers and resulting native camera schedules persisted; reapply to ensure no duplicated motion. Check 2D guard, malformed inputs, desktop/portrait phone touch controls, and a short SDXL render only after the CPU preview looks right.
- CI gates: backend normalization, interpolation, precedence, persistence and path clipping; REST preview and Apply integration; Node pointer drag of keyframe and path handles; browser UI/aria/mount and responsive tests. Gate on all green CI and above physical check before checkpoint/merge.

#### ML1b follow-up: Smooth curves and desktop checkbox polish (2026-10-09)

- User physically verified ML1b curve/path editing and requested smoother velocity curves plus compact checkboxes on desktop. Recovery checkpoint preserves the accepted original at `333045e`.
- Added `smoothstep` (smooth ease in/out), `smootherstep` (extra-smooth easing), and `cubic` (monotone shape-preserving Hermite) while preserving `linear` and `hold` compatibility. All are evaluated in the existing backend into native per-frame camera tracks, not cosmetic SVG splines. Frame zero remains stationary, clipping still applies, and keyframe interpolation persists on save/reopen.
- Motion Lab checkbox styles explicitly size Edit Curve, Edit Path, Loop, and layer enable checkboxes to 16px in their own workspace without touching unrelated controls.
- **Windows acceptance: PASSED (user confirmed on 2026-10-09).** Smooth curves and checkbox-sizing changes accepted. Recovery checkpoint at `c0e5f90`. Extended GPU and per-device test matrices remain future work.

**Deferred beyond ML1b:** true absolute-camera control points/Bezier 3D path editing, physical-world units, FOV-/depth-aware path handles, inverse kinematics, axis constraints with spatial solvers. Those would need a distinct calibrated editor rather than repurposing the auto-fit display.

### ML2: Interactive recording and live controllers (implemented; physical acceptance pending)

ML2 keeps the existing Motion Lab authoring/render boundary intact. Live input is sampled into an ordinary `type:"recording"` layer; preview and Apply still compile through `motion_lab.py` into native camera tracks, then the existing resolver/CPU preview/renderer takes over.

#### ML2.0: deterministic recording layer contract

Implemented backend format, still under `motion_lab.schema_version:1` because it is backward-compatible with existing preset/keyframe layers:

```json
{
  "id": "take-001",
  "type": "recording",
  "name": "Recorded keyboard take",
  "enabled": true,
  "blend": "add",
  "start_frame": 4,
  "end_frame": 28,
  "fps": 12,
  "source": "keyboard",
  "capture_version": 1,
  "axes": ["translation_x", "translation_z", "rotation_y"],
  "samples": [
    [0, 0, 0, 0, 0, 0],
    [0.012, 0, 0.01, 0, 0.2, 0]
  ]
}
```

Contract:
- Exactly one dense six-value row per frame in canonical axis order: X/Y/Z translation then X/Y/Z rotation.
- `axes` explicitly declares armed axes. Nonzero values on unarmed axes are rejected, and Replace only replaces armed axes.
- Values are native Morphorum **per-frame** scene-unit/degree deltas. They are not positions.
- Frame 0 must remain stationary.
- Recording length is bounded by the project/layer range and existing 3000-frame project limit; it does **not** consume the 128-keyframe manual-curve budget.
- `capture_version` is currently exactly 1. `source` is provenance only: keyboard, touch, gamepad, mixed, or unknown.
- Capture FPS must exactly match current project FPS. ML2 intentionally **rejects implicit FPS retiming** because changing FPS changes the meaning of native per-frame deltas. Explicit retime/preserve-time tooling belongs in later polish rather than silently changing travel.
- Existing Add/Replace ordering, per-axis clipping diagnostics, base/last-applied snapshots, conflict confirmation, idempotent repeated Apply, save/reopen and REST preview/apply all include recording layers.

Automated coverage: malformed rows, sample counts, NaN/Inf, duplicate/bad axes, hidden unarmed motion, frame-zero motion, FPS mismatch, preset + cubic-keyframe composition, Add/Replace behavior, resolver parity, idempotence and REST preview/apply/save-reopen.

#### ML2.1: keyboard, mouse/pointer and mobile touch recording

Implemented first-class **Live Motion Recording** card inside `panels.motion`, between Composer and Curves. Controls include:
- Record/Stop from the current/selected start frame.
- Six independently armed axes plus per-axis inversion.
- Native translation sensitivity (scene units/frame) and rotation sensitivity (degrees/frame).
- Deadzone, deterministic frame-based response/return smoothing, and a short explicit release tail.
- Keyboard: A/D strafe, R/F lift, W/S dolly, arrows pitch/yaw, Q/E roll.
- Two pointer/touch joysticks: translation X/Y and pitch/yaw, plus Z and roll hold buttons.
- Portrait-phone layout, large touch targets, `touch-action:none` on joysticks/buttons, pointer capture/release safety.
- Key-up, pointer-up, `pointercancel`, lost pointer capture, window blur and document hiding neutralize input. Leaving Motion Lab ends the take rather than allowing a hidden held input to keep accumulating.
- The browser recorder maps monotonic elapsed time to discrete project frames. Duplicate animation callbacks do not duplicate samples; dropped callbacks fill the missing **project frame indices** using the latest live input state. Browser rendering cadence is therefore not the stored timeline.
- Stop produces a normal draft recording layer, enters existing Undo/Redo history, automatically refreshes Motion Curves, and still requires explicit **Apply to Animation** before canonical project camera tracks are persisted.

#### ML2.2: optional browser Gamepad API

Implemented opt-in client-side Gamepad API support with honest fallback behavior:
- Reads the first controller visible to the **client browser**, not a controller merely attached to the Morphorum host.
- Left stick maps translation X/Y; right stick yaw/pitch; triggers map Z; bumpers map roll. Existing deadzone, sensitivity, arming and inversion apply.
- UI reports unavailable/blocked API, no visible controller, connected controller, and disconnect state.
- Keyboard/touch remain usable regardless of controller availability.
- No host XInput bridge and no claim that plain HTTP LAN origins will expose Gamepad API. Physical controller acceptance is conditional on the test browser/security context.

**ML2.0–ML2.2 automated gate:** code candidate `47b614f10993cfae0eb249b94ee94b932d693149` passed GitHub Syntax checks (including Node/browser regressions) and Backend tests/self-test. This is **not** a physical checkpoint.

**Physical gate before any ML2 checkpoint/merge:**
1. Windows desktop, saved 3D project, 48 frames at 12 FPS. Hard refresh. Confirm Live Motion Recording is in Motion Lab between Composer and Curves.
2. Record a keyboard take from frame 0 for roughly 24–36 frames. Use D/W plus arrow input, release controls, then Stop. Confirm frame 0 is still, the take appears in the layer list, Curves refresh, playback replays the take, and no input remains stuck.
3. Undo and Redo the take. Reorder it against Spiral and a cubic manual curve; test Add and Replace on armed axes. Confirm unrelated axes survive Replace.
4. Apply, inspect Editor native camera tracks, Apply again without doubled travel, save/reopen and confirm the recording samples/timing persist.
5. Run CPU calibration-grid Motion Preview and verify direction/signs. No GPU render is required for this initial ML2.0–2.2 gate.
6. Phone portrait browser: record using both touch sticks plus Z/roll buttons. Verify the page does not scroll while dragging a stick, pointer release/cancel returns cleanly, controls fit portrait, and switching tabs or backgrounding the page ends/neutralizes the take.
7. Change sensitivity, deadzone, response/return and per-axis inversion and verify visible differences.
8. Optional controller: enable Gamepad. If the browser exposes a controller, verify sticks/triggers/bumpers and disconnect behavior. If HTTP/browser security blocks it, confirm the explicit unavailable status and that keyboard/touch still work; this is an acceptable fallback result.
9. FPS rule: a persisted 12-FPS take must never be silently reinterpreted at another FPS. A mismatch should be rejected until explicitly retimed/re-recorded.
10. Confirm `main`, `dev-ui`, and `feature/b6-3-3-hybrid-masks` remain untouched. Only after physical acceptance create an ML2 checkpoint and proceed to ML2.3/punch-in polish or merge planning.

### ML2.3: Take management (first slice implemented; physical gate pending)

The ML2 keyboard/UX build was physically accepted October 10, 2026, and frozen in `checkpoint/motion-lab-ml2-recording-ux-verified-20261010` at commit `1245055f043519e9aab0a46cf8a5fa3310d31619`. Desktop toolbar behavior and mobile-only toolbar hiding were accepted. Browser gamepad remains optional and physically unverified.

Current ML2.3 feature-branch changes implement **inline rename** for recording layers and **Duplicate**. The copy receives its own ID, keeps its frame-aligned sample data and armed axes, and begins **disabled** to prevent doubling camera travel. Existing Undo/Redo, layer limits and backend validation apply. This is NOT a physical acceptance checkpoint yet.

**Next physical gate:** Create a recording, Rename it, Undo/Redo, Duplicate and confirm the copy is off by default. Verify enabling it deliberately adds the extra contribution; verify save/reopen retains names and copied samples and mobile inline editing is usable. Don't merge before physical approval.

**ML2.3 punch-in implementation now awaiting physical testing:** Select Take mode = Punch into existing take, select target, specify start and exclusive end frame, arm a subset of the target take's axes, then record until the selected end. New dense samples replace only that axis subset inside the interval. Outside frames and unrelated axes remain unchanged, including their original data. Source is copied before editing; existing draft Undo/Redo preserves the prior take. FPS must match and the range must fall completely inside the target. Stopping before the end discards an incomplete punch-in; no partial destructive overwrite. The draft then refreshes curves and requires normal Apply to persist native camera schedules.

**Physical gate:** choose a six-axis 12 FPS take; punch into frames [12, 24), arm only translation_x, hold D until automatic stop. Confirm only frames 12–23 X values change, the other five axes and frames 0–11/24+ remain identical. Undo restores exact original; Redo reapplies. Try an invalid range, arm an axis absent from target, and stop midway, all of which must preserve the original. Save/reopen, verify idempotent Apply and retry on mobile. Gamepad still optional. Do not merge without acceptance.

### ML2.3 acceptance checkpoint (2026-10-10)

Physical testing accepted ML2.3 punch-in, preserving original axes and untouched ranges. Frozen at `checkpoint/motion-lab-ml2-3-punch-in-verified-20261010` / `6ffc24bb9bac60e0be298b020833df176a7d0a10`. GitHub Syntax and Backend tests passed on the exact head. Optional browser gamepad remains untested. No merge.

### ML3: Audio-reactive motion

**ML3.0 foundation implemented on feature branch (not integrated, not yet physically accepted):** `backend/morphorum/audio_motion.py` offers CPU-only full-band RMS extraction from *already decoded* mono PCM, immutable SHA256 content identity, exact project-frame windows and symmetric positive/negative camera-velocity pulses from threshold-crossing onsets. Incomplete tails are skipped, not clipped, ensuring zero net displacement per pulse. Tests use known synthetic PCM and beat patterns. This module intentionally does not claim bass-band analysis, media upload, FFmpeg decode, project persistence, UI or GPU animation support. Those are later ML3 increments.

**ML3 next increments:** project-local audio upload/FFmpeg decode and bass-band extraction; persisted hashed envelope; validated independent audio layer with threshold, attack/release, direction and offset; preview/compiler wiring; desktop/mobile controls; synchronized browser preview; real SDXL export gate. Preserve source-free recording/renderer and prior checkpoints.

- Upload audio to project-managed asset storage, decode once with existing FFmpeg; analyze bass-band intensity and transient peaks on CPU. No model/GPU allocation.
- Adjustable band, threshold, attack/release, pulse distance, offset and direction.
- Add pulse as independent optional motion layer; generate a balanced push/return with uniform headroom scaling to respect axis limits, preserving continuous travel.
- Persist waveform/envelope or derived frame controls, content hash, source version and timing for deterministic resume. Audio playback in the browser can be synchronized to preview playback; separate soundtrack muxing/export can be planned.
- **Gate:** known synthetic beats, pulse timing, amplitude/return, movement clipping, save/reopen, a short SDXL animation + exported video.

**ML3.1 first integrated Windows test candidate (not physically accepted):** Added project-owned **PCM WAV** upload/analyze endpoint `POST /api/animation/projects/{project_id}/motion-lab/audio-analyze` (20 MiB maximum, 3 minute PCM maximum, mono/stereo WAV 8–32 bit, 8–192 kHz), content-addressed project WAV storage, and full-band RMS envelope at the project frame clock. New `type:"audio"` draft layers carry source hash, FPS-locked frame envelope and validated threshold/attack/release/pulse-distance/axis parameters. The backend derives balanced velocity pulses, compiles them through existing native camera tracks, and supports normal Preview, Apply, save/reopen and Undo/Redo. Frontend Motion Lab audio card supports file selection, analysis, parameter settings and Add Audio Motion Layer. This slice does **not** support MP3/FLAC/FFmpeg decode, bass-only filtering or soundtrack muxing yet. Those are subsequent steps and must not be claimed ready.

**Physical gate:** Use a short PCM WAV containing audible pulses/clear loud-soft sections; select a saved 3D project at 12 FPS and 48+ frames; Analyze WAV then Add Audio Motion Layer; inspect Z curves and Preview Draft Motion then Apply, reopen, repeat Apply and verify no drift/doubling. Check stale/invalid WAV, incorrect FPS after project changes, layer disable, Undo/Redo and phone layout. Onset detection currently triggers **upward RMS threshold crossings**, not every bass kick if the envelope stays above threshold. Do not merge before Windows acceptance.

**ML3.1 waveform-preview polish (physical acceptance pending):** Following Windows feedback that a default threshold of 0.25 produced no visible camera movement until lowered to 0.1, the Audio-Reactive Motion card now shows the analyzed full-band RMS envelope directly after WAV analysis, with threshold guide line, predicted complete pulse markers and pulse count. Changing threshold, attack or release updates this preview without adding a layer. On analyze, the threshold starts at min(0.1, 55% of the analyzed maximum), avoiding empty previews on quieter sources. This is a frame-aligned RMS envelope, not a raw audio waveform or audio playback. Test varying threshold from 0.25 to 0.1 with the same WAV and verify markers/count change before adding any draft layer; then Add Audio Motion Layer and confirm the resulting curves agree. No protected branches merged.

**ML3.1 audio-synchronized curve playback (physical gate pending):** Following Windows approval of analyzed WAV RMS/threshold preview, the browser now optionally plays that same analyzed WAV alongside **Motion Curves & Camera Path** interactive playback. Visualizer Play/Pause/seek/frame loop drive a local browser Audio element (frame/fps clock, drift correction). This is *not* a soundtrack added to GIF/video export and not synchronized to the separate CPU preview GIF or depth render. Playback source is a browser object URL to the selected file: after browser reload, reselect and reanalyze the WAV. Browser audio policies may block autoplay; UI reports this. Test play/pause/resume, scrub mid-audio, loop, audio shorter than project, disabling sync, mobile, and changing tabs. No extra GPU dependencies and no merge before physical acceptance.

### ML4: Final integration and physical acceptance

- Optional custom presets/import-export, compatibility test against Deforum `translation_x/y/z` and `rotation_3d_x/y/z`, field mapping.
- Stress test on RTX 4080 SUPER with 3D depth, cadence 3, prompt changes, four LoRAs, hybrid video source/opacity and long animation.
- Cross-check compiled schedule values against resolved live render metadata. No progressive VRAM growth caused by Motion Lab.
- Confirm mobile/browser usability, export fidelity, cancellation/resume, migrated project fidelity.
- **Gate:** checkpoint + reviewed PR → `dev-ui`. Keep B6.3.3 separately paused.

## Current next action

Perform the ML2.0–ML2.2 Windows/phone physical gate above on `feature/motion-lab`. Do not create a verified checkpoint or merge PR #19 until that gate is accepted. After acceptance, checkpoint ML2 and decide whether to continue directly into ML2.3 punch-in/take-management polish before the first recorded-motion GPU render.

## Architecture and legal notes

- Morphorum remains LAN-accessible on Windows; all authoring state belongs to the selected Morphorum project, not a local Tk app or the client's file system.
- Safe expression parsing uses existing `schedules.py`; never `eval` arbitrary expressions.
- No new GPU model dependencies. Optional audio analysis libraries must be weighed against installation footprint.
- The user reports express author permission to reuse any/all of the friend's code. Check that permission includes republishing adapted files under Unlicense before shipping direct copies; do not assume it covers third-party materials.
- Workspace shell is implemented and source-free calibration-grid preview was physically accepted. Media is hidden in a vault and its backend/data are preserved.
- ML0 now includes `backend/morphorum/motion_lab.py`, `GET /api/animation/motion-lab/presets`, and project-owned POST `/motion-lab/preview` and `/motion-lab/apply` endpoints.
- Presets: Still, Gentle Drift, Wave, Spiral, Figure Eight, Rocking, Push In, Pull Out; layer Add/Replace, frame range, fade/strength/cycle, per-axis native limits and diagnostics; preserve all other animation tracks, prompt/LoRA/depth/hybrid state.
- Draft preview compiles to actual native `tracks.camera_3d` schedules without saving and then uses the existing source-free CPU Motion Preview API. Apply saves only after explicit action. Projects persist editable layer data, base tracks and last-applied snapshot; external timeline edits cause an intentional conflict instead of silently being overwritten.
- ML0 safety: bounded 24 layers / 3000 frames per composition, numeric validation, clipping diagnostics, idempotent reapply, tests across API, project persistence, resolver and frontend.
- **2026-10-09 ML0 acceptance follow-up (reported by user):** Composer initially appeared under Editor instead of Motion Lab; fixed reparenting composer between Motion Lab intro and existing preview. Spiral was nearly invisible in short previews because of 8-second default cycle and reduced X/Y/Z/roll movement; new defaults 2-second cycle, 0.1-second fade, stronger helix, and in-place editing of previously saved layers. Editing 3D camera schedules after applying Motion Lab previously blocked *Preview* with a conflict; Preview now composes non-destructively on latest Editor camera (including unsaved edits). Apply still requires explicit user confirmation to rebase edited camera values, preserving previous no-double-apply safeguards. Motion Lab also has an in-tab **Use 3D Motion** switch, and Apply can offer to save pending Editor changes without requiring tab hopping.
- **Updated Windows gate:** on `feature/motion-lab`, confirm Camera Motion Composer is **inside Motion Lab** above Camera Motion Preview, not in Editor. On 24 frames at 12 FPS, test Spiral with 2s cycle / 0.1s fade, then edit an existing 8s Spiral to 2s using its Edit action and verify a strong helix. Apply, hand-edit a camera motion schedule in Editor (saved and unsaved cases), and verify *Preview Draft Motion* works without error or changing the saved project. On Apply, verify the explicit **Use Current Camera & Apply** confirmation appears and that confirming retains the edits as the new base without compounding old layers; canceling leaves project unchanged. Check quick 3D switch and phone layout.
- **Windows physical gate:** update `feature/motion-lab`; choose a saved 3D project at 512x512, FPS 12, 24–60 frames. Add Wave + Push In at strength 0.5 and fade 0.2, Preview Draft Motion (grid GIF with visible movement), then Apply to Animation and inspect 3D Translation X/Z in Editor. Reapply without duplicate travel; test Spiral/Figure Eight and replace mode. Save/reopen the project and verify layers persist. Check 2D mode disables composer, and mobile layout. No GPU render is required yet for ML0.
