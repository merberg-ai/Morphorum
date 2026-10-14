# Morphorum backend-only mode / Morphorum Studio contract

**Current status (2026-10-14):** DB1 through DB2.5 were physically accepted on Windows Omen/Ubuntu Mini and integrated into `main` via PR #32, merge commit `0cb5d489e27b5193fac8dd075d418b8e324beddd`. The integrated `dev-ui` branch also passed user testing of normal/browser and backend-only modes and the Morphorum Studio connection test on 2026-10-14. The separate [Morphorum-Studio](https://github.com/merberg-ai/Morphorum-Studio) repository now exists and is under active development.
**Original workstream:** `dev-backend` branched from `main` at `5a14fb52141000ce0316aa7372ffa3e1610a86b1`. Its milestones and original acceptance gates are retained below for historical traceability.
**Compatibility rule:** Keep normal browser launch, Linux compatibility, project schemas and existing generation behavior intact. Backend-only must remove only browser hosting; client API capability data must survive. See [promotion record](BACKEND_PROMOTION_20261014.md).

## Goal

Morphorum shall support two first-class server modes from the **same** backend codebase:

- **Standard:** existing `run.bat`, `run.sh` and `python -m morphorum serve` serve both the API and web UI, without behavioral regression.
- **Backend only:** `run.bat --backend-only` (forwarded to `python -m morphorum serve --backend-only`) starts only the FastAPI service, by default bound to `127.0.0.1:7866`. No browser opening, root HTML page, or `/assets` static files. Existing configured standard-mode port remains independent.
- **Backend only over LAN (explicit opt-in):** support `run.bat --backend-only --lan` or equivalently `python -m morphorum serve --backend-only --host 0.0.0.0 --port 7866`. Bind to all IPv4 interfaces **only when requested**, show detected machine LAN URLs such as `http://192.168.x.x:7866` (clients must never use `0.0.0.0` as destination), and use the same generation/preview/telemetry APIs. LAN mode **must require authentication before accepting sensitive API requests**; do not enable open unauthenticated access as an interim stage. Remote-client API, SSE, image preview and file transfer parity are acceptance requirements.

Morphorum Studio is a separate Windows desktop application/repository. Its installer may clone/pin and install a compatible Morphorum version and reuse user-configured checkpoint and LoRA paths **without copying model data**. Studio manages its own UI dependencies separately from the backend's Python/CUDA environment. Studio may attach to a compatible existing service, or launch its own child process, and may only stop processes it owns. Version/API compatibility and process ownership are mandatory.

## Architectural design

- Refactor `backend/morphorum/app.py` into reusable API route registration plus **conditional UI mounting**, preferably using an application factory (or API router registered by an application factory); do not duplicate business routes.
- Avoid importing/mounting/static-hashing frontend assets in backend-only startup. Preserve the existing normal app import path for test/backwards compatibility.
- Keep the existing generation, animation render, motion preview, model management, audio, project, telemetry, console, video export, depth, managed-download and job managers shared. **Backend only removes UI hosting, not any of their capabilities.**
- Ensure launcher scripts forward `--backend-only`, `--lan`, host and port correctly. Default to loopback, but honor explicit `0.0.0.0` requests in backend-only mode; avoid accidental public binding caused by saved LAN settings or the normal-mode launcher. On LAN startup, print a clear warning and the actual LAN address/port to connect to.
- Authentication is mandatory for backend-only mode, particularly on LAN: secure generated or supplied bearer token for sensitive endpoints including job/control, project, paths/settings, downloads, audio/source uploads, previews and console/SSE streaming. Keep the token out of URL query strings and logs; a PySide6 native HTTP client can supply authorization headers. Consider a minimal unauthenticated health response only if it discloses no sensitive data. Restrict browser origins, avoid permissive CORS and protect browser-origin requests; don't treat CORS as authentication. Do not enable LAN binding before the DB1 baseline protects these resources. Trust-only-LAN HTTP is an explicit threat-model limitation: recommend VPN/TLS for untrusted networks, prohibit direct internet exposure.
- Support reliable health/readiness, version/commit identification, an explicit API compatibility version, and feature/capability discovery. Do not assume the UI and backend are updated in lockstep.
- Keep project files, render manifest ownership, frozen soundtrack snapshots, rendered frames, and motion data compatible across normal and backend-only modes.
- Studio's Windows file-picker paths are **client paths** and may refer to a different PC. Use authenticated upload/download APIs or explicitly managed shared folders for soundtrack, source pictures, project assets and finished videos; never assume the backend can open `C:\\...` from the Studio PC. Preserve responsive previews and progress on LAN connections, with reconnection and resume behavior. Document concurrent UI/client editing hazards and ownership of render jobs.

