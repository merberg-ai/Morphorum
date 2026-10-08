# 3D Camera MVP

This document tracks the first depth-aware 3D camera phase for Morphorum.

## Baseline

The verified 2D checkpoint is:

- main merge commit: `8e985a73630b4b025f82b5edd2afea2063421a59`
- checkpoint branch: `checkpoint/timeline-beta-b2-2d-working`

All 3D work begins from that exact state on:

`feature/3d-camera-mvp`

## B3-A1: canonical 3D camera schedules

B3-A1 activates the previously reserved `camera_3d` timeline group.

The canonical tracks are:

- `camera_3d.translation_x`
- `camera_3d.translation_y`
- `camera_3d.translation_z`
- `camera_3d.rotation_x`
- `camera_3d.rotation_y`
- `camera_3d.rotation_z`
- `camera_3d.fov`

Translations and rotations are signed.

Default schedules:

```text
translation_x  0:(0)
translation_y  0:(0)
translation_z  0:(0)
rotation_x     0:(0)
rotation_y     0:(0)
rotation_z     0:(0)
fov            0:(40)
```

Numeric tracks support `linear` and `hold` interpolation through the same Timeline API used by 2D and generation tracks.

The visual timeline automatically exposes the 3D tracks because it is descriptor-driven. Mobile focused-track mode therefore works for 3D schedules without a separate editor implementation.

## Resolver contract

`resolve_project_frame()` now includes:

```json
{
  "camera_3d": {
    "translation_x": 0.0,
    "translation_y": 0.0,
    "translation_z": 0.0,
    "rotation_x": 0.0,
    "rotation_y": 0.0,
    "rotation_z": 0.0,
    "fov": 40.0
  }
}
```

These values are authoritative schedule state only. B3-A1 does not yet warp images in 3D.

The Resolved Frame Inspector and schedule curve viewer expose all seven fields so schedule behavior can be verified before the depth renderer consumes them.

## FOV validation

Perspective projection requires a finite field of view strictly between 1 and 179 degrees.

Morphorum validates the resolved FOV across the animation timeline. The default is 40 degrees.

Signed translation and rotation values are intentionally not clamped.

## Planned B3 sequence

### B3-A1
Canonical 3D schedules, project persistence, timeline editing, resolver contract, and validation.

### B3-A2
Depth subsystem abstraction and cache.

Initial goals:

- depth-estimator interface,
- local model lifecycle,
- frame depth cache,
- diagnostic depth preview,
- low-VRAM-safe loading.

### B3-A3
Depth-aware camera warp MVP.

Initial renderer controls:

- translation Z,
- rotation X,
- rotation Y,
- FOV.

Render flow:

```text
previous frame
  -> depth estimate/load
  -> depth-aware camera warp
  -> hole/edge handling
  -> scheduled noise + img2img
  -> next frame
```

### B3-A4
Complete camera controls:

- translation X/Y,
- rotation Z,
- renderer telemetry,
- resume behavior,
- preview integration.

## Design constraint

The verified 2D renderer remains untouched as the known-good fallback while the 3D path is developed.

A 3D project must never silently fall back to a fake flat affine transform while claiming to be depth-aware. Until the depth renderer is implemented, the 3D tracks are schedule state and inspection data only.


## B3-A2: depth estimation and cache

A2 adds a reusable monocular depth subsystem without changing the animation renderer.

### Initial estimator

The first supported estimator is:

```text
depth-anything-v2-small
depth-anything/Depth-Anything-V2-Small-hf
```

Morphorum loads it directly through Transformers using `AutoImageProcessor` and
`AutoModelForDepthEstimation`.

A2 intentionally exposes only the Small checkpoint. It is sufficient to validate the
depth/warp architecture with modest memory use. Larger estimators can be added through
the same registry later.

### Relative-depth convention

Depth Anything V2 Small produces relative depth rather than metric distance.

Morphorum stores:

- the raw model output,
- a normalized float32 map in the range 0..1,
- a grayscale diagnostic PNG.

The A2 convention is:

```text
higher relative-depth value = nearer
preview white = nearer
preview black = farther
```

This convention is recorded in cache metadata. The values are not meters and should
not be displayed or interpreted as physical distance.

