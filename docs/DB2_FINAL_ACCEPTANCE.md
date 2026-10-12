# DB2.5 backend integration and physical acceptance

**State:** isolated feature candidate `feature/db2-final-integration` from DB2.4 verified checkpoint `a449c51fb0fb7415899fffbe75d8e682ccb4d66a`. Draft PR #31 targets `feature/db2-live-recovery`. **Do not merge to `dev-backend` or `main` until explicit user approval.** The native Studio desktop application will live in a user-created **separate repository**, not this branch.

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

**Still awaiting physical acceptance:** Gate D (real backend process restart preserving installation ID, changing boot ID and downloading old GIF), Gate E (FFmpeg MP4 and WebM exports each containing genuine audio streams with SHA-256-verified downloads and guarded fixture cleanup), Gate F (normal Windows browser-mode/GPU regression). These are **not** covered by the user's initial “all tests passed” response, which included the 6/6 and 4/4 outputs only.

No full DB2.5 checkpoint or merge is authorized by these partial results. Keep PR #31 draft, `dev-backend` and `main` unchanged.
