# Morphorum DB2.1 native-client contract (implementation candidate)

**Branch:** `feature/db2-client-contract` branched from `dev-backend`.
**Status:** source/test candidate; CI and user hardware testing required before merging into `dev-backend`. `main` and DB1 checkpoint stay untouched.
**API contract:** version 1, same as DB1; additional read-only discovery and additive error envelope. No breaking changes to existing render routes, project schemas or standard web UI.

## Discovery and compatibility

`GET /api/health` retains `status`, `app`, `version`, `git_branch`, `git_commit`, `mode`, `api_contract_version`, etc.

New authenticated-when-backend-only `GET /api/client/capabilities` returns a JSON object with:

| Field | Semantics |
|---|---|
| `schema_version` | Capability payload schema, initially 1 |
| `api_contract_version` | Existing Morphorum backend REST contract version (1) |
| `client_protocol_version` | DB2 native-client discovery layer version (1) |
| `instance_id` | Persistent installation identifier (32 lowercase hex characters), **not proof of server authenticity** |
| `boot_id` | Process lifecycle identifier (32 lowercase hex characters), changes on backend process restart |
| `mode` | `standard` or `backend-only` |
| `authentication` | Whether bearer token required; whether pairing is actually implemented (currently **false**) |
| `features` | Boolean flags for render, downloads, source/audio uploads, SSE, video-export availability, and explicit negative flags for unimplemented features |
| `transfers` | Existing **distinct** source-image/WAV/soundtrack workflows and their documented maximum byte counts, accepted media formats and upload/download URL templates |
| `video` | Format/quality options and real-time FFmpeg detection, not a guarantee of a successful export |
| `models` | Current supported family names |
| `events` | Console SSE path; dedicated job SSE explicitly null/unavailable |

Do not use `instance_id` or `boot_id` as secrets, TLS trust anchors or authentication. The stable instance ID is stored inside the ignored `data/backend-instance-id`. Losing/restoring that file changes/duplicates the logical identity, respectively. Native clients must keep configured backend URL + credential ownership separate from this ID. DB2.2 handles secure credential storage and trusted per-client pairing design.

### Compatibility rules

- Compare `api_contract_version` on both health and capabilities. A client that only supports version 1 **must not silently treat an unknown value as compatible**.
- Check feature flags rather than assuming GIF/video or audio download support. `video_export` is dynamic (based on host FFmpeg detection).
- Recheck the identity and `boot_id` at reconnect. Console event IDs come from an **in-memory buffer** and must reset after a new boot.
- The discovery route requires the same bearer token as every other `/api/*` endpoint in backend-only mode.
- Plain HTTP on a private LAN does **not** encrypt credentials. Never expose backend-only mode to a public/WAN network. Use TLS or a trusted encrypted tunnel if the LAN cannot be trusted.

## API payload examples

### Model ID lookup and SDXL image

Use `GET /api/models?family=sdxl&kind=checkpoints` and take the **id** field from a matching checkpoint. The filename stem alone is not the model ID.

```http
POST /api/generation/jobs
Content-Type: application/json
Authorization: Bearer [secret]

{
  "model_id": "[indexed-model-id]",
  "prompt": "Haunted CRT computer, cinematic",
  "negative_prompt": "",
  "width": 512,
  "height": 512,
  "steps": 20,
  "guidance_scale": 6.5,
  "sampler": "dpmpp_2m_sde",
  "seed": 12345,
  "seed_mode": "fixed",
  "images": 1
}
```

Response is the job object with `id` and `status`. Poll `GET /api/generation/jobs/{id}`. The completed `results[*].url` is an authenticated PNG route.

### Animation and final preview

```http
GET /api/animation/projects/{project_id}
```

returns `{"project": full_saved_project, "path": server_path}`. The `path` is for diagnostics only; never assume the client can open it.

```http
POST /api/animation/renders
Content-Type: application/json
Authorization: Bearer [secret]

{"project": { ... full saved project object ... }}
```

Do **not** submit only `{"project_id": ...}`; that returns HTTP 400. Response has `id`, `project_id`, `status`. Poll `GET /api/animation/renders/{render_id}` for `current_frame`, `current_step`, `progress` (fraction 0..1), `eta_seconds`, `current_prompt_state`, `current_frame_state`, and `latest_frame_url`. Latest URL is a **completed** frame, not an in-diffusion step. GET frames/GIF with Authorization:

```text
/api/animation/renders/{project_id}/{render_id}/frames/{frame_number}
/api/animation/renders/{project_id}/{render_id}/preview
```

A completed render creates the GIF. Failed/interrupted renders may have completed PNGs but no GIF.

### Video export

```text
GET  /api/animation/video/availability
POST /api/animation/renders/{project_id}/{render_id}/video
     {"format":"mp4","quality":"balanced"}
GET  /api/animation/video/jobs/{video_job_id}
GET  /api/animation/renders/{project_id}/{render_id}/videos
GET  /api/animation/renders/{project_id}/{render_id}/video/{format}/{quality}/{fps}
```

FFmpeg is required on the backend. Video export, frozen audio sync and remote MP4 validation are follow-on physical tests, not yet part of DB2.1 acceptance.

### Existing project-owned uploads

```text
POST /api/animation/projects/{project_id}/source-image           # raw image bytes
POST /api/animation/projects/{project_id}/motion-lab/audio-analyze # PCM WAV <=20 MiB, <=180s
POST /api/animation/projects/{project_id}/motion-import/soundtrack # WAV/MP3/OGG/FLAC <=40 MiB
```

