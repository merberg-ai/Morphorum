# DB2: Morphorum Studio client protocol and connection management

**Status:** proposed plan only, 2026-10-12; **no DB2 runtime changes yet**.
**Backend branch:** `dev-backend` at the DB1 checkpoint `a0e6db1b9c1b21a7bfcd5fb178c49ec8a129c4ef`.
**Verified checkpoint branch:** `checkpoint/db1-remote-render-preview-verified-20261012`.
**Scope:** versioned, safe, resilient client interface between Morphorum backend and the future separate PySide6 `merberg-ai/Morphorum-Studio` application.
**Isolation:** DB2 implementation should be done on `feature/db2-client-contract` branched from `dev-backend`; `main`, the DB1 checkpoint, and existing normal-mode semantics stay unchanged until explicit review/merge approval.

## DB1 baseline and exact current reality

The user physically verified a Windows Omen backend-only instance controlled by Ubuntu Mini over a trusted LAN, including authenticated health, GPU telemetry, console SSE, still-image SDXL generation and remote PNG, and a corrected SDXL animation with authenticated GIF retrieval. CI on the implementation commit had 499 passing tests and 1 skip. See `BACKEND_ONLY.md`.

Existing server routes already provide:
- `GET /api/health`: app/version/commit/mode plus `api_contract_version: 1`; backend-only requires Authorization.
- `GET /api/generation/capabilities`, `GET /api/models`, `GET /api/system/telemetry`, `GET /api/system/gpu-memory`.
- `POST /api/generation/jobs` with a **model index ID** in `model_id`, `GET /api/generation/jobs/{id}` and authenticated PNG download.
- `GET /api/animation/projects/{id}` returns `{"project": ...}`; `POST /api/animation/renders` requires `{"project": full_project_object}`, **not just** `project_id`.
- `GET /api/animation/renders/{id}`: status, current frame/step, progress, ETA, current prompt/frame state, latest completed frame URL. Direct authenticated frame/GIF routes under `/api/animation/renders/{project_id}/{render_id}/...`.
- Video export exists: availability, asynchronous export start, job polling, list of finished exports and authenticated file download.
- `GET /api/console/stream?after_id=N`: SSE with `id:`, `event: console`, heartbeat. Console IDs are in-memory and **reset on process restart**; existing clients must not carry an old cursor across restarts.
- Source image upload is project-scoped (`POST /api/animation/projects/{id}/source-image`) and checks image validity/size. `POST /api/animation/projects/{id}/motion-lab/audio-analyze` accepts project-managed **PCM WAV, up to 20 MiB / 180 seconds**. `POST /api/animation/projects/{id}/motion-import/soundtrack` accepts project-owned WAV/MP3/OGG/FLAC, **up to 40 MiB**, with offset and checksum. These are **distinct workflows**, not one universal file API. Motion import soundtrack GET currently returns **metadata**, not its playable audio bytes.
- API-only mode rejects requests with an `Origin` header, and authenticates all `/api/*` requests against one persistent installation-level bearer token from `backend_access.py`.
- Job creation has no general idempotency key and project save lacks a standard If-Match version-precondition contract.

Avoid claiming existing generic binary asset transfer, automatic pairing, per-client revocation, persistent SSE events, video export physical acceptance or ordinary browser-mode acceptance until implemented/tested.

## Product decisions for DB2

1. **Native client first.** Python reference client and native PySide6 networking adapter will use REST + Authorization + console SSE. No Studio UI is built in DB2; that belongs in DB3/Studio. Maintain polling as an always-available fallback.
2. **Manual host address first.** `127.0.0.1:7866` for loopback and explicit host/IP for trusted LAN. Optional mDNS discovery is a future convenience; never depend on it for core operation and never advertise credentials.
3. **Transport boundary.** Local loopback is permitted. Trusted LAN plaintext HTTP remains a documented DB1 compatibility mode with confidentiality risks; for untrusted links require TLS/HTTPS or a trusted encrypted tunnel. Do not implement a custom encryption handshake. Never enable public/WAN discovery, token-in-URL, or unauthenticated file routes.
4. **Credential evolution in stages.** DB2's first reference client can use the DB1 token supplied out of band and stored in OS keyring for Studio. Design optional server-mediated pairing with explicit host-side approval and **per-client revocable credentials** on protected transport. Retain legacy token compatibility initially. Do not invent an insecure LAN PIN-exchange endpoint: a short code over plaintext HTTP is not equivalent to secure pairing.
5. **One engine and one asset store.** Reuse existing model paths, project-owned asset locations, preview routes, video exporter and frozen manifests. File picker paths live on the client and must never be assumed to exist on the host.
6. **Respect DB1 checkpoint and backward compatibility.** Additive API contracts preferred. Evolve `api_contract_version` only for deliberate incompatible changes; feature discovery allows older clients to degrade without guessing.