### Cache

Depth artifacts are content-addressed under:

```text
cache/depth/
```

The cache key includes:

- cache-format version,
- depth model repository ID,
- source image dimensions,
- source RGB pixel data.

Each entry contains:

```text
<key>.npz   raw + normalized float32 arrays
<key>.png   grayscale human diagnostic preview
<key>.json  model, source, range, convention and provenance metadata
```

Numeric and preview writes are atomic. Metadata is written last, and an entry is only
considered a cache hit when all three files exist.

The project itself stores only a lightweight pointer in:

```text
projects/<project>/assets/depth-preview.json
```

Replacing or clearing the project's source image invalidates this pointer. The global
content-addressed cache remains available, so restoring identical source pixels can
reuse the prior depth result.

### Renderer handoff

A3 can consume a cached map through:

```python
depth_manager.load_cached_array(cache_key)
```

which returns the normalized float32 HxW array. Raw model output is also available when
needed.

The renderer should not parse PNG previews.

### Memory lifecycle

The default A2 lifecycle is conservative:

```text
cache lookup
  -> if miss:
       load estimator
       estimate depth
       move output to CPU
       write cache
       unload estimator
       release CUDA cache
```

A cache hit performs no model load.

The UI blocks source-image replacement and animation render start while depth inference
is active.

### Lifecycle telemetry

The depth manager exposes lightweight status states:

- idle
- loading
- ready
- estimating
- error

The browser polls these while an uncached preview is running, so first-use model
download/loading is distinguishable from inference.

### 3D Depth UI

The Animation workspace includes a persistent accordion card named **3D Depth**.

It provides:

- estimator selection,
- auto/CUDA/CPU device selection,
- Generate Depth Preview,
- forced Recompute,
- Clear Preview,
- grayscale depth map,
- source resolution,
- raw model-output range,
- cache hit/miss status,
- near/far convention.

The depth card uses the existing browser-local accordion state.

### Physical A2 acceptance

Use a reference image with obvious foreground, midground and background separation.

Acceptance:

1. Upload the source/reference image.
2. Select Auto or CUDA.
3. Generate Depth Preview.
4. First use may download the estimator checkpoint.
5. Verify the preview is spatially sensible: foreground generally lighter and distant
   regions generally darker.
6. Confirm the UI returns to an unloaded depth-model state after inference.
7. Generate again without Recompute and verify a cache hit.
8. Use Recompute and verify inference actually runs again.
9. Reload the browser/project and verify the cached project preview returns.
10. Existing 2D animation generation must remain unchanged.

No 3D camera transform is applied in A2.

## Runtime build badge

The top-right runtime badge now uses the health API as the authority for:

- installed Morphorum package version,
- active Git branch,
- short Git commit.

Typical development display:

```text
v0.1.0a1 · feature/3d-depth-a2 · abc123def456
```

The browser does not hard-code a branch or release label. Switching branches with the
Morphorum updater and restarting the server changes the badge automatically.


## B3-A3: depth-aware 3D camera renderer

A3 turns the canonical 3D schedules and A2 depth maps into actual frame motion.

### Render pipeline

For every frame after frame 0 in a 3D project:

```text
previous rendered RGB frame
  -> content-addressed depth lookup
  -> CPU Depth Anything V2 Small on cache miss
  -> normalized relative depth
  -> perspective unprojection
  -> signed camera translation / rotation
  -> perspective reprojection
  -> nearest-depth z-buffer
  -> nearest-surface hole fill
  -> scheduled noise
  -> existing img2img diffusion
  -> next rendered frame
```

The diffusion model remains on its existing GPU path.

Depth Anything stays on CPU during an active 3D render. This is intentional for the
16 GiB acceptance target: SDXL can already consume almost all available VRAM during
img2img, so keeping the depth estimator resident on CUDA would make the first 3D
implementation unnecessarily fragile.

The CPU depth model is loaded lazily on the first cache miss, reused for subsequent
frames, and unloaded when the render completes, fails, or is cancelled.

### Camera conventions

Relative inverse depth is converted to a stable pseudo-scene range:

```text
near relative depth -> Z = 1 scene unit
far relative depth  -> Z = 4 scene units
```

