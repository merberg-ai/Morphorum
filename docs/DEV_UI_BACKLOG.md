# dev-ui: Morphorum UI and usability backlog

This is a planning backlog only. Do not implement entries until the list has been collected and the user requests the implementation pass.

Base branch: `dev-ui`, originally branched from B6.2 validated checkpoint `5826d2d96eedbc6fcaa0243dc6dab6eaeb8366a0`.
Keep `feature/deforum-compatibility-hybrid-b6` and `checkpoint/b6-2-hybrid-source-lab-validated-20261008` unchanged. B6 resumes at B6.3 Hybrid Animation Integration after this UI pass.

## 1. Persist Image Generation form fields in browser local storage

**Status:** Planned, not yet implemented.

**Requested:** Preserve the prompt and other Image Generation tab inputs so they survive browser refresh, tab navigation, and reopening Morphorum.

**Current finding:** `frontend/dist/assets/image.js` has no localStorage persistence for the Image Generation form. `frontend/dist/index.html` contains the following form state:

- Positive prompt (`image-prompt`), negative prompt (`image-negative-prompt`).
- Selected model (`image-model-select`), resolution preset (`image-resolution-preset`), width (`image-width`), height (`image-height`).
- Steps (`image-steps`), sampler (`image-sampler`), guidance/CFG (`image-guidance`).
- Seed (`image-seed`), seed mode (`image-seed-mode`), seed increment (`image-seed-increment`), number of images (`image-count`).
- LoRA picker selection (`image-lora-select`) and weight (`image-lora-weight`) where available. Embedded LoRA directives inside the positive prompt naturally persist with it.

**Implementation requirements for later:**

1. Save only allowlisted form values to versioned `localStorage` key, e.g. `morphorum.image.form.v1`. Debounce text input writes; save selects/numeric changes on change, including programmatic UI actions (seed reuse, randomize, swap resolution, preset changes, LoRA insertion).
2. Restore asynchronously and in correct order: load models, select a model if still available, rebuild model-family capabilities/samplers/presets/LoRA list, and only then reapply valid persisted field values. Avoid overwriting restored values with hard-coded defaults during startup.
3. For missing models, unsupported samplers, removed LoRAs, or out-of-range numbers, safely use current valid defaults instead of preventing rendering. Preserve prompt text even if no model is available.
4. Keep form draft entirely in the current browser; no backend project writes or automatic cloud/network sync. Browser storage is per origin, so `localhost:7865` and `192.168.x.x:7865` are separate drafts, as are phone and PC.
5. Provide a deliberate **Reset Image Form** / **Clear Saved Draft** action with confirmation, without clearing unrelated site settings or generated images.
6. Add browser regression tests for restore order, changes, missing/stale models, and browser storage unavailability.

**Acceptance:** Enter prompts and generation settings, refresh browser, switch tabs and return, close/reopen browser, and verify values persist on the same browser origin; verify stale model gracefully falls back. Nothing persists as server-side project settings.

## 2. Redesign the Animation workspace with dedicated Monitor, Media, and Outputs views

**Status:** Planned, not implemented.

**Problem:** The current Animation tab is one tall collection of cards. The render progress and live preview are below many project, camera, timeline, and motion settings. Hybrid Source Lab and Video Export also sit inside the already oversized render card. A user must scroll significantly during active generation just to see progress and the latest frame.

**Verified source details (dev-ui baseline):**
- `frontend/dist/index.html` contains the Render card with model-load, progress, prompt and frame telemetry, live frame and animated preview, performance summary, hybrid media upload/extraction, and MP4/WebM export as nested sections.
- `frontend/dist/assets/animation.js` has an existing render polling loop (~700 ms), `job.progress`, `current_frame`, `total_frames`, `current_step`, `eta_seconds`, model-load progress and preview image URLs.
- `backend/morphorum/animation_render.py` sends current diffusion step and overall job progress. Its img2img step budget is `effective_steps = round(steps * denoise_strength)`, and cadence frames may involve no diffusion. The backend does **not** currently publish that effective step total as a stable dedicated telemetry value; do not divide `current_step` by the nominal steps schedule.

### Proposed internal Animation navigation

Use **secondary tabs inside Animation**, not additional items in the main site navigation, and retain the selected project and persistent render status header across views:

