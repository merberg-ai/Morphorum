# Morphorum API-only mode (DB1–DB2.5 integrated)

**Current status (2026-10-14):** Integrated into `main` in [PR #32](https://github.com/merberg-ai/Morphorum/pull/32) after DB1–DB2.5 physical acceptance. Morphorum Studio connection and the normal/browser + backend-only launch smoke tests also passed against promoted `dev-ui`. This mode removes **browser UI serving only**; generation, animation, GPU telemetry, live completed-frame previews, console SSE, project/audio services and exports remain on the API. The dated DB1-only test notes below are retained as historical records; their old pending language was superseded by the [DB2.5 final acceptance](DB2_FINAL_ACCEPTANCE.md) and [promotion record](BACKEND_PROMOTION_20261014.md).

## Start

On Windows, from the installed Morphorum folder:

```powershell
.\run.bat --backend-only
```

Starts API-only service at **127.0.0.1:7866**, separate from the usual browser service on 7865.

To allow a desktop client on another PC on a **trusted LAN**:

```powershell
.\run.bat --backend-only --lan
```

Starts on **0.0.0.0:7866**, accessible to LAN clients via the rendering PC's **actual IP** (for example `192.168.1.50:7866`). Do not enter `0.0.0.0` into Studio as its destination. You may pass `--port 9000` to the batch launcher for a custom port.

Python entry point alternative (Windows/Linux):

```powershell
.\.venv\Scripts\python.exe -m morphorum serve --backend-only --host 0.0.0.0 --port 7866
```

Linux `./run.sh --backend-only` and `./run.sh --backend-only --lan` support equivalent defaults.

Normal `run.bat` / `run.sh` still serve the existing web UI and API; the standard LAN launcher remains unchanged.

## Auth and network safety

All `/api/*` endpoints, including read-only GPU stats, file/preview retrieval, model lists, render job controls and console/SSE, require a bearer token in API-only mode. Browser-origin requests are rejected in API-only mode; native desktop clients must supply the header.

The token is generated once at `data/backend-access-token` when the backend first starts (on POSIX, mode 0600). **Do not paste this file or token into issue reports, logs, screenshots, public chat, or repositories.** The directory is gitignored. Studio should store credentials in an OS-protected credential store, and allow secure pairing rather than prompting users to paste raw tokens casually. A valid environment-supplied `MORPHORUM_BACKEND_TOKEN` (at least 32 characters) overrides the file for managed launches; treat it as a secret and never print it.

A client can supply the token with the standard Authorization header. Example **on the backend machine**, with the local token file:

```powershell
$token = (Get-Content .\data\backend-access-token -Raw).Trim()
Invoke-RestMethod http://127.0.0.1:7866/api/health -Headers @{ Authorization = "Bearer $token" }
```

Expected: JSON status ok, mode `backend-only`, `api_contract_version: 1`. Without the header, `/api/health` returns HTTP 401. `/`, `/assets/app.js`, `/docs`, and `/openapi.json` are not served in API-only mode.

For remote clients: acquire the token through a trusted out-of-band mechanism; use the GPU computer's LAN address, open only the required Windows Firewall port for the private LAN as necessary, and **do not expose the port to the internet or an untrusted network**. Raw LAN HTTP does not encrypt the token or media in transit; for untrusted networks use an encrypted VPN/tunnel or future TLS termination. Loopback also requires authorization.

## Verified Windows + Ubuntu Mini acceptance (2026-10-12)

**User-reported physical tests passed** against backend-only mode on the Windows Omen at `D:\\Morphorum-test`, branch `dev-backend` commit `04100f7525b81c926299e9226c3a1da40b28ad3e`:

- Windows local backend-only startup: authenticated `GET /api/health` returns `status=ok`, `mode=backend-only`, `api_contract_version=1`, no frontend asset version.
- Windows `GET /api/system/telemetry` authenticated: CPU/RAM metrics returned and NVIDIA GPU backend detected.
- Windows unauthenticated `GET /api/health` correctly returns HTTP 401; `GET /` returns HTTP 404 instead of browser UI.
- Ubuntu Mini client on the trusted LAN successfully completed the seven instructed tests against `192.168.1.24:7866`: authenticated health, hardware telemetry, image-generation job endpoint, project-list endpoint, console SSE connection, unauthenticated HTTP 401 rejection, and web-root HTTP 404 rejection. No bearer token is stored in this report.
- GitHub Actions at tested commit: **499 tests passed, 1 skipped** in backend workflow, plus successful syntax and installer workflow runs.
- **Remote SDXL still-image generation accepted by user:** Ubuntu Mini submitted an authenticated `POST /api/generation/jobs` using the installed `artUniverse_sdxlV60_874843` SDXL checkpoint (looked up by its real model-index ID), polled the job to completion, and downloaded a valid completed PNG from `GET /api/generation/jobs/{job_id}/images/{filename}`. The generated haunted-computer/skull image was shared and visually confirmed. This validates the **end-to-end still-image remote GPU workflow** including job submission, job polling and file retrieval, but does not establish animation-specific frame-preview parity. The first attempt returned HTTP 400 due to an incorrect request schema / name-vs-ID confusion in the *test script*, not a confirmed backend defect.

**DB1 remote end-to-end status:** remote SDXL still-image generation/download **passed**; remote SDXL animation generation **completed after correcting camera configuration**; authenticated GIF retrieval/playback **passed**. Initial live polling and frame retrieval were exercised by the Ubuntu test client, although detailed prompt/frame-state, ETA accuracy, and MP4/WebM export are not independently asserted here. **Still open:** standard browser-mode regression on Windows after this branch's changes and optional video export parity. No merge to `main` until the outstanding gate is accepted.

## Remote SDXL animation failure diagnosed (2026-10-12)

**User-reported remote test:** Ubuntu Mini successfully retrieved and submitted the saved `api-test-short` project (`api-test-short-9f178d9f`) using `POST /api/animation/renders` with the full `{"project": ...}` payload. The previous helper script incorrectly submitted only `{"project_id": ...}` and received HTTP 400; this was **test-client misuse, not an API bug**.

The accepted render `anim-20261012-060549-b24a36` generated **84 frame records** but ended `status=failed`, without final GIF. The job reported:

```
3D depth/camera warp failed at frame 84:
3D camera projection produced no visible pixels.
```

Code location: `animation_render.py` wraps `Camera3DError` from `animation_3d.render_depth_warp`. The camera module raises this exception when projected source pixels are absent/behind the camera/outside the image bounds. This may be caused by an extreme resolved 3D translation/rotation/FOV or a projection edge case; root cause is **not yet confirmed**. A normal completed animation runs `_build_render_preview` in `_complete`; failed jobs retain frame PNGs and **do not** build `preview.gif`, so the missing GIF is expected for this failure.

**Resolution:** The user identified incorrect camera settings in the new project's configuration, corrected them, and subsequently completed a remote animation render. Preserve the failed run for regression diagnostics; investigate the New Project Wizard camera defaults/validation separately. This historical failure is **not** an ongoing DB1 remote-render blocker.

## Follow-up: successful corrected remote animation (2026-10-12)

**User-reported result:** After correcting the camera settings in the saved `api-test-short` project, the user reran the original Ubuntu Mini remote animation test script and **the render finished successfully**. This confirms remote API-driven SDXL animation submission and successful completion on the Windows GPU backend. The preceding 84-frame 3D projection failure was due to incorrect camera settings in that project. Do not interpret the earlier failure as proof of a rendering-engine or networking bug.

**Deferred UI issue:** Investigate the Morphorum browser **New Project Wizard**. The user reports a camera-setting setup issue that led to the invalid 3D configuration. Reproduce and validate wizard defaults, applied 3D motion schedules and saved project camera values. Fix in the web UI workstream later, not as part of DB1 backend startup.

**Follow-up verified:** Ubuntu Mini downloaded the finished animation's `preview.gif` with an authenticated call to `/api/animation/renders/{project_id}/{render_id}/preview`. The user confirmed the GIF is valid and the test **passed**. This verifies that the remote completed animation can be retrieved and viewed without the browser UI. **Pending:** MP4/WebM export and normal-browser-mode regression (if not already physically checked). Retain original failed render frames for diagnostics; keep `dev-backend` separate from `main` until approved.

## DB1 remote-verification checkpoint summary (2026-10-12)

**User-reported status: PASS** for API-only mode on Windows and remote Ubuntu Mini LAN access, authenticated SDXL still-image generation/download, corrected SDXL animation completion, and authenticated final animation GIF download/validation.

- Rendering PC: Windows Omen at `D:\\Morphorum-test`, server `192.168.1.24:7866`, token-protected `dev-backend`.
- Client: Ubuntu Mini with only a bearer token and HTTP calls; no shared model files or browser UI required.
- Workflows: health, unauthorized HTTP 401, absent browser root HTTP 404, telemetry, project retrieval, generation/render jobs, console SSE, image PNG and animation GIF remote retrieval.
- Earlier camera projection failure at frame 84 attributed by user to wrong camera settings, corrected before successful animation; New Project Wizard camera initialization/validation requires a separate follow-up.
- GitHub CI: 499 passed, 1 skipped backend tests on implementation commit `04100f7525b81c926299e9226c3a1da40b28ad3e`; syntax and installer checks passed.
- **Out of scope for claiming full release acceptance:** ordinary web UI regression on this branch, MP4/WebM video export, audio-mux parity and richer event stream/client integration.

This record is a checkpoint of the **verified API-only remote workflow**, not proof that every regular/UI/export path has been physically exercised.

## Physical DB1 acceptance checklist

1. Switch the Morphorum installation to `dev-backend`. Start normal `run.bat`; verify browser loads and animation/model functionality remains available at its configured port.
2. Stop it. Start `run.bat --backend-only`; verify the backend responds when supplied with its token, rejects missing/incorrect token, and doesn't serve web frontend routes. Check that `/api/system/telemetry`, `/api/generation/jobs`, `/api/animation/projects` and `/api/console` work with the token.
3. Validate on the GPU PC that no model directories changed, no new model download occurs, and video/frame URLs and model-load/render status are exposed as usual. For a meaningful live-preview check, submit a **short disposable SDXL animation** from an API client and poll `GET /api/animation/renders/{render_id}` while it runs. Inspect `latest_frame_url`, `current_frame`, `current_step`, `progress`, and `eta_seconds`. An API-only server does not itself show a progress bar; the Studio client will render those values.
4. Stop, then start `run.bat --backend-only --lan`. From a second PC on the trusted LAN, use its token securely and confirm authenticated health, GPU telemetry, console, progress and preview frame retrieval via the GPU machine's LAN IP. Verify unauthenticated calls return HTTP 401.
5. Stop the backend. Confirm starting standard Morphorum again works unchanged. Do not publish the token when sharing testing results.

**DB1 regression suite:** `python -m pytest tests/test_backend_only.py tests/test_cli.py tests/test_api.py tests/test_health.py -q`; backend workflows and PowerShell/Bash syntax checks should also pass. DB1 remains **unverified** until GitHub CI and the user's Windows hardware gate pass.

## Known constraints and next steps

- Native Studio lives in the separate [Morphorum-Studio](https://github.com/merberg-ai/Morphorum-Studio) repository. Backend-only has API endpoints and live *completed*-frame previews, **not** every intermediate diffusion step.
- Existing REST polling, console SSE and the DB2 typed client events/recovery contract are available. Durable historical SSE replay and a cryptographically secure pairing ceremony remain unsupported.
- Existing cancel/resume support stays available; a dedicated pause feature must be audited separately before claiming parity.
- Server/client file paths differ across LAN machines; Studio must upload soundtrack/asset bytes or use explicit managed shares, not send a Windows client path as if it were a backend file.
- Keep access to trusted private networks only. Do not enable public bind without credentials and transport protection.
