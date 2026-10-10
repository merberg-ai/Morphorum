# Morphorum — Complete Motion Lab Handoff
## Verified ML1b checkpoint and exact ML2 starting point

**Prepared:** October 9, 2026 (Windows/Pacific development session)  
**Repository:** https://github.com/merberg-ai/Morphorum  
**Active development branch:** `feature/motion-lab`  
**Open draft PR:** [#19 — Motion Lab](https://github.com/merberg-ai/Morphorum/pull/19), **base `dev-ui`**  
**Current product version:** `0.1.0a1` (early alpha)  
**Current phase:** **ML1b COMPLETE, physically accepted; PAUSED IMMEDIATELY BEFORE ML2**  
**Latest frozen, accepted checkpoint:** `checkpoint/motion-lab-ml1b-smoothing-windows-verified-20261009`  
**Checkpoint commit (full SHA):** `c0e5f90a692e14e32b48155f71d0a8afc923c6ae`  
**Branch HEAD:** `feature/motion-lab` now includes **documentation-only commits** beyond the accepted checkpoint. Check `git rev-parse HEAD` before future edits; the checkpoint above is the immutable source of truth for the accepted code.  
**Developer machine:** HP Omen 35L, Windows, RTX 4080 SUPER 16 GiB, ~64 GiB RAM, test installation `D:\Morphorum-test`  
**LAN:** Morphorum typically served at `http://192.168.1.24:7865/#animation`; LAN IP may change.  
**Do not merge this branch or start ML2 until the user explicitly resumes work in the next conversation.**

> **Immediate instruction to the next assistant:** Read this handoff and `docs/MOTION_LAB_ROADMAP.md`, inspect `feature/motion-lab` via the connected GitHub tools, and plan/implement ML2 starting from the current feature branch, preserving the protected checkpoint. **Do not create another renderer, reset the branch, resurrect Media, or start B6.3.3.** The user explicitly paused at the completed ML1b checkpoint to continue in a new conversation.

---

## 1. Hard state: what has actually been checked

### Repository status, verified October 9, 2026

| Ref | Exact commit | State |
| --- | --- | --- |
| `main` | `4bc996be29104590a78ae84759a837a8a29a5135` | Older stable integration; **not** Motion Lab |
| `dev-ui` | `bc40d18d4f5968904afedc798ecd3efdef71761a` | B6.3.2-accepted integration, remains unchanged |
| `feature/motion-lab` | **HEAD after this handoff commit**; before docs handoff, accepted ML1b code at `c0e5f90` | **Active feature development only; unmerged** |
| `checkpoint/motion-lab-preview-windows-verified-20261009` | `67138c26c70567198a154c1f35045b0713a49687` | First Motion Lab UI / source-free preview |
| `checkpoint/motion-lab-ml0-windows-verified-20261009` | `f75bdf617162391015d142f94f86ad3d059f03e5` | Composer, preset layers, conflict fixes physically accepted |
| `checkpoint/motion-lab-ml1a-windows-verified-20261009` | `b2bc351b2704ce51fa806e9f3923d0379aa8c1f5` | Curves, geometric path, playback, layer ordering |
| `checkpoint/motion-lab-ml1b-windows-verified-20261009` | `333045eda1a180682bd48dc0b563bcd1fb91859f` | Editable keyframes and path dragging before smoothing polish |
| **`checkpoint/motion-lab-ml1b-smoothing-windows-verified-20261009`** | **`c0e5f90a692e14e32b48155f71d0a8afc923c6ae`** | **LATEST ACCEPTED CHECKPOINT; DO NOT MODIFY** |
| `feature/b6-3-3-hybrid-masks` | `c0e9be0aa03472747ba4c2594c128bdcd80318ef` | **PAUSED**, planning only; separate from Motion Lab |
| `checkpoint/b6-3-3-planning-pause-20261009` | `c0e9be0aa03472747ba4c2594c128bdcd80318ef` | B6.3.3 safe planning point |

Other verified B6 checkpoint: `checkpoint/b6-3-2-hybrid-compositing-windows-verified-20261009` at `bc40d18`.

**PR #19** is **open, mergeable, and draft**, targeting `dev-ui`, not a nonexistent `dev-main`. Before the handoff changes, `feature/motion-lab` was 75 commits ahead of `dev-ui`, with no divergence. Subsequent handoff commits change documentation only. **There has been no Motion Lab merge into `dev-ui` or `main`.**

### Automated and human acceptance

The accepted checkpoint `c0e5f90` passed GitHub **Syntax checks** and **Backend tests**, including **359 passed Python tests, 5 warnings**, plus `python -m morphorum self-test`. Browser/Node regressions run under the syntax workflow. The user explicitly confirmed all of the following on the actual Windows/LAN UI:
- Motion Lab appears as a first-class Animation tab; unfinished **Media** is hidden.
- Camera Motion Preview works with a built-in calibration grid without uploading a source image.
- ML0: Camera Motion Composer lives inside Motion Lab; Spiral visibly moves; 3D shortcut, preset layering, non-destructive preview and manual Editor change conflict flow function.
- ML1a: all six movement traces, playback/scrubbing, geometric path, layer controls work.
- ML1b: direct per-axis keyframe editing, path/curve controls and numeric keyframe list work.
- Follow-up ML1b: **smooth curve interpolation** looks good and desktop checkbox sizing is corrected.
- User said **"awesome, working great now. go ahead and checkpoint here"** and requested this handoff **before ML2**.

**Do not overclaim:** the latest acceptance covers the Motion Lab UI/CPU-authoring behavior the user tested, not a full new GPU stress profile, arbitrary controller compatibility, universally accurate depth-aware camera paths, or ML2 recording, which is **not yet implemented**.

---

## 2. Non-negotiable product direction

Morphorum is a standalone, local, browser-operated Deforum-style image/animation studio with the following engine boundaries:
- **ONE authoritative image/animation renderer**, `animation_render.py`, using model adapters.
- **ONE native camera timeline and resolved-frame contract**, `animation_timeline.py` + `animation_resolution.py`.
- Motion Lab is an **authoring and compositing layer**. It generates native per-frame six-axis camera tracks and saves them through the existing project service after explicit Apply.
- **No alternative renderer**, no second diffusion pipeline, no direct joystick influence over an actively rendering model, no incompatible standalone Tk interface.
- Keep SDXL/Flux/Z-Image, LoRAs, cadence, 3D depth projection, prompt schedules, pause/resume, GPU telemetry and MP4/WebM export untouched unless explicitly in scope.
- UX must be first-class on desktop and a portrait mobile LAN browser. No tab hopping for fundamental motion operations.
- Physical Windows acceptance and CI green **before each merge/checkpoint**. Never infer physical acceptance from CI alone.

### Model/runtime and licensing

- Python 3.12 (managed `uv` and `.venv`), FastAPI/Uvicorn, vanilla static HTML/CSS/JavaScript in `frontend/dist`; `pyproject.toml` version `0.1.0a1`.
- Model families: SDXL, Flux and Z-Image. GPU verification target: Windows RTX 4080 SUPER, 16 GiB VRAM.
- Host FFmpeg for media and video export.
- Core repository `LICENSE` is the **Unlicense**.
- Inspiration: https://github.com/chicodog530/Deforum-Motion-Studio. The user reports explicit permission from the author to use any/all his code. The public upstream repo has no declared LICENSE in the review snapshot. **Before directly vendoring and redistributing upstream code under Unlicense, verify that permission covers redistribution/derivatives and record provenance in `THIRD_PARTY.md`.** No claim that our already-written Motion Lab code was directly copied.
- Upstream uses different camera translation scales/flat-depth projection than Morphorum. **Do not paste its numerical velocities into native camera coordinates 1:1.** Adapt algorithms to the Morphorum-native axes and test sign, FOV, and projected movement.

---

## 3. What is already built and verified

### UI organization

Animation workspace visible tabs are **Editor / Motion Lab / Monitor / Outputs**. The old **Media** video-import/hybrid panel is deliberately hidden in an inert DOM vault on this feature branch. It is **not removed from the backend**: B6.2/B6.3.1/B6.3.2 upload/extraction, video-sourced diffusion/compositing, and saved hybrid project settings remain intact. Video MP4/WebM export still appears under Outputs. Existing projects may retain active hybrid settings even though the Media controls are hidden.

Motion Lab sections are ordered:
1. Motion Lab introduction and shortcuts.
2. **Camera Motion Composer**: presets/layers with strength, cycle seconds, fade, start/end frames, Add/Replace, per-layer enable/edit/remove/order, draft undo/redo, Preview Draft Motion, Apply to Animation, Update Curves.
3. **Motion Curves & Camera Path**: six color-coded camera velocity curves, frame seek/play/pause/loop at project FPS, integrated **auto-fit** path, exact axis readouts, editable per-axis keyframes, linear/hold/smooth interpolation, optional curve/path pointer editing.
4. **Camera Motion Preview**: existing CPU-only 2D/3D image-warp preview, uploads optional; uses built-in calibration grid otherwise. In 3D mode, preview can highlight exposed pixels red. Preview has a **180-frame limit for 3D**; CPU preview is not equivalent to diffusion/cadence.

### ML0: compositional native six-axis engine

`backend/morphorum/motion_lab.py`:
- Axes: `translation_x`, `translation_y`, `translation_z`, `rotation_x`, `rotation_y`, `rotation_z`.
- Tracks are **per-frame relative velocities/deltas** in Morphorum scene units and **degrees per frame** for rotation. They are *not* global camera XYZ coordinates. Frame zero stays unwarped.
- Presets: `still`, `gentle-drift`, `wave`, `spiral`, `figure-eight`, `rocking`, `push-in`, `pull-out`.
- Each enabled layer has a bounded frame interval, Add/Replace blend, optional strength/cycle/fade. Preset output uses native camera amplitudes, axis limits, clamping diagnostics. Spiral was tuned for a visible two-second helical move.
- Layer order matters. Base camera tracks are frozen before application, preventing compounded movement on repeated Apply.
- When manual Editor camera tracks changed after Apply, draft preview uses latest camera temporarily; Apply responds with a conflict and requires explicit **Use Current Camera & Apply** rebase confirmation.
- Supports `include_series=True` for the non-mutating draft-preview API to return full, clipped, resolved six-axis frame values for the JS visualizer.
- Limits: **24 layers**, **3000 frames** per composition, **128 sparse keyframes per manual layer**; finite numbers, unique IDs/frames, clipping and frame-zero guard.
- The first version is **3D only**. In Motion Lab the **Use 3D Motion** shortcut helps switch modes. Do not treat 3D Z as equivalent to 2D zoom.

### ML1a: visual feedback and layer editing

`frontend/dist/assets/motion-lab-visual.js`:
- Charts actual per-frame camera motion, not cosmetic approximate splines.
- Translations and rotations plotted separately with dynamic scaling.
- Integrates X/Y/Z increments into a projected, **normalized/auto-fit** 2D camera path. The path is illustrative and not depth/FOV calibrated.
- Uses client-side `requestAnimationFrame` for preview playback (not render timing). Sliders/keyboard/pointer scrub, loop and frame/second readout.
- Draft edits mark curves stale, disable/stop outdated playback, and require Update Curves.
- Switch projects clears previous preview. Leaving Motion Lab pauses playback.
- Undo/redo retains up to 50 changes, with layer toggle, reorder, edit, clear, delete.

### ML1b: precise keyframes and smooth motion

Manual `type:"keyframes"` layers are in the **same** Motion Lab layer stack as presets:
- Single axis per layer, start/end frame, Add/Replace, enabled flag.
- `keys:[{"frame":n,"value":v}]`, max 128, frame-0 nonzero rejected, bounds/corrupt input rejected.
- **Five interpolation modes**, all implemented in backend and baked to native timeline:
  - `linear` = sharp straight line between velocities.
  - `hold` = step/hold.
  - `smoothstep` = ease-in/out with zero endpoint slope.
  - `smootherstep` = extra smooth C2 ease-in/out.
  - `cubic` = shape-preserving monotone Hermite/PCHIP-style continuous tangents (no keyframe overshoot).
- Exact numerical keyframe editing and optional SVG curve pointer dragging.
- Optional projected path handle dragging **adds X/Y per-frame velocity deltas** to manual keyframe layers at the selected frame; it is *not* an absolute path-position editor.
- Per-layer Add/Replace and ordering, undo/redo, Apply and round-trip save/reopen remain functional.
- User-requested checkbox polish scopes **16×16 px native checkboxes** to Motion Lab curve edit, path edit, loop and layer toggles.

### Native project structure (current)

`animation_projects.py` persists `project.motion_lab` (schema version 1). Minimal conceptual example:

```json
{
  "animation": {"mode": "3d", "max_frames": 120, "fps": 24},
  "motion_lab": {
    "schema_version": 1,
    "layers": [
      {
        "id": "wave-1", "type": "preset", "preset": "wave",
        "enabled": true, "blend": "add",
        "start_frame": 0, "end_frame": 120,
        "strength": 0.5, "cycle_seconds": 2, "fade_seconds": 0.1
      },
      {
        "id": "manual-translation_x", "type": "keyframes",
        "axis": "translation_x", "enabled": true, "blend": "add",
        "start_frame": 0, "end_frame": 120,
        "interpolation": "cubic",
        "keys": [
          {"frame": 0, "value": 0},
          {"frame": 30, "value": 0.04},
          {"frame": 60, "value": -0.03}
        ]
      }
    ],
    "limits": {
      "translation_x": 0.12, "translation_y": 0.12,
      "translation_z": 0.12, "rotation_x": 2.0,
      "rotation_y": 2.0, "rotation_z": 2.0
    },
    "base_tracks": null,
    "last_applied_tracks": null
  }
}
```

The compiler will populate the base/last-applied snapshots on **Apply**. A complete saved project also includes model, prompts, generation, `camera_3d` legacy mirror, and canonical `tracks.camera_3d` fields; the example is illustrative and not a standalone runnable project document.

---

## 4. Exact integration points and project map

| Path | Live responsibility |
| --- | --- |
| `backend/morphorum/motion_lab.py` | Pure deterministic motion composer, layer validation, preset math, keyframe interpolation, clipping, native-track export |
| `backend/morphorum/animation_projects.py` | Native project schema, `motion_lab` persistence/normalization |
| `backend/morphorum/animation_timeline.py` | Canonical camera track descriptors/mapping and legacy schedule bridge |
| `backend/morphorum/animation_resolution.py` | `resolve_project_frame`, source-of-truth per-frame camera values used by rendering |
| `backend/morphorum/animation_motion.py` | CPU motion preview, calibration grid fallback and optional image/depth preview |
| `backend/morphorum/animation_3d.py` | Actual depth-aware 3D camera reprojection and frame warp |
| `backend/morphorum/animation_render.py` | Actual diffusion/cadence/camera job loop, resume and output; do **not** add a parallel recording renderer |
| `backend/morphorum/app.py` | Motion Lab APIs and project endpoints |
| `frontend/dist/index.html` | Motion Lab markup and Animation navigation |
| `frontend/dist/assets/animation.js` | Motion Lab draft stack, form, endpoints, Apply flow, undo/redo, project switching, tab reparenting |
| `frontend/dist/assets/motion-lab-visual.js` | Client curves, projected path, interactive dragging/scrub/playback |
| `frontend/dist/assets/animation.css` | Responsive Motion Lab styling |
| `docs/MOTION_LAB_ROADMAP.md` | Full staged program; now reflects latest physical acceptance |
| `docs/B6_3_2_HYBRID_COMPOSITING.md` | Separate accepted hybrid render contract, currently hidden from visible Media tab |
| `docs/B6_3_3_HYBRID_MASKS_ROADMAP.md` | **On different branch only**, B6.3.3 planning/paused |
| `tests/test_motion_lab.py` | Presets, layer math, conflict/idempotence, resolver parity |
| `tests/test_motion_lab_keyframes.py` | Linear/hold/smooth/cubic curves, validation, save/reapply, no overshoot |
| `tests/test_motion_lab_api.py` | Non-mutating preview vs explicit Apply, persistent native tracks, conflict resolution |
| `tests/test_animation_motion.py` and `tests/test_api.py` | Reference-grid CPU preview and API coverage |
| `tests/frontend_motion_lab_navigation.test.cjs` | Dynamic tab placement, Media vault and UI elements |
| `tests/frontend_motion_lab_visual.test.cjs` | JS curve model, frame scrub, time playback, stale-state behavior |
| `tests/frontend_motion_lab_keyframes.test.cjs` | Pointer-edit paths, frame-zero safety, smoothing UI and checkbox styles |
| `.github/workflows/backend-tests.yml` | Python 3.12/CPU torch CI, pytest and `morphorum self-test` |
| `.github/workflows/` | Syntax/frontend checks (inspect workflow filename before changing) |

**Critical UI trap already fixed twice:** The Animation workspace dynamically moves cards into tab panels in `setupAnimationWorkspaceTabs()` in `animation.js`. **Any new ML2 card must be explicitly reparented into `panels.motion`**, otherwise it will appear in Editor or a hidden parent. Add a regression test for ownership/order and phone layout. The earlier Camera Motion Composer and Motion Curves placement bugs came from missing this step.

**Current visible workspace tab list:** `['editor','motion','monitor','outputs']`; there is no visible `media` tab.

### HTTP API (existing)

- `GET /api/animation/motion-lab/presets`: preset catalog.
- `POST /api/animation/projects/{project_id}/motion-lab/preview`: accepts `{"layers":[...], "project": <optional unsaved editor draft>}`. Compiles using `conflict_policy="use-current"`, **does not save**, and returns `project` plus `diagnostics` with full `series`, frame count, FPS, clipping/rebase indicators.
- `POST /api/animation/projects/{project_id}/motion-lab/apply`: accepts `{"layers":[...], "rebase_current":false}`; explicitly saves native `tracks.camera_3d` and `camera_3d` mirror with Motion Lab metadata. Manual schedule conflicts produce HTTP 409 unless the user confirmed `rebase_current:true`.
- Standard project save/load API: `/api/animation/projects/{project_id}`.
- Existing `POST /api/animation/motion-preview`: CPU geometric/depth preview of a project, optional source image.

**ML2 must reuse the first two Motion Lab endpoints, rather than launching a second background render manager.** Extend layer normalization/composer; keep frontend input capture purely browser-side.

---

## 5. Starting a new development session

### Windows host update/launch

Stop the running Morphorum server first to avoid an old process binding 7865, then:

```powershell
Set-Location D:\Morphorum-test
.\update.bat feature/motion-lab
git branch --show-current
git log -1 --oneline
.\run-lan.bat
```

Expected branch: `feature/motion-lab`; HEAD will be the newest documentation commit (later than the accepted `c0e5f90`). Hard-refresh in Chrome (`Ctrl+Shift+R`) when testing changed static JS/CSS.

Use the **protected checkpoint** to recover the exact accepted code if needed:

```powershell
Set-Location D:\Morphorum-test
.\update.bat checkpoint/motion-lab-ml1b-smoothing-windows-verified-20261009
.\run-lan.bat
```

Do not overwrite or delete `data/`, `outputs/`, `.venv/`, `.runtime/`, `backups/`, render manifests or configured external model/LoRA directories. Check the updater's rollback output on failure before manually switching refs.

### Useful developer checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_motion_lab.py tests\test_motion_lab_keyframes.py tests\test_motion_lab_api.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m morphorum self-test
node --test tests\frontend_motion_lab_navigation.test.cjs tests\frontend_motion_lab_visual.test.cjs tests\frontend_motion_lab_keyframes.test.cjs
git status
git rev-parse HEAD
```

On GitHub, require both named workflows to pass at the **exact new head SHA**, then perform actual Windows browser/CPU/GPU tests as relevant. Feature branches are primarily tested through draft PR checks. Do not accept a green build from an older head.

---

## 6. Next phase: ML2 — Live motion recording (PLANNED, NOT IMPLEMENTED)

### Why

Make Motion Lab one of the application's main creative tools by letting the user **fly the camera** with keyboard, phone touch joysticks, and an optional gamepad, **record** six-axis movement over a defined animation frame interval, review a take, and add it as an editable/undoable motion layer. Preserve predictable native motion values and never cause a second render pipeline.

### Recommended engineering phases

#### ML2.0 — Recording contract and deterministic compiler (backend-first)

Add `type:"recording"` to the versioned Motion Lab layer schema (possibly `schema_version:2` only if needed; legacy v1 preset/keyframe layers must load unchanged). Suggested normalized take:

```json
{
  "id": "take-001",
  "type": "recording",
  "name": "Hand-flown orbit",
  "enabled": true,
  "blend": "add",
  "start_frame": 12,
  "end_frame": 96,
  "fps": 12,
  "axes": [
    "translation_x", "translation_y", "translation_z",
    "rotation_x", "rotation_y", "rotation_z"
  ],
  "samples": [
    [0, 0, 0, 0, 0, 0],
    [0.012, -0.008, 0.004, 0.1, -0.04, 0.2]
  ],
  "source": "touch",
  "capture_version": 1
}
```

**This is a proposed schema, NOT yet existing in code.** Resolve its precise encoding and limits first. One sample per animation frame (or sparse/RLE samples expanded deterministically), six numbers each; avoid treating recorded motion as a 128-point manual keyframe layer. At up to 3000 frames, 3000×6 samples are feasible with bounded JSON/data size, but review render-manifest schedule size and HTTP payload limits before committing. Source labels are provenance only; never require a device to replay a take.

Required:
- Capture/compose in **native** camera velocities, degrees per frame, and exact project-frame indices, starting with frame-zero identity.
- Normalize finite values, valid axes, exact frame count, FPS/retiming rules, allowed Add/Replace and optional axis arming, per-axis safety clipping.
- Keep recorded samples **editable and non-destructive** and included in the same `motion_lab.layers` ordered composition flow.
- If project FPS/count changes, specify resample vs preserve frame-index behavior and test determinism. Do **not** silently shift recorded motion.
- Pause/reapply must not compound motion. Manual Editor changes must still require an explicit Apply rebase.
- Test four families: mathematical normalization, API preview/apply/save-reopen, interaction with presets/manual keyframes, and concurrency/security/payload limits.
- **Gate ML2.0:** green CI; simulated sample series compiled frame-for-frame to native `resolve_project_frame`. No UI or gamepad assumptions.

#### ML2.1 — Browser recording controls and keyboard/touch input

Build a **dedicated Motion Recording card inside Motion Lab** and explicitly move it into `panels.motion`.

Suggested first version: Start/Stop/Record, seek-to-frame, arm six axes, one or two thumb joysticks for X/Y, Z/pitch/yaw/roll controls, keyboard layout, per-axis sensitivity, deadzone, return/spring behavior, smoothing, optional pre-roll and a live frame/velocity status. Show a six-axis plot preview as input changes. **Responsive portrait mobile layout is mandatory.**

Timing:
- **The user's frame clock**, not GPU frame generation or a browser timestamp sequence, is the authoritative recording timeline.
- `requestAnimationFrame` is a sampling/visual input mechanism only; translate monotonic elapsed recording time to discrete `floor(elapsed * project_fps)` or another documented mapping, including dropped/duplicate event handling.
- Define playback speed separately from render FPS; when browser throttles/hides the page, stop or flag a gap. Do not backfill hidden frames with stale held input unnoticed.
- Key-up/pointer-up/blur/visibilitychange must release input; do not leave a camera moving after focus loss.
- Touch and keyboard input must work without HTTPS/gamepad permissions.
- Consider brief post-release deceleration as explicit recorded samples (not implicit renderer behavior).
- New recording can replace a take over a punch-in range or create a separate additive layer, but default action should not overwrite anything.
- Draft/preview using the existing `/motion-lab/preview` and `motion-lab-visual.js` charts, and persist only when the user selects **Apply to Animation**.
- A recording must be deterministic to replay regardless of input device, and must not depend on keeping a controller connected later.
- **Gate ML2.1 physical:** record and replay 48 frames at 12 FPS using keyboard on Windows and touchscreen on phone; check axis signs, start/stop latency, released controls return to zero, frame alignment, undo/redo, Apply/save/reopen, and Mobile browser rotation/navigation.

#### ML2.2 — Optional Gamepad API

Read browser Gamepad API client-side with polling inside the actual user gesture/focused tab and clear opt-in, device indicator, calibration/deadzone/sensitivity mappings, axis inversion, triggers/bumpers, disconnect/reconnect handling. Do not implement host XInput bridge by default.

**LAN caveat:** `http://192.168.x.x:7865` is often an **insecure origin**. Certain browsers restrict `navigator.getGamepads` to secure contexts, even with a controller physically connected. Gamepad availability depends on the browser and device the user is actually viewing, not merely the Windows box running Morphorum. Provide honest UI status and keyboard/touch fallback. If genuine LAN gamepad access is necessary, plan a supported local HTTPS dev/test path (including trusted cert), rather than falsely advertising support on plain HTTP.

Use friend's Motion Studio `controller.py` and GUI behaviors as approved algorithmic reference, **calibrate axis/units** for Morphorum. Document vendoring/permissions if source actually copied.

**Gate ML2.2 physical:** Windows browser with a known controller in a supported secure context, plus explicit fallback test on LAN HTTP and a phone with no controller. Verify no motion when disconnected, no spurious drift, correct trigger mapping and no double captures.

#### ML2.3 — Punch-in, motion cleanup, take management

- Arming/disarming individual axes, region-based punch-in/out, Add/Replace recording layers.
- Sensitivity, smoothness, spring return and soft limiting without wiping intentional sharp movement.
- Multiple takes and delete/rename/reorder; undo/redo remains stable.
- Save/reopen and deterministic conversion to existing native tracks, with screenshots/video clips for UX acceptance.
- No export or rendering feature creep in this phase.
- **Gate:** CPU preview checks and one short SDXL/GPU render using recorded motion, verifying cadence/LoRA/timeline consistency, MP4 export, and no unrelated regressions.

### Immediate first ML2 task

1. **Read current source**, especially `motion_lab.py`, `animation_projects.py`, `animation_resolution.py`, `frontend/dist/assets/animation.js`, `motion-lab-visual.js`, and current tests; verify branch/ref status, not old docs.
2. Choose exact `recording` sample schema and bounded FPS/memory semantics. Specify input-device-neutral samples and axis calibrations.
3. Write normalization + frame-accuracy + preview/apply/resume regression tests **first**.
4. Add a pure recording-series compiler to the existing Motion Lab `compile_motion_lab` layer loop.
5. Submit on **`feature/motion-lab`**, leave PR #19 **draft**, wait for physical acceptance before further milestones or merging.

### ML2 acceptance checklist (overview)

| Scenario | Expected |
| --- | --- |
| Keyboard/touch controlled motion | Correct six axes, visible movement in Motion Lab preview |
| Record at 12 FPS | Exactly frame-aligned samples, no dependence on machine/GPU inference speed |
| Pause/stop/focus loss | No stuck inputs, clock behavior documented and testable |
| Blend with Spiral + smooth keyframe curve | Respect layer order, Add/Replace, limits and clipping warnings |
| Undo/redo, save/reopen | Take survives without altering applied tracks until explicit Apply |
| Switch FPS or frame count | Explicit validated policy; no silent time shifts |
| Browser Gamepad not available | Useful fallback and clear message; no broken Motion Lab controls |
| 3D calibration-grid preview | Input velocities match actual compiled native camera schedules |
| Windows RTX 4080 SUPER short run | Stable existing SDXL/LoRA/cadence/3D rendering, correct export |
| Mobile portrait browser | No oversized checkboxes, scrolling bugs, misplaced cards or impossible touch targets |
| GitHub CI + branch protection | Both workflows green at exact PR head; checkpoint before merge |

---

## 7. Separate work and what's intentionally NOT in ML2

### B6 status

- B6.1 Deforum JSON import implemented.
- B6.2 source-video upload/inspect/FFmpeg extraction Windows validated.
- B6.3.1 extracted frames as diffusion anchors accepted.
- B6.3.2 hybrid-video opacity blending and source replacement regression accepted, merged to `dev-ui` in PR #18 at `bc40d18`.
- B6.3.3 **hybrid masks** planned separately and **PAUSED** on `feature/b6-3-3-hybrid-masks` with `docs/B6_3_3_HYBRID_MASKS_ROADMAP.md` on that branch.
- B6.4 compatibility/stability follows later. **Do not accidentally begin B6.3.3 or B6.4 while the user focuses on Motion Lab.**
- The Media UI is deliberately hidden only on Motion Lab branch, for focus. Do not delete the APIs or user source media.

### Later Motion Lab phases

- **ML3** audio-reactive motion: upload audio/FFmpeg decode/CPU bass envelope, transient pulses with attack/release, returning pulses without permanent travel drift; persist as independent layers and time-lock to project frames. No GPU audio model.
- **ML4** polished custom presets, Deforum six-axis settings export, deep 3D depth/cadence/LoRA/GPU regression tests, official Motion Lab PR review/integration.
- Optional future features, **not part of ML2**: true physically calibrated 3D path editing, automatic subject tracking, RAFT optical flow, Bezier absolute-camera rigs, ControlNet, RIFE/FILM, multi-video composites.

---

## 8. Known limitations, pitfalls and guardrails

1. **Reference-grid preview ≠ generated video.** It is a CPU diagnostic; depth/cadence/diffusion outputs can differ.
2. **Geometric camera path is auto-fit**: visualized accumulated motion, not absolute calibrated space. Dragging X/Y changes *per-frame* velocity at a frame and affects downstream positions.
3. **High-quality smooth interpolation already works**: preserve `linear`, `hold`, `smoothstep`, `smootherstep`, `cubic` semantics; do not replace it with decorative SVG splines.
4. **Motion Lab UI card placement matters**: dynamic tabs require explicit reparenting; test in desktop/phone.
5. **Project conflict handling is intentional**: Preview accepts recent unsaved Editor motion; Apply requires explicit confirmation when applied tracks were modified. Preserve idempotent Apply.
6. **3D-only composer** as currently built. New recording controls should follow this until explicit 2D conversion semantics are designed.
7. **Frame 0 fixed**, limited camera velocities, bounded 3000-frame compositions and 24 layers. Do not feed unvalidated controller floats directly into project schedules.
8. **No browser Gamepad promise over plain LAN HTTP.** Fallback must work.
9. **Old docs are stale.** The historical `handoff.md` before this update and `docs/CURRENT_STATUS.md` describe earlier B6 states (some falsely say compositing not implemented). Current source, frozen checkpoints, this updated handoff and `docs/MOTION_LAB_ROADMAP.md` take precedence. Previous root handoff remains retrievable from Git history at [the accepted checkpoint](https://github.com/merberg-ai/Morphorum/blob/c0e5f90a692e14e32b48155f71d0a8afc923c6ae/handoff.md).
10. **Branch hygiene**: no force-push/reset/merge without explicit user acceptance; keep `main`, `dev-ui`, paused B6 branches and recovery checkpoints intact.
11. **UI and browser navigation were human-tested** on the Windows host. Remote CI has no GPU; actual recording/gamepad/SDXL GPU features still need physical tests.

---

## 9. Source, test and documentation links

- [Morphorum repo](https://github.com/merberg-ai/Morphorum)
- [Motion Lab active branch](https://github.com/merberg-ai/Morphorum/tree/feature/motion-lab)
- [Draft PR #19](https://github.com/merberg-ai/Morphorum/pull/19)
- [ML1b accepted checkpoint](https://github.com/merberg-ai/Morphorum/tree/checkpoint/motion-lab-ml1b-smoothing-windows-verified-20261009)
- [Motion Lab roadmap](https://github.com/merberg-ai/Morphorum/blob/feature/motion-lab/docs/MOTION_LAB_ROADMAP.md)
- [Friend's Motion Studio](https://github.com/chicodog530/Deforum-Motion-Studio)
- [Frozen B6.3.3 planning branch](https://github.com/merberg-ai/Morphorum/tree/feature/b6-3-3-hybrid-masks)
- [Earlier B6 handoff in Git history](https://github.com/merberg-ai/Morphorum/blob/c0e5f90a692e14e32b48155f71d0a8afc923c6ae/handoff.md)

---

## 10. Paste this into the next chat

> Continue development of Morphorum Motion Lab from `feature/motion-lab`, using the current repository-root `handoff.md` and `docs/MOTION_LAB_ROADMAP.md` as handoff. We have completed and physically verified ML0, ML1a, ML1b and the smoothing/checkbox fixes. The latest frozen checkpoint is `checkpoint/motion-lab-ml1b-smoothing-windows-verified-20261009` at `c0e5f90a692e14e32b48155f71d0a8afc923c6ae`. PR #19 targets `dev-ui` and remains draft; `main` and `dev-ui` must not change yet. B6.3.3 hybrid masks remain paused. Begin **ML2: live camera motion recording**, first planning a versioned, frame-accurate `recording` layer integrated with the existing six-axis composer and native renderer, then keyboard/touch capture and optionally gamepads. Keep it desktop/mobile friendly, do not create another renderer, run CI, and stop for physical Windows acceptance before merging.

**End handoff. No ML2 work has been started.**