1. **Editor** (default): project/model configuration, prompt keyframes, visual timeline, cadence, start frame, camera/depth, motion preview, frame inspector, notes. Group advanced/expert controls in collapsible panels, not one endless page.
2. **Monitor**: primary render dashboard, selected render, start/pause/resume/cancel actions as supported, current phase/status, dual progress bars, latest generated frame large and above the fold, optional animated preview, compact ETA/performance details, link to completed output. Optionally switch here automatically when rendering starts.
3. **Media**: Hybrid Source Lab upload/FFprobe, bounded FFmpeg extraction, scrubber, project-managed video assets, and future B6.3 hybrid conditioning inputs. Preserve the tested upload/extraction flow.
4. **Outputs**: render history, completed render preview, image-sequence/results navigation, video export (MP4/WebM), playback, and download links. Keep outputs visible independently of the active render.

**Live status strip:** Across all four Animation subtabs, show compact status, frame count, overall percent, ETA and a **View Monitor** action while a render is active. On mobile use a small nonintrusive bar, not a huge overlay that covers inputs. Clicking it takes the user directly to the Monitor view. When no render is running, show latest status unobtrusively.

### Monitor layout and two progress bars

**Desktop idea:** slim top row with current project/render and run controls; below it a wide live frame preview on the left and a compact stats/progress stack on the right. Mobile: status/progress first, live preview immediately after, secondary diagnostics collapsed below.

- **Bar 1: overall animation progress** = existing `job.progress`; label `Frame N / Total · X%`. Must be monotonic through model load/render/finalization as appropriate, with nonmisleading phase labels.
- **Bar 2: current diffusion pass** = `current_step / current_step_total`; label `Diffusion step n / m`. Add a small backend field to publish the **actual effective step count** for the current frame/pass; do not infer solely from nominal scheduled steps. For `loading_model`, `queued`, `finalizing`, or cadence-interpolated frames, show explicit `Loading model`, `Waiting`, `Compositing`, or `No diffusion this frame` state rather than fabricated step percentages. Reset the second bar on a new diffusion frame to prevent a stale 100% display.
- Reuse model-loading progress as a distinct phase indicator, not as a third permanently visible bar. Preserve frame time, estimated remaining time, average frame time, and clear paused/cancelled/failed states.
- **Latest frame should be immediately visible** without scrolling, at usable size and preserving aspect ratio. Separate it from the completed GIF/video preview and don't refetch unchanged images needlessly.
- Put current prompts/weights, seed/LoRAs, resolved camera parameters, CPU/CUDA/VRAM/WDDM diagnostics into an **Advanced Diagnostics** expandable panel. Leave a small always-visible status/ETA row for day-to-day use.
- Finished render shows success state, last frame and direct **Open Outputs**; failed render shows a readable error plus supported Resume/Retry/Inspect actions, never a fake success state.

### Further usability suggestions to consider

- Preserve selected Animation subtab per browser, but auto-switch to Monitor on explicit Render start (with an optional preference to keep current view).
- Add a project identity banner and **dirty/unsaved** marker visible across subtabs so edits aren't lost when navigating.
- Add breadcrumb-like shortcuts: `Edit prompts` from Monitor and `Monitor` from Editor; no duplicate/conflicting render controls.
- Responsive layout and touch-sized actions on phone/laptop browsers.
- Keep existing active render polling and render history reconnect working when switching internal tabs or primary app tabs.
- Prefer moving existing DOM elements and reusing existing IDs and event handlers over duplicating state, creating two independent polling loops, or changing rendering semantics.
- Explicitly test accessibility: tab keyboard navigation, focus management, announceable progress values, hidden panels not receiving focus, no text overlap at 125–150% zoom.

**Acceptance for implementation:** During a 50–75 frame SDXL test, start the render and see both accurate progress bars and the latest frame without scrolling; switch Editor/Media/Outputs/Monitor and back while render runs without losing job state; demonstrate skipped cadence frames, model loading, cancel/resume, finished preview, video export, and phone viewport; do not regress legacy Deforum import or B6.2 extraction.

**Scope:** UI/telemetry polish on `dev-ui` only. No B6.3 hybrid synthesis, no changes to stable render behavior. Capture the rest of the backlog before coding.

## 3. LoRA Manager cleanup and Copy Prompt Tag with trigger words

**Status:** Planned, not implemented.

**Requested:** Make the LoRA Manager much more intuitive and compact, fix the oversized bottom `Include recorded trigger words` checkbox, and offer a **Copy Prompt Tag** button that includes available trigger words.

