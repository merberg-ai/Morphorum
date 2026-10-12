# DB2.2: Backend connection management, credentials and recovery

**Status:** candidate code pending CI and physical Ubuntu Mini / Windows verification.
**Implementation branch:** `feature/db2-connection-manager`, created from user-verified DB2.1 checkpoint `8e1ab014fb43a84fdc8ac069efb688b8e4a0034f`.
**Parent PR:** DB2.1 draft #27 against `dev-backend`; DB2.2 work remains isolated pending approval.
**Preserve:** `main`, `dev-backend`, DB1/DB2.1 checkpoint branches, normal browser UI, existing API schemas and render arithmetic.

## DB2.2 scope delivered

### 1. Host-local, revocable per-client credentials

`backend/morphorum/client_credentials.py` adds a local JSON registry at `data/backend-client-credentials.json`. It stores per-client ID, friendly name, `SHA-256` digest of a **random high-entropy** token, expiry (1-365 days), creation timestamp and revocation flag. **The plaintext secret is never written to the registry.** The token may be written exactly once to a new, operator-chosen secret file with permissions 0600 on POSIX; do not place it in the repository or sync it to public cloud storage. Windows filesystem ACLs must still be secured by the user/installer; `0600` is not a Windows ACL guarantee. This is not password hashing for low-entropy passwords: SHA-256 is acceptable here only because issued tokens have independent random entropy.

Commands **run locally on the backend host only**:

```powershell
cd D:\\Morphorum-test
.\\.venv\\Scripts\\python.exe -m morphorum clients issue "Ubuntu Mini" --days 90 --out ".\\data\\ubuntu-mini-client.token"
.\\.venv\\Scripts\\python.exe -m morphorum clients list
.\\.venv\\Scripts\\python.exe -m morphorum clients revoke CLIENT_ID_FROM_LIST
```

The token file must be transferred to Ubuntu Mini through a trusted private mechanism (e.g. authenticated SSH/SCP on a trusted network or encrypted tunnel, USB, physically controlled channel). **Do not paste the token in chat or log output.** Remove the one-time issuance file from the backend host once it has been safely imported. On the client, keep it outside repositories with private filesystem permissions; `chmod 600 ~/tmp/backend-client-token`. Revocation becomes effective immediately even if Morphorum remains running. Legacy DB1 `backend-access-token` and `MORPHORUM_BACKEND_TOKEN` continue to authenticate and are *not revocable per client*. To rotate a client token: issue a new one, provision it, confirm, revoke old ID.

**Deliberate restriction:** There is no HTTP endpoint for token issue/list/revoke and **no insecure PIN/code pairing over unencrypted LAN**. Per-client tokens provide revocation and reduce shared-token exposure, but HTTP on a LAN does not encrypt them. TLS/HTTPS, authenticated SSH tunnel or VPN is mandatory before trusting an untrusted network. The current `/api/client/capabilities` advertises `authentication.per_client_credentials=true`, `per_client_pairing=false`, `provisioning=local-host-admin-only`.

### 2. Named, non-secret connection profiles

`scripts/morphorum_connections.py` stores connection **metadata only** at `~/.config/morphorum/connections.json`: name, URL, label, pinned installation `instance_id`, last known `boot_id`. No bearer token or plaintext password is stored. POSIX permissions 0600; Windows users should verify OS directory ACLs.

Optional credential source priorities: explicit `--token-file` (for portable/Ubuntu tests), environment `MORPHORUM_BACKEND_TOKEN` (with the usual environment visibility caveat), or **OS keyring** if a Python `keyring` package and a working provider are available. Studio will integrate with Windows Credential Manager via its own UI/OS adapter; the Python reference client's optional `keyring` import keeps Ubuntu test dependencies to the standard library. There is deliberately no insecure plaintext-keyring fallback.

```bash
# Download these three Python files into the SAME folder:
curl -fsSL https://raw.githubusercontent.com/merberg-ai/Morphorum/feature/db2-connection-manager/scripts/morphorum_client.py -o ~/tmp/morphorum_client.py
curl -fsSL https://raw.githubusercontent.com/merberg-ai/Morphorum/feature/db2-connection-manager/scripts/morphorum_connections.py -o ~/tmp/morphorum_connections.py
curl -fsSL https://raw.githubusercontent.com/merberg-ai/Morphorum/feature/db2-connection-manager/scripts/db2_connection_smoke.py -o ~/tmp/db2_connection_smoke.py

python3 ~/tmp/morphorum_client.py profile add omen http://192.168.1.24:7866 --label "Windows Omen"
python3 ~/tmp/morphorum_client.py profile list

# First pin only after verifying the intended backend machine out of band:
python3 ~/tmp/morphorum_client.py --token-file ~/tmp/backend-access-token connect omen --trust-first

# Normal reconnect; no repinning is allowed:
python3 ~/tmp/morphorum_client.py --token-file ~/tmp/backend-access-token connect omen
python3 ~/tmp/morphorum_client.py --profile omen --token-file ~/tmp/backend-access-token doctor
```

