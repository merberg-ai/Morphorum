# Animation project format

Morphorum animation projects are stored as human-readable JSON in:

```text
projects/<project-id>/project.json
```

The project directory is intentionally broader than the JSON file. Later phases can place source images, masks, migration reports, thumbnails, and other project-owned assets beside the project state without changing the top-level storage model.

## Schema version 2

Timeline Alpha upgrades native projects to schema 2. The new canonical timeline lives in a top-level `tracks` bundle containing prompt, 2D camera, generation, and reserved 3D/cadence/LoRA groups. Existing schema 1 files are migrated automatically when loaded.

The legacy fields documented below remain synchronized during the transition so the current schedule editor and renderer-facing APIs stay compatible. See [TIMELINE_SCHEMA.md](TIMELINE_SCHEMA.md) for the track/keyframe contract and migration rules.

### Legacy-compatible project fields

Deforum-style schedule strings remain present as compatibility data while the UI moves to native tracks.

Example:

```json
{
  "schema_version": 1,
  "id": "night-city-8d93cfa1",
  "name": "Night City",
  "created_at": "2026-10-06T15:00:00+00:00",
  "updated_at": "2026-10-06T15:04:00+00:00",
  "animation": {
    "max_frames": 240,
    "fps": 24.0,
    "width": 1024,
    "height": 1024,
    "prompt_transition": "blend",
    "start_mode": "source",
    "source_image": "assets/source.png",
    "source_image_name": "starting-frame.png"
  },
  "model": {
    "model_id": "managed:zimage-turbo",
    "family": "zimage",
    "variant": "turbo"
  },
  "prompts": {
    "0": "a ruined futuristic city at night",
    "120": "a glowing alien city emerging from the ruins"
  },
  "negative_prompts": {
    "0": ""
  },
  "motion": {
    "angle": "0:(0), 120:(4), 239:(-3)",
    "zoom": "0:(1.002), 239:(1.008)",
    "translation_x": "0:(0), 120:(8), 239:(-4)",
    "translation_y": "0:(0)",
    "border_mode": "replicate"
  },
  "generation": {
    "strength": "0:(0.65), 239:(0.55)",
    "noise": "0:(0.02)",
    "steps": "0:(9)",
    "guidance": "0:(0)",
    "sampler": "flowmatch_euler",
    "seed": -1,
    "seed_behavior": "fixed",
    "seed_increment": 1
  },
  "notes": ""
}
```

## Sections

### `animation`

Timeline/output geometry shared by all model adapters:

- `max_frames`: number of animation frames.
- `fps`: target playback frame rate.
- `width`, `height`: requested frame dimensions.
- `prompt_transition`: `blend` or `hold`; controls how prompt keyframes resolve between frames.
- `start_mode`: `prompt` generates frame 0 with txt2img; `source` uses the uploaded image as frame 0.
- `source_image`: optional project-relative normalized image. It is the real frame 0 only when `start_mode=source`; otherwise it can still serve as the CPU camera-preview reference.
- `source_image_name`: original user-facing filename for the uploaded source.

### `model`

A stable reference to a Morphorum model-index entry:

- `model_id`
- `family`
- `variant`

The project keeps this reference even if the model is temporarily unavailable from the current index. A missing model should not silently rewrite project intent.

### `prompts` and `negative_prompts`

Maps of frame number to raw prompt text. Frame zero is always normalized into both maps.

Phase 2 resolves these keyframes into explicit from/to prompts and weights. The project stores the transition mode, while model adapters later decide how those weights become conditioning.

### `motion`

Raw Deforum-style 2D schedule strings:

- `angle`
- `zoom`
- `translation_x`
- `translation_y`
- `border_mode`: `replicate` or `wrap` for pixels exposed by 2D camera motion.

The project format allows additional motion keys to survive round trips so future 3D/depth fields do not require destructive migrations.

### `generation`

Model-independent animation generation state:

- `strength`
- `noise`
- `steps`
- `guidance`
- `sampler`
- `seed`
- `seed_behavior`
- `seed_increment`

Schedule-bearing values remain strings until the schedule engine resolves them for a frame.

## Forward compatibility

Morphorum preserves unknown top-level, motion, generation, animation, and model fields during a load/edit/save round trip wherever possible. This is deliberate. Native projects and imported compatibility data should not lose information merely because an older Morphorum build does not understand a future field.

## Persistence guarantees

Project writes use a temporary file followed by an atomic replace. A partially written `project.json` should therefore not be exposed as the current saved project after a normal save operation.

Project IDs are restricted to safe filename characters and project paths are constrained beneath Morphorum's `projects/` directory.

## API

Phase 1 exposes:

```text
GET  /api/animation/projects
POST /api/animation/projects
GET  /api/animation/projects/{project_id}
PUT  /api/animation/projects/{project_id}
```

Rendering is intentionally not part of this phase.

See [SCHEDULES.md](SCHEDULES.md) for Phase 2 schedule parsing, math expressions, validation, curve sampling, and resolved-frame state.