**Verified source findings (dev-ui baseline):**
- `frontend/dist/index.html` currently has a Library list/search/family selector at left and an ever-growing Details panel with metadata, raw diagnostics, optional Civitai lookup, runtime adapter audit and an insertion area at the very bottom.
- `frontend/dist/assets/app.css` applies `input {width:100%;min-height:43px;padding:9px 11px}` globally, while `.lora-manager-checkbox` only styles the surrounding flex label. The checkbox itself inherits the enormous dimensions. Fix locally with `.lora-manager-checkbox input[type="checkbox"] { width: 16px; height:16px; min-height:16px; padding:0; margin:0; flex:0 0 16px; accent-color:var(--accent); }` or equivalent; do not harm normal touch targets.
- `frontend/dist/assets/loras.js` currently uses local inspection `detail.trigger_words`, with optional `state.civitai?.trained_words` fallback, for the **Add to Image Prompt** action. `frontend/dist/assets/image.js` builds `<lora:name:weight>` and prepends comma-separated trigger words. The latter validates LoRA family and index before inserting into the selected Image model.
- LoRA training frequency tags (top_training_tags) are explicitly *not* guaranteed trigger words and must **never** be silently copied as triggers.

### Proposed layout

Retain a responsive **Library + Details** layout on desktop and a single-column/two-pane layout on mobile:

1. **Library:** compact model-family filter + search at top, scrollable selectable results, clear selected state; optional source/family pill per row and brief selection summary. Scanning status and action should stay visible without a huge vertical toolbar.
2. **Quick Use** directly below selected LoRA name at the top of Details, not below all metadata. Compact strength input, normal-sized **Include trigger words** checkbox, read-only live preview of the full prompt snippet, **Copy Prompt Tag** button and existing **Add to Image Prompt** button. The preview updates when strength/trigger checkbox changes.
3. **At-a-glance Details:** model family/base model compatibility, file size, format, LoRA rank and trigger provenance. Recorded triggers shown as easy-to-read chips, with a meaningful `Not recorded` state.
4. **Advanced details** behind expandable sections: training tags (labelled *not verified triggers*), tensor diagnostics, training metadata, raw metadata/tensor samples, and runtime adapter audit. Keep Civitai lookup in an optional **Online metadata** section, not the primary workflow.
5. At narrow screen widths, place the compact Quick Use area above collapsible metadata. Preserve readable wrapping, reasonable max heights, consistent card spacing, and full-size touch-friendly *button/label* surfaces while keeping checkbox glyph approximately 16–18px.

### Copy Prompt Tag semantics

- Reuse one **pure prompt snippet formatter** between clipboard copying and image-prompt insertion, with shared LoRA name sanitization, finite strength bounds (-4..4), canonical numeric formatting, trigger normalization/deduplication and safe comma separators. Avoid diverging tag behavior between actions.
- Example when triggers exist and checkbox is on: `trigger one, trigger two, <lora:LoRAName:1>`.
- Example with triggers unavailable/off: `<lora:LoRAName:1>`.
- Prefer explicitly recorded trigger words from local safetensors/sidecars. If the user explicitly fetched Civitai metadata and the local record has none, allow verified-response `trained_words` as fallback and clearly label the provenance; do not infer from frequent training tags.
- The **Copy Prompt Tag** action should function even if the Image tab has no model selected; it is a clipboard action, *not* activation/loading of a LoRA. Existing **Add to Image Prompt** must retain its model-family/index validation.
- When clipboard APIs are unavailable because Morphorum is served over HTTP on a LAN IP, use a safe fallback (temporary input/selection and legacy copy where supported, otherwise visibly selectable text + clear manual-copy feedback); never claim success before copying works. Show concise Copy/ Copied/ failure feedback and retain accessible keyboard behavior.
- Do not copy absolute local file paths, Civitai descriptions, unverified training tags or raw metadata into prompts.

### Acceptance for implementation

- Standard 16–18px checkbox and compact Quick Use controls at desktop, phone and 125–150% zoom.
- Select a LoRA and change strength or trigger checkbox: preview and copied content match actual **Add to Image Prompt** insertion.
- Test: no trigger words; recorded local triggers; fetched Civitai triggers; malformed names and weights; duplicate triggers; LoRA family mismatch; clipboard API available, unavailable, and restricted on HTTP LAN.
- Existing scan/index, Civitai lookup, runtime diagnostics and raw metadata remain functional, but no longer dominate the everyday workflow.
- No model loading, tensor inspector, runtime LoRA application or API behavior changes are needed for this UI-only item.

**Scope:** Backlog only, implement during the consolidated `dev-ui` pass after collecting the full list. Leave B6 branches and renderer untouched.

## Next entries

Append items #4, #5, etc. as supplied by the user. Collect the list before implementing the UI pass.
