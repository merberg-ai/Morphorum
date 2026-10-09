# B6.1.1 and B6.2 staging

## Import dialog readability

The Deforum popup now uses one scrollable dialog rather than nested scroll panes and a sticky action bar. Fields are full-width, long mapping values wrap within their cells, report sections remain in document flow, and narrow viewports stack mappings vertically. This is a CSS containment fix; parser and project mapping contracts are unchanged. Validate on the Windows browser at normal and 125–150% zoom plus phone width.

## B6.2 first staged code: safe media probe

`animation_hybrid_source.py` contains a separately testable managed source path and FFprobe JSON normalizer. This is groundwork, **not yet a video upload or frame extraction endpoint**. The module rejects path components, uses project-managed storage, bounds sizes and metadata, and never executes imported paths. The next implementation packet adds browser streaming upload, atomic managed asset persistence, deterministic FFmpeg extraction jobs, progress/cancel, per-project metadata, and a source frame preview. Hybrid render/composite is not enabled until B6.3.

Physical gates: first confirm the importer layout fix, then B6.1 short SDXL render; do not checkpoint B6.1 on file import alone.
