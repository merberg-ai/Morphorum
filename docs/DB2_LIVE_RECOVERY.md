# DB2.4: Live progress, safe submission replay and render recovery

**Status:** automated implementation candidate. Ubuntu Mini / Windows Omen physical acceptance is still required.
**Branch:** `feature/db2-live-recovery` forked from verified DB2.3 checkpoint `2b986186493680bbc255e3af9fbb35feb322f867`.
**Draft PR:** #30, targeting `feature/db2-project-assets`. No code merged to DB2.3/DB2.2/DB2.1, `dev-backend` or `main`.
**Model/render code:** no changes to diffusion math, camera schedules, source media or GPU engine.

## What's implemented

### Durable opt-in job submission keys

Existing job submission routes now accept optional HTTP `Idempotency-Key`:

- `POST /api/generation/jobs`
- `POST /api/animation/renders`
- `POST /api/animation/renders/{project_id}/{render_id}/video`

If the header is omitted, existing browser callers behave as before. The key is 8–128 permitted ASCII characters and scoped to the current caller's bearer credentials + operation (for standard mode, the local browser caller). Canonical JSON body must be the same on a retry.

Server writes a private, checksum-addressed journal entry **before** enqueueing GPU work and persists the accepted job ID/result afterward. An identical retry can return the same job ID, including after process restart; for active jobs, it fetches the latest status through the manager. A reused key for a different JSON payload returns **409 CONFLICT**. A reservation left pending after an uncertain server failure also returns **409** rather than risking a duplicate job. Never treat 409 as permission to submit again with a new key without inspecting existing work.

A pending reservation cannot reliably reconstruct a job ID when the process dies between enqueue and journal commit. This is a deliberately safe **stop-and-reconcile** state, not a guarantee of exactly-once commit after every possible crash. The journal only coordinates within one backend process, not multiple independent servers sharing the same data directory. Never expose multiple writers to the same journal directory. Journal records contain request hashes/IDs, not raw bearer tokens or project prompts.

### Typed SSE event feed

```text
GET /api/client/jobs/{kind}/{job_id}/events?boot_id=PREVIOUS_BOOT_ID
kind = animation | image | video
```

Authentication is exactly the same as other `/api/*` endpoints in backend-only mode. The stream carries `job_snapshot`, `job_progress`, `frame_ready`, terminal `job_completed`/`job_ended`, and `stream_reset` when the supplied previous backend boot ID differs. Every event ID starts with this process's boot ID. The stream sends only compact progress snapshots, not all completed frame data on each poll.

**Important:** This is **not a durable historical SSE replay service**. When Studio reconnects it must issue authoritative `GET /api/animation/renders/{id}` (or image/video job GET), inspect completed `results` and download missing PNGs, then reopen the event stream. The existing polling endpoints remain fully supported.

### Console stream replay/gap diagnostics

`GET /api/console` now includes `boot_id`, while `GET /api/console/stream` accepts optional `boot_id=PREVIOUS_BOOT_ID` and includes `X-Backend-Boot-ID`. On server restart or stale cursor, it emits `console_reset`; if the in-memory 1500-line ring buffer has discarded old events, it emits `console_gap` with the first available ID. Existing `event: console` and heartbeat messages are unchanged; backlog streaming now consumes the oldest available chunk first rather than dropping intermediate batches.

### Durable native-client render session

Files under `scripts/`:

- `morphorum_client.py`: Python standard library HTTP reference client and optional caller-supplied idempotency keys.
- `morphorum_recovery.py`: private session file holding backend instance ID, last boot ID, **exact saved project submission body**, random idempotency key, last completed frame and accepted render ID.
- `db2_recovery_cli.py`: phone-friendly read-only event probe, safe render start, reattachment and completed image/GIF recovery.

