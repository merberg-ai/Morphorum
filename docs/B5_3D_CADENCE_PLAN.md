# B5: Depth-Aware 3D Quality and Cadence Audit

## Branch and checkpoint

Active development branch: `feature/3d-depth-quality-b5`.

Created directly from the physically tested SDXL + Flux LoRA checkpoint
`checkpoint/b4-sdxl-flux-loras-working-20261008` at
`b6cec416053e9364d621534f67a325d44c52ba1a`.

The checkpoint and B4 branch remain unchanged. B5 improvements must retain
the shared image/animation LoRA loader, Flux non-streamed CPU offload on 16 GB
hardware, and the prior 2D/3D behavior.

## Cadence control discovery update

The B5 Animation UI puts a dedicated **Diffusion Cadence** card directly
after **Project**, rather than leaving the only editor buried in Generation State
(on mobile, that lower card was collapsed by default). The new card is expanded
by default on mobile and offers presets for cadence 1, 2, 3, 4, 6, and 8.
The existing `#animation-cadence` schedule field remains editable for
advanced keyframes such as `0:(1), 24:(3)` and keeps its original
`project.cadence.diffusion` representation. The Visual Timeline keyframe
track remains unchanged. Choosing a preset updates the schedule, marks
the project unsaved, and triggers validation; manually editing a custom
schedule does not overwrite it.

## B5.0 animation conditioning GPU memory fix

Physical Windows RTX 4080 SUPER test: SDXL
`artUniverse_sdxlV60_874843` at 512x512, 3D camera, with scheduled
`DonM0v3rC4ff31n4t3dXL` LoRA weight from 0 to 1.
A cadence-1 render rose from 13.9 GiB allocated after the first diffused
frame to 17.3 GiB by frame 8 (reported virtual CUDA allocation under
Windows WDDM) and repeatedly took 75 to 81 seconds for diffusion.
Cadence-3 transformed intermediate frames quickly, but anchor diffusion
could still stall ~75 seconds. The console explicitly recorded
`Model ready on cuda ... (native-gpu)`, so **this was not a
whole-model CPU fallback**. Depth Anything V2 was separately running
on CPU at 0.4 to 0.5 seconds per frame.

Root-cause code audit found `_prompt_conditioning_kwargs()` calling
SDXL/Flux `pipe.encode_prompt()` before the separate
`with torch.inference_mode(): pipe(**call_args)` region.
Diffusers 0.40.0 SDXL `encode_prompt` itself has no `@torch.no_grad`
decorator, so direct embedding generation could build autograd graphs
while CLIP weights have `requires_grad=True`. Those embeddings were
retained for the entire render in an **unbounded dictionary**, keyed
by LoRA adapter ID **and weight**. The test LoRA weight changed each
anchor, which meant repeated fresh encodes and long-lived graphs.
The allocated memory stopped growing after the LoRA weight reached
the final constant value, supporting this mechanism.

**Fix:** Apply `torch.inference_mode()` around the entire explicit
animation conditioning and blending function, not just Diffusers
`pipe.__call__`. Bound the conditioning-cache dictionary to eight entries
regardless of family, preserving prompt/LoRA signature isolation.
The global diffusion pipeline, CUDA device selection, SDXL LoRA loading,
and cadence itself remain unchanged. No CPU offloading was introduced.

Added CPU PyTorch regression tests to simulate an unfrozen text
encoder, assert gradients are disabled while encoding and that
the resulting embeddings hold no `grad_fn`, and verify bounded cache
size even with 10-14 distinct LoRA strengths for SDXL and Flux.

**GPU acceptance still required:** Re-run the same 26-frame cadence-3
scene and compare `allocated` and `diff` telemetry around anchors
3, 6, 9, 12, 15, 18. Expected: no monotonic ~0.5 GiB increase per
changing LoRA weight, and no periodic ~75 s diffusion stalls.
If allocation still grows, separately inspect PEFT
`set_adapters()` and Diffusers attention buffers with allocator
snapshots. A physical retest is required before accepting the fix.

## Cadence implementation audit

**Cadence is implemented in the actual animation render loop.**

