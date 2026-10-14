# DB2.5 backend integration and physical acceptance

**Current disposition (2026-10-14): ACCEPTED AND INTEGRATED.** This page preserves the original 2026-10-12 DB2.5 acceptance script and incremental test record, including dated instructions for an isolated feature branch. Those instructions are historical, not the current branch/release status. DB2.5 was accepted on Windows Omen/Ubuntu Mini, integrated into `dev-backend`, promoted through `dev-ui` and then into `main` by [PR #32](https://github.com/merberg-ai/Morphorum/pull/32). The final `main` backend merge commit is `0cb5d489e27b5193fac8dd075d418b8e324beddd`. [Morphorum-Studio](https://github.com/merberg-ai/Morphorum-Studio) is the separate native client repository.

DB2.5 does not redesign GPU inference, alter camera motion, replace the current Web UI or create a Studio application. Its purpose is to close the remaining backend/client acceptance gaps and prepare an API contract ready for a new native desktop client.

## Delivered for DB2.5

1. **Verifiable MP4/WebM:** Completed video export jobs now store a `sha256` of the actual encoded media. The authenticated video download response carries `X-Content-SHA256`, strong `ETag` and private no-store cache controls. Existing pre-DB2.5 video exports remain compatible: their hash is computed when requested. The reference client validates both SHA-256 and the MP4/WebM file signature before replacing a local file.
2. **GPU-free real FFmpeg fixture:** `scripts/db2_video_audio_fixture.py` runs **locally on the Windows backend host**, creates a clearly labeled disposable project, 12 real PNG frames, a one-second 330-Hz 16-kHz PCM WAV, and a completed render manifest with a **frozen audio snapshot**. It does not generate images, load models, or alter existing projects. The production `video_export_manager` must still use FFmpeg to build the output. The script's explicit `cleanup` action verifies the fixture ID/marker, trashes its test project, and removes only its own synthetic output folder.
3. **Short phone-friendly acceptance:** `scripts/db2_final_acceptance.py` runs on Ubuntu Mini using only Python standard library and the previously verified reference client. It supports `preflight`, `record-boot`, `verify-boot`, `lost-response` and `video`. It never prints the token. Every check prints a PASS/FAIL line and writes a local log under `~/tmp/db25-<action>.log`.
4. **Safe lost HTTP response simulation:** Uses the user's existing **completed DB2.4 render** and the exact existing session's idempotency key and frozen project payload. The script intentionally drops one **replayed** response at the client and repeats it again, ensuring the same job ID and no new GPU jobs. This tests journal replay over real LAN HTTP without producing another 120-frame animation. It does **not** simulate an actual server crash between queueing and journaling; the fail-closed reservation behavior remains covered by automated tests.
5. **Restart acceptance:** Records backend `instance_id` and `boot_id` before a deliberate process restart; afterward requires unchanged instance, changed boot, existing render still completed, and authenticated GIF retrieval.
6. **Regression tests:** Export checksum/old-record compatibility, private download headers, corrupted video file rejection, physical fixture generation and constrained cleanup, boot-change requirements and same-key replay checks.

## Acceptance sequence

### A. Switch backend to DB2.5 on Windows Omen

Stop the old backend first. Use **Windows PowerShell**, *not* ConnectBot on Ubuntu:

```powershell
cd D:\Morphorum-test
git fetch origin
git switch --track origin/feature/db2-final-integration
.\run.bat --backend-only --lan
```

If already tracked locally, use `git switch feature/db2-final-integration`. The server remains reachable on the trusted LAN at `http://192.168.1.24:7866`. Do not expose it to public networks. Plain HTTP does not encrypt bearer credentials.

### B. Ubuntu Mini: download client and run read-only preflight

```bash
mkdir -p ~/tmp
BASE="https://raw.githubusercontent.com/merberg-ai/Morphorum/feature/db2-final-integration/scripts"
for FILE in morphorum_client.py morphorum_recovery.py db2_final_acceptance.py; do
  curl -fsSL "$BASE/$FILE" -o ~/tmp/"$FILE" || exit 1
done

python3 ~/tmp/db2_final_acceptance.py \
  --url http://192.168.1.24:7866 \
  --token-file ~/tmp/backend-access-token \
  preflight
```

It relies on the **same already completed** DB2.4 session `~/tmp/db2-render-session.json`. Expected: **RESULT: 6/6 PASSED**. No new GPU work.

### C. Safely verify the lost HTTP response path

From **Ubuntu Mini**:

```bash
python3 ~/tmp/db2_final_acceptance.py \
  --url http://192.168.1.24:7866 \
  --token-file ~/tmp/backend-access-token \
  lost-response
```

Expected: **RESULT: 4/4 PASSED**, checking the original render remains completed, intentional client-side loss, idempotent replay and unchanged render list. This uses the **original** session file and key. If it is absent, stop and investigate rather than inventing a new render.

### D. Real Windows backend restart

From **Ubuntu Mini**, while the current backend process is running:

```bash
python3 ~/tmp/db2_final_acceptance.py \
  --url http://192.168.1.24:7866 \
  --token-file ~/tmp/backend-access-token \
  record-boot
```

Expected **2/2 PASSED**. On **Windows PowerShell**, stop the current Morphorum backend normally, then relaunch `.\run.bat --backend-only --lan` on the **same checkout and data directory**.

On Ubuntu:

```bash
python3 ~/tmp/db2_final_acceptance.py \
  --url http://192.168.1.24:7866 \
  --token-file ~/tmp/backend-access-token \
  verify-boot
```

Expected **5/5 PASSED**, including changed process boot ID and retrieval of the old final GIF. Does not require killing an active render. If you later want to explicitly test interruption of an **active** job by restarting the backend, do so as a separate GPU experiment; it should become `interrupted`/`resumable`, not falsely claim to remain active.

### E. Real FFmpeg MP4 + WebM audio export without GPU generation

First, leave the DB2.5 backend running. Open a **second Windows PowerShell** terminal on the Omen:

```powershell
cd D:\Morphorum-test
.\.venv\Scripts\python.exe scripts\db2_video_audio_fixture.py create
```

Expected `RESULT: 2/2 PASSED`, plus output project/render IDs. The script creates only its own temporary project. Use `show` to retrieve these later.

On **Ubuntu Mini** run (the `--fixture` flag finds the test project automatically):

```bash
python3 ~/tmp/db2_final_acceptance.py \
  --url http://192.168.1.24:7866 \
  --token-file ~/tmp/backend-access-token \
  video --fixture --format mp4 --require-audio
```

Then:

```bash
python3 ~/tmp/db2_final_acceptance.py \
  --url http://192.168.1.24:7866 \
  --token-file ~/tmp/backend-access-token \
  video --fixture --format webm --require-audio
```

These tests submit to the **actual backend FFmpeg export manager** (the synthetic frames are already present). Each expects **10/10 PASSED**, including encoding complete, `audio_included` true, SHA-256-verified download, `ffprobe` video stream and **audio stream**. Saved videos will be `~/tmp/db25-export.mp4` and `~/tmp/db25-export.webm`. Both formats have separate persisted idempotency keys, so re-running after temporary network failure cannot silently create another encoding job.

**Prerequisite:** FFmpeg with `libx264`, `libvpx-vp9`, `aac` and `libopus` support must be available to the **Windows backend**. `ffprobe` must be installed on Ubuntu Mini to actually verify that the downloaded files contain video and audio streams. If missing, the audio tests will fail with a clear instruction rather than report an unverified PASS.

After **both** formats pass, clean up on **Windows PowerShell**:

```powershell
cd D:\Morphorum-test
.\.venv\Scripts\python.exe scripts\db2_video_audio_fixture.py cleanup
```

Expected `RESULT: 2/2 PASSED`. This removes **only the verified synthetic render outputs** and moves the fixture project to Morphorum's Trash. It does not delete any other projects or completed GPU renders.

### F. Standard browser-mode GPU regression

The backend-only checks **cannot** confirm that the old browser UI and normal GPU generation still work, because `--backend-only` deliberately suppresses browser routes.

After remote acceptance and fixture cleanup, stop the LAN backend. On Windows, start the **standard** launcher:

```powershell
cd D:\Morphorum-test
.\run.bat
```

Open the usual local Morphorum web UI (standard port 7865); confirm the project list/editor, status and telemetry, model selection, and an SDXL still-image generation with one of the *already installed* models. Optionally preview an existing saved project/animation. Watch for any errors from model selection, progress bars, asset controls or source imports. Do not modify the old known-good DB2.4 render or simulate a New Project Wizard camera fault while testing backend integration.

Please report **PASS/FAIL** for standard browser mode separately. The New Project Wizard camera settings issue remains an independent Web UI work item.

## CI / integration gates

- Full backend pytest, internal self-test, frontend JavaScript syntax/regression checks, installer checks.
- A–D physically accepted on Windows Omen + Ubuntu Mini.
- E physical MP4 and WebM **with audio tracks** verified using ffprobe and SHA-256; no GPU inference required.
- F normal browser-mode smoke/GPU accepted by user.
- Record outcomes and exact branch SHA in this document; create a DB2.5 verified checkpoint only after user acceptance.
- Only then discuss integration of the **five stacked draft PRs** into `dev-backend`, in dependency order. No merge into `main` until the user explicitly approves.
- After backend acceptance, the user will create a **new, separate Morphorum Studio repository**. The implementation handoff is `docs/STUDIO_CLIENT_HANDOFF.md`. No Studio UI source code is created by DB2.5.

**Known caveats:** no public-WAN transport, no secret safe pairing over bare LAN HTTP, no distributed multi-server exactly-once job commit guarantee, no durable historical SSE replay, and no Windows native Qt Studio UI yet.

## DB2.5 physical acceptance progress (2026-10-12)

**Gate B (preflight): PASS by direct Ubuntu Mini terminal output, 6/6.** The authenticated backend at `http://192.168.1.24:7866` on Windows Omen reported versioned DB2 capabilities, preserved installation identity, a completed previously accepted DB2.4 render and available saved frames. The video-export API was reachable and **host FFmpeg was reported available**. Observed `boot_id` prefix: `676e9b269c2f`. User's local log: `/home/jim/tmp/db25-preflight.log`.

**Gate C (simulated response loss): PASS by direct Ubuntu Mini terminal output, 4/4.** The completed render remained available; the test deliberately discarded a response to a **replay of its existing idempotency key/request**, retried the exact request and received the original render ID; the project render list was unchanged, with no duplicate GPU job created. User's local log: `/home/jim/tmp/db25-lost-response.log`. This confirms keyed replay under the tested scenario, **not** an actual server crash between enqueue and journal commit.

**Gate D (actual Windows backend process restart): PASS by direct Ubuntu Mini terminal output, 2/2 before restart and 5/5 after restart.** The pre-restart `record-boot` call verified the original completed animation remained accessible and the correct backend installation was running; Ubuntu saved the previous boot identity in `/home/jim/tmp/db25-record-boot.log`. The user then restarted the backend on the Omen and ran `verify-boot`, confirming the backend URL was unchanged, the stable installation `instance_id` was preserved, the process `boot_id` had changed, the original completed render remained retrievable, and its GIF successfully downloaded. Result: **`2/2 PASSED` + `5/5 PASSED`**. Local post-restart log: `/home/jim/tmp/db25-verify-boot.log`. This verifies recovery of a *completed* animation after a process restart; it does **not** claim GPU execution survived restarting the backend.

**Gate E (real FFmpeg MP4/WebM with imported soundtrack): PASS, confirmed by Windows PowerShell and Ubuntu Mini terminal output.** The Windows host created a GPU-free fixture project `db25-audio-fixture-bb29643f-9b326564` and synthetic completed render `anim-db25-fixture-660cc7f1ed0a` with 12 PNG frames and a one-second frozen PCM WAV attachment. The fixture creation command printed **`2/2 PASSED`**. On Ubuntu Mini, `ffprobe` was installed at `/usr/bin/ffprobe`. The authenticated export script independently exercised **MP4** and **WebM** through the actual FFmpeg backend export manager: each reported **`10/10 PASSED`**, including completed encoding, frozen soundtrack inclusion, exported SHA-256 metadata, checksum-verified file download, playable video stream and a genuine audio stream confirmed by `ffprobe`. Output files: `~/tmp/db25-export.mp4` and `~/tmp/db25-export.webm`. The script's log location was `/home/jim/tmp/db25-video.log` for both invocations, so the second run may have overwritten the first detailed log; the user supplied explicit separate terminal output for both successful formats. The Windows `cleanup` command then verified fixture ownership, removed **only the marked synthetic render outputs**, and moved the temporary project to Trash, reporting **`2/2 PASSED`**. No new GPU inference was performed for this test.

**DB2.5 physical acceptance so far: 41/41 checks passed** (preflight 6/6, lost-response replay 4/4, restart 2/2 + 5/5, fixture creation 2/2, MP4 10/10, WebM 10/10, safe fixture cleanup 2/2). **Gate F later accepted:** normal Windows browser-mode/GPU functionality was verified by the user; see the final acceptance section below. Neither browser behavior nor GPU inference in standard launcher mode is established by the backend-only checks.

At the time of the first four gates, DB2.5 was not yet accepted. The final physical acceptance is documented below. PR #31 remains draft and no merge into `dev-backend` or `main` has been authorized.

## Final DB2.5 acceptance (2026-10-12)

**Gate F: PASS (user-confirmed).** The user verified that the normal Windows Web UI functions as expected, including image/video generation, telemetry, and other application functionality.

**DB2.5 acceptance: PASS.** Gate B–E scripted physical tests returned 41/41 passing checks, and the remaining Gate F browser/GPU regression was accepted. Prior DB2.1–DB2.4 checkpoint acceptance remains valid. Limits on interrupted backend processes, live SSE history and crash-uncertain submissions remain as documented.

**Post-acceptance update (2026-10-14):** DB2 PRs #27–#31 were integrated in order; the combined backend was verified and promoted through `dev-ui` (PR #33) to `main` (PR #32). The user confirmed the integrated checkout passes native Studio connection testing and both browser/normal and backend-only launch modes. This supersedes the dated pending-integration notes above. See [promotion record](BACKEND_PROMOTION_20261014.md).
