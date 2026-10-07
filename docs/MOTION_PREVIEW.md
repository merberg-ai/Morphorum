# 2D motion preview

Morphorum Phase 3 turns resolved Deforum-style 2D schedules into real pixel transforms without loading a diffusion model.

The motion preview is a diagnostic tool. It answers a cheap question before an expensive render:

> Does this camera path actually move the way I intended?

## Project source image

Each animation project can own one starting image:

```text
projects/<project-id>/assets/source.png
```

The browser can upload PNG, JPEG, WebP, BMP, or another Pillow-readable image. Morphorum normalizes the stored project asset to RGB PNG while preserving the original filename as project metadata.

The project state stores:

```json
{
  "animation": {
    "source_image": "assets/source.png",
    "source_image_name": "my-start-frame.png"
  }
}
```

Replacing or clearing the source image does not alter prompt, motion, or generation schedules.

## Cumulative Deforum-style 2D motion

The following schedules are interpreted as per-frame transforms:

- `angle`
- `zoom`
- `translation_x`
- `translation_y`

For example:

```text
zoom = 0:(1.01)
```

does not mean “show the original source at 1.01× for every preview frame.”

It means each successive animation frame applies another 1.01× transform to the previous camera state. The camera motion therefore accumulates across time, matching the useful Deforum 2D mental model.

Morphorum avoids repeatedly resampling the image during preview. It multiplies the per-frame affine matrices into one cumulative transform and rasterizes only the preview frames that will actually be displayed. This keeps the camera path cumulative while reducing blur and CPU cost.

## Transform direction

Morphorum's image coordinate system uses:

- positive translation X: move content right
- positive translation Y: move content down
- positive angle: clockwise on screen
- zoom greater than 1: zoom in
- zoom equal to 1: no scale change

The transform origin is the frame center.

## Border modes

Phase 3 supports the classic two 2D edge strategies:

### Replicate

Pixels beyond an edge use the nearest edge pixel.

Useful when you prefer stretched edges over an obvious seam.

### Wrap

Pixels leaving one side of the frame re-enter from the opposite side.

Useful for motion styles where wrapping is acceptable or desirable.

Project state:

```json
{
  "motion": {
    "border_mode": "replicate"
  }
}
```

## Preview resolution

Motion preview is deliberately cheaper than final rendering.

The source image is:

1. EXIF-oriented.
2. Converted to RGB.
3. Center-cropped to the project's aspect ratio.
4. Downscaled so its largest dimension is at most 512 pixels by default.

Translation schedules are authored in project-resolution pixels. Morphorum scales those translation values into preview-resolution pixels before composing the affine matrices.

Angle and zoom are resolution-independent and do not require scaling.

## Preview frame sampling

Morphorum resolves every project frame's motion matrix, but it does not need to rasterize every frame for the diagnostic GIF.

By default it captures at most 72 evenly distributed preview frames while always including:

- frame 0
- the final project frame

GIF frame durations account for skipped project frames so the preview still represents the project's intended duration and FPS.

This makes long camera paths practical to preview without generating hundreds or thousands of full raster frames.

## CPU-only execution

Motion preview uses:

- Pillow for image decode/encode
- NumPy for affine matrices
- SciPy interpolation for edge-aware resampling

It does not:

- load SDXL, Flux, or Z-Image
- allocate CUDA model memory
- run diffusion
- apply prompt conditioning
- apply strength/noise schedules

Those generation settings remain visible in the resolved frame inspector, but Phase 3 motion preview is geometry only.

## Background jobs

Motion previews run as server-side background jobs:

```text
POST /api/animation/motion-preview
GET  /api/animation/motion-preview/{job_id}
GET  /api/animation/motion-preview/{job_id}/image
```

CPU preview work is serialized to one active render at a time so multiple browser tabs cannot unintentionally launch several expensive interpolation jobs simultaneously.

The browser polls progress and displays the completed animated GIF in the Animation workspace.

## Source image API

```text
POST   /api/animation/projects/{project_id}/source-image
GET    /api/animation/projects/{project_id}/source-image
DELETE /api/animation/projects/{project_id}/source-image
```

Upload requests send raw image bytes. Morphorum does not require a multipart-form dependency for project source images.

## Phase boundary

Phase 3 proves:

- resolved schedule values drive correct cumulative geometry
- source-image asset ownership works
- 2D edge modes work
- preview jobs work independently of diffusion
- mobile users can inspect the camera path cheaply

The next rendering phase can reuse the same transform engine on previous diffusion frames rather than inventing a second motion implementation.


## 2D zoom semantics

Morphorum follows Deforum's 2D zoom convention exactly:

- `1.0` = no zoom
- values slightly above `1.0` = zoom in
- values between `0.0` and `1.0` = zoom out
- `0.0` and negative values are invalid for 2D zoom

The value is a multiplicative factor applied every frame, so it compounds. Small values
are therefore appropriate for smooth motion. Useful starting points are:

```text
0:(1.005)   # slow zoom in
0:(1.0)     # static
0:(0.995)   # slow zoom out
```

For example, a constant `1.01` becomes roughly 1.64x cumulative scale after 50
transformed frames. A value such as `0.5` halves the image every frame and will
collapse the visible canvas almost immediately.

Signed toward/away camera motion is a separate 3D concept and will be represented by
`translation_z`, where zero is neutral and positive/negative values select direction.
