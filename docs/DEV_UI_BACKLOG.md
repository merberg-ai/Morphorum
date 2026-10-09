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

## 4. Shared Morphorum modal dialogs for alerts, warnings, confirmations and input

**Status:** Planned, not implemented.

**Requested:** Replace default browser-native alert/confirm/prompt boxes with one reusable, consistently styled, accessible Morphorum modal system. It must support safety warnings, confirmations, informative messages and text entry, without breaking existing flows.

**Verified source findings (dev-ui baseline):**
- `frontend/dist/assets/app.js` currently implements lightweight nonblocking `MorphorumToast` notifications, but there is no reusable interactive dialog API.
- `frontend/dist/assets/animation.js` uses `window.confirm` for high-resolution render advisories, discarding dirty project changes during Deforum import and project switching; `window.prompt` is used when creating a new animation project.
- `frontend/dist/index.html` already uses a native `<dialog>` for Deforum settings import. That complex feature-specific dialog should remain; the shared alert/confirm/prompt service complements it, not replaces its importer workflow.
- JavaScript loads `app.js` (global UI services) before `models.js`, `image.js`, `loras.js` and `animation.js`.

### Proposed reusable dialog service

Implement a centralized frontend `MorphorumDialog` service (separate `modal.js` module or `app.js` with a single shared `<dialog>` host) and uniform CSS, with promise-based calls that can be `await`ed by existing asynchronous handlers:

- `MorphorumDialog.alert({ title, message, variant: 'info'|'warning'|'error', confirmText })` -> resolves after acknowledgment.
- `MorphorumDialog.confirm({ title, message, variant: 'normal'|'warning'|'danger', confirmText, cancelText, details })` -> resolves `true` only on an explicit affirmative action, `false` on cancel/Escape/backdrop.
- `MorphorumDialog.prompt({ title, message, initialValue, placeholder, maxLength, validate, confirmText })` -> resolves a string only on validated submission and `null` on dismissal; do not coerce cancellation into an empty value.
- Optional details/expandable diagnostics for long GPU memory advisories; keep summary short and readable.
- Support a compact warning icon or header accent for severity, but avoid huge colorful confirmation cards and use **danger** styling only for genuinely destructive actions.

### Interaction and safety requirements

1. A consistent, centered, mobile-friendly native `<dialog>` with overlay, spacing, typography and scrolling that does not reproduce the former Deforum popup overlap issue. Keep long text inside the modal, action buttons in visible normal flow, and provide mobile-sized touch controls.
2. Full keyboard behavior: move focus into modal, trap focus, restore focus to originating control on close, Enter submits the expected action, Escape cancels (never confirms), accessible dialog title/message, descriptive button labels, reasonable `aria-labelledby`/`aria-describedby`, and sensible handling for screen readers.
3. **Default-to-cancel** for destructive or render-costly confirmations. Never let backdrop/Escape accept an operation. Await a positive response before any side effect such as discarding edits, submitting a costly render, or replacing a source video.
4. Use `textContent`/text nodes for plain strings, never interpolate arbitrary user-supplied prompts, paths, filenames, imported settings, or backend errors as `innerHTML`. Treat all modal input as untrusted.
5. Serialize requests or otherwise handle simultaneous modal calls deterministically; every returned Promise must settle exactly once even if closed by escape, navigation, or error.
6. Keep `MorphorumToast` for transient nonblocking status updates; reserve blocking dialogs for actual acknowledgment, confirmation or required input. Avoid modal spam on normal routine generation telemetry.
7. If `showModal()` is unsupported, fail safely and visibly; do not silently auto-confirm. Avoid relying on native `window.confirm` except a consciously chosen last-resort fallback.
8. Migrate all existing `window.confirm` and `window.prompt` calls after setting up the service: high-res warnings; unsaved project changes (project change and Deforum import); new project naming. Integrate later with UI #1 reset draft and any future destructive actions, with clear labels.
9. Preserve existing `<dialog>` Deforum importer lifecycle; ensure shared dialogs do not trap focus behind it or conflict with it. In particular, dirty-state confirmation triggered **from inside** the Deforum importer needs correct topmost dialog focus/stacking, or an equivalent safe close/reopen sequence that does not lose import form data.
10. No backend API changes or changes to B5/B6 generation behavior are needed; this is frontend user-experience infrastructure.

### Acceptance for implementation

- Confirm from browser on Windows, Android and over LAN: high-resolution render advisory; discard unsaved animation edits from project switching; Deforum import discard confirmation while importer is open; create new project (valid, invalid, Escape).
- Test warning/info acknowledgment; safe defaults; backdrop/Escape cancellation; keyboard and screen-reader semantics; mobile sizing and 125–150% zoom; long warning content with optional diagnostics; concurrent dialog calls and correct Promise resolution.
- Ensure the user cannot accidentally start a render or lose edits because a dialog is dismissed. Verify the existing toast system and importer still work.

**Scope:** Add to the `dev-ui` planning backlog only. No app code changes until the user requests the consolidated implementation pass.

## 5. Responsive top banner, bottom navigation and compact global generation status

**Status:** Planned, not implemented.

**Requested:** On phone, make the header/status banner and bottom main navigation fit the usable screen, avoid cropping/overlap with mobile browser chrome, and display a compact live generation indicator/progress bar accessible from every page.

**Visual evidence:** User screenshot from Android accessing `192.168.1.24:7865` shows topbar telemetry cards pushed/clipped at the right, oversized header area and runtime version/build chip, and the bottom nav only partially visible immediately above the mobile browser's own navigation toolbar. This is responsive layout debt, not evidence of a telemetry backend failure.

