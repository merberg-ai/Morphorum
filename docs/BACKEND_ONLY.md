# Backend-only mode and remote clients

Morphorum can run as a **generation server without its browser UI**. This is useful when controlling a GPU computer from [Morphorum Studio](https://github.com/merberg-ai/Morphorum-Studio) or another compatible API client on the same machine or a trusted network.

For regular browser use, **you do not need backend-only mode**. Start Morphorum normally using `run.bat` on Windows or `./run.sh` on Linux.

## How the two modes differ

| | Normal Morphorum | Backend-only Morphorum |
| --- | --- | --- |
| Purpose | Browser UI plus generation API | Generation API for a separate client |
| Windows launch | `.\run.bat` | `.\run.bat --backend-only` |
| Linux launch | `./run.sh` | `./run.sh --backend-only` |
| Default listening address | `127.0.0.1` | `127.0.0.1` |
| Default port | **7865** | **7866** |
| Browser home page | Yes | No (HTTP 404) |
| API authorization | No built-in login in standard mode | **Bearer token required**, even on localhost |
| Remote LAN | Separate `run-lan` launcher, not authenticated | Explicit `--lan`, bearer token required |

The same Morphorum backend provides model management, projects, generation, animation, previews, telemetry, console events and video exports. Backend-only mode does **not** mean CPU-only generation or a separate model installation.

## Start backend-only mode

From your installed Morphorum directory:

**Windows PowerShell:**

~~~powershell
cd C:\Morphorum
.\run.bat --backend-only
~~~

**Linux terminal:**

~~~bash
cd ~/Morphorum
./run.sh --backend-only
~~~

By default, it listens on **http://127.0.0.1:7866** for an authenticated client. A browser opening that URL will **not** show the Morphorum user interface.

### Enable access from another computer on your private LAN

Stop the existing backend and restart with explicit LAN binding:

**Windows:**

~~~powershell
.\run.bat --backend-only --lan
~~~

**Linux:**

~~~bash
./run.sh --backend-only --lan
~~~

It now listens on the machine's network interfaces using port **7866**, unless configured otherwise. In your client, enter the backend computer's real IP address and port, for example `http://192.168.1.50:7866`. **Never enter `0.0.0.0` as the destination.**

On Windows, an optional launch-time port override is supported: `.\run.bat --backend-only --port 9000`. The Linux runner supports `MORPHORUM_BACKEND_PORT_OVERRIDE=9000` and `MORPHORUM_BACKEND_HOST_OVERRIDE`.

Only open the relevant firewall port to trusted local-network devices. Do not forward it on your router.

## Give a client access

Every backend-only API request requires a **bearer token**. Morphorum creates its initial admin/backend token in `data/backend-access-token` the first time this mode starts. That file is a secret; never paste its contents into a public issue or expose it through an untrusted connection.

For a desktop client, **per-client revocable credentials** are preferable to sharing the admin token. These are created **locally on the backend host**; there is no automatic PIN-based LAN pairing endpoint.

### Issue a separate token on Windows

In another PowerShell window, from the backend install directory:

~~~powershell
cd C:\Morphorum
.\.venv\Scripts\python.exe -m morphorum clients issue "Studio PC" --days 90 --out ".\data\studio-client-token-once.txt"
~~~

The issued secret appears **only in the new file**, not in the terminal output. Import it into the client using a **trusted and secure method**, then delete the temporary token file from the backend host after confirming the client safely stores the credential. Do not upload it to GitHub, attach it to an issue, or send it over plain HTTP.

You can manage client access from the backend computer:

~~~powershell
.\.venv\Scripts\python.exe -m morphorum clients list
.\.venv\Scripts\python.exe -m morphorum clients revoke CLIENT_ID
~~~

Replace `CLIENT_ID` with the ID printed by `clients list`. Revocation is immediate. A client token has a configured expiration (90 days in this example) and can be reissued when necessary.

**Linux equivalent:** replace `.\.venv\Scripts\python.exe` with `./.venv/bin/python` and use normal Linux file paths.

> [!WARNING]
> Credentials authenticate clients but do **not** encrypt the connection. On an untrusted network, use **TLS, VPN, or an encrypted tunnel** before transmitting bearer tokens or media. An ordinary household LAN should be treated according to its actual trust level. Do not expose the API directly to the public internet.

## Check that the server is working

The API-only server requires authorization even for `/api/health`. On the **backend host** you can verify it using the locally generated admin token.

**Windows PowerShell:**

~~~powershell
$token = (Get-Content ".\data\backend-access-token" -Raw).Trim()
Invoke-RestMethod "http://127.0.0.1:7866/api/health" -Headers @{ Authorization = "Bearer $token" }
Remove-Variable token
~~~

**Linux terminal:**

~~~bash
TOKEN="$(cat ./data/backend-access-token)"
curl -fsS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:7866/api/health
unset TOKEN
~~~

A successful response reports a healthy API and `backend-only` mode. A request without authorization normally returns **401**; `/` and browser asset paths are not available.

For native clients, authenticated `GET /api/client/capabilities` describes the current `api_contract_version`, model families and advertised features. A compatible client should check those capabilities, not merely assume every backend version implements everything.

## Connect Morphorum Studio

1. Run Morphorum backend-only on the GPU machine.
2. In the separate Morphorum Studio application, configure the backend URL (host IP and port **7866**) and an appropriate issued credential.
3. Verify the reported backend identity and API compatibility when first connecting.
4. Keep the backend process open for remote generation. Exiting a remote Studio client should **not** stop a server it did not launch.

Details of the Studio user interface, credential storage and supported features are maintained in the [Morphorum-Studio repository](https://github.com/merberg-ai/Morphorum-Studio); they can vary by Studio version. Model paths on the backend machine do **not** refer to files on your client computer. The client must use the API's upload/download capabilities to transfer project assets.

## Troubleshooting backend-only mode

| Symptom | What to check |
| --- | --- |
| Browser shows 404 at `/` | Expected: API-only mode does not serve the web UI |
| HTTP 401 | Missing, invalid, expired or revoked token; check your client Authorization header |
| Connection refused | Backend process not running, wrong port/IP, firewall rule or binding mode |
| Works on localhost but not LAN | Restart using `--lan` and use the backend computer's real private IP address |
| Studio disconnects after restart | Reconnect and refresh authoritative job/project state; active GPU jobs do not keep running through a process restart |
| Media missing on client | Use authenticated asset/download APIs, not a file path from a different computer |

For general installation, GPU, logging and model issues, see [Troubleshooting](TROUBLESHOOTING.md). For supported client features and limits, see [Features and limitations](CURRENT_STATUS.md).

**Security summary:** normal browser LAN is *unauthenticated*; backend-only LAN is *authenticated but not encrypted by default*. Do not mix them up.
