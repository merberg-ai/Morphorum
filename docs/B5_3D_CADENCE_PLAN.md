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
