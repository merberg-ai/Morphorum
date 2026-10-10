# B6.3.2: Hybrid video source-over compositing (physical acceptance pending)

**Branch:** `feature/b6-3-2-hybrid-compositing`, created from the B6.3.1 merge commit `cb3dae1`.

## What changed

B6.3.1 used time-aligned extracted frames as img2img inputs at anchors. B6.3.2 adds an **independent, opt-in video layer** over the completed generated PNG sequence:

- Animation → Media → Source Video: **Composite source video over rendered frames** (off by default).
- **Video opacity schedule**: numeric Deforum-like frame schedule `0:(0.35)`; e.g. `0:(0), 12:(0.5), 24:(1)`.
- `0` = entirely generated image; `1` = entirely the time-aligned original video frame; intermediate values = linear source-over RGB blend.
- Uses the exact frozen, time-mapped source sequence from B6.3.1. The last source frame is held if a render outlasts the extracted clip.
- The compositor operates **after all diffusion, 2D/3D motion and future-anchor temporal refinement**. It never changes the images fed into later diffusion or 3D warps and cannot be overwritten by temporal frame rewrites.
- Compositing runs on the CPU after diffusion. It writes PNG metadata (`hybrid_composite`) and render-manifest `results[].hybrid_composite` with opacity and source-frame provenance.
- Interrupted post-processing is **idempotent**: already blended PNGs are marked and skipped after resume. Incomplete jobs can finish compositing when all generated frames already exist.
- Guardrails: invalid schedules, out-of-range opacity or compositing without hybrid source are rejected before starting diffusion.
- No changes to existing renders when either hybrid input or compositing is disabled.

**Not included yet:** keyed/transparency masks, subject segmentation, ControlNet/optical flow, tracked masks, optical-flow-consistent video reprojection, per-layer depth occlusion. These belong to later B6 work.

## Windows physical acceptance

1. Close Morphorum; update with `update.bat feature/b6-3-2-hybrid-compositing`, then launch.
2. Use a short, visually obvious source clip; **extract ~2 seconds at 12 FPS** (24 source frames).
3. Set animation **512×512, 12 FPS, 24 frames, cadence 3**, SDXL checkpoint known to work. Keep LoRAs at a previously verified setting, or start with none to isolate compositing.
4. Turn on **Use extracted video frames for animation diffusion anchors**, then **Composite source video over rendered frames**. Set video opacity `0:(0), 12:(0.5), 23:(1)`.
5. Render. Expect the first frame to use the source as in B6.3.1. Midway, generated imagery and video should be visibly mixed. Final frame should be wholly source-video imagery. All frames, including cadence-skipped frames, are composited in a CPU pass before the final preview and video export.
6. Repeat with `0:(0)` (compositing enabled but visually identical to B6.3.1) and `0:(1)` (output follows the source video). Try future-anchor temporal mode on a separate small render.
7. Confirm MP4 export and that inactive compositing does not affect a standard B5 animation. Optionally cancel during the compositing pass and resume to verify the idempotent path.

**Physical test gate:** do not merge this branch into `dev-ui` until these tests succeed. The `checkpoint/b6-3-1-hybrid-anchors-windows-verified-20261009` branch remains the recovery point.

## Implementation details

- Backend: `animation_hybrid_render.py` normalizes hybrid composite fields, resolves and validates the opacity schedule, and applies source-over with Pillow.
- Renderer: `animation_render.py` validates before submission, then applies an idempotent compositing pass in `_complete` before preview/video output.
- UI: HTML/JS/CSS Media controls persist settings via native project schema and can be used from desktop/mobile.
- Automated checks: Python schedule/opt-in/pixel/finalization tests, JavaScript UI regressions, repository syntax and backend self-test CI.
