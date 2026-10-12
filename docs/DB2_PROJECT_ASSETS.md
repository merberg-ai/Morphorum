# DB2.3: Project-owned asset transfers and conditional project saves

**Status:** implementation candidate; Windows + Ubuntu Mini physical acceptance pending.
**Branch:** `feature/db2-project-assets`, based on DB2.2 checkpoint `32bd70af783009688cd8122d2f695c90d607232e`.
**Draft PR:** #29, targeting `feature/db2-connection-manager`. DB2.2, DB2.1, `dev-backend`, all verified checkpoints, and `main` remain untouched.

## Contract

Morphorum remains the owner of its projects, WAV files, soundtrack attachments, images and finished outputs. A Studio client receives project and asset IDs, checksums, media type, byte count, filename and authenticated API URLs. Client machine filesystem paths do not work on the host and must never be sent as remote paths.

### Project asset catalog

`GET /api/animation/projects/{project_id}/assets` returns:

```json
{
  "schema_version": 1,
  "assets": [{
    "schema_version": 1,
    "project_id": "example",
    "kind": "soundtrack",
    "id": "[asset sha256]",
    "filename": "song.wav",
    "bytes": 12345,
    "media_type": "audio/wav",
    "sha256": "[asset sha256]",
    "url": "/api/animation/projects/example/motion-import/soundtrack/file"
  }]
}
```

Available kinds are a canonical source PNG, the attached WAV/MP3/OGG/FLAC soundtrack and retained Motion Lab analyzed WAVs. Existing project-owned files are used without copying them to a second asset store. Catalog URLs expose no absolute host paths.

### New authenticated binary download routes

```text
GET /api/animation/projects/{project_id}/motion-import/soundtrack/file
GET /api/animation/projects/{project_id}/motion-lab/audio/{sha256}
```

Each route requires the existing backend-only bearer authentication and returns real audio bytes (rather than metadata alone), with MIME type, filename, `ETag`, `X-Content-SHA256`, and `Cache-Control: private, no-store`. Starlette `FileResponse` supports byte ranges. The reference client validates the SHA-256 against the catalog and writes into a temporary `.part` file before replacing the final download.

Existing PNG/GIF and MP4/WebM download routes are retained, as is the existing FFmpeg exporter. Video export/audio mux is not claimed physically tested in DB2.3.

### Safer existing uploads

Existing input routes and accepted media remain unchanged:

```text
POST /api/animation/projects/{project_id}/source-image
POST /api/animation/projects/{project_id}/motion-lab/audio-analyze
POST /api/animation/projects/{project_id}/motion-import/soundtrack
```

Limits remain 32 MiB for source image, 20 MiB / 180 seconds for Motion Lab PCM WAV, 40 MiB for attached WAV/MP3/OGG/FLAC. Source-image and soundtrack uploads are now read from bounded request chunks; an optional `X-Content-SHA256` request header is verified before any stored asset changes. Oversized uploads return 413; invalid digest/media return 400. Existing valid assets survive rejected uploads. The pure-Python reference client streams upload bytes from disk without buffering an entire media file at the client.

### Opt-in project save conflict protection

`GET /api/animation/projects/{project_id}` supplies the strong `ETag` of the project's saved JSON bytes. `PUT /api/animation/projects/{project_id}` accepts an optional `If-Match: "[etag]"` and returns a new ETag. A stale conditional save returns **HTTP 412 PRECONDITION_FAILED** without overwriting the project. The shared project-save lock covers normal project-save calls as well as conditional PUT checks. Existing browser clients may omit `If-Match` and keep their previous behavior.

This does not magically provide full collaborative editing transactions across all timeline endpoints. New Studio clients should use the conditional project PUT and handle 412 by reloading.

### Important safety limits

- The bearer token and media are **not encrypted** over plain HTTP LAN. Trusted LAN only, or TLS/VPN/SSH tunnel for untrusted networks.
- The client never follows an external redirect with credentials.
- Uploads with an ambiguous network failure are **not automatically retried**; inspect the server's asset catalog before retrying.
- No arbitrary server-side filesystem browsing, model download, new GPU feature, or duplicate media store is introduced.
- The maximum 20/40 MiB audio upload sizes are unchanged; larger Audio Director media requires an explicit later design.
- New Project Wizard camera initialization remains a separate web UI defect.
- DB2.4 remains responsible for durable render reconnect and idempotent generation job submission.

## Phone-friendly physical acceptance

**On Windows Omen PowerShell** after stopping the currently running Morphorum backend:

```powershell
cd D:\Morphorum-test
git fetch origin
git switch --track origin/feature/db2-project-assets
.\run.bat --backend-only --lan
```

If local branch already exists, use `git switch feature/db2-project-assets` instead.

**On Ubuntu Mini using ConnectBot** (the files need only Python 3, no Morphorum/PyTorch installation):

```bash
mkdir -p ~/tmp
BASE="https://raw.githubusercontent.com/merberg-ai/Morphorum/feature/db2-project-assets/scripts"
for FILE in morphorum_client.py morphorum_connections.py db2_assets_smoke.py; do
  curl -fsSL "$BASE/$FILE" -o ~/tmp/"$FILE" || exit 1
done

python3 ~/tmp/db2_assets_smoke.py \
  --url http://192.168.1.24:7866 \
  --token-file ~/tmp/backend-access-token
```

The test creates **one disposable project**, generates a 16×16 PNG and a short PCM WAV in a local temporary folder, uploads those files, checks the server catalog, downloads/validates image and both WAV representations with SHA-256, exercises conditional ETag save and stale-save rejection, and sends only that disposable project to Trash afterward. **No model or GPU render required.** It prints about 12 short PASS lines and saves detailed results to `~/tmp/db2-assets-test.log`. Expected **RESULT: 12/12 PASSED**.

Do not paste credentials in chat. For failures, the local test log includes per-check outcomes.

## Automated and remaining acceptance

GitHub CI includes all existing backend, standard browser frontend syntax, installer and new DB2.3 asset-contract tests. The source test verifies optional digest protection, upload limits, canonical PNG and WAV roundtrips, catalog ownership, range reads and 412 response, alongside backward-compatible unconditional browser saves.

After CI + user-reported Ubuntu physical acceptance: checkpoint DB2.3, stop before DB2.4 and do not merge without explicit approval. Normal Windows browser-mode GPU smoke and physically validated MP4/audio mux remain outstanding.