If the host address later presents a different `instance_id`, connection fails `identity_mismatch`. You can deliberately run `connect omen --replace-instance` **only after physically verifying the backend change**. A restart of the *same* backend installation changes its `boot_id` and returns `restarted`; Studio must invalidate transient SSE cursors after restart. Instance pinning is a convenience and detects accidental host switches, **not cryptographic proof of identity on plaintext LAN**.

Connection statuses include `disconnected`, `connecting`, `connected`, `unauthorized`, `incompatible`, `reconnecting`, `offline`, and `identity_mismatch`. A successful connection reports process ownership `attached_remote`. The reference client does not start, kill or cancel any backend process on reconnection. Bounded retries apply to transient network errors, **not** invalid credentials or mismatched identities. Render reattachment and exactly-once POST submission semantics are DB2.4; DB2.2 does not pretend to implement them.

### 3. Phone-friendly physical smoke suite

`scripts/db2_connection_smoke.py` prints short, labeled PASS/FAIL lines, a total and a local detail log. The script uses the same Python reference client and does **not** start any generation job or expose tokens. It creates only a temporary isolated profile in a temporary directory, leaving named user profiles unchanged.

On Ubuntu Mini:

```bash
python3 ~/tmp/db2_connection_smoke.py --url http://192.168.1.24:7866 --token-file ~/tmp/backend-access-token
```

Expected format:

```text
[PASS] Authenticated API handshake
[PASS] Server identity & boot IDs
[PASS] Correct capability flags
[PASS] Profile pin and reconnect
[PASS] Identity mismatch protection
[PASS] Invalid credential rejected
RESULT: 6/6 PASSED
Details: /home/.../tmp/db2-connection-test.log
```

After provisioning an actual client token on Ubuntu, repeat using `--token-file ~/tmp/backend-client-token --expected-client`. After Windows admin revokes its ID, run the same script with `--expect-revoked`, which must report `[PASS] Revoked credential rejected`. Do **not** publicly paste secrets.

## Security assumptions and deferred pairing UI

- **No remote admin API:** issuance/revocation only from a trusted backend-host terminal. No arbitrary API client can mint credentials.
- **Explicit approval:** the operator must run the issuance command and securely deliver the secret. One-time, host-approved QR/pairing UX requires a reviewed protocol over an authenticated confidential channel; it is not part of this phase.
- **No TLS termination bundled:** LAN plain HTTP remains the user-accepted DB1 compatibility mode, and remains vulnerable to packet interception/MITM. Recommend encrypted VPN/TLS before using an untrusted LAN.
- **Key storage:** Python client metadata contains no secrets; OS keyring is optional on systems with a functioning provider; the Ubuntu acceptance token file is controlled explicitly by its owner.
- **Immediate revocation:** service rereads the small credential registry when checking presented client tokens. Registry parse/permission failures reject per-client auth (fail closed); legacy installation token remains separately valid.
- **Local concurrency:** admin commands should be serialized. Atomic file replacement protects active request readers but there is not yet a cross-process transaction lock for simultaneous separate issuer processes.
- **Identity and recovery:** `instance_id` is stable per installation; `boot_id` changes on restart; client avoids automatic host repin and cannot safely assume jobs survive a server restart.

## CI and physical acceptance gates

1. Automated: new `tests/test_db2_connection_manager.py`, `test_db2_client_contract.py`, existing backend-only/full CI, installer and browser syntax regressions.
2. Windows: launch backend-only LAN on this branch. Issue an individual client token on the host, list with ID but without plaintext, authenticate from Ubuntu, revoke without server restart; confirm old shared token still authenticates.
3. Ubuntu: run phone-friendly six-check smoke with legacy token and with newly provisioned client token. Wrong token must give 401. After revocation, client-token smoke `--expect-revoked` must pass.
4. Restart the backend once, rerun profile connect and verify it reports same pinned installation and changed boot ID; no remote backend process killed.
5. Record tests as passed **only after user reports them**, checkpoint the branch, and stop before DB2.3. Do not merge without explicit acceptance.

**Outstanding from prior gates:** normal browser-mode GPU regression, MP4 export, client-side audio assets, durable job retry/idempotency, full Studio GUI, New Project Wizard camera-default bug.
