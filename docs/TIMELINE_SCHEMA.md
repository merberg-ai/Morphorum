# Animation timeline schema

Morphorum project schema 2 introduces a track/keyframe timeline while preserving the
existing Deforum-style schedule fields as a compatibility bridge.

The renderer-facing source of truth is now `tracks`. Existing schema 1 projects are
migrated automatically when loaded. During the transition to the visual timeline UI,
legacy prompt/motion/generation fields remain synchronized so the current editor and
older project tooling continue to work.

## Track bundle

A project contains:

```json
{
  "schema_version": 2,
  "tracks": {
    "schema_version": 1,
    "prompts": {},
    "camera_2d": {},
    "camera_3d": {},
    "generation": {},
    "cadence": {},
    "loras": {}
  }
}
```

`camera_3d`, `cadence`, and `loras` are reserved in Timeline Alpha so later
features can be added without another project-level schema redesign.

## Prompt tracks

Prompt tracks use native keyframe lists:

```json
{
  "prompts": {
    "positive": {
      "kind": "prompt",
      "interpolation": "blend",
      "keyframes": [
        {"frame": 0, "value": "a dark forest"},
        {"frame": 60, "value": "a ruined neon city"}
      ]
    },
    "negative": {
      "kind": "prompt",
      "interpolation": "blend",
      "keyframes": [
        {"frame": 0, "value": ""}
      ]
    }
  }
}
```

Prompt interpolation is stored per track and currently supports `blend` and `hold`.
This removes the old architectural restriction that positive and negative prompts must
share one transition mode.

## Numeric tracks

2D camera and generation tracks retain a Deforum-compatible schedule string and also
store a parsed keyframe cache:

```json
{
  "camera_2d": {
    "zoom": {
      "kind": "numeric",
      "value_type": "float",
      "interpolation": "linear",
      "schedule": "0:(1.0), max_f:(1.15)",
      "keyframes": [
        {
          "frame": 0,
          "frame_expression": "0",
          "value": "1.0"
        },
        {
          "frame": 119,
          "frame_expression": "max_f",
          "value": "1.15"
        }
      ]
    }
  }
}
```

Keeping the schedule string is intentional. It preserves Deforum-style mathematical
expressions exactly while the keyframe cache provides a structured representation for
the upcoming timeline editor. Numeric tracks support `linear` and `hold`
interpolation.

Timeline Alpha defines these numeric tracks:

- `camera_2d.angle`
- `camera_2d.zoom`
- `camera_2d.translation_x`
- `camera_2d.translation_y`
- `generation.strength`
- `generation.noise`
- `generation.steps`
- `generation.guidance`

## Migration and compatibility bridge

When a schema 1 project is loaded, Morphorum:

1. normalizes the existing project,
2. creates prompt tracks from `prompts` and `negative_prompts`,
3. creates numeric tracks from the existing motion/generation schedules,
4. bumps the project to schema 2,
5. writes the migrated project atomically.

No legacy schedule expression is intentionally rewritten during migration.

During Timeline Alpha, the old fields remain present. If the existing schedule-based UI
changes those fields, Morphorum refreshes the track mirror. If a track-aware client
changes `tracks` while the legacy fields are unchanged, Morphorum treats the track
data as canonical and synchronizes the compatibility fields from it.

This bridge is temporary architecture, not a second permanent timeline model.

## Resolved frame state

`resolve_project_frame()` now resolves prompt and numeric values from tracks. The
existing renderer contract remains stable, so animation rendering does not need a GPU
pipeline rewrite for schema 2.

Resolved frames include:

```json
{
  "timeline": {
    "schema_version": 1,
    "source": "tracks"
  }
}
```

The remaining resolved motion, prompt, generation, seed, model, and dimension fields
retain their existing shape.

## Future extensions

The reserved groups are intended for the already-planned work:

- `loras`: model-family-aware LoRA state derived initially from
  `<lora:name:weight>` prompt directives and later exposed as timeline controls.
- `cadence`: diffusion cadence and between-cadence frame behavior.
- `camera_3d`: rotation, translation, perspective/FOV, and later depth-assisted warp
  controls.

Legacy Deforum JSON import will translate into this schema rather than becoming a
second internal project format.
