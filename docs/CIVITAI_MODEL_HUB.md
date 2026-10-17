# Civitai Model Hub roadmap

The optional Civitai Model Hub is developed on `feature/civitai-model-hub`. It is disabled by default.

## C1.0: Settings foundation (implemented)

Settings → Civitai Hub contains:
- Enable/disable preference (default off)
- Mature preview policy (default off)
- Preview thumbnail preference
- Automatic update-check preference (saved now, not yet scheduled)
- Grid/list layout and download concurrency preferences (saved now, used in later stages)
- **Test Connection** button: POST `/api/civitai/test-connection`

The connection test contacts Civitai only when explicitly clicked and only when the feature was **enabled and saved**. It sends no model hashes. A personal API token is optional and supplied to the host process using `CIVITAI_API_TOKEN` (environment variable), not browser settings. The API returns diagnostic status, but never the token or an upstream response body. The toggle is a preparatory feature flag; browser, download queue, and background checks do **not** exist in C1.0.

Existing local model browsing, generation, and opt-in LoRA Civitai lookup remain unchanged regardless of the Hub preference. Turning off the Hub does not delete existing files.

## Roadmap

- **C1.1**: Backend API client, search, model-type/base-family filters, pagination and disabled-state guards.
- **C1.2**: Responsive gallery; visible only when enabled.
- **C1.3**: Model versions, image gallery, metadata and compatibility information.
- **C2.1–C2.2**: Destination-aware download queue, progress, cancellation, resume, integrity checks; disabling Hub must stop or safely retire active Hub jobs.
- **C3.1–C3.3**: Local hash identification, updates, thumbnails, metadata sync and duplicate handling.
- **C4.1–C4.2**: Prompt/checkpoint integration and bulk management.

Only supported SDXL, FLUX and Z-Image runtime formats should be selectable for generation. Never overwrite existing external checkpoint/LoRA files without user approval.

## C1.0 UI polish and acceptance conventions

- Keep toggles at normal checkbox dimensions; use paired label/control tiles and bounded-width dropdowns, never full-workspace selects.
- Reuse existing Morphorum toast notifications for success and errors. Use discreet screen-reader live regions instead of redundant raw status text.
- Show a spinner, disabled button, and descriptive busy label during every asynchronous Civitai operation; always restore the button on success or failure.
- Apply these responsive and accessible feedback patterns throughout search, filters, gallery, metadata, download queue, update checks and model management.
- Prefer bounded content sections on wide desktop screens and a single-column layout at mobile widths. Test desktop and mobile before approving each stage.

## C1.1: Read-only search API (implementation committed, awaiting runtime verification)

`GET /api/civitai/models` performs server-side model discovery only when `civitai.enabled` is saved as true. The backend supports `query`, `tag`, `username`, `model_type` (Checkpoint/LORA), `base_model` (supported-family Civitai values), `sort`, `period`, `cursor`, `limit` (1–50), and `allow_mature`. Responses contain normalized model cards and `next_cursor`; they do not include file downloads or raw API responses. Do not use offset pages for full-text search: Civitai now requires cursor pagination for `query` searches.

Example after enabling Hub in Settings:
`/api/civitai/models?query=portrait&model_type=LORA&base_model=SDXL%201.0&limit=10`
Pass the returned `next_cursor` URL-encoded as `cursor` on subsequent calls. Model previews honor the Hub thumbnail preference and mature-content requests cannot override the saved mature setting. Search API tokens remain backend-only. Requests are bounded in size/time and upstream errors are sanitized.

C1.1 does **not** add the gallery/navigation UI; that is C1.2. Tests in `tests/test_civitai_search.py` cover disabled network guard, filters, opaque cursor, mature restriction, and thumbnail preference.

## C1.2: Model discovery gallery (awaiting physical tests)

With the Civitai Hub enabled and saved, the **Civitai Hub** sidebar entry exposes a responsive search gallery. Searching supports free-text, model type, base-model family, creator, tag, sort and period. Cards include the model thumbnail (when enabled), name, creator, version, base family, downloads and an external Civitai link. Results use the C1.1 API with cursor-based Next/Previous navigation, without assuming opaque cursors are numeric. A request gets a busy spinner, disabled Search button and live-region status; network/API errors trigger the existing toast notification system.

