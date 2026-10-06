# Deforum-style schedules

Morphorum Phase 2 implements a clean-room schedule parser/evaluator compatible with the familiar Deforum keyframe vocabulary.

The schedule engine is model-independent. It resolves animation text into numeric per-frame values before a model adapter is involved.

## Basic keyframes

A numeric schedule uses:

```text
frame:(value), frame:(value)
```

Example:

```text
0:(1.0), 100:(1.1)
```

At frame 50, linear resolution produces approximately `1.05`.

Numeric motion/generation fields currently use linear interpolation.

## Math expressions

Schedule values may be expressions:

```text
0:(1.0 + 0.02*sin(t/10))
```

A single expression remains active across the animation and is evaluated for each requested frame.

Expressions can also be blended toward later keyframes:

```text
0:(sin(t)), 100:(4)
```

Between frames 0 and 100, Morphorum evaluates both sides at the current frame and linearly blends their influence. This preserves the useful Deforum-style behavior where an oscillation can fade toward a later constant or expression.

## Variables

Supported built-in variables:

- `t`: current frame.
- `f`: alias for current frame.
- `max_f`: final frame index, equal to `max_frames - 1`.
- `s`: project base seed, or zero when the project seed is random.
- `seed`: alias for `s`.
- `fps`: project frame rate.
- `pi`, `e`: mathematical constants.
- `pw_a` through `pw_d`: reserved prompt-weight variables, currently zero unless a future caller supplies values.

## Functions

Supported safe functions include:

```text
sin cos tan
asin acos atan atan2
sinh cosh tanh
sqrt abs exp log log10
floor ceil round
min max pow
radians degrees
```

Morphorum also provides small convenience functions:

- `clamp(value, minimum, maximum)`
- `lerp(a, b, amount)`
- `where(condition, when_true, when_false)`

Example:

```text
0:(lerp(1.0, 1.08, clamp(t/max_f, 0, 1)))
```

## Safe evaluation

Schedule expressions are parsed through a restricted AST evaluator.

They cannot:

- import modules,
- access object attributes,
- call arbitrary Python functions,
- access files,
- execute shell commands,
- use comprehensions/lambdas or other general Python constructs.

The schedule language deliberately resembles mathematical Python expressions without being an `eval()` escape hatch.

## Expression-based frame positions

Morphorum accepts integer-resolving math expressions for frame positions as well as literal frame numbers.

Examples:

```text
0:(1.0), max_f:(1.1)
0:(0), "max_f-1":(5)
0:(0), (max_f+1)/2:(10)
```

The resolved frame position must be a non-negative integer.

This is useful for projects whose total frame count may change.

## Project fields resolved in Phase 2

Current numeric schedule fields:

```text
motion.angle
motion.zoom
motion.translation_x
motion.translation_y

generation.strength
generation.noise
generation.steps
generation.guidance
```

`generation.steps` resolves to an integer. The remaining fields resolve to floats.

Sampler selection remains a project-level string in Phase 2.

## Prompt transitions

Prompt keyframes are not combined into a fake text prompt.

Instead, the frame resolver returns a transition state:

```json
{
  "from_frame": 0,
  "from_text": "a dark forest",
  "to_frame": 100,
  "to_text": "a neon city",
  "from_weight": 0.75,
  "to_weight": 0.25
}
```

Projects can choose:

- `blend`: weights move linearly between prompt keyframes.
- `hold`: the previous prompt remains at weight 1 until the next keyframe.

A later rendering adapter can turn those weights into architecture-appropriate conditioning.

## Resolved frame state

The animation engine can resolve a project into a renderer-facing state without running diffusion.

For a single frame it returns:

- frame number and time,
- dimensions,
- selected model reference,
- positive/negative prompt transitions,
- resolved 2D motion,
- resolved generation values,
- deterministic seed where possible.

Random seeds remain marked as `random_at_render` until the future render manifest assigns the actual seed.

## Validation

The validator reports:

- malformed schedule syntax,
- unsupported expressions/functions,
- non-finite results,
- out-of-range keyframes,
- unsupported prompt transition modes.

Out-of-range future keyframes are warnings rather than destructive errors. This allows a user to temporarily shorten a project without deleting schedule information they may want again later.

## Phase 2 APIs

```text
POST /api/animation/resolve-frame
POST /api/animation/validate-schedules
POST /api/animation/schedule-series
```

These endpoints accept the current project payload directly. The browser can therefore inspect unsaved schedule edits without first modifying `project.json`.

## Next phase boundary

Phase 2 resolves values only.

Geometric frame transforms, image warping, motion-only preview frames, and diffusion rendering belong to later phases.