| Component | Existing behavior |
| --- | --- |
| Default project | `animation_projects.py`: `cadence.diffusion = "0:(1)"` |
| Timeline editing | `animation_timeline.py`: `cadence.diffusion` integer numeric track with keyframe UI |
| Frontend | `animation.js`: cadence schedule field, timeline binding, resolved value, per-frame render telemetry |
| Resolution | `animation_resolution.py`: resolves each frame and validates cadence range 1 through 64 |
| Renderer | `animation_render.py`: frame `f` is an anchor if cadence <= 1, `f % cadence == 0`, or `f == total - 1` |
| Strength | An anchor only runs img2img if denoise strength is positive (`retention_strength < 1`) |
| Between anchors | 2D/3D camera transform still runs; scheduled noise, prompt conditioning and diffusion do not |
| Persistence | Every frame saved as lossless PNG with resolved cadence and diffusion mode; resume uses absolute frame indices |

Frame 0 is handled independently as a source image or txt2img starting
frame. Cadence scheduling controls frames 1 onward.

### Test coverage

- `test_diffusion_cadence_skips_intermediate_diffusion_but_keeps_motion`
  exercises cadence 2, seed alignment, skipped noise, and persisted metadata
  on a 2D animation.
- `test_3d_cadence_three_keeps_depth_camera_warps_and_forces_last_anchor`
  exercises cadence 3 with full depth-aware 3D projection at every frame,
  img2img only at frame 3 and forced-final frame 5, and per-frame metadata.
- `test_cadence_validation_rejects_out_of_range_values`, 
  `test_cadence_schedule_series_is_resolvable`, and
  `test_cadence_keyframe_crud_updates_legacy_schedule` cover validation,
  schedule evaluation, and the visual-timeline-to-legacy link.
- The preexisting interrupted-render tests cover persistent frame numbering;
  a physical interrupted cadence render remains part of B5 acceptance.

**Current limitation:** This is *forward-transform cadence*. An intermediate
frame is generated by transforming the previous rendered frame, **not** by
generating a later anchor in advance and tweening between two diffusion anchors.
Optical-flow-aware interpolation is not implemented.

## B5.1: Depth-aware projection quality and disocclusion masks

Implemented on the B5 branch, pending physical GPU/image-quality acceptance:

- `animation_3d.render_depth_warp()` now accepts `projection_mode` and
  `fill_mode`. Defaults stay `legacy`/`nearest`; existing projects,
  PNG rendering, and cadence keep their exact old path.
- **Legacy:** unchanged integer-rounded forward projection with closest-z
  source selection followed by nearest-visible-pixel fill.
- **Subpixel splat:** for each source pixel, distribute color to the
  neighboring four destination pixels with bilinear weights. A per-pixel
  nearest-depth buffer rejects color from farther competing surfaces before
  weight-normalized accumulation.
- **Fill modes:** `nearest` replicates nearby visible pixels.
  `background` preferentially fills holes from the farther 35% of
  projected depths, as a deterministic *heuristic*, not learned inpainting.
  Background fill is only used in splat mode; it can look worse in scenes
  with complex geometry and should be compared visually.
- **Disocclusion mask:** every 3D animation frame after frame 0 now stores
  a separate 8-bit `masks/frame_00000N.png`. Black (0) means explained
  by the projection; white (255) means the pixel was exposed/unsampled
  and filled for diffusion. The frame's embedded
  `render_state.depth_3d.disocclusion_mask` is a render-folder-relative
  path. `disoccluded_pixels`, `visible_pixels`,
  `projected_coverage`, and `filled_fraction` are recorded.
- **Animation UI:** 3D Camera Schedules now contains 3D Projection Quality
  (`Legacy` or `B5.1 subpixel splat`) and Exposed-Pixel Fill
  (`Nearest` or `Prefer background`). Both are persisted as plain
  non-keyframed `project.camera_3d` options and appear in resolved
  frame state.
- **Tests:** exact legacy compatibility, identity geometry, mask/coverage
  consistency, deterministic near-surface z ordering, invalid modes,
  options persistence, and a full 3D cadence-3 mock render in both modes
  with individual mask PNGs and frame metadata.

**Physical test gate** (do not claim pass without Windows GPU images):

1. Update B5 and restart the app. Reopen the existing known-working
   26-frame SDXL + LoRA / 512×512 / cadence 3 project.
2. Run once with `Legacy: nearest-pixel Z-buffer` and the existing
   `Nearest visible pixel` fill; retain that output as baseline.
