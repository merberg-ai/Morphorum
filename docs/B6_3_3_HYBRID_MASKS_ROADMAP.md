# Morphorum B6.3.3 | Hybrid masks: roadmap and pause handoff

**State:** PLANNED / PAUSED. No B6.3.3 renderer or UI implementation has started.
**Planning branch:** `feature/b6-3-3-hybrid-masks`
**Branched from:** `dev-ui` merge `bc40d18d4f5968904afedc798ecd3efdef71761a` (PR #18, B6.3.2)
**Stable recovery branch:** `checkpoint/b6-3-2-hybrid-compositing-windows-verified-20261009` (same `bc40d18`)
**Predecessor:** `checkpoint/b6-3-1-hybrid-anchors-windows-verified-20261009` (`92e2a0d`)
**Primary hardware acceptance:** Windows, RTX 4080 SUPER (16 GiB), existing SDXL + LoRA environment
**Next release milestone after B6.3.3:** B6.4 compatibility polish, long-run acceptance, then promotion to `main`

> Resume instruction: The sole purpose of this branch at creation is to retain
> an actionable implementation design and exact code baseline. Do not mistake
> this planning commit for implementation or physical acceptance. The user has
> intentionally **paused B6.3.3** to work on other Morphorum features.

## 1. What is already complete: the starting contract

- B6.1 safe Deforum JSON import (compatibility/mapping preview, native project conversion).
- B6.2 Source Lab: browser upload, FFprobe inspect, FFmpeg extraction, cancel, preview.
- B6.3.1: optional frozen source frame 0 and time-aligned img2img diffusion anchors,
  including cadence-aware frame mapping and resume provenance.
- B6.3.2: optional CPU Pillow post-render source-over compositing, source opacity
  numeric schedules, per-frame metadata, and safe idempotent resume.
- Uploading a different video now invalidates old extraction; extraction manifests
  are tied to the accepted source revision; previews use no-store/cache-busting.
- Current `dev-ui` baseline from PR #18 passed Syntax and Backend workflows.

**Must not regress:** standard image/animation modes, GPU SDXL model residency,
text-encoder/UNet LoRAs and scheduling, 2D/3D camera and depth, future-anchor
temporal refinement, cadence skips, pause/cancel/resume, and MP4/WebM export.

## 2. Intended behavior and pixel contract

Masks selectively reveal the time-aligned *original video* over the finished
AI-generated frame. Existing video-opacity schedule `O(f)`, new mask-strength
schedule `S(f)` and grayscale mask pixel `M(x,y,f)` combine as:

```text
effective_opacity(x, y, f) = O(f) × S(f) × M(x, y, f)
output(x, y, f) =
    generated(x, y, f) × (1 - effective_opacity)
    + source_video(x, y, f) × effective_opacity
```

All inputs in `[0,1]`:

- Mask white (`255`) reveals source according to scheduled opacity/strength.
- Mask black (`0`) preserves generated output.
- Gray masks linearly blend.
- **Invert:** `M = 1 - M` before feathering/compositing.
- **Feather:** blur the mask's edges only; never blur the source/generated images.
- With masking disabled, existing B6.3.2 source-over blending remains unchanged.
- With video compositing disabled, mask settings must have no effect and should
  be disabled in the UI, not silently perform a different kind of rendering.
- Post-process after *all* diffusion, depth/2D/3D warps, cadence, and future-anchor
  interpolation. **Never feed composited frames back into diffusion.**
- Use the same crop/resize/alignment as source video when converting masks to
  the render's output image size. Define and test EXIF/orientation behavior.

## 3. Minimal v1 mask sources

**A. Static mask**

- Browser uploads grayscale PNG (one image), stored in project-managed media.
- Accept L or grayscale-equivalent RGB/RGBA PNG with documented conversion.
  Avoid arbitrary server paths/Deforum paths, SVG/script payloads or external URLs.
- Display a mask thumbnail with black/white polarity legend.

**B. Frame-aligned mask sequence**

- Accept an ordered series of PNGs (bounded number/bytes) from the browser.
- Explicit `mask_fps` for time alignment, initially defaulting to animation FPS.
- Map animation frame `f` to a mask by nearest-time sampling, documented
  zero-based offset; hold the last mask frame when the sequence ends.
- Clearly handle missing indices, unsafe filenames, duplicates and corrupt PNGs.
- Do not implement optical-flow tracking, segmentation, or inference-generated
  masks in this milestone.

## 4. Proposed persisted project fields

Extend the existing `hybrid` data under `animation_projects.py` with a
validated mask namespace. Suggested data structure (final names can be refined
without breaking existing project files):

```json
{
  "hybrid": {
    "enabled": true,
    "offset_frames": 0,
    "composite_enabled": true,
    "composite_opacity": "0:(0.35)",
    "mask": {
      "enabled": false,
      "source_mode": "static",
      "asset_id": "",
      "invert": false,
      "feather_px": 0,
      "strength": "0:(1)",
      "mask_fps": 12,
      "offset_frames": 0,
      "end_policy": "hold-last"
    }
  }
}
```

- `mask.enabled=false` by default for complete backward compatibility.
- Enabling a mask without a valid uploaded asset **or without hybrid compositing**
  must fail early with an actionable error before loading GPU models.
- Strict bounded values and numeric-schedule evaluation with the existing safe
  `schedules.py` parser; reject NaN, infinity, negative/oversized feather radius,
  illegal masks and values outside `[0,1]` before rendering.
- Existing B6.3.2 projects and render manifests remain readable.

## 5. Architecture: targeted integration points

| Component | Planned change |
| --- | --- |
| `animation_hybrid_source.py` / new mask asset module | Secure mask upload and image validation in managed project storage; never interfere with the accepted video/extraction assets. |
| `animation_hybrid_render.py` | Resolve mask strength and per-frame mask image; calculate effective per-pixel source opacity; extend current Pillow blend helper rather than adding a second compositor. |
| `animation_projects.py` | Normalize/save/reload opt-in mask settings without touching legacy B5 fields. |
| `animation_render.py` | During submit, freeze selected mask files into each render snapshot; during `_apply_hybrid_compositing`, use the mask and write per-frame provenance and render state. |
| `app.py` | Browser upload, masked asset metadata, safe preview endpoints, no-store media response headers and errors. |
| `frontend/dist/index.html` / `assets/animation.js` / `assets/animation.css` | Responsive Media section: static/sequence upload, preview, enable/invert, feather, strength schedule and status messages. |
| `tests/` | Upload/validation, mapping, exact pixel math, scheduled inversion/feather, resume, old project compatibility, UI and exporter tests. |

**Snapshot semantics:** A queued render must freeze its selected mask inputs,
mask FPS/mapping, validated settings, and source video inputs. Replacing a project
mask or uploading a new video must not change or corrupt an existing render or
its resume. Observe bounded disk budgets and cleanup of failed snapshots.

**Resume/idempotence:** Extend existing `hybrid_composite.applied` metadata with
mask identity, effective strength and mode. Skip already-composited PNGs on
resume; never double-blend. Do not attempt to reapply a different mask to a
previously composited output as if it were the original generated image.

## 6. Work packages and test gates

### B6.3.3a | Managed mask assets and preview

- Validate/upload static PNG and optional PNG sequence, with safe filenames,
  limits, and source/mask revision IDs.
- Add a dedicated browser preview and restore it when reopening the project.
- Regression-test rejection, replacement, cache invalidation, cancel/retry,
  mixed resolutions and mobile file picker.

**Gate:** CI + manual browser upload/preview (desktop and phone). No renderer changes.

### B6.3.3b | Mask state and schedules

- Persist normalized mask settings, enable/invert/feather and numeric strength.
- Provide clear UI gating when source video, extraction or mask is missing.
- Resolve keyframes deterministically and validate schedule bounds once per
  render before GPU work; add timeline preview if easily supported by current API.

**Gate:** Save/reopen on desktop/mobile, invalid-schedule errors, unit tests.

### B6.3.3c | Post-temporal masked blend + resume

- Reuse frozen source PNGs and add a per-render frozen mask snapshot.
- Composite after future-anchor interpolation and before thumbnail/MP4/WebM
  export, using deterministic mask frame mapping and orientation.
- Store `mask_source_frame`, strength, invert/feather, and applied state in
  saved PNG metadata and job manifest.
- Regression tests for black/white/gray masks, `O=0/1`, `S=0/1`, inversion,
  blur, static/sequence, FPS mismatch, hold-last, partial cancellation/resume.

**Gate:** green CI, then short actual SDXL GPU/Windows render.

### B6.3.3d | Acceptance and checkpoint

Windows test (initially **512×512**, 12 FPS, 24 frames, cadence 3):

1. Baseline non-hybrid render unchanged.
2. B6.3.2 video compositing with mask disabled looks unchanged.
3. White circular static mask: source video inside white, generated output
   outside black; then invert and verify reversal.
4. Feather mask ~8–16 px; confirm soft edge and scheduled strength
   `0:(0), 12:(0.5), 23:(1)`.
5. Animated PNG mask sequence at differing FPS; check alignment, source-frame
   hold-last and source/strength provenance.
6. Enable 3D depth, cadence and a known SDXL LoRA combination in a short run;
   watch CUDA memory and ensure no unexpected CPU diffusion fallback.
7. Cancel/resume and replace project mask after render start; the snapshot must
   remain reproducible. Verify final MP4/WebM against saved composited PNGs.
8. Validate phone browser mask preview/layout.

On acceptance, create `checkpoint/b6-3-3-hybrid-masks-windows-verified-<date>`,
merge the reviewed feature PR to `dev-ui`, then proceed to B6.4.

## 7. Out of scope: do not let B6 become endless

No AI subject segmentation, automatically tracked roto masks, RAFT flow,
ControlNet, RIFE/FILM, polygon editing, multiple stacked source videos, advanced
depth occlusion, or a full compositing node editor. Those are viable later phases.
B6.4 should focus on compatibility/export polish and long-run stability.

## 8. Exact pause and safe restart

At pause time:

- `dev-ui` HEAD: `bc40d18d4f5968904afedc798ecd3efdef71761a`
  (green post-merge Syntax/Backend checks).
- `main` remains at `4bc996be29104590a78ae84759a837a8a29a5135`;
  **do not promote unaccepted later work yet**.
- B6.3.2 checkpoint is frozen at `bc40d18`.
- `feature/b6-3-3-hybrid-masks` begins at that same code baseline. This file
  is the only intended change at the planning pause; B6.3.3 has NOT been coded.
- A different Morphorum feature can be developed on its *own* fresh branch
  from current `dev-ui`, without modifying the paused B6.3.3 branch.

To resume B6.3.3 later:

```powershell
Set-Location D:\Morphorum-test
.\update.bat feature/b6-3-3-hybrid-masks
```

If work on another feature has advanced `dev-ui` in the meantime, first compare
against current `dev-ui` and intentionally merge/rebase that newer baseline
into the B6.3.3 feature branch **without force-resetting or losing this plan**.
Begin with B6.3.3a and require the physical gates above.

**Next immediate action when returning:** inspect the current
`_apply_hybrid_compositing` and `blend_hybrid_video` functions, design managed
mask API/validation and write failing unit tests before changing GPU behavior.
