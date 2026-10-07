# Animation rendering

Phase 4 is Morphorum's first real Deforum-style diffusion animation loop.

It uses the same schedule resolver and 2D transform engine as the motion-only preview, then feeds each transformed previous frame into an image-to-image diffusion pipeline.

## Frame loop

Frame 0 is controlled by `animation.start_mode`:

- `prompt`: Morphorum generates frame 0 with the selected model's normal txt2img pipeline using the resolved frame-0 prompt/seed/steps/guidance.
- `source`: Morphorum uses the uploaded project image as frame 0, normalized to the project width and height.

For every later frame:

```text
previous rendered frame
        ↓
resolve this frame's schedules
        ↓
apply 2D angle / zoom / translation
        ↓
apply scheduled deterministic uniform noise
        ↓
img2img using resolved prompt / strength / steps / guidance / seed
        ↓
save frame PNG + metadata
        ↓
write render-manifest.json atomically
        ↓
next frame
```

The transformed diffusion output becomes the source for the next frame. Motion therefore compounds through the generated sequence rather than repeatedly transforming the original upload.

## Deforum strength semantics

Morphorum's animation `strength` schedule follows the familiar Deforum meaning: it describes how strongly the previous frame should be preserved.

This differs from Diffusers' img2img `strength` argument, which describes denoise amount.

Morphorum maps:

```text
diffusers_img2img_strength = 1 - deforum_strength
```

Examples:

```text
Deforum strength 1.00 → denoise 0.00 → preserve transformed frame
Deforum strength 0.65 → denoise 0.35
Deforum strength 0.20 → denoise 0.80
Deforum strength 0.00 → denoise 1.00 → maximum redraw
```

A resolved denoise strength of zero skips diffusion for that frame.

## Noise schedule

Phase 4 applies the project's `noise` schedule as deterministic uniform RGB noise after geometry and before img2img.

The amount is interpreted from 0 to 1.

A value of `0.02` adds a small amount of per-pixel variation. The noise RNG is derived from the frame's resolved diffusion seed, which makes resumed renders reproduce the same noise instead of inventing a different frame after recovery.

Additional Deforum noise types such as Perlin remain future work.

## Prompt transitions

The Phase 2 prompt transition state is consumed by the render adapters.

### Hold

The current keyframe prompt is passed directly to the model.

### Blend

Morphorum encodes the two surrounding prompt keyframes and linearly blends their model conditioning according to the resolved Phase 2 weights.

Adapter handling:

- SDXL: prompt, negative-prompt, pooled, and negative-pooled embeddings.
- Flux: T5 prompt embeddings plus pooled CLIP embeddings.
- Z-Image: Z-Image prompt embedding lists. Z-Image removes padding after text encoding, so surrounding prompts may have different token-sequence lengths. Morphorum pads only the shorter embedding sequence with zero vectors before weighted interpolation instead of truncating the longer prompt.

This keeps animation scheduling model-independent while letting each architecture receive conditioning in its native form.

## Img2img pipeline task switching

Morphorum's still-image model manager remains the owner of loaded diffusion weights.

Animation does not load a second independent copy of a model.

When animation needs img2img, the loaded pipeline wrapper is converted using Diffusers `from_pipe()`:

```text
SDXL:
StableDiffusionXLPipeline
↔ StableDiffusionXLImg2ImgPipeline

Flux:
FluxPipeline
↔ FluxImg2ImgPipeline

Z-Image:
ZImagePipeline
↔ ZImageImg2ImgPipeline
```

The underlying components are reused.

The manager records whether the current wrapper is `txt2img` or `img2img`. A later Image-tab generation automatically switches an animation-loaded model back to txt2img.

Still-image generation and animation inference share one inference lock, so two GPU jobs cannot use the same model state simultaneously.

Manual model unload is rejected while either still or animation inference is active.

## Output layout

Each render is self-contained:

```text
outputs/
  animations/
    <project-id>/
      <render-id>/
        source.png
        render-manifest.json
        preview.gif
        frames/
          frame_000000.png
          frame_000001.png
          frame_000002.png
          ...
```

If a project image exists, it is copied into the render directory at submission time. It is mandatory only for `start_mode=source`.

The render therefore uses a frozen project snapshot, frozen seed plan, and frozen source image when applicable even if the user edits the live project while the render continues.

## Render manifest

`render-manifest.json` is rewritten atomically after every completed frame.

It stores:

- schema version
- render/project ID
- render status
- frozen project snapshot
- frozen per-frame seed plan
- current frame and progress
- completed frame records
- timing/ETA state
- errors
- final preview metadata

Random seed mode is resolved into a complete seed plan when the render is submitted. Resume therefore keeps the exact same future seeds.

## Resume

If Morphorum stops after some frames are complete, the manifest and frame PNGs remain.

After restart, manifests left as:

- queued
- loading_model
- rendering
- finalizing

are presented as `interrupted` and resumable.

Resume scans for the first missing contiguous frame and continues from the previous completed PNG.

Completed renders are not resumable because there is nothing left to do. Apparently software occasionally gets to say that.

## Render preview

After all frames complete, Morphorum creates a lightweight GIF preview from up to 72 evenly sampled rendered frames.

This preview is for browser inspection. It is not intended to be the final video-delivery format.

FFmpeg MP4/WebM assembly belongs to the following video-output phase.

## Current supported model families

Phase 4 has img2img adapters for:

- SDXL
- Flux Dev
- Flux Schnell
- Z-Image Turbo

The first physical GPU acceptance test should use a short sequence before attempting a long animation.

## API

```text
POST /api/animation/renders
GET  /api/animation/renders/{render_id}
POST /api/animation/renders/{render_id}/cancel

GET  /api/animation/projects/{project_id}/renders
POST /api/animation/renders/{project_id}/{render_id}/resume

GET /api/animation/renders/{project_id}/{render_id}/frames/{frame}
GET /api/animation/renders/{project_id}/{render_id}/preview
```

## Phase boundary

Phase 4 produces real diffusion frame sequences and a browser GIF preview.

It does not yet provide:

- final FFmpeg MP4/WebM muxing
- audio
- diffusion cadence
- color coherence
- contrast scheduling
- Perlin noise
- 3D/depth warping
- optical flow

Those build on this frame-loop/manifest foundation rather than replacing it.