3. Run identical settings/seeds with `B5.1: subpixel depth-tested splat`
   and `Nearest visible pixel`. Inspect image-edge quality, foreground
   occlusions, and frame consistency as the camera moves.
4. Repeat with `Prefer background layer`, focusing on freshly exposed
   pixels behind foreground objects. It may trade stretched foreground
   textures for a different background-color smear.
5. Inspect `outputs/animations/<project-id>/<render-id>/masks/` masks;
   validate that white pixels coincide with uncovered/disoccluded regions.
   Check frame PNG metadata for `depth_3d.disocclusion_mask` and
   `projection_mode`.
6. Compare frame times and VRAM allocation; no increase in GPU memory
   is expected because splatting and mask creation are CPU NumPy/Pillow
   operations. Stop if cadence-3 diffusion stalling returns.

**Limitations:** The preview frame given to img2img is always complete
RGB. No diffusion mask-conditioned inpainting is performed yet; the masks
enable a future inpainting step without losing true occlusion geometry.
Spline/optical-flow temporal interpolation is reserved for B5.2.

## B5.2: Temporal continuity with future-anchor depth reprojection

**Status:** Implemented on the B5 development branch. CPU/mocked integration
and syntax validation required before physical GPU/image acceptance. B5.1's
user-verified checkpoint remains at
`checkpoint/b5-1-depth-quality-gpu-verified-20261008` (`7bd68e7`).

### Behavior

- The original sequential cadence and all diffusion model/LoRA code stay
  unchanged. The default new project setting is
  `temporal.mode: forward` (exact B5.1 behavior).
- Opt-in `future-anchor` mode is available for **3D projects** in the
  Diffusion Cadence section. It does not enable extra diffusion passes.
- At each *diffused* anchor, Morphorum takes the future anchor's RGB image
  and estimates its depth on CPU. The depth cache is reused by the next
  normal 3D warp, avoiding a redundant depth estimate at that boundary.
- Each skipped 3D cadence frame since the preceding diffused anchor is
  reprojected from that **future anchor** into the intermediate camera pose,
  using composition of inverse camera rotations/translations and independent
  source/target FOV. Projection uses B5.1 subpixel Z-buffer splatting.
- A confidence-gated blend merges this future-aligned view with the
  already-rendered forward frame, protecting unrelated content from
  obvious double-exposure ghosts. B5.1 forward disocclusion masks receive
  a prioritized future-content repair **only where the future reprojection
  has valid geometry**.
- Updated intermediary PNGs retain their existing metadata and include
  `render_state.temporal`: mode, adjacent anchor indices, mix, contrast
  threshold, blended/repaired fractions, average weight, and projected
  coverage. The original B5.1 disocclusion masks remain untouched because
  they record the original forward projection.
- The **forward-only** baseline remains available in the UI, so A/B tests
  can compare identical models, LoRAs, prompts, seed, cadence, and camera
  movement.
- The feature supports intervals up to 32 frames; longer anchor gaps fall
  back to forward-only with a warning instead of using excessive CPU
  resources. No GPU memory is allocated by geometric blending.
- If a reverse projection or depth estimation fails, the corresponding
  segment remains forward-only, with a warning. Resume uses saved frame
  metadata to find the last diffusion anchor.

### Project fields

```json
"temporal": {
  "mode": "forward",
  "mix": 0.65,
  "contrast_threshold": 96
}
```

`mode` can be `forward` or `future-anchor`. `mix` ranges from 0 to
1. `contrast_threshold` ranges from 1 to 255 and suppresses blending
where two corresponding pixels disagree strongly.

### Physical Windows GPU test gate

1. Pull the latest B5 and **restart Morphorum**. Keep the B5.1 checkpoint.
2. Using the same known-good 26-frame 512×512 SDXL+LoRA 3D scene, set
   **cadence 3**, B5.1 **subpixel splat**, and start with
   **Forward-only (original cadence)**. Keep that output as the baseline.
3. Switch only **3D temporal continuity** to
   **Future-anchor depth-aligned tween**, with mix 0.65 and appearance
   guard 96. Use the same seed, settings, and prompts for a second render.