The session is **persisted before the first render POST**. After response loss, client retries the *same key and same body* rather than creating a second render. Once an ID is known, reattachment only GETs that render. It refuses a changed backend URL/instance ID. A process restart changes boot ID; existing persisted animation manifests can report interrupted/resumable status, but **nothing automatically resumes GPU work**. The client never cancels work because its connection drops. The watch loop also performs up to five bounded reconnect attempts for temporary network failures, verifying the same backend identity and existing render; if the outage persists, the saved session remains available for later manual reattachment. Terminal state and final GIF download are reported explicitly. No remote process-control capability is added.

Never put a bearer token into the session file. It can contain private project prompts, so keep it out of public repositories and protect it with OS file permissions (0600 on POSIX). Authentication still comes from `--token-file` or a secure keyring workflow.

## Physical acceptance: Windows Omen + Ubuntu Mini

### Windows PowerShell, after stopping Morphorum

```powershell
cd D:\Morphorum-test
git fetch origin
git switch --track origin/feature/db2-live-recovery
.\run.bat --backend-only --lan
```

If the local feature branch exists, use `git switch feature/db2-live-recovery` instead. No new model downloads are needed.

### Ubuntu Mini (ConnectBot): download and read-only probe first

```bash
mkdir -p ~/tmp
BASE="https://raw.githubusercontent.com/merberg-ai/Morphorum/feature/db2-live-recovery/scripts"

for FILE in morphorum_client.py morphorum_connections.py morphorum_recovery.py db2_recovery_cli.py; do
  curl -fsSL "$BASE/$FILE" -o ~/tmp/"$FILE" || exit 1
done

python3 ~/tmp/db2_recovery_cli.py \
  --url http://192.168.1.24:7866 \
  --token-file ~/tmp/backend-access-token \
  probe --project api-test-short-9f178d9f
```

This locates the latest **completed** render of the previous corrected project, GETs its status, and checks the typed event stream **without starting new GPU work**. Expected final summary: `RESULT: 5/5 PASSED`. If the project ID is no longer present, use another known completed project's ID.

### Full live recovery with one SHORT, camera-verified project

The first time, **do not reuse an existing session file**. A prior session represents a particular submitted job. Choose a known-valid project; use the previously corrected `api-test-short-9f178d9f` only if it is still configured for a suitably short run. We are not repeating the old bad-camera settings.

```bash
python3 ~/tmp/db2_recovery_cli.py \
  --url http://192.168.1.24:7866 \
  --token-file ~/tmp/backend-access-token \
  --session ~/tmp/db2-render-session.json \
  --frames-dir ~/tmp/db2-recovered-frames \
  start api-test-short-9f178d9f --watch
```

Watch the job reach an active rendering state, then **interrupt the client only** using Ctrl+C in ConnectBot or close the SSH session. This does not cancel the render on Windows. Reconnect to Ubuntu Mini and run:

```bash
python3 ~/tmp/db2_recovery_cli.py \
  --url http://192.168.1.24:7866 \
  --token-file ~/tmp/backend-access-token \
  --session ~/tmp/db2-render-session.json \
  --frames-dir ~/tmp/db2-recovered-frames \
  attach
```

Expected: `[PASS] Session reattached: ...` with the **same** job ID, progress continuing or already completed; completed PNGs are recovered from the backend and the final GIF downloaded next to the session file. Do not launch a second `start` with a new session unless you specifically intend another render.

For a **real backend restart test**, deliberately stop and relaunch the backend **only after the first successful live-disconnect test**, then run `attach` again. A previously completed job should still be recoverable; a job interrupted by shutdown should explicitly report interrupted/resumable and must NOT restart automatically. This test should not claim that an active GPU job continues running through a backend process restart.

### Short-output format

```text
[PASS] Durable submission session prepared before POST
[PASS] Render ID: anim-...
[PASS] Idempotency key saved locally (not printed).
[PASS] Session reattached: anim-...
[PASS] Retrieved N additional completed frame(s).
[PASS] Reached terminal state: completed
[PASS] Retrieved completed GIF: ...
```