## Feature parity is a *hard acceptance requirement*

Existing API capabilities to retain in backend-only mode:

| Area | Existing contract / route | Studio use |
| --- | --- | --- |
| Status and compatibility | `GET /api/health`, `GET /api/generation/capabilities` | startup readiness, version and model capabilities |
| Machine stats | `GET /api/system/telemetry`, `GET /api/system/gpu-memory` | CPU/GPU/RAM/VRAM meters, CUDA memory info |
| Model setup | `GET /api/models`, `GET /api/settings`, managed-model endpoints | available models and paths |
| Still generation | `POST /api/generation/jobs`, `GET /api/generation/jobs/{job_id}`, image routes | progress, ETA, completed images, cancellation |
| Animation render | `POST /api/animation/renders`, `GET /api/animation/renders/{render_id}` | frame, diffusion step, model loading, percentage, ETA, prompt/frame telemetry |
| Render image previews | `GET /api/animation/renders/{project_id}/{render_id}/frames/{frame}`, `.../preview` | latest completed frames and animated preview |
| Motion preview | `POST /api/animation/motion-preview`, GET job/image/frames | geometry preview playback |
| Render controls | cancel/resume endpoints already available | cancellation/recovery; examine explicit pause support and do not claim a pause endpoint exists without implementing it |
| Console events | `GET /api/console/stream` (SSE) and snapshot endpoint | continuous diagnostics and toasts |
| Project and timeline | existing project CRUD, resolve-frame/resolve-timeline, timeline tracks, motion lab, audio and Deforum motion import endpoints | project editor and animation orchestration |
| Export | existing video export endpoints | finished MP4/WebM with audio |

**Definition of “live preview”:** timely display of the newest *completed* rendered frame(s) while a job is active; not necessarily previews of intermediate, still-denoising diffusion steps. Do not promise diffusion-step preview until explicitly implemented and tested. Preview URLs and image responses must remain usable by a native HTTP client without web static assets.

Existing frontend polls render/generation job state and telemetry and consumes console SSE. This already supplies the necessary data, but desktop integration may add an **optional job-event SSE stream** with event identifiers/reconnection semantics and frame-ready/progress/model-loading notifications. Do not require this stream for the initial backend-only startup gate; polling remains a compatible fallback. UI update frequency must avoid stressing a GPU-bound renderer.

## Gates

### DB1: Server split and CLI (implemented and physically accepted)
- `--backend-only` works through Python CLI and Windows entry scripts. Starts on loopback by default, and supports explicit `--lan` / `--host 0.0.0.0` with mandatory minimal API authentication. Standard browser and existing standard LAN modes still behave exactly as before.
- Backend-only serves all `/api/*` functional routes and does **not** serve `/` HTML or `/assets/*`.
- No new default downloads, model path changes, or duplicated model installations.
- FastAPI/TestClient route parity tests, CLI/startup/security baseline tests (including authenticated vs unauthorized LAN API access and actual bind address); regular frontend smoke tests must still pass.
- Stop for review and acceptance before advancing.

### DB2: Client contract and safety (DB2.1–DB2.5 implemented and physically accepted)
- DB2.1: additive versioned capabilities, stable backend installation/boot IDs, structured compatible errors, Python reference client. Verified checkpoint: `checkpoint/db2-1-client-contract-verified-20261012`.
- DB2.2: local-only per-client revocable credentials, named connection profiles, safe token storage boundaries and identity-aware reconnection. Verified checkpoint: `checkpoint/db2-2-connection-security-verified-20261012`.
- DB2.3: project asset descriptors, soundtrack/Motion Lab WAV retrieval, SHA-256 transfers, conditional If-Match saves. Verified checkpoint: `checkpoint/db2-3-project-assets-verified-20261012`.
- DB2.4: idempotent GPU submissions, typed SSE with restart/gap detection, persistent remote render sessions; physical 120-frame render survived client Ctrl+C/reconnect and downloaded final GIF. Verified checkpoint: `checkpoint/db2-4-live-render-recovery-verified-20261012`.
- DB2.5: final video checksum integrity, synthetic audio/FFmpeg acceptance fixture, restart/lost-response smoke tests, normal browser regression and new-repo Studio handoff. **Physically accepted on 2026-10-12** with separate integrated-mode confirmation on 2026-10-14; detailed test provenance remains in `DB2_FINAL_ACCEPTANCE.md`.
- See `DB2_FINAL_ACCEPTANCE.md` and `STUDIO_CLIENT_HANDOFF.md`; no insecure LAN pairing ceremony or durable SSE replay is claimed.