4. Compare intermediate frames 1–2, 4–5, 7–8 and corresponding anchors
   3, 6, 9. Anchors must not change; intermediates should show smoother
   transitions or better repair of exposed background pixels.
5. Confirm intermediate PNG embedded metadata reports
   `render_state.temporal.mode: future-anchor` with the correct
   `previous_anchor` and `future_anchor`. The independent forward
   disocclusion masks should still exist.
6. Inspect logs for `B5.2 future-anchor refinement updated...` and
   check SDXL diffusion times/VRAM remain comparable to the baseline.
   The refinement runs on CPU and may add processing time after each
   diffusion anchor.
7. Check a cancelled 3D render and Resume: completion should preserve
   all frame files with valid metadata. If there is a large prompt/LoRA
   subject change, inspect for residual ghosting and reduce mix.

**Limitations:** This is geometry-based two-anchor RGB reprojection and
confidence-gated blending. It is **not optical flow**, latent interpolation,
or neural video frame synthesis. It cannot invent unseen geometry, and
reprojection using a monocular depth estimate can be imperfect. This first
implementation prioritizes preserving the already-proven 3D, LoRA, and CUDA
pipeline. Further temporal filtering/optical flow can be scoped separately
after actual image comparisons.

## B5.3: CPU-only 3D camera preview, presets, and coverage metrics

**Status:** Implemented on `feature/3d-depth-quality-b5`; automated
checks pending Windows acceptance. B5.2 is independently preserved at
`checkpoint/b5-2-temporal-gpu-verified-20261008`
(commit `e69b70503563d899affb2bb484cbd77bdfd18bcb`).

### Motion preview

- Extends the existing `/api/animation/motion-preview` asynchronous job
  and animated GIF output to **3D projects**. Existing 2D affine preview
  remains unchanged.
- Uses the optional uploaded source/reference image. A source image is
  required **only for this diagnostic preview**. Real prompt-start
  rendering does not depend on it.
- Simulates sequential 3D depth warps on the CPU using the same
  `render_depth_warp` projection settings and resolved per-frame
  camera schedules used by real 3D renders. Depth Anything V2 Small
  is estimated per intermediate preview frame at up to **320 px**.
  The CPU depth estimator is released after preview completion/failure.
- Saves an animated GIF and a JSON per-frame coverage series,
  plus average, minimum, worst frame, and final projected coverage.
- Optional red overlay highlights **unexplained/disoccluded pixels**
  for captured preview frames. Red is a diagnostic and is never fed
  back into subsequent camera transforms.
- At most 180 project frames are supported for a 3D preview. Longer
  projects currently require a shorter diagnostic project/segment.
  GIF frames are sampled down to the existing 72-frame preview cap.
- No diffusion checkpoint or LoRA is loaded by the motion preview.
  Unlike full renders, intermediate frames are **never rediffused**.
  Strong camera motion therefore accumulates forward-warp artifacts;
  preview coverage is a planning aid, not a prediction of final
  diffusion-corrected quality.

### Camera presets

The 3D Camera Schedules card offers one-click conservative
`0:(constant)` values for the **six** translations/rotations:

- Slow dolly in/out;
- Orbit left/right (yaw with small lateral translation);
- Pan left/right (yaw-only);
- Tilt up/down (pitch-only);
- Still camera reset.

The preset operation resets the six **motion** schedules only.
It intentionally leaves FOV, projection/fill, depth resolution,
cadence, source mode, prompts, LoRAs, and model unchanged. Applying
a preset marks the project unsaved so the user can inspect/edit it
before saving. Regular manual keyframes remain supported.

### Performance diagnosis from Windows Oct 8 console + screenshot

- SDXL checkpoint `artUniverse_sdxlV60_874843` reports
  **`Model ready on cuda ... (native-gpu)`**. This explicitly rejects
  the hypothesis that diffusion was CPU-offloaded.
- At anchor frames PyTorch reports about **14.0–14.4 GiB allocated**
  and 14.3–14.5 GiB reserved on the 16 GiB GPU. GPU utilization
  in the screenshot was 100%. Diffusion per anchor typically took
  **6–10 s**, with a slower outlier around 14.8 s.
- CPU Depth Anything V2 Small performs relative depth estimation
  on every intermediate frame, around **0.45–0.5 s** per frame.
  Forward-only motion frames complete around **0.5–0.6 s**,
  with `diff 0.00s` showing no diffusion pass.
