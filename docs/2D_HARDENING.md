# Timeline Beta B2: 2D hardening

B2 is the final focused hardening pass before Morphorum begins the depth-aware 3D
camera renderer.

The goal is not to add more 2D features. The goal is to make the existing renderer
observable and regression-tested enough that later 3D failures can be isolated from
prompt, schedule, seed, or img2img behavior.

## Live frame-state telemetry

Animation render jobs now expose `current_frame_state` alongside the B1
`current_prompt_state`.

The state comes from the same resolved frame object and transform matrix used by the
renderer.

It reports:

- frame number,
- whether the 2D transform was applied,
- per-frame angle,
- per-frame zoom factor,
- per-frame translation X and Y,
- border mode,
- cumulative 2D zoom,
- cumulative 2D rotation,
- cumulative center offset X and Y,
- retention strength,
- effective img2img denoise strength,
- noise,
- steps,
- guidance,
- sampler,
- actual render seed,
- seed behavior and increment,
- diffusion mode.

Diffusion mode is one of:

- `source`: uploaded source frame; no diffusion on frame 0,
- `txt2img`: prompt-generated frame 0,
- `img2img`: transformed frame plus diffusion,
- `transform-only`: transformed frame where retention strength is 1.0 and
  denoise is zero.

The Animation Render card displays this state live under the prompt telemetry.

## Cumulative 2D telemetry

2D motion is applied to the previous rendered frame, so small per-frame values compound.

B2 tracks the geometric transform chain with a cumulative 3x3 matrix. The UI exposes
the most useful decomposition:

- cumulative zoom,
- cumulative rotation,
- cumulative center offset.

For example, per-frame zoom factors of:

```text
1.01
1.02
1.03
```

produce cumulative zoom:

```text
1.01 * 1.02 * 1.03 = 1.061106
```

This is diagnostic telemetry. Diffusion changes image content after each transform, so
it should be interpreted as the cumulative camera transform applied by Morphorum, not
as a claim that every pixel remains an affine transform of frame 0.

## Saved frame metadata

Each rendered PNG stores both:

- `resolved`: the canonical schedule/prompt state,
- `render_state`: the B2 renderer telemetry state.

This makes a completed frame independently inspectable even after the live render job
has moved to a later frame.

## Resume behavior

A resumed render reconstructs the cumulative transform from all already completed
motion frames before rendering the next one.

The regression suite verifies that a resumed constant +1 px X translation reaches the
same cumulative +3 px center offset at frame 3 as an uninterrupted render.

## Renderer-level acceptance coverage

B2's fake SDXL renderer tests exercise the actual animation loop rather than only the
schedule resolver.

The combined 2D acceptance test covers:

- angle schedule,
- zoom schedule,
- translation X,
- translation Y,
- wrap border mode,
- strength and effective denoise,
- noise,
- steps,
- guidance,
- incrementing seed behavior,
- cumulative transform telemetry,
- saved PNG telemetry metadata.

B1's render-level blend test remains in place and B2 adds a render-level hold test.

For a four-frame hold transition:

```text
F0: forest
F3: city
```

the diffusion calls must receive:

```text
F1: forest
F2: forest
F3: city
```

## Physical GPU acceptance project

Before checkpointing B2, run one short SDXL project on the normal Windows test
installation.

Recommended shape:

```text
24 to 36 frames
512x512 or another inexpensive test resolution
incrementing seed
two dramatically different prompt keyframes
```

Use visible but sane schedules, for example:

```text
Angle:       0:(0), 18:(2), 35:(0)
Zoom:        0:(1.0), 18:(1.005), 35:(0.995)
Translate X: 0:(0), 18:(4), 35:(-3)
Translate Y: 0:(0), 18:(-2), 35:(2)
Strength:    0:(0.65), 18:(0.55), 35:(0.65)
Noise:       0:(0.01), 18:(0.03), 35:(0.01)
```

Prompt acceptance should be done twice if practical:

1. Hold mode, so the visual scene change is abrupt at the keyframe.
2. Blend mode, so the live prompt telemetry visibly shifts the endpoint weights across
   the transition.

During the render, compare the live Prompt telemetry and Resolved 2D / generation state
against the intended schedules.

B2 is considered physically accepted when:

- prompt telemetry changes exactly where expected,
- hold and blend behave as described,
- motion direction matches the resolved values,
- zoom remains sane and its cumulative telemetry explains the visible motion,
- strength/denoise and noise values match the schedules,
- seed behavior increments correctly,
- the render completes and preview is produced,
- resume preserves cumulative motion if interruption/resume is tested.

After B2 acceptance, create a known-good 2D checkpoint and begin the 3D depth/camera
engine.
