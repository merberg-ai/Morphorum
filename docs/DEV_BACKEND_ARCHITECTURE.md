# Morphorum backend-only mode / Morphorum Studio contract

**Status:** architecture approved 2026-10-11; implementation **not started**.
**Branch:** `dev-backend`, created from verified `main` commit `5a14fb52141000ce0316aa7372ffa3e1610a86b1` after Deforum Motion Settings Import integration.
**Rule:** Keep normal Morphorum startup, its browser UI, Linux compatibility, project schemas, and existing generation behavior unchanged. No merge to `main` before physical Windows acceptance.

## Goal

Morphorum shall support two first-class server modes from the **same** backend codebase:

- **Standard:** existing `run.bat`, `run.sh` and `python -m morphorum serve` serve both the API and web UI, without behavioral regression.
- **Backend only:** `run.bat --backend-only` (forwarded to `python -m morphorum serve --backend-only`) starts only the FastAPI service, by default bound to `127.0.0.1:7866`. No browser opening, root HTML page, or `/assets` static files. Existing configured standard-mode port remains independent. The backend service never silently binds to `0.0.0.0`: reject conflicting LAN/host options, or otherwise explicitly guarantee loopback-only behavior.

Morphorum Studio is a separate Windows desktop application/repository. Its installer may clone/pin and install a compatible Morphorum version and reuse user-configured checkpoint and LoRA paths **without copying model data**. Studio manages its own UI dependencies separately from the backend's Python/CUDA environment. Studio may attach to a compatible existing service, or launch its own child process, and may only stop processes it owns. Version/API compatibility and process ownership are mandatory.

## Architectural design

- Refactor `backend/morphorum/app.py` into reusable API route registration plus **conditional UI mounting**, preferably using an application factory (or API router registered by an application factory); do not duplicate business routes.
- Avoid importing/mounting/static-hashing frontend assets in backend-only startup. Preserve the existing normal app import path for test/backwards compatibility.
- Keep the existing generation, animation render, motion preview, model management, audio, project, telemetry, console, video export, depth, managed-download and job managers shared. **Backend only removes UI hosting, not any of their capabilities.**
- Ensure launcher scripts forward `--backend-only` correctly and port selection does not accidentally override `--host` restrictions.
- Loopback binding is necessary but insufficient protection: design local token authentication for mutating and sensitive endpoints, browser-origin/CORS/CSRF boundary checks, and authorization for image/frame/file/stream routes. Do not expose unauthenticated backend-only write APIs to arbitrary local web origins.
- Support reliable health/readiness, version/commit identification, an explicit API compatibility version, and feature/capability discovery. Do not assume the UI and backend are updated in lockstep.
- Keep project files, render manifest ownership, frozen soundtrack snapshots, rendered frames, and motion data compatible across normal and backend-only modes.

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

### DB1: Server split and CLI
- `--backend-only` works through Python CLI and Windows entry scripts, starts on loopback; standard/LAN modes still behave exactly as before.
- Backend-only serves all `/api/*` functional routes and does **not** serve `/` HTML or `/assets/*`.
- No new default downloads, model path changes, or duplicated model installations.
- FastAPI/TestClient route parity tests, CLI/startup/security baseline tests; regular frontend smoke tests must still pass.
- Stop for review and acceptance before advancing.

### DB2: Client contract and safety
- Version/capabilities discovery; token/local-origin boundary and process lifetime semantics; stable errors/status schemas; separate compatibility tests for standard and backend-only modes.
- Verify SSE console delivery, REST job updates and file/image streaming; plan efficient event stream if warranted.

### DB3: Studio workflow completeness
- Verify desktop client can load model, manage projects and timelines, start still/animation render, follow model load progress/frame/step/ETA, view live completed frames, cancel and resume where supported, fetch output files, view GPU telemetry and console, without any web UI.
- Decide whether any missing pause semantics or job-event streaming need new endpoints, avoiding artificial parity claims.

### DB4: Physical Windows acceptance
- Test SDXL on real Windows/CUDA hardware; validate frame-level preview, model-load/overall progress bars, accurate ETA, prompt/frame state, live console, CPU/GPU/RAM/VRAM gauges, cancellation, recovery and MP4/WebM export with frozen soundtrack sync.
- Run all relevant tests and existing browser-mode regression tests; preserve baseline screenshots where useful.
- Create verified checkpoint only after user confirms physical acceptance. Merge to `main` only on explicit approval.

## Out of scope for initial backend-only mode

- Replacing the existing Morphorum browser UI.
- Porting Deforum Motion Studio's Tkinter UI.
- Copying a second generation engine or duplicating user checkpoints.
- Modifying camera compatibility math or audio-import behavior just to support headless operation.
- Promising true sub-step diffusion previews or a network-remote unauthenticated service.

## Desktop integration outlook

Morphorum Studio should remain a **separate repository** (proposed `merberg-ai/Morphorum-Studio`) with its own installer, Qt/PySide6 desktop UI, unified frame/audio/prompt timeline, and backend manager. Pin the backend to compatible tested commits/releases; local installations can be reused. The advanced motion/audio editor is a follow-on project and must not delay DB1.

## Documentation/acceptance principle

All existing server-derived telemetry belongs to the API, not to the browser UI. **Backend-only is permitted to omit only UI hosting; feature data must survive.** Document any real gaps and implement them behind explicit, tested endpoints rather than fabricating equivalent-looking progress bars.