- Header's **RAM FREE 51.2 / 63.6 GiB** at the captured moment
  means system RAM was not exhausted. VRAM free was just 0.24 GiB.
- Three changing SDXL PEFT LoRAs were logged across prompt windows;
  their injected parameters put additional pressure on GPU memory.
  An optimization pass should profile LoRA residency and CUDA peak
  memory separately, *not* silently enable CPU offload for SDXL.
- The supplied Oct 8 console capture had **no**
  `B5.2 future-anchor refinement updated...` messages. Those two
  75-frame renders alone do not establish that the opt-in B5.2
  mode was enabled, though both completed successfully.

### Physical Windows GPU/UI test gate

1. Pull B5.3, restart Morphorum, and load the 75-frame three-prompt
   project (or a reduced 30-frame copy). Keep the successful B5.2
   checkpoint available.
2. Under 3D Camera Schedules choose **Slow dolly in** and Apply.
   Verify the Z schedule becomes `0:(0.02)`, and the other five
   motion schedules are reset. FOV, LoRAs, prompts, and other settings
   must remain unchanged. Save and reload.
3. Upload a **reference image** in Start Frame if one is not
   already present. Start Mode may still remain Prompt.
4. Generate Camera Motion Preview. Ensure progress advances, a GIF
   appears, and the coverage panel shows avg/minimum/worst/final
   statistics. No GPU model load should occur.
5. Enable the exposed-pixel overlay, preview again, and inspect red
   areas around edges and surfaces appearing behind moving objects.
   Compare against the non-overlay preview.
6. Repeat with Orbit left and a gentle Pan/Tilt preset; inspect
   orientation, clip and disocclusion behavior. Extreme motion
   should lower projected coverage rather than trigger inference OOM.
7. Switch to 2D mode and verify its original affine preview works.
8. If you test the B5.2 feature itself, explicitly select
   `Future-anchor depth-aligned tween` under Diffusion Cadence and
   confirm the console logs `B5.2 future-anchor refinement updated`
   at later anchors.
9. For SDXL performance comparisons, use identical seed/schedules/
   model/LoRAs and record anchor diffusion time, GPU VRAM reserved,
   and number of resident LoRAs. B5.3 does not change this pipeline.

## B5.4: FFmpeg video output (implemented, pending physical Windows test)

**Checkpoint:** B5.3, validated on Windows with the preview GIF,
is preserved at `checkpoint/b5-3-preview-gpu-verified-20261008`
(commit `cd280280e3e5df8f3dad2ff2f8c7f4c4a3d1a99d`).

B5.4 adds MP4/WebM outputs from **existing completed animation PNG
sequences**. It never performs diffusion or reloads any model/LoRA.
A completed render's immutable `render-manifest.json` supplies the
original FPS and total-frame count. All frames `frame_000000.png`
through `frame_N.png` must exist before encoding starts. Interrupted
or cancelled renders must be resumed to completion first.

Backend:

- `GET /api/animation/video/availability`: host FFmpeg installation.
- `POST /api/animation/renders/{project_id}/{render_id}/video`:
  enqueue encoding with optional format/quality/fps; omitted or null FPS
  uses the original render-manifest FPS.
- `GET /api/animation/video/jobs/{job_id}`: async export status and progress.
- `GET /api/animation/renders/{project_id}/{render_id}/videos`:
  export history from persistent JSON records, including after restart.
- `GET /api/animation/renders/{project_id}/{render_id}/video/{format}/{quality}/{fps}`:
  download ready video. `?inline=true` enables HTML5 playback.

Encoders: MP4 H.264 via `libx264`, WebM VP9 via `libvpx-vp9`;
`high`, `balanced`, and `compact` map to codec-specific CRFs.
Inputs retain original dimensions; FFmpeg scales to even dimensions for
`yuv420p` as required. No audio. Constant frame rate 1–120 integer FPS.
The encoder uses argv with no shell, writes a `.part` file and atomically
renames on success, logs FFmpeg diagnostics, and rejects missing frames,
unsupported options, or duplicate concurrent variant jobs. Exports live
under `outputs/animations/<project>/<render>/exports/`.