**Verified source causes:**
- `frontend/dist/index.html` header contains brand mark/name, long runtime/version/branch/commit pill, and four CPU/RAM/GPU/VRAM telemetry cards.
- `frontend/dist/assets/app.css` sets `.telemetry-strip {grid-template-columns:repeat(4,minmax(112px,1fr))}`, with `.telemetry-item {min-width:112px}`. Mobile switches to two `minmax(0,1fr)` columns but telemetry labels and RAM/VRAM values use `white-space:nowrap`; the screenshot confirms these still overflow on narrow devices. Runtime chip is capped at `45vw` and ellipsized, consuming excess vertical space.
- Mobile `.main-nav` is `position:fixed; bottom:max(8px,env(safe-area-inset-bottom))`, while `.app-shell` has static bottom padding `88px`; this does not fully account for dynamically changing Android browser controls or viewport keyboard height. Six tabs share one narrow dock.
- `frontend/dist/assets/app.js` already polls CPU/RAM/GPU/VRAM telemetry every 2.5s, and `image.js` already receives `job.progress`, `current_image`, `current_step` and `total_steps`. Animation's `animation.js` polls render `job.progress`, current frame and ETA (~700ms). Reuse this state, **not** additional duplicate backend polling.
- `index.html` already sets `viewport-fit=cover`; use CSS dynamic viewport and safe-area primitives with tested fallbacks.

### Proposed topbar hierarchy

**Desktop:** Keep a restrained brand/status row, with compact 4-card system telemetry aligned right. Optionally expandable diagnostics for verbose build and GPU facts.

**Phone:** A compact one- or two-row header, not a tall card:
1. **Primary row:** small Morphorum logo/title + tiny live connection dot / concise server status. Do not show full branch and commit hash as a wide persistent chip; put version/branch/commit under a tap-for-details affordance (or About in header menu, with title tooltip on desktop).
2. **Secondary row (optional):** condensed system telemetry, e.g. small CPU/GPU and RAM/VRAM badges with values clipped/wrapped safely. Collapse to a **System** details popover or a horizontally scrollable, bounded row at very narrow widths; avoid unbounded horizontal page overflow and oversized RAM numerals.
3. **Active job strip:** compact semantic progress bar (3–5px) with short label: `Image 2/4 · 61%` or `Animation 32/75 · 43% · ETA 02:34`. Displays relevant loading/queued/finalizing/cancelled/error/completed states without claiming progress not reported by the backend. Tapping the strip jumps to Image progress or Animation → Monitor (UI item #2). Hide when truly idle or show very small latest-status indicator, avoiding wasted vertical space.
4. For multiple job types, prefer active job identification and clearly labelled selection, not mixing image percentage with animation percentage. Show latest updated only when valid. Do not claim a global job queue or perpetual background monitoring where it does not exist.

### Proposed mobile bottom navigation

- Redesign the six-item navigation as a compact app dock with consistent icon/short label, active state, accessible name and at least a ~44px touch target. For the narrowest screens consider four high-frequency items + **More** popup/secondary list for Models, Settings and Console, but preserve direct discoverability and do not bury essential destinations without an obvious More entry.
- Use `env(safe-area-inset-bottom)`, `100dvh`, appropriate layout fallbacks and a practical viewport keyboard strategy (including focusing prompt textarea). Ensure the bar sits visibly **above the Android browser toolbar**, not underneath it, and that opening the keyboard does not obscure text inputs or create huge empty gaps.
- Reserve bottom content padding dynamically based on dock height and safe area so final buttons/fields are not hidden by the dock. Toast positions must remain above the dock.
- No horizontal overflow, cut-off status pills, clipping, or full-page sideways scrolling at 320px, 360px, 390px, 412px, phone landscape and tablet breakpoints; maintain contrast and readable text at 125–150% zoom.
- Preserve deep-link navigation, active-state selection, primary app view routing, and all animation subtab behavior proposed in UI item #2.

### Shared progress architecture

- A **single front-end job status channel** (custom event or shared small UI state store) receives the already-available image and animation status updates. Reuse existing `image.js` and `animation.js` polling loops; do not introduce a third independent network poller or duplicate generation jobs.
- Header mini-bar represents **overall job progress only**. The detailed Animation Monitor retains the two dedicated overall and current-diffusion-step bars from UI item #2.
- Handle page switching, reconnect/reload, job completion and cancellation without stale `100%` or stuck `Rendering` indicators. Clear or time-limit completed status sensibly.
- Keep the UI cheap to update, avoid DOM thrashing or repeated image requests, and use accessible status/progress semantics without announcing every frame/step to screen readers.

### Acceptance for implementation

- Verify user's Android browser over LAN visually: entire banner/telemetry and bottom navigation fit inside usable viewport with no clipped RAM/VRAM or overlapping browser controls.
- Test both Android browser chrome expanded/collapsed, keyboard open, portrait/landscape, 320–430px widths and desktop/tablet layouts.
- Run an Image generation and an Animation render while navigating across tabs. Header mini-progress should show the correct job and open the matching detail/Monitor, while each source screen retains its own progress handling.
- Confirm navigation remains easy to tap, content remains scrollable to the last input, and console toasts remain visible above the dock. No backend or render engine changes.

**Scope:** Add to `dev-ui` backlog only. Defer implementation until the consolidated UI pass; preserve B6.2 checkpoint and feature branch.

## Next entries

Append items #6, #7, etc. as supplied by the user. Collect the list before implementing the UI pass.
