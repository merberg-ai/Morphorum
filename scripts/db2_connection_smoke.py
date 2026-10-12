#!/usr/bin/env python3
"""DB2.2 phone-friendly physical acceptance. Never prints a bearer token.

Run from a directory containing morphorum_client.py and
morphorum_connections.py. No Morphorum/PyTorch installation is required.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from morphorum_client import ClientError, MorphorumClient
from morphorum_connections import ConnectionManager, ProfileError, ProfileStore


def main() -> int:
    parser = argparse.ArgumentParser(description="DB2.2 read-only remote connection smoke")
    parser.add_argument("--url", default="http://192.168.1.24:7866")
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--expected-client", action="store_true",
                        help="Require successful authentication for issued client token.")
    parser.add_argument("--expect-revoked", action="store_true",
                        help="Require HTTP 401 for a revoked client token.")
    parser.add_argument("--log", default=str(Path.home() / "tmp" / "db2-connection-test.log"))
    args = parser.parse_args()
    report: list[str] = []
    counts = [0, 0]

    def record(label: str, success: bool, detail: str = "") -> None:
        counts[not success] += 1
        line = f"[{'PASS' if success else 'FAIL'}] {label}"
        print(line, flush=True)
        report.append(line + (": " + detail if detail else ""))

    try:
        secret = Path(args.token_file).expanduser().read_text(encoding="ascii").strip()
        client = MorphorumClient(args.url, secret, timeout=15)
        if args.expect_revoked:
            try:
                client.handshake()
                record("Revoked credential rejected", False, "Backend accepted revoked credential")
            except ClientError as exc:
                record("Revoked credential rejected", exc.status == 401,
                       f"HTTP status={exc.status}, code={exc.code}")
        else:
            info = client.handshake()
            record("Authenticated API handshake", info.get("api_contract_version") == 1)
            record("Server identity & boot IDs", len(info.get("instance_id", "")) == 32
                   and len(info.get("boot_id", "")) == 32)
            record("Correct capability flags",
                   info.get("authentication", {}).get("per_client_credentials") is True
                   and info.get("authentication", {}).get("per_client_pairing") is False)
            with tempfile.TemporaryDirectory(prefix="morphorum-db2-smoke-") as directory:
                store = ProfileStore(Path(directory) / "profiles.json")
                store.add("physical", args.url, "DB2.2 temporary")
                manager = ConnectionManager(
                    store, lambda url, token: MorphorumClient(url, token, timeout=15)
                )
                first = manager.connect("physical", secret, trust_first=True)
                second = manager.connect("physical", secret)
                record("Profile pin and reconnect",
                       first["state"] == "connected" and second["state"] == "connected"
                       and store.get("physical")["instance_id"] == info["instance_id"])
                try:
                    store.update_identity("physical", instance_id="0" * 32,
                                          boot_id="0" * 32)
                    record("Identity mismatch protection", False)
                except ProfileError:
                    record("Identity mismatch protection", True)
            if not args.expected_client:
                try:
                    MorphorumClient(args.url, "wrong-db2-token").handshake()
                    record("Invalid credential rejected", False)
                except ClientError as exc:
                    record("Invalid credential rejected", exc.status == 401)
    except (ClientError, ProfileError, OSError, ValueError, KeyError) as exc:
        record("Unexpected connection failure", False, type(exc).__name__ + ": " + str(exc))
    destination = Path(args.log).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(report) + f"\nRESULT: {counts[0]} passed, {counts[1]} failed\n",
                           encoding="utf-8")
    print(f"RESULT: {counts[0]}/{sum(counts)} PASSED", flush=True)
    print(f"Details: {destination}", flush=True)
    return 0 if counts[1] == 0 and counts[0] >= (1 if args.expect_revoked else 5) else 1


if __name__ == "__main__":
    raise SystemExit(main())
