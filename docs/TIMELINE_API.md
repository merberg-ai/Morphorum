# Animation timeline API

Timeline Alpha A2 adds a generic editing and resolution API on top of the schema 2
track model introduced in A1.

The API uses canonical track paths such as:

- `prompts.positive`
- `prompts.negative`
- `camera_2d.zoom`
- `camera_2d.angle`
- `generation.strength`
- `generation.steps`

The API deliberately does not encode UI widget names. Desktop, mobile, and future
compatibility importers can all operate on the same track contract.

## Track descriptors

```text
GET /api/animation/timeline/descriptors
```

Returns timeline group metadata and editable track descriptors. Descriptors include:

- canonical track id,
- group and name,
- label,
- track kind,
- value type,
- unit when applicable,
- supported interpolation modes,
- whether frame zero is required,
- legacy compatibility field for numeric tracks.

The descriptor response already reserves `camera_3d`, `cadence`, and `loras`
groups. They are marked reserved until their later phases register concrete tracks.

## Project timeline snapshot

```text
GET /api/animation/projects/{project_id}/timeline
```

Returns the complete normalized track bundle plus descriptors and project timeline
context:

- timeline schema version,
- project id,
- frame count,
- FPS,
- duration,
- canonical tracks.

This is intended to be the initial state payload for the future timeline editor.

## Read one track

```text
GET /api/animation/projects/{project_id}/timeline/tracks/{group}/{name}
```

Returns the descriptor and normalized track state.

## Create or update a keyframe

```text
PUT /api/animation/projects/{project_id}/timeline/tracks/{group}/{name}/keyframes/{frame}
```

Body:

```json
{
  "value": "1.15"
}
```

The same operation creates a missing keyframe or replaces the value at an existing
frame.

Numeric values remain expressions, not prematurely converted constants. For example:

```json
{
  "value": "1.0 + 0.02*sin(t/10)"
}
```

Numeric edits are validated by the existing safe schedule engine before the project is
saved. Invalid functions, malformed expressions, and non-finite results are rejected at
the timeline API boundary.

## Delete a keyframe

```text
DELETE /api/animation/projects/{project_id}/timeline/tracks/{group}/{name}/keyframes/{frame}
```

Prompt tracks require frame zero and reject deletion of that keyframe. Numeric tracks
must retain at least one keyframe.

## Move a keyframe

```text
POST /api/animation/projects/{project_id}/timeline/tracks/{group}/{name}/keyframes/{frame}/move
```

Body:

```json
{
  "frame": 48,
  "overwrite": false
}
```

Moving a numeric keyframe converts its frame-position expression to the explicit target
frame. The value expression itself is preserved.

A move onto an occupied frame is rejected unless `overwrite` is true.

## Change interpolation

```text
PUT /api/animation/projects/{project_id}/timeline/tracks/{group}/{name}/interpolation
```

Body:

```json
{
  "interpolation": "hold"
}
```

Current modes:

- prompt tracks: `blend`, `hold`
- numeric tracks: `linear`, `hold`

Prompt interpolation is genuinely per-track. The legacy
`animation.prompt_transition` field mirrors the positive prompt track only, because
schema 1 had no way to represent independent positive/negative modes.

Timeline API writes therefore save with canonical tracks authoritative. This prevents
the legacy compatibility mirror from overwriting richer schema 2 state.

## Resolve a timeline range

```text
POST /api/animation/resolve-timeline
```

Body:

```json
{
  "project": { "...": "current project payload" },
  "start_frame": 0,
  "end_frame": 120,
  "step": 4
}
```

The endpoint accepts an unsaved project payload just like the existing frame resolver,
so the future editor can preview edits before saving.

The response contains the same renderer-facing frame contract returned by
`/api/animation/resolve-frame`, repeated for the requested range.

To avoid accidentally returning enormous JSON payloads, one request may resolve at most
2,000 frames. Use a larger `step` or a narrower range for longer projects.

## Compatibility behavior

A2 does not replace the renderer contract. Timeline edits synchronize the schema 1
compatibility fields required by the current UI and existing render code, while the
canonical schema 2 tracks remain authoritative for timeline-specific writes.

No diffusion pipeline, model loading, or low-VRAM Z-Image behavior is changed by this
phase.

## Phase boundary

A2 provides the manipulation layer needed by later work:

- A3 can register LoRA tracks and resolve their state through the same timeline model.
- the visual timeline can use descriptors instead of hard-coded field lists.
- 3D camera and cadence phases can add track definitions without inventing new CRUD
  endpoints.
- Deforum JSON import can translate imported schedules directly into canonical tracks.