## DB2.1: Versioned API contract, diagnostics and structured errors

Deliverables:
- Contract document with exact request/response examples for health, model lookup, projects, generation/animation creation, job progress, frame/GIF fetch, video export and source/audio uploads.
- Additive authenticated `GET /api/client/capabilities` (proposed endpoint) with `api_contract_version`, feature identifiers, backend instance ID, startup/boot ID, supported auth methods, upload and media format/size limits, supported event feeds, and feature-specific availability (e.g., FFmpeg). Keep health compatible.
- Stable error envelope with machine-readable `code`, concise `message`, optional `details`, `request_id`; preserve existing FastAPI `detail` for legacy clients as needed. Document 400/401/403/404/409/413/429/5xx and network timeout/error handling, without exposing filesystem secrets.
- Authentication and compatibility diagnostics: wrong token, bad host/port, backend not running, unsupported contract, model unavailable, missing FFmpeg, missing/mismatched asset.
- Schema/contract tests against standard mode, backend-only loopback and backend-only LAN; a checked-in Python reference client sends correct payloads, avoiding earlier model-filename and `{"project_id":...}` mistakes.
- Avoid exposing absolute host filesystem paths as primary media identifiers.

**Acceptance:** reference client identifies compatible backend, surfaces explicit errors and matches documented types; all DB1 tests green. Halt for automated check.

## DB2.2: Connection lifecycle, client identity and authorization

Deliverables:
- Named connection profiles: URL, friendly label, backend instance identity, negotiated capabilities, preferred transport. No bearer token in projects, logs or git repositories; use OS credential store in Studio. Reference CLI can use a token file/environment for Ubuntu acceptance only.
- First connection handshake: validate host identity and compatibility, authenticate, detect capabilities, show secured/insecure LAN warning and permission errors.
- Lifecycle states: disconnected, connecting, connected, unauthorized, incompatible, reconnecting, offline/render-still-running; clear local-owned vs attached-remote process identity. A client never kills an unowned backend.
- Optional per-client credentials/pairing backend component: host-side opt-in approval, bounded expiry for offers, one-time use, client-specific token/key, audit, revoke, rotate, retry/rate limits; transport must be protected before secrets are provisioned. Existing installation token remains a migration/fallback path. Final protocol and threat model must be reviewed before coding.
- Explicit server `instance_id` persisted across restarts plus `boot_id` varying per process. Warn if the saved address resolves to a different instance.
- Manual LAN connection is mandatory first; discovery optional only after correctness/security acceptance.

**Acceptance:** Ubuntu and Windows reference clients can reconnect after backend restart; unauthorized/revoked clients are denied; OS-stored credentials don't appear in logs or files; no unowned process is stopped.

## DB2.3: Project-owned assets and reliable transfers

Deliverables:
- Inventory existing project-scoped source image, hybrid video, motion-analyze WAV, imported soundtrack, frame/GIF and encoded video endpoints. Reuse them and provide a unified *client-level* `AssetDescriptor` (project ID, kind, logical ID, filename, bytes, MIME, SHA-256, backend-owned URI), not a duplicate on-disk store.
- Add only necessary missing server interfaces: authenticated soundtrack **binary download** for Studio local waveform/playback and/or a project-asset read endpoint; asset metadata/URL retrieval independent of host OS path.
- Bounded streaming uploads with sanitized basenames, MIME/magic validation, per-type size limits, hash verification, staging file + atomic move, error cleanup and project sandbox checks. Prefer shared reusable upload plumbing with adapters into existing stores. Long soundtrack support requires an **explicit Audio Director limit/decoder plan**, not silent removal of the current 20/40 MiB caps.
- Download streaming with cancellation, retry, optional range request, verified SHA-256 and temporary output + atomic rename. Resume/chunked transfers only where justified by realistic file sizes. Never hold multi-hundred-MB videos in memory.
- Host-managed audio assets can be frozen with the render and reused for soundtrack-accurate export, consistent with `STUDIO_AUDIO_DIRECTOR_PLAN.md`.
- Concurrency: propose project revision/ETag and conditional saves `If-Match` / HTTP 409 or 412, with actionable reload/compare response. Existing browser clients remain compatible.

