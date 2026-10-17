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