### DB3: Studio workflow completeness (planned)
- Verify desktop client can load model, manage projects and timelines, start still/animation render, follow model load progress/frame/step/ETA, view live completed frames, cancel and resume where supported, fetch output files, view GPU telemetry and console, without any web UI.
- Decide whether any missing pause semantics or job-event streaming need new endpoints, avoiding artificial parity claims.

### DB4: Physical Windows acceptance (planned)
- Test SDXL on real Windows/CUDA hardware in backend-only loopback **and remote LAN** modes; validate authenticated remote frame-level preview, source/audio upload, project operation, model-load/overall progress bars, accurate ETA, prompt/frame state, live console/SSE, CPU/GPU/RAM/VRAM gauges, cancellation, recovery and remote MP4/WebM download/export with frozen soundtrack sync.
- Run all relevant tests and existing browser-mode regression tests; preserve baseline screenshots where useful.
- Create verified checkpoint only after user confirms physical acceptance. Merge to `main` only on explicit approval.

## Out of scope for initial backend-only mode

- Replacing the existing Morphorum browser UI.
- Porting Deforum Motion Studio's Tkinter UI.
- Copying a second generation engine or duplicating user checkpoints.
- Modifying camera compatibility math or audio-import behavior just to support headless operation.
- Promising true sub-step diffusion previews, direct WAN exposure, or an unauthenticated LAN service.

## Desktop integration outlook

Morphorum Studio should remain a **separate repository** (proposed `merberg-ai/Morphorum-Studio`) with its own installer, Qt/PySide6 desktop UI, unified frame/audio/prompt timeline, and backend manager. Pin the backend to compatible tested commits/releases; local installations can be reused **or a remote LAN backend can be connected with explicit host/port and secure token**. The advanced motion/audio editor is a follow-on project and must not delay DB1.

## Desktop UI direction (concept for discussion)

- A dark studio workspace with black/near-black backgrounds, dark blue and dark purple accent areas, graphite/grey panels and readable light text. No large bright surfaces; clear color semantics and configurable UI scale.
- Main frame preview and scene monitor, primary dockable multitrack timeline (audio waveform, frequency channels, camera X/Y/Z & rotations, prompts, LoRA/parameter automation, markers), inspector/settings panel, and bottom collapsible renders/console/profiling panel.
- Keep important render controls always reachable: model, image size, FPS, frame count, cadence, prompt schedules, active LoRAs, render/pause-if-supported/cancel; don't conceal all of them behind tabs.
- Native Qt/PySide6 application, with configurable pane layout, shortcuts, detachable graph/preview and a clear connection panel for Local or Remote backend with connected/authenticated/job-active states.
- UI remains usable while a long GPU job runs: move network calls, file transfers, playback and waveform/audio analysis off the UI thread. Timeline follows project-frame time and offers audio-sync scrubbing independent of render FPS. Qt styling must not require the browser assets.
- Design choices remain conceptual until Studio implementation; this doc locks API and startup compatibility, not a full finalized mockup.

**DB1 test procedure:** See [`BACKEND_ONLY.md`](BACKEND_ONLY.md) for authentication and loopback/LAN startup steps, API checks, and the Windows physical acceptance checklist. See [`STUDIO_AUDIO_DIRECTOR_PLAN.md`](STUDIO_AUDIO_DIRECTOR_PLAN.md) for the soundtrack-first motion/prompt/seed roadmap.

## Documentation/acceptance principle

All existing server-derived telemetry belongs to the API, not to the browser UI. **Backend-only is permitted to omit only UI hosting; feature data must survive.** Document any real gaps and implement them behind explicit, tested endpoints rather than fabricating equivalent-looking progress bars.