Those routes are distinct. Do not assume there is a generic `/api/assets` route or playable audio download yet. Consistent asset descriptors/streaming transfers are DB2.3.

## Additive error contract

For common HTTP routing and request-validation errors, responses now preserve FastAPI's `detail` (string or validation array) **and add**:

```json
{
  "detail": "Animation project payload is required.",
  "error": {
    "code": "INVALID_REQUEST",
    "message": "Animation project payload is required.",
    "request_id": "24-character-hex"
  }
}
```

`X-Request-ID` header matches `error.request_id` for support diagnostics. Typical codes: `AUTH_REQUIRED` (401), `BROWSER_ORIGIN_FORBIDDEN` (403 browser Origin blocked in backend-only), `FORBIDDEN` (403 otherwise), `INVALID_REQUEST` (400), `NOT_FOUND` (404), `CONFLICT` (409), `VALIDATION_ERROR` (422), and `HTTP_ERROR` for unmapped status. This is **additive**, keeping existing browser consumers of `detail` working.

Unhandled internal exceptions and non-HTTP server errors are not promised a uniform client error payload in DB2.1. Clients must gracefully handle bad JSON, timeouts, server disconnection or an unknown error code. `request_id` is for correlation only; it grants no access.

## Standalone reference client (Ubuntu Mini)

Download the Python standard-library client source from the feature branch (no GPU/PyTorch/Morphorum install on the client machine):

```bash
mkdir -p ~/tmp
curl -fsSL https://raw.githubusercontent.com/merberg-ai/Morphorum/feature/db2-client-contract/scripts/morphorum_client.py -o ~/tmp/morphorum_client.py
python3 ~/tmp/morphorum_client.py --help
```

Use the existing backend-only access token file, **never put the token on the command line**:

```bash
BASE="python3 ~/tmp/morphorum_client.py --url http://192.168.1.24:7866 --token-file ~/tmp/backend-access-token"
# These are direct examples, not an instruction to expand the BASE variable:
python3 ~/tmp/morphorum_client.py --url http://192.168.1.24:7866 --token-file ~/tmp/backend-access-token doctor
python3 ~/tmp/morphorum_client.py --url http://192.168.1.24:7866 --token-file ~/tmp/backend-access-token models
python3 ~/tmp/morphorum_client.py --url http://192.168.1.24:7866 --token-file ~/tmp/backend-access-token projects
```

Optional repeat-image acceptance:

```bash
python3 ~/tmp/morphorum_client.py --url http://192.168.1.24:7866 --token-file ~/tmp/backend-access-token generate --model artUniverse_sdxlV60_874843 --watch
```

Existing successful render can be inspected without rerendering:

```bash
python3 ~/tmp/morphorum_client.py --url http://192.168.1.24:7866 --token-file ~/tmp/backend-access-token watch EXISTING_RENDER_ID --kind animation
python3 ~/tmp/morphorum_client.py --url http://192.168.1.24:7866 --token-file ~/tmp/backend-access-token download-gif PROJECT_ID EXISTING_RENDER_ID --output ~/tmp/db2-preview.gif
```

The client refuses external redirects, accepts only same-backend `/api/` download URLs, never includes the token in query strings, and atomically replaces a downloaded file after basic PNG/GIF signature verification. Commands that create a render/generation job **do not retry automatically** after ambiguous network failure. DB2.4 will add durable idempotency tokens and recovery semantics.

## DB2.1 acceptance gates

1. CI: `python -m pytest tests/test_db2_client_contract.py tests/test_backend_only.py tests/test_api.py tests/test_health.py`, complete suite, syntax and browser JS regression tests.
2. Standard server: existing browser UI and existing `detail` errors work unchanged.
3. Backend-only loopback and Ubuntu LAN: anonymous discovery 401, valid token discovery 200, Origin 403, same backend instance ID across restarted processes, changing boot ID, readable formats/features.
4. Ubuntu: `doctor`, `models`, `projects` through Python reference client; existing render status, PNG/GIF retrievable.
5. Stop for user confirmation before DB2.2. Do not merge `dev-backend` or `main` automatically.

**Explicitly not built in DB2.1:** per-client pairing/revocation, new general media transfer API, soundtrack binary download, idempotent job submission, persistent job event SSE, concurrency/ETag, Qt connection panel.

## DB2.1 acceptance recorded (2026-10-12)

**Automated:** GitHub Actions at code commit `8fe589fb52232339107cd3d5a3a18e172ff3274b` passed **506 tests, 1 skipped, 0 failed**, including Morphorum self-test; syntax/browser JavaScript checks and installer checks also passed.

**Physical remote client:** The user switched the Windows Omen backend-only service to `feature/db2-client-contract` and ran the Ubuntu Mini reference client checks for `doctor`, `models`, `projects`, and authenticated download/validation of a prior successful animation GIF. **User reports all physical commands completed successfully.** The user was on a phone with ConnectBot and could not conveniently copy the complete console output; therefore the detailed JSON/diagnostic transcript was not independently reviewed in this record. Do not reinterpret that limitation as a failed test.

**Acceptance:** DB2.1 Ubuntu remote-client acceptance **passed by user report**, pending separate normal browser-mode GPU regression from the DB1 backlog. DB2.2 may be planned next. Draft PR #27 remains open and **unmerged**; `dev-backend` and `main` have not been advanced.

**Mobile-friendly test output convention going forward:** Make acceptance scripts print brief, individually labeled PASS/FAIL lines and a final summary, with full logs retained as files on the test machine. Never print bearer tokens. Do not require users to paste long terminal output merely to confirm success.