**Acceptance:** Ubuntu uploads a project source image and a short WAV/soundtrack from local files; Windows backend resolves them; Ubuntu downloads/validates audio, PNG/GIF and final MP4 (if FFmpeg available). Verify checksum mismatch, oversized upload, bad extension, lost connection and concurrent save rejection. No shared filesystem.

## DB2.4: Reliable progress, event recovery and job identity

Deliverables:
- Keep existing job GET endpoints authoritative. Poll model loading, live frame/step, prompt/frame state, ETA and terminal status at a sensible rate; fetch **new completed frames only** and avoid saturating LAN/GPU.
- SSE console reconnect using event IDs and backfill via `GET /api/console?after_id=N`, scoped to the server boot instance. Reset cursor and backfill safely when `boot_id` changes; on buffer overflow issue a gap notice rather than silently asserting continuous history.
- Add an **optional dedicated typed render-job event feed** only if the real Qt client needs it, with `render_progress`, `frame_ready`, `model_loading`, `render_completed`, `render_failed` IDs plus reconnect semantics; polling fallback still required. No promise of previews during diffusion sub-steps.
- Track selected project ID, render ID, last received completed-frame index, current prompt/frame state and export ID in persistent client session metadata. Reattach to server records after Studio/network restart; do not retry an ambiguous POST blindly.
- Propose `Idempotency-Key` or `client_request_id` for rendering/submission/export, with durable body-hash/dedup window to prevent duplicate GPU work after request timeout. Return conflict for same key with different body.
- No automatic cancel after connection loss; manual cancellation/resume only where backend semantics exist. No false pause button.

**Acceptance:** interrupt Ubuntu network mid-render, restart reference client, reconnect to same render and fetch subsequent completed frames and final GIF/video; test backend restart separately (interrupted render vs still-running job) and explicit resume. No duplicate render from retry. Old client polling continues to work.

## DB2.5: Reference remote client, tests, checkpoint

Deliverables:
- Checked-in standard-library or lightweight HTTP **reference CLI/test harness** to use from Ubuntu Mini and Windows; command modes for doctor/health, list models/projects, generate SDXL single image, start animation from saved project, watch/reattach existing render, download GIF/frames/video, upload source/audio and verify hashes.
- Offline FastAPI contract/security tests, SSE and disconnect simulation, file-size/invalid-upload abuse tests, Windows/Linux startup smoke tests; network tests include wrong token, aborted transfer, stale instance/boot ID, concurrent saves, lost submission response.
- Physical acceptance on Windows Omen (CUDA), Ubuntu Mini (LAN), plus normal web UI smoke to avoid regression; optional video audio-offset sync check for AD0 readiness.
- Preserve DB1 checkpoint; create a DB2 verified checkpoint only after user reports tests passing. No merge to `main` without user approval.

## Implementation order and review gates

1. DB2.1 contract/capabilities/errors and CLI skeleton. Run CI; physical Ubuntu connection diagnostics. Stop for approval.
2. DB2.2 connection lifecycle/identity and credential handling. Define pairing security before implementing short-code pairing. Run CI and token-rotation/reconnect physical tests. Stop for approval.
3. DB2.3 project assets and transfer consistency. Keep old audio behavior working; long-audio changes staged explicitly. CI + Ubuntu image/audio/video transfer. Stop for approval.
4. DB2.4 progress/reconnect/retry and optional events. CI + disconnect mid-render physical tests. Stop for approval.
5. DB2.5 documentation, cross-mode regressions and final acceptance checkpoint.

## Non-goals and deferred defects

- No new diffusion model loaders or duplicate model installation; no Studio GUI, timeline, waveform renderer or Audio Director seed/event implementation yet.
- No unsupported WAN mode, unauthenticated discovery/control or custom ad-hoc cryptography.
- No effort to mask invalid 3D camera settings in the renderer. User reported the browser New Project Wizard initialized incorrect camera settings: record as a **separate web UI bug** and fix/validate in a later UI workstream.
- No claim that plain HTTP LAN protects tokens against eavesdropping; recommend TLS/VPN when LAN trust is uncertain.
- Ordinary browser-mode regression and MP4/WebM export are outstanding physical acceptance items carried over from DB1.

## Handoff to Studio and Audio Director

DB2 must provide a Python-level client adapter that Studio can wrap in a Qt worker, documented `AssetDescriptor`, capability/status negotiation, deterministic project/asset IDs and time-aware telemetry. Keep Studio source files local only as *client staging assets*, and guarantee the server owns render inputs before starting a frozen manifest. Once DB2 passes, DB3 consumes this client without duplicating HTTP/auth logic. AD0 can then focus on waveform/audio timeline and subsequent Audio Director milestones.
