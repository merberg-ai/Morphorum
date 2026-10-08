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