Copying full JSON from a phone is **not required**.

## Automated tests and unresolved scope

Full CI includes the existing DB1–DB2.3 contract/animation tests and new `tests/test_db2_live_recovery.py` tests: duplicate suppression, different-body 409, caller isolation, crash-pending fail-safe behavior, authentication and SSE boot reset, console reset/gap, and native session lost-response/re-attach.

**DB2.4 intentionally does NOT provide:** durable historical job SSE, automatically resumable active diffusion across a server restart, exactly-once guarantees across multiple servers or an unresolved server crash window, automatic GPU cancellation on disconnect, a new Qt UI, WAN/TLS server termination, or a completed physical MP4/audio mux regression. General browser-mode GPU testing and the New Project Wizard camera bug remain separately tracked.

## Acceptance gate

1. GitHub backend/installer/frontend/syntax checks all green.
2. User reports read-only Ubuntu SSE probe.
3. User reports one active render connection interruption followed by same-render reattachment and final GIF recovery (physical GPU acceptance).
4. Verify a completed render remains discoverable after a backend restart. Check independent revoked-client 401 still works if useful.
5. Write verified checkpoint from this branch only after acceptance; no merge to ancestor branches or `main` without explicit permission.

## DB2.4 physical acceptance recorded (2026-10-12)

**User-confirmed Ubuntu Mini / Windows Omen acceptance: PASSED.** This run used the authenticated backend-only LAN endpoint at `http://192.168.1.24:7866` on branch `feature/db2-live-recovery`.

**Read-only event probe:** `db2_recovery_cli.py ... probe --project api-test-short-9f178d9f` returned **`RESULT: 5/5 PASSED`**: authenticated handshake; completed render `anim-20261012-062016-d23669` found; status `completed`; typed job SSE produced a valid event; boot-ID metadata received (prefix `b898e0fed86b`). This did not submit a render.

**Live disconnect and recovery:** Started a new 120-frame animation with persistent session at `~/tmp/db2-render-session.json`; accepted render ID **`anim-20261012-110819-b29995`**. Client observed `loading_model`, then `rendering`, retrieved completed PNGs, and the user deliberately pressed **Ctrl+C** at approximately **10.1%** progress (frame 12). The reference client printed `Client monitoring stopped. GPU job was NOT cancelled.` The user reconnected via a new `attach` invocation; the **same render ID** was returned, the backend had continued to **24.2%** (frame 28), and the client downloaded additional completed frames over the remaining rendering progress. Render reached `finalizing` at 100%, then `completed` at frame 119; the final GIF was downloaded successfully as `/home/jim/tmp/db2-render-session.gif`.

**Supported acceptance conclusions:** Live terminal/client interruption did not cancel the remote animation; persistent-session reattachment recovered the same job ID; progress polling and completed-frame retrieval continued across interruption; final GIF could be fetched. No duplicate submission was observed in this session. The typed SSE read-only probe passed separately. User supplied explicit terminal output for both tests.

**Automated checks:** Source implementation commit `4542378b16a7e5b99757d7fbf9a6ba7fa99c1e15` passed GitHub Actions backend tests (**529 passed, 1 skipped, 0 failed**), self-test, syntax/browser JS checks and installer checks.

**Still outstanding and not claimed physically tested:** an actual backend **process restart** and reattachment to previously completed/interrupted work; a forced dropped-HTTP-response idempotency replay; native client live SSE reconnection through packet loss (the physical live render used authoritative REST polling); normal browser-mode GPU regression; and MP4/video audio-mux export acceptance. Retain these as targeted DB2.5 integration gates rather than marking them passed. No merge to DB2.3 or `dev-backend`/`main` is authorized.

**Checkpoint disposition:** DB2.4 client-disconnect acceptance passed and is suitable for a verified checkpoint, explicitly scoped to the proven behavior above. The following DB2.5 milestone should prioritize pending process restart, error injection, video export and standard browser regressions.
