# Morphorum Studio: Native UI repository handoff

**Purpose:** Give the future separate Morphorum Studio repository an explicit, tested backend contract. This file is authored in the Morphorum backend repository; **no Studio UI repository has been created**. The user will create that repository when ready.

**Recommended new repo name:** `merberg-ai/Morphorum-Studio` (proposal, not yet created).
**Candidate technology:** Python 3.12+, PySide6/Qt 6 for native Windows first, Linux as follow-up; package into a desktop installer later. An eventual Android/mobile app can use the same versioned API contract independently.

**Backend integration baseline:** DB2.1–DB2.5 work currently sits in the *stacked* feature PRs, not `main`:
- #27 `feature/db2-client-contract` targets `dev-backend`
- #28 `feature/db2-connection-manager` targets #27's branch
- #29 `feature/db2-project-assets` targets #28's branch
- #30 `feature/db2-live-recovery` targets #29's branch
- #31 `feature/db2-final-integration` targets #30's branch

Every milestone has a verified checkpoint through DB2.4, and DB2.5 remains subject to physical acceptance. Do not base a newly created Studio repository on `main` until backend PR integration is deliberately completed and verified. For early Studio prototyping, explicitly point at the accepted DB2 feature branch and document the pinned contract version.

## Separation of responsibilities

```text
┌──────────────────── Morphorum Studio (new repo) ───────────────────┐
│ Qt UI: Projects, Editor, Model Selector, Motion Lab, Audio, Preview │
│                                                                      │
│ Connection Profiles → OS Credential Store → Typed API Client       │
│       ↓                             ↓                        ↓       │
│ Reconnect + Boot ID           Asset SHA-256 cache        Job monitor │
└──────────────────────────────────┬───────────────────────────────────┘
                                   │ authenticated HTTP(S) REST + SSE
                                   ↓
┌───────────────────────── Morphorum backend ─────────────────────────┐
│ Models / CUDA / PyTorch     Render queue      FFmpeg export          │
│ Versioned capability API   Project files     Soundtrack/WAV store   │
│ Job status + typed events  Asset catalog     Render manifests       │
└──────────────────────────────────────────────────────────────────────┘
```

Studio must **never** depend on a shared filesystem, direct model path on the client, or a locally running GPU. All model IDs are resolved by the backend. Users with two machines can control the Omen from a modest client PC. A future loopback backend may be started by Studio **only if Studio launched that process itself**; an attached remote process is never stopped during client exit.

## Backend connection/auth contract

1. Store named backend URL, label, stable `instance_id` and last `boot_id` in a profile; store **no bearer secrets** in a JSON/SQLite profile. See `scripts/morphorum_connections.py`.
2. Use Windows Credential Manager/OS keyring for bearer tokens. Existing DB1 backend installation token continues working. Per-client tokens are high entropy and issued/revoked via *local backend-host* `python -m morphorum clients issue/list/revoke`. No network pairing PIN endpoint exists and the UI should not pretend one does.
3. Never transmit tokens over the public Internet or an untrusted plaintext LAN. Support TLS/VPN/SSH-tunnel configuration before wider distribution. Native clients must omit browser `Origin` headers in backend-only mode.
4. `GET /api/health` and `GET /api/client/capabilities` with Authorization for discovery. Require `api_contract_version=1` and inspect actual feature flags. Store `instance_id` to detect accidental wrong host; this alone is **not TLS identity verification**.
5. On reconnect with same instance but different boot ID, reset all ephemeral SSE cursors and fetch **authoritative** REST job/asset state. For a different instance ID, stop and require explicit human approval.

## Minimal Studio transport API matrix

| UI functionality | Backend API |
| --- | --- |
| Backend compatibility | `GET /api/client/capabilities` and `GET /api/health` |
| Model families & real IDs | `GET /api/models/families`, `GET /api/models?family=...` |
| Health and GPU/VRAM telemetry | `GET /api/system/telemetry`, `GET /api/system/gpu-memory` |
| Project browser | `GET /api/animation/projects` |
| Project load/revision | `GET /api/animation/projects/{project_id}`; strong `ETag` |
| New project | `POST /api/animation/projects` |
| Conflict-safe Studio edit | `PUT /api/animation/projects/{project_id}` + `If-Match` |
| Existing timeline/motion APIs | See `GET /api/animation/projects/{project_id}/timeline` and `GET /api/animation/timeline/descriptors` |
| Project media catalog | `GET /api/animation/projects/{project_id}/assets` |
| Project source PNG upload/download | `POST/GET /api/animation/projects/{project_id}/source-image` |
| Attach soundtrack | `POST /api/animation/projects/{project_id}/motion-import/soundtrack` |
| Soundtrack bytes | `GET /api/animation/projects/{project_id}/motion-import/soundtrack/file` |
| Analyze WAV and fetch waveform source | `POST /api/animation/projects/{project_id}/motion-lab/audio-analyze`, `GET /api/animation/projects/{project_id}/motion-lab/audio/{sha256}` |
| Still-image job | `POST /api/generation/jobs`, `GET /api/generation/jobs/{id}` |
| Animation render | `POST /api/animation/renders` with **full saved project object**, not just project ID; `GET /api/animation/renders/{id}` |
| Completed PNG frames | `GET /api/animation/renders/{project_id}/{id}/frames/{frame}` |
| Animation preview GIF | `GET /api/animation/renders/{project_id}/{id}/preview` |
| Live job events | `GET /api/client/jobs/{animation|image|video}/{id}/events`; polling fallback mandatory |
| Console events | `GET /api/console/stream` and `GET /api/console` |
| Video export | `POST /api/animation/renders/{project_id}/{render_id}/video` |
| Video job status | `GET /api/animation/video/jobs/{id}` |
| Archive video variants | `GET /api/animation/renders/{project_id}/{render_id}/videos` |
| Download MP4/WebM | `GET /api/animation/renders/{project_id}/{render_id}/video/{format}/{quality}/{fps}` |