These are projection units, not meters.

Camera schedules are applied per frame to the previous rendered image, so motion
compounds naturally.

Initial practical ranges:

```text
Translation Z:  about +/-0.02 to +/-0.08 per frame
Translation X/Y: about +/-0.01 to +/-0.05 per frame
Rotation X/Y:   about +/-0.25 to +/-1.0 degrees per frame
Rotation Z:     about +/-0.25 to +/-1.0 degrees per frame
FOV:            normally 25 to 80 degrees
```

Larger values are accepted but can expose large image regions or move the virtual
camera outside useful geometry.

Positive Translation Z moves the virtual camera forward into the scene; negative moves
backward. Translation X/Y and rotations are signed camera-space motion.

### FOV

FOV is an absolute camera property rather than a per-frame multiplier.

The previous frame's resolved FOV is used to unproject the source image, and the
current frame's resolved FOV is used for reprojection. This means an FOV keyframe
actually changes perspective rather than cancelling itself during unproject/project.

### Projection and holes

A3 uses a forward depth projection with a nearest-depth z-buffer.

When multiple source pixels project to the same destination pixel, the nearest
projected surface wins. Newly exposed pixels are filled from the nearest valid
projected surface before diffusion.

The render telemetry reports:

- current 3D translation and rotation,
- source and target FOV,
- depth cache hit/miss,
- depth-estimation time,
- projected pixel coverage,
- filled/exposed fraction,
- depth-warp implementation identifier.

The same state is persisted into each PNG's Morphorum metadata.

### Resume

3D resume uses the last completed RGB frame as the new source, resolves the prior FOV,
and obtains or recomputes that frame's depth map.

Because depth cache keys are based on source RGB pixels, an unchanged saved frame can
reuse the exact depth map created before interruption.

## Runtime-noise cleanup included with A3

A3 also reduces third-party terminal noise without muting Morphorum errors.

### torchvision

Morphorum now installs the official companion image package for Torch 2.14:

```text
torch 2.14.0
torchvision 0.29.0
```

This removes Transformers' CLIP/SigLIP PIL-fallback warnings and enables the normal
image-processor backend.

### Diffusers 0.40 empty float32 warning

Diffusers 0.40 emits a known spurious warning whenever its
`_keep_in_fp32_modules` list exists but is empty:

```text
There are modules in ... that should be kept in float32: [] ...
```

Morphorum filters only this empty-list warning. Non-empty float32 preservation warnings
remain visible.

### Other targeted noise

Morphorum also suppresses:

- Diffusers' internal SDXL `upcast_vae` deprecation warning,
- PEFT's multiple-adapter warning in Morphorum's intentional adapter-management path,
- Hugging Face and Diffusers progress bars during model/pipeline loading.

Morphorum's own Console progress, warnings, failures, model-load state and render
telemetry remain enabled.

## Physical A3 acceptance

Start with a short project before attempting a cinematic odyssey.

Recommended first test:

```text
Mode:          3D depth-aware
Frames:        12 to 20
Resolution:    512x512
Start mode:    source image
Translation Z: 0:(0.03)
Rotation X:    0:(0)
Rotation Y:    0:(0)
Rotation Z:    0:(0)
FOV:           0:(40)
Strength:      0:(0.65)
Noise:         0:(0.01)
```

Expected result: foreground objects expand/move more than distant background regions
as the camera advances.

Then test a gentle yaw:

```text
Translation Z: 0:(0.02)
Rotation Y:    0:(0.4)
```

Finally test FOV independently:

```text
FOV: 0:(40), 10:(55)
```

Acceptance criteria:

1. Render launches in 3D mode rather than falling back to 2D.
2. Depth inference reports CPU or cache in live telemetry.
3. Foreground/background show visible parallax.
4. Translation Z and Rotation Y visibly affect perspective.
5. FOV changes perspective across its keyframes.
6. Projection coverage remains sensible for gentle motion.
7. Diffusion stabilizes filled/exposed regions instead of catastrophic tearing.
8. Cancel unloads the depth estimator.
9. Resume continues from the last completed frame.
10. Existing 2D rendering still follows the unchanged affine path.