When the Hub is disabled, its navigation is hidden, search is blocked in the UI and by the backend, and the local Models and LoRAs tools are not affected. Layout preference is loaded from existing Hub settings: thumbnail grid or compact list. Card image failures display a placeholder rather than breaking the layout. Download and local library actions are reserved for later stages.

### Windows test checklist

1. Enable and save Civitai Hub in Settings, then refresh the browser. Confirm the sidebar entry appears.
2. Open Civitai Hub, search for an SDXL LoRA, and check thumbnails, card layout and external model links.
3. Change sorting, time period, creator/tag filters; verify searches work and display feedback while busy.
4. Use Next then Previous on a query with multiple pages. Confirm the previous page is restored.
5. Toggle list mode in Settings, save and refresh; verify list layout. Check narrow/mobile widths.
6. Disable and save Hub, reload; confirm navigation disappears and direct requests to `/api/civitai/models` return HTTP 403.

**Status:** Code pushed; physical Windows/mobile verification pending. Do not mark C1.2 passed until confirmed.

## C1.3: Detail inspection and sidebar grouping (pending Windows verification)

- Read-only `GET /api/civitai/models/{model_id}` returns bounded model descriptions, creator/tags, up to 40 versions with file sizes/formats/hashes, trigger words, and up to 16 example images per version. Backend enforces the Hub enabled flag, hides mature models unless permitted, and sanitizes upstream responses.
- Gallery cards now provide **Details & versions**, opening a native responsive dialog. Version selection updates metadata and example previews without a download.
- Compatibility is deliberately advisory, not a promise of successful loading: family names alone do not establish runtime compatibility.
- Primary navigation now has an expandable **Project** item immediately beneath **Image**, containing Project Manager, New Project and Project Editor. The optional Civitai Hub item follows Project and precedes Motion Lab. Existing Motion Lab workspace links remain.

### Physical test sequence

1. Open a Civitai model card's **Details & versions** button; confirm the dialog loads, closes, and version selection switches previews/metadata.
2. Try models with no example images or file metadata; confirm clear graceful empty states.
3. Check SDXL vs FLUX model compatibility messaging and test the mature-content preference.
4. Expand/collapse **Project** and visit all three project views; confirm no change to the underlying project behavior.
5. Test navigation with Civitai Hub disabled, and check sidebar and dialog responsiveness at narrow widths.

No downloads or model modifications occur in C1.3. Runtime/CI and physical Windows tests have not been executed from this chat.

## C2.1: Download queue MVP and navigation polish (pending physical tests)

- Downloads are opt-in from a selected version's `.safetensors` file entry. The backend resolves the model/version/file ID again from Civitai and uses the exact file ID; it does not accept caller-supplied URLs or destination paths.
- Models go to the **first** configured directory for that architecture and kind: SDXL/FLUX checkpoints or SDXL/FLUX/Z-Image LoRAs. A missing directory, unsupported family or existing destination is rejected. No overwrites.
- A single worker processes queued downloads; status polling reports bytes, estimated file size, errors and completion. Cancel is supported. Completed downloads trigger a model scan.
- Files are written as private `.part` files, SHA-256 checked when supplied by Civitai, then published without replacing existing files. Partial files are removed on failure/cancellation.
- C2.2 remains responsible for robust resume, parallelism, disk-space preflight and recovery across restarts. Queue jobs in C2.1 are process-memory only.
- Motion Lab sidebar is collapsible like Project. Model descriptions retain paragraph/list line breaks in a bounded, readable panel.

### C2.1 acceptance tests

1. Expand/collapse Motion Lab and Project independently; verify all destinations.
2. Open Civitai detail, select a version and enqueue a small supported Safetensors LoRA.
3. Confirm download queue progress, completion, and that Models / LoRAs scans discover the file.
4. Queue the same file again: confirm safe rejection without overwrite.
5. Test a deliberately unsupported model type and unconfigured destination; verify meaningful errors.
6. Cancel a queued or active job; verify no final/partial model file remains.
7. Disable Civitai Hub while a job is active; verify transfer stops and existing local models remain usable.

**Implementation committed; automated execution and Windows physical tests not yet performed.** Do not merge before verifying C2.1.