The Video Export panel is in Animation Render for both 2D and 3D
completed renders. It offers format, quality, override FPS, progress,
HTML5 playback, download, and saved export discovery. A missing FFmpeg
installation is reported to the user before the export starts.

**Windows installation:** `ffmpeg.exe` must be on the Morphorum host's
`PATH`, or the `MORPHORUM_FFMPEG` environment variable must point
to its full executable path. Restart Morphorum after changing either.
LAN clients and phones do not need FFmpeg installed.

### B5.4 physical Windows acceptance gate

1. Confirm Video Export shows `FFmpeg ready`. If FFmpeg is absent, the
   panel should show installation guidance instead of affecting renders.
2. Select an already-completed 75-frame render. Export MP4 at Balanced
   quality with FPS left blank (uses original project FPS). Verify video
   plays, downloads, has all frames, and no model loads.
3. Export the same render as WebM. Both encodings should coexist inside
   the render's `exports/` directory. PNGs, masks, GIF, and render
   manifest must be unaffected.
4. Change renders, return, restart Morphorum, and confirm the MP4/WebM
   exports remain available without encoding again.
5. Export at another FPS/quality. Separate variants must not overwrite
   the earlier files. FPS adjustment changes playback speed, not frame
   synthesis.
6. Running/cancelled renders should not be exportable. A missing numbered
   frame must return a descriptive error rather than silent truncation.
7. CPU encoding and FFmpeg progress should be observable. No CUDA
   diffusion model or depth estimator should load for this phase.

The backend/browser suite covers validation, encoder command construction,
job lifecycle, persisted records, download routes and completion gating.
Actual Windows codecs and browser playback remain at the physical gate.

## B5.5: Performance and stability validation (physical GPU gate)

**B5.4 accepted and protected:** user verified MP4/WebM video export;
checkpoint `checkpoint/b5-4-video-export-windows-verified-20261008`
at `f5db57cab8173c5a8038762a20bb5cc5650f2bd7`. Development
continues on `feature/3d-depth-quality-b5`. **Do not start B6 until
B5.5 is accepted on the Windows GPU.**

### Scope and deliberately safe changes

The pipeline was physically verified for SDXL/Flux LoRA influence,
and the memory regression caused by autograd graphs in prompt
conditioning was already fixed. B5.5 therefore does **not** change
model placement, scheduler, steps, LoRA adapter weights, cadence,
CUDA allocator cache policy, or depth renderer. A speculative switch
to CPU offload on an RTX 4080 SUPER would harm throughput. It is more
useful to observe the real cause of slow diffusion anchors.

New `backend/morphorum/animation_performance.py` adds:
- A compact append-only `performance.jsonl` beside the existing render
  manifest, with **one record per completed frame** after source frame
  0. Each record includes total/prepare/conditioning/diffusion/warp/
  depth/temporal/save/manifest/memory stage seconds, CUDA free/
  allocated/reserved and *process-high-water* peaks, device/optimization,
  task, active LoRA adapter names/weights, loaded (resident) LoRA count,
  and bounded conditioning-cache occupancy. The log contains no prompts,
  images, model tensors, or filesystem paths.
- No CUDA synchronization, `empty_cache`, forced garbage collection
  or parameter transfers are added for diagnostics. Peak numbers are
  **process-wide since the last PyTorch reset**, not per-frame peaks.
  `cuda_before` and `cuda_after` capture allocator state and do not
  pretend to measure driver-side shared RAM or page faults directly.
- A small persisted `performance` summary in render status/manifests:
  observed frames, diffusion anchors, average diffusion time, cumulative
  stage time, maximum observed allocated/reserved VRAM, maximum resident
  adapters, current device/optimization, and last 24 slow anchor indices
  (an informational 30+ second threshold, **not an error or offload**).
- Crash/restart support: rehydrates diagnostic history from the
  frame-number-keyed JSONL file, ignores truncated records, and repairs
  an unterminated record before appending. A resumed run does not count
  already-completed frames twice.
- A read-only endpoint at
  `GET /api/animation/renders/{project_id}/{render_id}/performance`
  returns summary plus frame records; it rejects traversal and render-ID
  mismatches. The Animation Render UI shows a compact diagnostic summary
  and a direct link to the JSON report.

