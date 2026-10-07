# Visual Timeline UI

Timeline Alpha A4 adds the first visual editor for Morphorum's canonical animation
tracks.

The visual timeline is a client of the Timeline Alpha API introduced in A2. It does
not create a second browser-only schedule model.

## Visible tracks

A4 renders every editable descriptor currently registered by the backend:

- Positive Prompt
- Negative Prompt
- Angle
- Zoom
- Translate X
- Translate Y
- Strength
- Noise
- Steps
- Guidance

Future descriptor-backed tracks such as 3D camera, cadence, and explicit LoRA tracks can
appear in the same editor without inventing new CRUD routes.

## Timeline layout

The editor provides:

- a frame ruler,
- a playhead synchronized with the Resolved Frame Inspector,
- one lane per canonical track,
- visible keyframe markers,
- horizontal scale control,
- horizontal scrolling for longer animations,
- sticky track labels,
- responsive mobile layouts.

The browser derives visual positions from frame numbers. Project data remains expressed
as integer frames and canonical track values.

## Keyframe selection and editing

Click a keyframe to select it. The editor exposes:

- frame,
- value or expression,
- interpolation mode,
- Apply,
- Delete.

Numeric values remain Deforum-compatible expression strings. The browser does not
evaluate or rewrite those expressions itself; the backend timeline API validates and
stores them.

Prompt values use the same editor but expand the value area for text.

Required frame-zero prompt keyframes cannot be deleted.

## Adding keyframes

Select a track, position the playhead, then choose **+ Keyframe at playhead**.

The initial value is copied from the nearest preceding keyframe so adding a point does
not unexpectedly change the current animation state. The value can then be edited.

## Dragging keyframes

Editable keyframes can be dragged horizontally. On release, A4 calls the A2 move
endpoint with the target integer frame.

Moves do not overwrite an occupied frame implicitly. Collision errors are surfaced to
the user instead.

Required frame-zero keyframes remain fixed.

Pointer events are used so the same interaction works with mouse, pen, and touch.

## Interpolation

The editor obtains interpolation options from track descriptors instead of hard-coding
them.

Current modes are:

- prompts: `blend`, `hold`
- numeric tracks: `linear`, `hold`

Changing interpolation is persisted through the canonical track API.

## Persistence and compatibility fields

Timeline edits save immediately because the A2 keyframe APIs are project mutations.

The backend then synchronizes legacy fields such as:

- `prompts`
- `negative_prompts`
- `motion.zoom`
- `motion.angle`
- `generation.strength`

The existing raw schedule and prompt controls remain visible during A4 as an advanced
compatibility editor.

If those raw form controls contain unsaved changes when the user performs a visual
timeline mutation, A4 saves the current form payload first. This prevents an old raw
schedule from silently overwriting a newer track edit or vice versa.

After a visual mutation, the project form is refreshed from the saved server project,
so both representations remain visibly synchronized.

## Playhead synchronization

The visual timeline playhead and the existing Resolved Frame Inspector use the same
frame.

Changing any of these updates the others:

- inspector frame number,
- inspector slider,
- timeline frame number,
- ruler click,
- lane click,
- keyframe selection,
- keyframe drag preview.

The resolved-frame API remains the authority for renderer-facing state.

## Mobile behavior

On narrow screens:

- timeline labels become narrower,
- the track canvas remains horizontally scrollable,
- editor controls collapse into two columns and then one,
- action buttons expand into touch-friendly rows,
- keyframes use pointer events with touch drag enabled.

The timeline is intentionally not shrunk until individual frames become unusable.
Longer projects scroll horizontally instead.

## Raw schedule editor

The existing Deforum schedule fields remain available below the visual timeline during
the migration period.

For example, a user can still type:

```text
0:(1.0), 30:(1.005), max_f:(0.998)
```

Saving the project updates canonical tracks from that legacy-compatible schedule.
Refreshing or editing the visual timeline then displays those keyframes.

This compatibility editor is expected to become an advanced view rather than the
primary workflow as later timeline phases mature.

## Server terminal logging

A4 also changes the local server launcher so Uvicorn access logging is disabled by
default. Browser polling previously produced large amounts of terminal noise such as
per-request `GET /api/...` lines.

Morphorum's in-app Console still receives its structured API events, server events,
generation logs, warnings, and errors.

Raw Uvicorn access logs can be restored for diagnostics with:

```text
morphorum serve --access-log
```

or:

```text
MORPHORUM_ACCESS_LOG=1
```

The normal `run.bat`, `run-lan.bat`, `run.sh`, and `run-lan.sh` paths remain
quiet by default.
