#!/usr/bin/env python3
"""DB2.3 phone-friendly end-to-end media transfer test.

Creates one disposable project on the target backend. No GPU inference.
Uploads synthetic PNG/WAV, validates bytes and hashes, verifies stale ETag
rejection, then trashes ONLY the project this script created.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import struct
import tempfile
import uuid
import wave
import zlib
from pathlib import Path
from urllib.parse import quote

from morphorum_client import ClientError, MorphorumClient


def tiny_png() -> bytes:
    width = height = 16
    row = bytes([0]) + bytes([35, 65, 135] * width)
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack("!I", len(data)) + kind + data
                + struct.pack("!I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * height))
            + chunk(b"IEND", b""))


def tiny_wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 800)
    return output.getvalue()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://192.168.1.24:7866")
    p.add_argument("--token-file", required=True)
    p.add_argument("--log", default=str(Path.home() / "tmp/db2-assets-test.log"))
    args = p.parse_args()
    passed, failed = 0, 0
    lines = []
    project_id = None
    client = None

    def record(label: str, ok: bool, detail: str = ""):
        nonlocal passed, failed
        passed += bool(ok)
        failed += not ok
        line = f"[{'PASS' if ok else 'FAIL'}] {label}"
        print(line, flush=True)
        lines.append(line + (": " + detail if detail else ""))
        if not ok:
            raise RuntimeError(label + (": " + detail if detail else ""))

    try:
        token = Path(args.token_file).expanduser().read_text(encoding="ascii").strip()
        client = MorphorumClient(args.url, token)
        capability = client.handshake()
        record("Authenticated DB2.3 capabilities",
               all(capability.get("features", {}).get(k) for k in (
                   "project_asset_listing", "soundtrack_attachment_download",
                   "motion_lab_wav_download", "conditional_project_saves")))
        title = "DB23 Transfer Smoke " + uuid.uuid4().hex[:8]
        created = client.request("POST", "/api/animation/projects", payload={"name": title})
        project_id = created["project"]["id"]
        record("Disposable remote project created", bool(project_id))
        with tempfile.TemporaryDirectory(prefix="db2-assets-") as temp:
            folder = Path(temp)
            src_png = folder / "source.png"
            src_png.write_bytes(tiny_png())
            img = client.upload_file(project_id, src_png, kind="source-image")
            record("Streamed PNG upload", img["asset"]["kind"] == "source_image")
            src_wav = folder / "soundtrack.wav"
            src_wav.write_bytes(tiny_wav())
            snd = client.upload_file(project_id, src_wav, kind="soundtrack")
            record("Streamed soundtrack upload", snd["asset"]["sha256"] ==
                   hashlib.sha256(src_wav.read_bytes()).hexdigest())
            analysis = client.upload_file(project_id, src_wav, kind="motion-lab-wav")
            record("Motion Lab WAV upload", analysis.get("status") == "analyzed")
            assets = client.project_assets(project_id)
            by_kind = {item["kind"]: item for item in assets}
            record("Server project asset catalog",
                   all(k in by_kind for k in ("source_image", "soundtrack", "motion_lab_wav")))
            for kind, label in (
                ("source_image", "PNG"), ("soundtrack", "soundtrack WAV"),
                ("motion_lab_wav", "analyzed WAV"),
            ):
                item = by_kind[kind]
                target = folder / ("download-" + kind)
                client.download(item["url"], target, expected_sha256=item["sha256"])
                original = src_png if kind == "source_image" else src_wav
                if kind == "source_image":
                    # Source upload is canonicalized to PNG by Pillow; its
                    # binary bytes need not match the original byte stream.
                    ok = target.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
                else:
                    ok = target.read_bytes() == original.read_bytes()
                record("Verified " + label + " download", ok)
            project, etag = client.get_project_with_etag(project_id)
            project["notes"] = "DB2.3 first save"
            _, new_etag = client.save_project_conditionally(project_id, project, etag)
            record("Conditional project save", new_etag != etag)
            try:
                client.save_project_conditionally(project_id, project, etag)
                record("Stale concurrent save rejected", False)
            except ClientError as exc:
                record("Stale concurrent save rejected", exc.status == 412)
    except Exception as exc:
        failed += 1
        line = "[FAIL] Unexpected test error: " + type(exc).__name__ + ": " + str(exc)
        print(line, flush=True)
        lines.append(line)
    finally:
        if project_id and client:
            try:
                result = client.request(
                    "DELETE", f"/api/animation/projects/{quote(project_id, safe='')}"
                )
                print("[PASS] Disposable project moved to Trash", flush=True)
                lines.append("[PASS] Disposable project moved to Trash")
                passed += 1
            except Exception as exc:
                print("[WARN] Disposable test project cleanup failed:", str(exc), flush=True)
                lines.append("[WARN] Project cleanup failed: " + str(exc))
                failed += 1
        output = Path(args.log).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(lines) + f"\nRESULT: {passed} passed, {failed} failed\n")
        print(f"RESULT: {passed}/{passed+failed} PASSED", flush=True)
        print("Details:", output, flush=True)
    return 0 if failed == 0 and passed >= 11 else 1


if __name__ == "__main__":
    raise SystemExit(main())
