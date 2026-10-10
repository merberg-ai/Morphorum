# Morphorum Motion Lab — implementation roadmap

**Status:** Motion Lab UI and source-free CPU preview physically accepted on Windows (2026-10-09); ML0 deterministic preset composer and draft/apply UI implemented and undergoing Windows acceptance. Interactive recording ML2 and audio-reactivity ML3 remain future work.
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

### ML2: Interactive recording and live controllers

- Implement on-screen touch joysticks and keyboard/mouse control, record/play/seek/stop, smoothing/deadzone/sensitivity, axis arming, punch-in replacement, deceleration tail and undo.
- Offline record results mapped against **project frame clock**, not wall-clock diffusion speed. Do not steer running diffusion.
- Optional browser Gamepad API input when available in the page's security context; test actual Windows/LAN browser behavior. Cross-device gamepads depend on connection to the **client** browser, not automatically to host PC.
- LAN HTTP may restrict Gamepad API in some browsers: provide touch/keyboard fallback, and consider HTTPS or an explicitly designed host-side XInput bridge only later. Never silently promise raw browser controller access on all LAN clients.
- **Gate:** phone touch recording, Windows browser controller where supported, determinism/replay, no render-thread interaction.

### ML3: Audio-reactive motion

- Upload audio to project-managed asset storage, decode once with existing FFmpeg; analyze bass-band intensity and transient peaks on CPU. No model/GPU allocation.
- Adjustable band, threshold, attack/release, pulse distance, offset and direction.
- Add pulse as independent optional motion layer; generate a balanced push/return with uniform headroom scaling to respect axis limits, preserving continuous travel.
- Persist waveform/envelope or derived frame controls, content hash, source version and timing for deterministic resume. Audio playback in the browser can be synchronized to preview playback; separate soundtrack muxing/export can be planned.
- **Gate:** known synthetic beats, pulse timing, amplitude/return, movement clipping, save/reopen, a short SDXL animation + exported video.

### ML4: Final integration and physical acceptance

- Optional custom presets/import-export, compatibility test against Deforum `translation_x/y/z` and `rotation_3d_x/y/z`, field mapping.
- Stress test on RTX 4080 SUPER with 3D depth, cadence 3, prompt changes, four LoRAs, hybrid video source/opacity and long animation.
- Cross-check compiled schedule values against resolved live render metadata. No progressive VRAM growth caused by Motion Lab.
- Confirm mobile/browser usability, export fidelity, cancellation/resume, migrated project fidelity.
- **Gate:** checkpoint + reviewed PR → `dev-ui`. Keep B6.3.3 separately paused.

## First implementation target / next action

Begin ML0 with a small backend-focused PR on this branch. Define the versioned layer schema, pure preset math and six-axis composer, and a minimal compile-to-native-tracks adapter. Write tests **before** adding a UI or live controller. The first physical test should be a 60-frame 3D spiral or figure-eight, 512x512, cadence 1, with CPU motion preview then SDXL render only after the compiled tracks match the resolved frames.

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
