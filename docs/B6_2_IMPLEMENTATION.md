# B6.1.1 and B6.2 staging

> **Validation update (2026-10-09):** B6.2 is now **physically validated**, not merely staged. Checkpoint: `checkpoint/b6-2-hybrid-source-lab-validated-20261008` at `5826d2d96eedbc6fcaa0243dc6dab6eaeb8366a0`. The browser-based hybrid-video upload, FFprobe examination, time/FPS-bounded FFmpeg frame extraction, cancellation and frame previews work. Later development and PR #14's promotion preserved this checkpoint. There is still **no hybrid source-frame synthesis/compositing**, which belongs to B6.3. The passages below document how B6.2 was built and contain historical “pending” wording. See [CURRENT_STATUS.md](CURRENT_STATUS.md).


## Import dialog readability

The Deforum popup now uses one scrollable dialog rather than nested scroll panes and a sticky action bar. Fields are full-width, long mapping values wrap within their cells, report sections remain in document flow, and narrow viewports stack mappings vertically. This is a CSS containment fix; parser and project mapping contracts are unchanged. Validate on the Windows browser at normal and 125–150% zoom plus phone width.

## B6.2 first staged code: safe media probe

`animation_hybrid_source.py` contains a separately testable managed source path and FFprobe JSON normalizer. This is groundwork, **not yet a video upload or frame extraction endpoint**. The module rejects path components, uses project-managed storage, bounds sizes and metadata, and never executes imported paths. The next implementation packet adds browser streaming upload, atomic managed asset persistence, deterministic FFmpeg extraction jobs, progress/cancel, per-project metadata, and a source frame preview. Hybrid render/composite is not enabled until B6.3.

Physical gates: first confirm the importer layout fix, then B6.1 short SDXL render; do not checkpoint B6.1 on file import alone.

## B6.2 managed upload backend packet

`PUT /api/animation/projects/{project_id}/hybrid-video` accepts browser-sent raw video bytes with `x-filename`; it streams to a bounded temporary file and only atomically replaces a previously accepted source after FFprobe accepts video metadata. `GET /api/animation/projects/{project_id}/hybrid-video?filename=source.mp4` re-probes the managed file. Both return `render_enabled: false`. Frontend upload selection, source manifest, extraction jobs, previews, cancel/restart, and rendering integration remain upcoming. The on-disk source is isolated under the project’s managed `assets/hybrid/` folder.

## B6.2 extraction implementation (physical test pending)

New dedicated Animation **Hybrid Source Lab** provides browser file selection, managed upload, time range and FPS extraction, cancellation, per-project FFmpeg PNG sequence staging, atomic publication, and a frame slider preview. Backend routes: `POST .../hybrid-extraction`, `GET .../hybrid-extraction/{job_id}`, `POST .../hybrid-extraction/{job_id}/cancel`, `GET .../hybrid-frames`, and `GET .../hybrid-frames/{frame_number}`. Frame extraction is bounded to 1200 frames; one extraction per project. No hybrid synthesis is wired into the B5 renderer.

Windows acceptance: select saved project; upload short MP4; inspect metadata; extract 0–3 sec at 12 FPS; scrub preview; try cancel; test upload through LAN laptop browser; confirm normal animation renders remain unchanged. This is not GPU-verified.