The LoRA residency audit confirms adapters are intentionally reused
across task switches and changing prompt windows. B5.5 records both
active and cached-resident counts to determine whether the number of
adapters correlates with VRAM growth **before** imposing an eviction
policy. Existing LoRA cache and live weighting remain unchanged.
The SDXL `native-gpu` log and earlier measured 14 GiB allocations
do **not** constitute CPU generation. Depth Anything on CPU is
separate and expected. Any remaining 75-second anchors need real
per-frame correlation with VRAM/driver memory pressure.

### Physical Windows acceptance procedure

1. Pull B5 branch and restart. Keep the B5.4 checkpoint unchanged.
2. Use the **same 512×512 SDXL scene** with fixed seed, unchanged sampler,
   steps and denoise. First run **26 frames, cadence 3, one scheduled
   LoRA**, including any changing LoRA weights.
3. From the Animation Render summary and frame-by-frame JSON, confirm
   `pipeline_device: cuda` and `optimization: native-gpu`. Observe
   anchor diffusion seconds versus `cuda_before/cuda_after` allocated
   and reserved VRAM. Intermediate frames should show
   `diffused: false` with zero diffusion time.
4. Repeat with your known-working **75-frame / three-prompt** project
   and multiple LoRAs. Verify adapter activation changes exactly with
   prompt windows; `resident_loras` may grow as new adapters are first
   loaded but should not grow for repeated selection of the same adapters.
   Observe trends in cumulative and maximum VRAM and diffusion times,
   especially around LoRA transitions.
5. Run the same project with no LoRA or a single constant LoRA as a
   controlled comparison, if latency is still unexpectedly high.
   This distinguishes LoRA residence cost from image size, diffusion
   steps, model loading and Windows WDDM oversubscription.
6. Test cancel/resume in a short scene, including a 3D project with
   future-anchor refinement. Ensure completed PNGs, disocclusion
   masks, temporal metadata and video exports remain correct.
   `performance.jsonl` and the persisted summary must preserve earlier
   frames without duplicate counts.
7. Restart Morphorum, select the completed render and use **View
   frame-by-frame JSON** to confirm performance history remains
   accessible. Both 2D and 3D exports should work from existing
   PNGs, independently of model loading.
8. Compare output frames and LoRA/prompt influence with the B5.4
   checkpoint. **No visual output changes are expected** in B5.5.
   If stable and performance is acceptable, checkpoint B5.5 and close
   B5; begin **B6** on a new development branch only afterward.

Do not claim a measurable speed improvement until the physical
tests provide comparable timings. If actual VRAM exhaustion/Windows
shared-memory spill is confirmed, scope a targeted optimizer (e.g.,
adapter residency cap) under a separate physical-test gate without
risking the verified checkpoint.

## Proposed B5 work order

1. **B5.1 Depth warp quality**: retain the original Z-buffer/occlusion mask,
   improve splatting/resampling, track disoccluded pixels, and add controlled
   fill/inpaint preparation instead of unconditional nearest-pixel smearing.
   Keep geometry deterministic and test with artificial depth discontinuities.
2. **B5.2 Temporal continuity**: cache/reference depth more intelligently,
   test coherence across 3D camera steps, and introduce optional future-anchor
   interpolation/tweening. Preserve existing cadence 1 and simple cadence N
   as selectable baseline modes.
3. **B5.3 Camera preview/UI**: expose depth-aware motion-only preview,
   presets for dolly/orbit/pan/tilt, and explicit occlusion/coverage metrics
   before expensive diffusion.
4. **B5.4 Video output**: FFmpeg-based MP4/WebM assembly from existing PNG
   sequences without rerendering.

## GPU acceptance before changing the cadence algorithm

Use a known-working SDXL checkpoint + LoRA for a short 512x512 3D project:

1. Render with `0:(1)` to verify all eligible frames denoise.
2. Render the same project with `0:(2)` to verify skipped intermediate
   diffusion, depth-aware movement, and proper anchor restoration.
3. If stable, test `0:(3)`; check the final frame is an anchor even
   when its index is not divisible by three.
4. Inspect frame timing and coherence, including disocclusion artifacts,
   and test cancellation/resume.
5. Repeat with Flux only after 3D SDXL quality and VRAM use are acceptable.

Do not claim a 2x speedup without measurements. Depth estimation,
camera warping, PNG output, and animation manifests still run on
intermediate cadence frames.