Sources of truth: `docs/DB2_CLIENT_CONTRACT.md`, `docs/DB2_CONNECTION_MANAGER.md`, `docs/DB2_PROJECT_ASSETS.md`, `docs/DB2_LIVE_RECOVERY.md`, `docs/DB2_FINAL_ACCEPTANCE.md`.

## Client correctness requirements

### Idempotent GPU job submissions

Before the first `POST`, persist the **exact JSON body**, stable random `Idempotency-Key` (8–128 allowed characters), intended backend URL/instance and a local session ID. If a request times out, **retry the same exact key + body**, never create a fresh key merely to dismiss the error. Handle a journal `409` pending/uncertain response by showing a reconcile screen and searching project job history. Do not guess that a pending job is cancelled.

Store accepted job ID and use GET polling to reattach. Refer to `scripts/morphorum_recovery.py` and `scripts/db2_recovery_cli.py`. If the backend has restarted, an animation manifest may report `interrupted`/`resumable`; Studio must ask before explicitly invoking a resume endpoint. Still-image and FFmpeg video job managers have different in-memory persistence and archive behavior; do not assume they all survive a restart identically.

### Timeline and project concurrency

Use a revisioned project GET + conditional `PUT If-Match` for Studio edits. HTTP 412 means the saved project changed elsewhere; offer reload/compare rather than overwriting the browser editor's work. The existing Web UI can still do unconditional saves for compatibility, so guard against that through revision checks on every Studio PUT. Do not cache server absolute paths or perform client-local file writes to backend paths.

### Assets & completed output

Use asset-descriptor `sha256` and `bytes`, download into a `.part` staging file, validate expected digest + basic media magic, then atomically replace the user's selected destination. Validate an audio media type and duration before waveform display; do not assume an arbitrary filename suffix identifies the decoder. Project soundtracks and analyzed Motion Lab WAVs are distinct resources and have different upload limits (40 MiB vs 20 MiB/180 s). MP4/WebM exported video jobs publish `sha256` with DB2.5 and binary responses expose the hash; audio output is not proven until a post-export ffprobe check actually finds an audio track.

Avoid fetching all full-size frames on every SSE event. Deduplicate downloaded frame IDs and use REST job `results` for replay/backfill. SSE is an optimization, not the authoritative record. Cache images in bounded memory/disk; unload distant thumbnails.

### Native UI organization proposal

Suggested initial modules in the **future** Studio repo:

```text
morphorum_studio/
  app.py
  windows/main_window.py
  ui/connection_panel.py
  ui/project_browser.py
  ui/editor.py
  ui/motion_lab.py
  ui/audio_director.py
  ui/render_monitor.py
  ui/preview_player.py
  backend/connection_profiles.py
  backend/auth_store.py
  backend/client.py
  backend/events.py
  backend/recovery.py
  backend/assets.py
  models/project_state.py
  models/job_state.py
tests/
  test_connection.py
  test_render_recovery.py
  test_conflict_saves.py
  test_asset_integrity.py
```

Separate Qt widgets from the transport layer. Use signals/worker threads or async bridges for network calls; never block the GUI event loop with a GET, download or audio decode. The Studio editor should reuse the backend's normalized motion schedules and save semantics instead of inventing a second conflicting project schema.

### Phased first UI build

- **Studio S0:** Create the **new repo only when the user requests it**, choose license/branding, skeleton with PySide6 window, settings and CI.
- **S1:** Connection profiles, trust/identity confirmation, OS credential storage, capability handshake and connection status.
- **S2:** Project browser, model discovery, existing project inspector and conflict-safe save; distinguish local/remote file ownership.
- **S3:** Still image generation, animation submission/reattach, live job progress, completed PNG/GIF preview and verified video export/download.
- **S4:** Native timeline/Motion Lab, smoothing, keyframes, prompt schedules, camera control and audio waveform UX with the correct API payload semantics.
- **S5:** Packaging, launch/updater strategy, Windows physical UI acceptance, then Linux tests. Revisit mobile UX as a separate client, not a replacement for the desktop interface.

Keep the existing browser UI functional throughout. UI appearance can reuse Morphorum's dark glass branding without coupling the native UI to its JavaScript or frontend build system.

## Remaining acknowledged limitations

The backend currently lacks historical durable job SSE replay and a cryptographically secure host-pairing ceremony over ordinary LAN HTTP; a single server owns its idempotency journal. Diffusion does not resume its GPU kernels across a host restart. The New Project Wizard camera-default issue belongs to the Web UI workstream. Large multi-minute Audio Director soundtrack support needs separate upload/transfer design. Any still-open physical checks are recorded in `docs/DB2_FINAL_ACCEPTANCE.md` and **must not be silently marked passed**.

**Handoff readiness rule:** Finish DB2.5 physical tests, record a verified checkpoint and obtain explicit approval for backend branch integration; then the user creates the separate Studio repository and we start S0/S1 from the accepted backend contract.
