# Interface language cleanup

## Scope

A presentation-only text cleanup on `dev-ui`, following the verified UI overhaul checkpoint `checkpoint/dev-ui-verified-20261009`. The checkpoint and the paused B6.2 branches remain unchanged.

- Removed milestone and internal phase names from headings, dropdown options, helper text, render warnings, import reports, Console events and model/LoRA messages
- Replaced development-oriented descriptions with concise explanations of what a setting does and when a user should choose it
- Removed the purely informational Animation Pipeline architecture card; it contained no interactive controls or API hooks
- Kept Deforum import, cadence/temporal blending, depth-aware projection, performance panels, FFmpeg video export, Hybrid Source Lab, GPU warnings and other functional features
- Changed the main header status to **Connected / Disconnected** instead of an always-visible development branch and Git SHA; version details remain available through the server API
- Preserved truthful limitations: extracted source video frames are for inspection and preparation, and do not yet condition animation rendering

## Physical acceptance

1. Hard-refresh on Windows and Android after updating `dev-ui`.
2. Inspect Image Generation, all four Animation workspace tabs, LoRA Manager, Models, Settings and Console for stale phase badges or text intended for developers.
3. Check high-resolution render confirmation, Deforum importer error and warning report, and video source upload/extraction success status.
4. Verify the existing SDXL image render and one short animation still start and finish correctly. No render parameters or file formats were intentionally changed.
5. Check that the former architectural description card is gone but Editor, Monitor, Media, Outputs and Video Export are still available.

The cleanup is not independently hardware-verified until these checks pass.
