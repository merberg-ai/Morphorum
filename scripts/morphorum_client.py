#!/usr/bin/env python3
"""DB2.1 Morphorum reference client. Python 3.12+, standard library only.

For native clients, the backend owns all models/projects/media. This script
never sends local paths as server paths and never logs bearer credentials.
Commands that submit jobs intentionally never auto-retry on network failures.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_VERSION = 1
TERMINAL_STATES = {"completed", "failed", "cancelled", "interrupted"}


class ClientError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, code: str = ""):
        super().__init__(message)
        self.status = status
        self.code = code


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ClientError("Redirect refused; credentials must never leave the configured host.")


class MorphorumClient:
    def __init__(self, base_url: str, token: str, *, timeout: float = 20):
        parsed = urlsplit(base_url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.path not in {"", "/"}
                or parsed.query or parsed.fragment):
            raise ClientError("Use an HTTP(S) backend origin, e.g. http://192.168.1.24:7866.")
        if not token or not token.strip():
            raise ClientError("Missing backend bearer token; supply --token-file or MORPHORUM_BACKEND_TOKEN.")
        self.base_url = parsed.scheme + "://" + parsed.netloc
        self.token = token.strip()
        self.timeout = timeout
        self._opener = build_opener(_NoRedirect)

    def request(self, method: str, path: str, *, payload: dict | None = None) -> dict:
        data, _ = self._http(method, path, payload=payload)
        try:
            return json.loads(data)
        except (UnicodeDecodeError, ValueError) as exc:
            raise ClientError("Backend did not return valid JSON.") from exc

    def _http(self, method: str, path: str, *, payload: dict | None = None):
        if (not path.startswith("/api/") or path.startswith("//")
                or "://" in path or "\\" in path or "#" in path):
            raise ClientError("Only same-backend /api/ routes are permitted.")
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Authorization": "Bearer " + self.token}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                return response.read(), response.headers
        except HTTPError as exc:
            detail = exc.read(128 * 1024).decode("utf-8", errors="replace")
            try:
                body = json.loads(detail)
                info = body.get("error") or {}
                message = info.get("message") or body.get("detail") or exc.reason
                if not isinstance(message, str):
                    message = str(message)
                code = str(info.get("code") or "HTTP_ERROR")
            except (ValueError, AttributeError):
                message, code = exc.reason, "HTTP_ERROR"
            raise ClientError(f"HTTP {exc.code} [{code}]: {message}", status=exc.code, code=code) from exc
        except URLError as exc:
            raise ClientError(f"Connection failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise ClientError("Request timed out. Check the job list before retrying any submit.") from exc

    def download(self, path: str, destination: Path, *, file_type: str | None = None) -> Path:
        """Stream to a temporary file and replace only after validation."""
        if (not path.startswith("/api/") or path.startswith("//")
                or "://" in path or "\\" in path or "#" in path):
            raise ClientError("Refusing external or malformed download URL.")
        destination = Path(destination).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        part = destination.with_name(destination.name + ".part")
        part.unlink(missing_ok=True)
        request = Request(self.base_url + path,
                          headers={"Authorization": "Bearer " + self.token})
        try:
            with self._opener.open(request, timeout=max(self.timeout, 120)) as response:
                with part.open("wb") as out:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        out.write(block)
            if part.stat().st_size == 0:
                raise ClientError("Downloaded file was empty.")
            if file_type:
                with part.open("rb") as sample:
                    magic = sample.read(12)
                if file_type == "png" and not magic.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ClientError("Image download is not a PNG.")
                if file_type == "gif" and magic[:6] not in (b"GIF87a", b"GIF89a"):
                    raise ClientError("Animation preview is not a GIF.")
            part.replace(destination)
            return destination
        except HTTPError as exc:
            raise ClientError(f"Download returned HTTP {exc.code}.", status=exc.code) from exc
        except URLError as exc:
            raise ClientError(f"Download connection failed: {exc.reason}") from exc
        finally:
            part.unlink(missing_ok=True)

    def handshake(self) -> dict:
        health = self.request("GET", "/api/health")
        if health.get("api_contract_version") != API_VERSION:
            raise ClientError(
                f"Incompatible API contract {health.get('api_contract_version')!r}; "
                f"this client supports {API_VERSION}."
            )
        info = self.request("GET", "/api/client/capabilities")
        if info.get("api_contract_version") != API_VERSION:
            raise ClientError("Capability contract version does not match the health endpoint.")
        return info

    def models(self, family: str = "sdxl") -> list[dict]:
        result = self.request("GET", f"/api/models?family={quote(family)}&kind=checkpoints&limit=500")
        return result.get("models", [])

    def resolve_model(self, model_name_or_id: str) -> dict:
        models = self.models("sdxl")
        exact = [m for m in models if m.get("id") == model_name_or_id]
        if exact:
            return exact[0]
        matching = [
            m for m in models
            if model_name_or_id.lower() in str(m.get("name", "")).lower()
            or model_name_or_id.lower() in str(m.get("filename", "")).lower()
        ]
        if len(matching) != 1:
            raise ClientError(f"Expected one SDXL model matching {model_name_or_id!r}, found {len(matching)}.")
        return matching[0]

    def projects(self) -> list[dict]:
        return self.request("GET", "/api/animation/projects").get("projects", [])

    def render(self, project_id: str) -> dict:
        project_id = quote(project_id, safe="")
        project = self.request("GET", f"/api/animation/projects/{project_id}")["project"]
        # Exact current contract: the render accepts the full saved project,
        # never just a project ID. No implicit save or mutation.
        return self.request("POST", "/api/animation/renders", payload={"project": project})

    def generate(self, model_id: str, prompt: str, *, width: int = 512,
                 height: int = 512, steps: int = 20, seed: int = 12345) -> dict:
        payload = {
            "model_id": model_id, "prompt": prompt, "negative_prompt": "",
            "width": width, "height": height, "steps": steps,
            "guidance_scale": 6.5, "sampler": "dpmpp_2m_sde",
            "seed": seed, "seed_mode": "fixed", "images": 1,
        }
        return self.request("POST", "/api/generation/jobs", payload=payload)

    def watch(self, job_id: str, *, kind: str, interval: float = 2.0,
              max_seconds: float = 3600, frames_dir: Path | None = None) -> dict:
        job_path = (f"/api/generation/jobs/{quote(job_id, safe='')}" if kind == "image"
                    else f"/api/animation/renders/{quote(job_id, safe='')}")
        end = time.monotonic() + max_seconds
        last_state = None
        last_frame = -1
        while time.monotonic() < end:
            job = self.request("GET", job_path)
            latest_frame = job.get("latest_completed_frame")
            state = (job.get("status"), job.get("current_frame"), job.get("current_step"),
                     round(float(job.get("progress") or 0), 3), latest_frame)
            if state != last_state:
                print(f"{job.get('status')}  {100 * float(job.get('progress') or 0):.1f}%  "
                      f"frame={job.get('current_frame', '-')}  step={job.get('current_step', '-')}  "
                      f"eta={job.get('eta_seconds')}  {job.get('message', '')}", flush=True)
                last_state = state
            if (frames_dir is not None and kind == "animation"
                    and isinstance(latest_frame, int) and latest_frame > last_frame):
                url = job.get("latest_frame_url")
                if url:
                    dest = Path(frames_dir) / f"frame_{latest_frame:06d}.png"
                    self.download(url, dest, file_type="png")
                    print("Received completed frame:", dest)
                    last_frame = latest_frame
            if job.get("status") in TERMINAL_STATES:
                return job
            time.sleep(interval)
        raise ClientError("Watch timed out; the backend may still be rendering. Reattach with 'watch'.")


def _token(args: argparse.Namespace) -> str:
    if args.token_file:
        try:
            return Path(args.token_file).expanduser().read_text(encoding="ascii").strip()
        except OSError as exc:
            raise ClientError(f"Could not read token file: {exc.strerror}") from exc
    supplied = os.getenv("MORPHORUM_BACKEND_TOKEN", "").strip()
    if supplied:
        return supplied
    if getattr(args, "profile", None):
        from morphorum_connections import keyring_get
        return keyring_get(args.profile) or ""
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Morphorum DB2.1 API reference client")
    parser.add_argument("--url", default="http://127.0.0.1:7866")
    parser.add_argument("--token-file", help="Trusted token-file path; no token in shell arguments")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--profile", help="Select a stored connection profile.")
    commands = parser.add_subparsers(dest="command", required=True)
    profiles = commands.add_parser("profile", help="Manage named, non-secret connections.")
    profile_cmd = profiles.add_subparsers(dest="profile_action", required=True)
    add = profile_cmd.add_parser("add")
    add.add_argument("name")
    add.add_argument("origin")
    add.add_argument("--label", default="")
    profile_cmd.add_parser("list")
    remove = profile_cmd.add_parser("remove")
    remove.add_argument("name")
    secret = profile_cmd.add_parser("set-secret", help="Prompt for token; store in OS keyring.")
    secret.add_argument("name")
    drop_secret = profile_cmd.add_parser("forget-secret")
    drop_secret.add_argument("name")
    connect = commands.add_parser("connect", help="Probe a named backend with identity pinning.")
    connect.add_argument("name")
    connect.add_argument("--attempts", type=int, default=3)
    connect.add_argument("--trust-first", action="store_true",
                         help="Pin the first backend identity after out-of-band verification.")
    connect.add_argument("--replace-instance", action="store_true",
                         help="Explicitly accept a different backend identity (verify host first).")
    commands.add_parser("doctor")
    models = commands.add_parser("models")
    models.add_argument("--family", default="sdxl")
    commands.add_parser("projects")
    gen = commands.add_parser("generate")
    gen.add_argument("--model", required=True, help="Actual ID or unambiguous model filename fragment")
    gen.add_argument("--prompt", default="A haunted CRT computer in a dark laboratory, cinematic.")
    gen.add_argument("--watch", action="store_true")
    render = commands.add_parser("render")
    render.add_argument("project_id")
    render.add_argument("--watch", action="store_true")
    watch = commands.add_parser("watch")
    watch.add_argument("job_id")
    watch.add_argument("--kind", choices=("image", "animation"), required=True)
    watch.add_argument("--frames-dir")
    preview = commands.add_parser("download-gif")
    preview.add_argument("project_id")
    preview.add_argument("render_id")
    preview.add_argument("--output", default="morphorum-preview.gif")
    args = parser.parse_args(argv)
    try:
        if args.command in ("profile", "connect") or args.profile:
            from morphorum_connections import (
                ProfileStore, ConnectionManager, keyring_set, keyring_delete,
            )
            store = ProfileStore()
        if args.command == "profile":
            if args.profile_action == "add":
                store.add(args.name, args.origin, args.label)
                print("[PASS] Profile saved (no token stored):", args.name)
            elif args.profile_action == "list":
                for name, item in store.load()["profiles"].items():
                    print(name, item["url"], "pinned" if item["instance_id"] else "unverified")
            elif args.profile_action == "remove":
                store.remove(args.name)
                print("[PASS] Profile removed (OS secret, if present, remains until forgotten):", args.name)
            elif args.profile_action == "set-secret":
                import getpass
                store.get(args.name)
                token = getpass.getpass("Backend token (not echoed): ")
                keyring_set(args.name, token)
                print("[PASS] Credential saved in OS keyring:", args.name)
            elif args.profile_action == "forget-secret":
                keyring_delete(args.name)
                print("[PASS] OS credential deleted:", args.name)
            return 0
        if args.command == "connect":
            args.profile = args.name
            result = ConnectionManager(
                store, lambda url, token: MorphorumClient(url, token, timeout=args.timeout)
            ).connect(
                args.name, _token(args), attempts=args.attempts,
                trust_first=args.trust_first,
                replace_identity=args.replace_instance,
            )
            print("[PASS] Authenticated and API compatible")
            print("[PASS] Backend identity:", result["boot"])
            print("[PASS] Connection:", result["url"], "mode=" + str(result["backend_mode"]))
            if result["insecure_lan_http"]:
                print("[WARN] Plain HTTP LAN: use only trusted LAN or encrypted VPN/tunnel.")
            print("RESULT: PASS; backend process ownership: attached, not controlled.")
            return 0
        url = store.get(args.profile)["url"] if args.profile else args.url
        client = MorphorumClient(url, _token(args), timeout=args.timeout)
        if args.command == "doctor":
            data = client.handshake()
            print(json.dumps({
                "url": client.base_url, "instance_id": data["instance_id"],
                "boot_id": data["boot_id"], "mode": data["mode"],
                "api_contract_version": data["api_contract_version"],
                "features": data["features"], "transfers": data["transfers"],
            }, indent=2))
        elif args.command == "models":
            for m in client.models(args.family):
                print(m.get("id"), m.get("name"))
        elif args.command == "projects":
            for p in client.projects():
                print(p.get("id"), p.get("name"))
        elif args.command == "generate":
            client.handshake()
            m = client.resolve_model(args.model)
            job = client.generate(m["id"], args.prompt)
            print("Image job:", job["id"], job["status"])
            if args.watch:
                result = client.watch(job["id"], kind="image")
                print("Final:", result.get("status"), result.get("error") or "")
                for item in result.get("results", []):
                    print("Image:", item.get("url"))
                return 0 if result.get("status") == "completed" else 1
        elif args.command == "render":
            client.handshake()
            job = client.render(args.project_id)
            print("Animation job:", job["id"], job["status"])
            if args.watch:
                result = client.watch(job["id"], kind="animation")
                print("Final:", result.get("status"), result.get("error") or "")
                print("Preview:", result.get("preview_url"))
                return 0 if result.get("status") == "completed" else 1
        elif args.command == "watch":
            result = client.watch(args.job_id, kind=args.kind, frames_dir=args.frames_dir)
            print("Final:", result.get("status"), result.get("error") or "")
            return 0 if result.get("status") == "completed" else 1
        elif args.command == "download-gif":
            project = quote(args.project_id, safe="")
            render_id = quote(args.render_id, safe="")
            path = f"/api/animation/renders/{project}/{render_id}/preview"
            print("Saved:", client.download(path, Path(args.output), file_type="gif"))
        return 0
    except (ClientError, RuntimeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
