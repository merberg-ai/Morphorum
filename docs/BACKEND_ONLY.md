# Morphorum API-only mode (DB1 test candidate)

**Workstream:** `dev-backend` — never merge until Windows physical acceptance and CI are verified. This mode removes **browser UI serving only**; generation, animation, GPU telemetry, live completed-frame previews, console SSE, project/audio services and exports remain on the API.

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

## Physical DB1 acceptance checklist

1. Switch the Morphorum installation to `dev-backend`. Start normal `run.bat`; verify browser loads and animation/model functionality remains available at its configured port.
2. Stop it. Start `run.bat --backend-only`; verify the backend responds when supplied with its token, rejects missing/incorrect token, and doesn't serve web frontend routes. Check that `/api/system/telemetry`, `/api/generation/jobs`, `/api/animation/projects` and `/api/console` work with the token.
3. Validate on the GPU PC that no model directories changed, no new model download occurs, and video/frame URLs and model-load/render status are exposed as usual. For a meaningful live-preview check, submit a **short disposable SDXL animation** from an API client and poll `GET /api/animation/renders/{render_id}` while it runs. Inspect `latest_frame_url`, `current_frame`, `current_step`, `progress`, and `eta_seconds`. An API-only server does not itself show a progress bar; the Studio client will render those values.
4. Stop, then start `run.bat --backend-only --lan`. From a second PC on the trusted LAN, use its token securely and confirm authenticated health, GPU telemetry, console, progress and preview frame retrieval via the GPU machine's LAN IP. Verify unauthenticated calls return HTTP 401.
5. Stop the backend. Confirm starting standard Morphorum again works unchanged. Do not publish the token when sharing testing results.

**DB1 regression suite:** `python -m pytest tests/test_backend_only.py tests/test_cli.py tests/test_api.py tests/test_health.py -q`; backend workflows and PowerShell/Bash syntax checks should also pass. DB1 remains **unverified** until GitHub CI and the user's Windows hardware gate pass.

## Known constraints and next steps

- Studio isn't built yet. Backend-only has API endpoints and live *completed*-frame previews, **not** every intermediate diffusion step.
- Existing REST polling and console SSE stay available. Dedicated job-progress SSE/push events, native Studio client and secure LAN pairing UX are DB2/Studio work.
- Existing cancel/resume support stays available; a dedicated pause feature must be audited separately before claiming parity.
- Server/client file paths differ across LAN machines; Studio must upload soundtrack/asset bytes or use explicit managed shares, not send a Windows client path as if it were a backend file.
- Keep access to trusted private networks only. Do not enable public bind without credentials and transport protection.
