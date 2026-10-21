# Civitai Model Hub guide and milestone history

## Current shipped status (October 21, 2026)

The optional Civitai Model Hub and local model/LoRA metadata tooling are available on the published **`main`** branch, and remain **disabled by default** until enabled in Settings. PR [#51](https://github.com/merberg-ai/Morphorum/pull/51) brought the responsive Models thumbnail cards, LoRA preview panels and improved cached-artwork status messages to `main`. Previews synchronize only on an explicit **Sync Civitai Info** action, and opening local managers reads the local cache without making automatic online requests. Mature-content and thumbnail preferences still apply. The owner confirmed the formerly missing previews appeared after synchronization. Backend, Syntax and Installer CI passed for the merge; full mobile/maturity/CDN combinations are not documented as physical acceptance.

**Historical roadmap below:** C1–C5 headings and statements such as "pending Windows verification", "feature branch only" or "do not merge" record the state **at those earlier milestones**, not the status of the published `main` branch. The current supported behavior and limitations are summarized here and in [Current Status](CURRENT_STATUS.md). The later C5/C5.1 sections describe the active local-cache and placeholder workflows.

## Original development milestones

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

## C2.2: Resumable persistent download jobs (awaiting Windows testing)

- Queue metadata is saved atomically under `data/civitai-downloads.json`; incomplete jobs become **interrupted** on process restart rather than restarting without user consent.
- **Resume** is offered for failed and interrupted jobs. Partial bytes are preserved. The backend sends an HTTP Range request, insists on a matching 206 Content-Range, and refuses to append if a server ignores the range.
- Download concurrency is bounded at **1–3** by Settings → Civitai Hub. Downloads are published only after the complete transfer and optional SHA-256 verification.
- Disk space is checked before enqueue and when resuming, retaining a 256 MiB safety reserve. Jobs always use host-configured destination folders and never overwrite existing models.
- Explicit **Cancel** removes partial data; disabling the Hub halts active transfers as chunks arrive. The queue is intentionally not auto-resumed on startup.
- UI offers Resume, Cancel, a per-job progress bar, status and failure information; existing polling/toast behavior is retained.
- Resume depends on Civitai/CDN byte-range support. When unsupported, the partial file is preserved with a useful error; a fresh-download reset mechanism is deferred.

### C2.2 physical acceptance
1. Set concurrency to 2, queue two small compatible LoRAs, and confirm simultaneous progress.
2. Interrupt Morphorum during a download, restart, and confirm an **interrupted** job, preserved bytes, and an explicit Resume action.
3. Verify a resumed download completes with the correct checksum and appears in Models/LoRAs.
4. Test Cancel of a partial job and check the partial file is gone.
5. Attempt a download with insufficient free disk space or an existing destination; confirm rejection.
6. Disable the Hub during an active transfer, confirm it stops and local generation is unaffected.

**Code committed, not yet runtime/Windows verified. Do not merge to main before acceptance.**

## C2.3: Authentication & diagnostic controls (awaiting Windows acceptance)

Settings → Civitai Hub now has a masked key field and **Save/Replace Key** / **Clear Key** actions. Stored credentials use `data/.civitai-token` (host-only; restrictive permissions where supported), not the public settings JSON. The `CIVITAI_API_TOKEN` environment variable takes precedence. Keys are never sent back to the browser, stored in queue metadata, or included in raw download-error messages. Note: the local key file is **not encrypted at rest**; protect local system access and backups.

**Test Connection** now validates a configured token against Civitai's authenticated `/api/v1/me` endpoint. Anonymous mode reports public access only. The Download queue now distinguishes HTTP 401, HTTP 403 and HTTP 429. Failed or interrupted jobs offer **Retry from beginning**, removing preserved partial bytes after a disk-space check; existing Resume remains available.

### Test procedure for formerly blocked models
1. Create an API token in your Civitai account.
2. Open Settings → Civitai Hub, paste the token, click Save/Replace Key and then Test Connection.
3. Return to the failed download and click Retry from beginning.
4. Verify the model downloads or receives a clear access-denied response (account access restrictions may remain even with a valid key).
5. Refresh Settings: the token itself must never reappear in the input or any API JSON, only the configured status.

Do not merge until Windows testing; no automated execution was performed in this chat.

## C3.1: Manual installed-file identification (awaiting Windows verification)

The **Models** manager now offers **Identify on Civitai** on each indexed model and LoRA row. A deliberate click hashes the selected file locally with SHA-256, caches the digest using the indexed model ID and size/mtime, and looks up the exact hash on Civitai. On a verified result the row displays a direct version link and a success toast; unmatched hashes are explicitly identified as unverified. No local model directory, filename, raw file bytes or prompts are transmitted.

`POST /api/civitai/identify/{model_id}` uses the server-side Civitai credential, requires the Hub to be enabled, handles disabled/missing/mature/no-match cases, and returns a bounded normalized result. The existing LoRA-specific sidecar fallback endpoint is unchanged; C3.1 reports **exact file hashes only**, never guesses from names or sidecars. Automatic scans and persistent identification badges are later stages.

### Windows physical test

1. Enable Civitai Hub. Open Models; click **Identify on Civitai** for an installed LoRA known to be downloaded from Civitai.
2. Confirm a verified Civitai version link appears, and opens the matching model/version.
3. Try a locally created model or file with no Civitai entry; verify the no-match toast.
4. Disable the Hub and confirm the lookup returns a guarded error. Existing generation and model scans must continue normally.
5. Re-identify a previously hashed file; verify the cached digest behavior without uploading weights.

**Implementation committed. Regression tests added but not executed; physical Windows test still required.**

### C3.1 follow-up: identify result layout and LoRA Manager integration

- The Models list holds exactly one verified identity per row. Repeating identification replaces the old result instead of appending new links.
- The dedicated **LoRAs** manager's selected-adapter **Identification** section includes **Identify on Civitai**. It uses the same explicit SHA-256 lookup endpoint as Models, while the existing LoRA metadata and sidecar lookup remain available.
- Identification results are tied to the selected LoRA. Switching adapters clears the previous identification and ignores stale asynchronous responses.
- Verify repeated clicks in Models do not stack links, then identify a selected LoRA and switch selection while a request is running.

## C3.2: Explicit installed-model update detection (Windows acceptance pending)

**Models** rows and the dedicated **LoRAs** Identification panel now offer **Check Updates**. This endpoint re-identifies a local file by exact SHA-256, fetches its Civitai model's version list, and compares dated versions against the identified installed version.

`POST /api/civitai/updates/{model_id}` is read-only and honors the Hub's enabled state and maturity preference through the existing identification/detail endpoints. The API returns newer version candidates, release dates, base-model families, verified installed version, and advisory compatibility flags. A version with the same base family and model kind is only **potentially compatible**, not guaranteed compatible. Cross-family versions remain visible but explicitly flagged for verification.

The checks are initiated only by user action. No automatic network traffic, local file modification, download, or replacement takes place in C3.2. Civitai detail listing is currently capped at 40 versions; no newer result only means no newer *dated version in that returned set*. Models lacking exact hash matches or usable dates cannot be confidently classified as up to date.

### Windows test

1. Identify a locally installed Civitai LoRA, then press **Check Updates**. Confirm newer versions and links are correct.
2. Repeat in the LoRAs manager; ensure the result is cleared when changing selected adapters.
3. Check an up-to-date or unrecognized model. Confirm that an unverified match does not claim a verified update.
4. Test a model that has SDXL and FLUX variants. Cross-family releases should show a compatibility warning.
5. Disable Hub and verify the update endpoint refuses requests without affecting local generation.

**Committed, but automated execution and physical Windows tests are still pending.**

## C3.3: Local model metadata and preview synchronization (pending Windows verification)

- **Models** and **LoRAs** now offer explicit **Sync Civitai Info** and **View Cached Info** actions.
- Synchronization first requires an exact SHA-256 identity from C3.1; it never relies on a filename or an unverified sidecar. It caches normalized model/version name, creator, base model, trained words, descriptive text, verified Civitai link, and sync timestamp.
- Metadata and optional thumbnail are stored only beneath `cache/civitai-library/<indexed_model_id>/`. No checkpoint/LoRA files or original model folders are modified.
- Image retrieval happens only on a user-triggered sync, only for `https` Civitai image hosts, with a 4 MiB cap and supported JPEG/PNG/WebP types. It respects the existing thumbnail and mature-content settings, including on later cache reads.
- Cache records are invalidated when the indexed local file's size or modification time changes. **View Cached Info** makes no external network requests.
- The new endpoints are `GET /api/civitai/library/{model_id}`, `POST /api/civitai/library/{model_id}/sync`, and `GET /api/civitai/library/{model_id}/preview`. Access requires the Civitai Hub to be enabled; model weights never leave the system.
- No automated metadata sync, no model replacements, and no modifying existing preview sidecars during C3.3.

### Physical Windows acceptance

1. Open **Models** or **LoRAs**, select an installed, identifiable Civitai model, and use **Sync Civitai Info**. Confirm a readable summary and optional small preview.
2. Refresh the page and click **View Cached Info**. Confirm the summary is available without an online lookup.
3. Disable thumbnail previews and verify cached thumbnails no longer display. Restore the setting and retest.
4. Replace or modify a test file and re-scan; confirm old metadata is reported stale rather than matched to the changed file.
5. Confirm unrelated model files, folders, and locally generated outputs remain unchanged.

Automated regression tests were added, but not executed from this chat. C3.3 requires physical Windows acceptance before merge.

### C3.3 follow-up: LoRA triggers and multi-select synchronization

- **Sync Civitai Info** in the dedicated LoRA Manager now refreshes the existing **Quick Use** prompt snippet using verified Civitai trained/trigger words, when returned. **Include recorded trigger words** still controls whether those words appear in the copied/inserted prompt tag. **View Cached Info** restores those trigger words without a network call. No trigger is inserted automatically into an already-written prompt.
- The LoRA Library supports independent per-row checkboxes without changing the LoRA currently being inspected. **Select visible** selects items matching the current family/search filter, **Clear selection** clears all selected items, and **Sync Selected (N)** synchronizes all checked IDs sequentially with per-item progress and an end-of-batch success/failure summary. Selections may span family/search changes; invalid indexed IDs are removed on library reload.
- Failed or unidentified files are reported and do not abort the remainder of the batch. Backend exact-SHA validation, mature-preview restrictions, and explicit opt-in are unchanged.
- On Windows, verify selection with multiple families, filter changes, partial failures, and prompt tag trigger-word inclusion/exclusion after both single and bulk sync. No automatic bulk sync is scheduled.

This follow-up is committed to `feature/civitai-model-hub` but requires Windows UI acceptance.

## C4.1: Use installed verified Civitai models in Image (Windows acceptance pending)

- The Civitai gallery and model detail dialog now query local installed versions by **verified C3.3 cached metadata**, not by guessing filenames. `GET /api/civitai/installed/{model_id}` is offline, requires the Hub enabled, and returns only indexed identifiers, kinds, base families, versions, and synchronized trigger words.
- For verified installed checkpoints, **Use in Image** chooses that model in the existing Image selector without automatically running generation or downloading weights.
- For verified installed LoRAs, **Add to Image Prompt** first refreshes available Image LoRAs, verifies the currently selected checkpoint has the same family, then uses the existing `MorphorumImage.insertFromManager` method, with default strength 1 and cached trigger words. The Image subsystem performs its own final validations.
- The dedicated LoRA Manager now **automatically loads cached synchronized Civitai trigger words** when selecting a LoRA. No online lookup occurs; Quick Use, Copy Prompt Tag, and Add to Image Prompt can use them immediately. Unsynced local trigger words remain as fallback.
- No background model downloads, no substitution of incompatible checkpoint families, and no overwriting model files.

### Windows acceptance test

1. In Models or LoRAs, synchronize a known Civitai model, then open that model in the Civitai Hub gallery. Confirm an installed badge/action appears.
2. Choose an installed checkpoint's **Use in Image**, confirm the Image model selector changes but no generation starts.
3. Choose a compatible installed LoRA and **Add to Image Prompt**. Verify its tag and synchronized triggers appear in Image.
4. Select a checkpoint from a different family and verify the LoRA action refuses to insert it.
5. Select an already-synced LoRA in LoRA Manager without clicking View Cached Info and verify recorded Civitai trigger words appear in Quick Use when the trigger checkbox is on.
6. Confirm non-installed models offer no Use actions, and that disabling the Hub prevents Civitai actions.

Automated regression coverage is committed but has not been executed on the Windows host.

## C4.2: Project Editor and Motion Lab integration (awaiting Windows verification)

Verified installed checkpoint and LoRA entries in the Civitai Hub now offer **Use in Project** and **Add to Project Prompt** alongside the C4.1 Image actions. They invoke the existing Motion Lab/Project Editor controller rather than creating a second project-saving mechanism.

- **Use in Project** selects an indexed checkpoint in the existing animation model field. It requires an open project, marks the project dirty, and does not start a render.
- **Add to Project Prompt** validates that the LoRA is indexed and matches the current project's checkpoint family, then inserts its standard Morphorum LoRA tag (weight 1) plus any synchronized trigger words into the **first prompt keyframe**. Existing project prompts and other keyframes are preserved. It marks the project dirty.
- Neither action automatically saves: use **Save Project** explicitly in Project Editor. Saved projects retain the existing checkpoint ID and prompt syntax, compatible with existing project loading and rendering.
- A missing checkpoint in the project's saved state continues to show the Project Editor's existing **Missing indexed model** option; the Civitai actions reject missing indexed entries instead of silently substituting another model.
- Selecting models and LoRAs from Hub does not start any download or model-weight load. Motion Lab uses its existing compatibility and render preflight checks.

### Windows acceptance

1. Open an existing animation project, find an installed verified Civitai checkpoint and click **Use in Project**. Confirm model selector changes, project is marked unsaved, and no render begins.
2. Save and reload the project. Confirm the checkpoint choice survives.
3. Select an installed same-family LoRA in Hub, choose **Add to Project Prompt**, and verify its tag and synchronized triggers appear at the first prompt keyframe.
4. Save/reload the project; verify other keyframes and motion tracks remain unchanged.
5. Try a different-family LoRA and a project with no checkpoint; confirm refusal.
6. Remove a test checkpoint from the index and reopen its project to confirm the existing missing-model warning rather than a silent replacement.

**Historical C4.2 checkpoint:** This note describes the state before the Civitai work was promoted to main; see the shipped-status section above.

## C4.3: Bulk verification and final Hub polish (Windows acceptance pending)

The **Models** library now includes compact multi-select checkboxes plus **Select visible**, **Clear selection**, **Identify Selected**, and **Check Updates**. Selection persists across filter changes and is pruned when the indexed library is refreshed. Operations execute sequentially via the existing guarded single-item SHA-256 identification and update endpoints, with current-item status and a completed/failed/unchanged summary. Individual errors do not abort the rest of the batch. Nothing is downloaded or overwritten.

The previously completed C4.1/C4.2 Hub gallery continues to show verified installed versions (from C3.3 local metadata) and actions for Image and Project Editor; unverified versions are never advertised as installed. The existing download queue, Civitai metadata/preview cards, LoRA bulk sync, and Civitai Hub opt-in remain unchanged.

### C4.3 Windows test checklist

1. In **Models**, select a few indexed LoRAs and checkpoints; filter to another family and select more. Confirm the count reflects all checked models.
2. Click **Identify Selected**. Verify progress, success/unmatched/error summary and that one failed file does not abort the batch.
3. Click **Check Updates** on the selection. Confirm it uses each local model's exact identity and does not update or replace model files.
4. Clear selection and verify disabled bulk actions; rescan libraries and confirm stale IDs are discarded.
5. Test narrow/mobile layouts: checkboxes should remain small, the toolbar should wrap, and all model-row controls remain usable.
6. In Civitai Hub, verify installed-version indicators and Image/Project actions, model detail previews, and the download queue still work.
7. Disable Civitai Hub and ensure bulk operations report guarded failures instead of performing network requests.

**Historical C4.3 checkpoint:** This milestone was feature-branch-only at the time. The later C5 work and cached artwork improvements have since been promoted; see the current shipped-status section above.

## C5 release hardening: staged validation

This pass is intentionally separate from release/merge acceptance. The feature branch remains isolated until physical Windows signoff.

**Changes reviewed and corrected:** GitHub push CI now includes `feature/civitai-model-hub`; the frontend syntax job checks `civitai.js`; cached preview images are checked for a recognizable JPEG/PNG/WebP file signature before being stored, are published via atomic rename, and synchronized metadata is rejected if the underlying model file changes during the request. Invalid cache JSON object shapes are treated as misses. Additional tests cover malformed cached metadata and absent preview files. Older Project submenu test assertions were adjusted to the markup's actual attribute ordering (the UI was not changed).

**Security/operation boundaries:** Hub disabled by default. Civitai auth keys are host-side and never returned in API responses; note that keys stored in `data/.civitai-token` are *not encrypted at rest*. All remote discovery/identification/sync/update requests require explicit user action and the Hub enabled. Download jobs retain partial files for user-triggered resume, do not overwrite model files, and verify SHA-256 when Civitai provides it. Civitai galleries and downloaded metadata remain untrusted, displayed as text or constrained local data, not executable HTML.

**Release checklist:** Review the latest [Backend tests](https://github.com/merberg-ai/Morphorum/actions/workflows/backend-tests.yml) and [Syntax checks](https://github.com/merberg-ai/Morphorum/actions/workflows/syntax.yml) runs for this branch. Physically verify Windows install/updater, opt-in and token save/clear/test, protected downloads and resume, local metadata cache and previews, LoRA trigger restore, bulk library operations, Image integration, Motion Lab/Project Editor selection and save/reload, and narrow/mobile layouts. Run a smoke generation after a Civitai-sourced model selection. Confirm disabled mode retains completely local generation.

**Merge gate:** Do not merge into `main` until both required CI checks pass on the final commit and Windows physical tests pass. No release/merge is implied by this hardening change.

## Download queue cleanup follow-up

The Civitai queue supports **Remove** for completed, failed, interrupted and cancelled entries. Removal updates the persisted queue manifest and cleans partial `.part` files for unfinished jobs, but **never deletes installed `.safetensors` weights**. A queued or still-running job must first be cancelled, and removal waits for the worker to exit to avoid a race with the downloader. Interrupted jobs remain resumable until they are removed.

The explicit `DELETE /api/civitai/downloads/{job_id}` endpoint requires Civitai Hub enabled, returns 409 for active jobs, and returns 404 for nonexistent entries. Regression tests check protected model files, interrupted partial cleanup, and rejection of running jobs.

## Standalone Civitai Z-Image checkpoint discovery

Civitai chooses the **first configured** `models.zimage.checkpoints` folder when present. For a fresh installation without such a custom folder, standalone Z-Image checkpoint downloads now go under the configured managed Z-Image location in `civitai-checkpoints/` (by default `ckpts/z-image/civitai-checkpoints/`). The official `Z-Image-Turbo` Diffusers snapshot lives separately and is never overwritten.

The model scanner includes both the explicitly configured standalone checkpoint locations and the dedicated Civitai location. Previously completed files in a custom configured Z-Image checkpoint path become visible after clicking **Scan Models**. To determine the path of a previous completed download, inspect its `destination` in the host-local `data/civitai-downloads.json` manifest. Do not share that manifest unredacted because it also contains private download information.

**Compatibility boundary:** An indexed standalone Civitai `.safetensors` file is not necessarily a complete Diffusers pipeline. Morphorum's current Z-Image generation backend only supports the managed full Diffusers snapshot; standalone Civitai checkpoints appear in Models as **Indexed only** and are disabled for generation until a tested single-file loader/conversion workflow exists. This is intentionally not a claim of runtime support.

Acceptance: restart, Scan Models, verify a previously downloaded Z-Image file in the Models library under Z-Image, confirm the full managed Z-Image-Turbo remains loadable, and verify standalone checkpoint **Use** is unavailable rather than causing a rendering error.

## C5: Offline cached artwork in Models and LoRA Manager (released on main)

The original C3.3 metadata cache remains the single source of truth; no
second thumbnail database or background Civitai scanner was introduced.
After **Sync Civitai Info**, an exact SHA-256 match stores text metadata
and, when a suitable still image is available and previews are enabled, one
bounded JPEG/PNG/WebP preview under `cache/civitai-library/<indexed_id>/`.
Images are retrieved only through a user-initiated sync. The server excludes
video previews, validates a recognizable image signature and size, and can
try up to three eligible image candidates. If a resync's image request fails,
previously verified artwork for the same exact file/version is kept.
Mature-content and thumbnail settings continue to govern whether it is served.
No checkpoint or LoRA sidecars are overwritten.

Models and LoRAs now both read the same local cache through
`POST /api/civitai/library-catalog`, a read-only bounded request accepting
up to 120 indexed IDs at a time. It returns only compact cached summaries and
does not contact Civitai. The browser serves images exclusively from the
existing `GET /api/civitai/library/{model_id}/preview` endpoint. Missing,
stale, disabled or unsynchronized artwork shows a clean **NO PREVIEW**
placeholder, not a broken external image. Models also has an explicit
**Sync Civitai Info (N)** bulk action, alongside the previous identify/update
actions. LoRAs keeps its existing bulk synchronization.

The Models screen now uses responsive thumbnail cards with name, filename,
architecture badges, file size, expandable path and existing model/tag/Civitai
actions. The LoRA library adds thumbnails to its selection list, with a larger
aspect-preserving preview above the selected adapter's Quick Use controls.
Existing local metadata inspection, triggers, prompt-tag copying/insertion,
model selection and rendering pipelines are unchanged.

**Manual acceptance (Windows + mobile):** Enable Civitai Hub in Settings,
keep previews on, identify/sync one checkpoint and one LoRA with safe example
images. Open both managers and verify the images appear immediately after
reopening or restarting Morphorum. Verify records with no images show
placeholders, filter/search/family switching, bulk actions, failed network
resync preserving already cached images, disabled Hub/previews, and mature
preference changes. Test a 320–390px phone width, desktop cards, and the
selected LoRA image with both portrait and landscape examples. Run a normal
single-image generation afterward to catch unrelated model-selection changes.

Tests: `tests/test_civitai_library.py`,
`tests/test_civitai_detail.py`, `tests/frontend_cached_art.test.cjs`.
Owner feedback confirmed cached previews now appear correctly after synchronization. The feature was promoted to `main` via [PR #51](https://github.com/merberg-ai/Morphorum/pull/51). The checklist above remains useful for regression testing; complete mobile/mature-filter/CDN edge-case physical acceptance was not separately recorded.

### C5.1: "NO PREVIEW" after successful metadata sync

A successful SHA-256 metadata lookup does **not** imply a thumbnail was cached.
Earlier C5 UI falsely used the same success notification for both operations.
C5.1 distinguishes them and surfaces the reason in the Models/LoRAs detail
panel and on the art placeholder. After syncing, inspect the message:
- **PREVIEWS OFF**: enable Settings → Civitai Hub → Load Previews and save.
- **PREVIEW HIDDEN**: the existing image is filtered by the mature-content
  preference; changing this setting is explicit.
- **CACHE MISSING / IMAGE LOAD FAILED**: a previously recorded preview is
  unavailable on disk or failed the local image endpoint. Sync again.
- **NO IMAGE AVAILABLE**: Civitai returned no allowed still, or the CDN failed;
  the exact reason is shown after syncing (including sanitized CDN HTTP status).

The sync now tries a handful of still-image candidates, handles bounded
same-provider redirects, and can use a *representative* preview from another
version of the **same SHA-256-verified Civitai model** when the installed
version has none. Such images are labeled as representative rather than
presented as examples generated with the installed version. Mature-content
rules continue to apply; network requests happen only on explicit Sync.
A successful metadata sync does not claim an image was downloaded.

Physical Windows acceptance: with Civitai Hub enabled, verify Load Previews is
on; sync one installed checkpoint and LoRA with known Civitai still images.
Expect a thumbnail after sync and on reopening. If no image appears, note the
new displayed diagnostic message, and if possible the `preview_status` and
`preview_warning` from `GET /api/civitai/library/{indexed_id}`. Do not share
authentication tokens or complete local model paths. Test filtered/disabled
previews and a CDN failure without damaging previously cached metadata.
