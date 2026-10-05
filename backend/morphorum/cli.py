from __future__ import annotations

import argparse
import json
import os
import sys

import uvicorn
from fastapi.testclient import TestClient

from . import __version__
from .app import app
from .paths import ensure_runtime_dirs
from .system_info import doctor_report, write_install_manifest


def command_serve(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    host = args.host or os.getenv("MORPHORUM_HOST_OVERRIDE", "127.0.0.1")
    port = args.port or int(os.getenv("MORPHORUM_PORT_OVERRIDE", "7865"))
    uvicorn.run("morphorum.app:app", host=host, port=port, reload=False)
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    report = doctor_report()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("Morphorum Doctor")
        print("================")
        for check in report["checks"]:
            state = "OK" if check["ok"] else "WARN"
            print(f"[{state:4}] {check['name']}: {check['detail']}")
        gpu = report.get("gpu", {})
        for device in gpu.get("devices", []):
            print(f"[INFO] GPU: {device['name']} ({device['memory_mib']} MiB, driver {device['driver']})")
    return 0 if report["ok"] else 1


def command_self_test(_: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    try:
        with TestClient(app) as client:
            response = client.get("/api/health")
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") != "ok":
                raise RuntimeError(f"unexpected health payload: {payload}")
        write_install_manifest({"self_test": "passed"})
    except Exception as exc:
        print(f"Morphorum self-test failed: {exc}", file=sys.stderr)
        return 1
    print("Morphorum self-test passed: API health check OK.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="morphorum")
    parser.add_argument("--version", action="version", version=f"Morphorum {__version__}")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Start the Morphorum API server.")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.set_defaults(func=command_serve)

    doctor = sub.add_parser("doctor", help="Run installation and runtime diagnostics.")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=command_doctor)

    self_test = sub.add_parser("self-test", help="Exercise the local API without opening a port.")
    self_test.set_defaults(func=command_self_test)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
