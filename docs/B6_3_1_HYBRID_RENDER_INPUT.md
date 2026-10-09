# B6.3.1: Hybrid video frames as diffusion-anchor inputs

**Branch:** `feature/b6-3-hybrid-compositing`
**Gate:** automated regression CI, followed by a short physical Windows render before merging to `dev-ui`.

## Scope

This milestone connects B6.2's managed, inspected and extracted PNG sequence to the **existing** animation renderer. It does **not** implement video-source alpha compositing, mask tracks, optical flow or other B6.3.2/3 effects.

The Animation **Media → Source Video** section has two additional project-persisted controls:

- **Use extracted video frames for animation diffusion anchors**: disabled by default, so existing B5 renders are untouched.
- **Start at extracted frame offset**: zero-based source sequence offset (default 0), not a filename or host filesystem path.

When enabled:
1. At render submission, validate the project-owned `assets/hybrid/frames/manifest.json`. Missing/corrupt/unsafe frames, out-of-range offsets, invalid FPS, and stale extraction after a new video upload result in an actionable validation error.
2. Map each animation frame `f` at project FPS `R` onto extracted source FPS `S` using nearest-time sampling: `source_index = min(count, offset + floor(f*S/R + 0.5) + 1)`. Frames beyond the video use **hold-last**.
3. Freeze the *selected* source PNGs into `outputs/animations/<project>/<render>/hybrid-source/` before enqueuing. The frozen manifest with the full mapping is saved into the render's frozen project snapshot; a 2-GiB copy budget prevents accidentally replicating huge sequences. No arbitrary imported Deforum paths are read.
4. **Frame 0** is the first selected video frame, without txt2img, even when the project's normal start mode is Prompt.
5. At every **diffused anchor**, its time-aligned frozen video frame replaces the *img2img input image*. Native strength/noise/LoRA/prompt schedules, sampler and seed behavior remain intact.
6. **Cadence-skipped frames** continue from the normal preceding-frame 2D/3D camera warp, without a source-frame blend. B6.3.2 will add compositing and opacity control.
7. Per-frame PNG metadata, render-state telemetry, render job results and the persistent manifest identify the exact source frame, extraction FPS and whether that source was applied. Resume reuses the frozen PNGs even after new source extraction. A missing frozen file aborts rather than silently substituting current project assets.

### Test matrix

- Hybrid option disabled: existing render and image pipeline regression tests must stay green.
- 6-frame test, 12 FPS source and 12 FPS animation, cadence 3, retention strength 0.5: frame 0 starts from source 1; generated anchors at frames 3 and 5 take source frames 4 and 6.
- 24 FPS output with 12 FPS extracted sequence: nearest-time frame mapping and end-of-source hold-last.
- Reject path traversal, missing extraction, wrong offsets, and source-upload revision mismatch.
- Resume a partially completed render after re-extracting project source; generation must still reference the frozen original frames.
- **Windows physical acceptance:** extract ~2–4 s of an obvious moving clip, set animation size conservatively (e.g., 512×512), 12 FPS, 12–36 frames, cadence 1 or 3, native model/LoRA settings. Enable hybrid input, render and inspect starting/anchor frames. Compare with disabled mode; confirm export and resume behavior; monitor GPU memory and no CPU diffusion fallback. Do not use large clips for the first test.

### Known behavior

This stage intentionally does not interpolate source-video frames, warp the referenced source frame in 3D, blend it with the previous generated result, or apply masks. Such behavior belongs to B6.3.2/3, after this source-input integration is physically verified. Using a new source as img2img input at each anchor may cause visible jumps; this is expected at this stage and should not be described as final hybrid video fidelity.

`main` and `dev-ui` remain protected baselines until physical acceptance.
