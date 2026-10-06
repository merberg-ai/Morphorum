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
            health_response = client.get("/api/health")
            health_response.raise_for_status()
            health = health_response.json()
            if health.get("status") != "ok":
                raise RuntimeError(f"unexpected health payload: {health}")

            frontend = client.get("/")
            frontend.raise_for_status()
            if "Morphorum" not in frontend.text or "Settings" not in frontend.text or "Image Generation" not in frontend.text:
                raise RuntimeError("frontend shell did not contain expected Morphorum UI markers")

            settings_response = client.get("/api/settings")
            settings_response.raise_for_status()
            settings_payload = settings_response.json()
            settings = settings_payload.get("settings", {})
            models = settings.get("models", {}) if isinstance(settings, dict) else {}

            family_response = client.get("/api/models/families")
            family_response.raise_for_status()
            family_defs = family_response.json().get("families", [])
            enabled_families = [item["id"] for item in family_defs]
            if enabled_families != ["sdxl", "flux", "zimage"]:
                raise RuntimeError(f"unexpected enabled model families: {enabled_families}")

            external_families = [
                item["id"] for item in family_defs if item.get("source") == "external"
            ]
            managed_families = [
                item["id"] for item in family_defs if item.get("source") == "managed"
            ]
            for family in external_families:
                if family not in models:
                    raise RuntimeError(f"settings schema is missing external model family: {family}")
            if managed_families != ["zimage"]:
                raise RuntimeError(f"unexpected managed model families: {managed_families}")

            managed_response = client.get("/api/managed-models")
            managed_response.raise_for_status()
            managed_catalog = managed_response.json().get("models", [])
            if not any(item.get("id") == "zimage-turbo" for item in managed_catalog):
                raise RuntimeError("managed model catalog is missing Z-Image-Turbo")

            animation_projects_response = client.get("/api/animation/projects")
            animation_projects_response.raise_for_status()
            if not isinstance(animation_projects_response.json().get("projects"), list):
                raise RuntimeError("animation projects endpoint did not return a projects list")

            models_response = client.get("/api/models?limit=1")
            models_response.raise_for_status()
            if not isinstance(models_response.json().get("models"), list):
                raise RuntimeError("model index endpoint did not return a models list")

            capabilities_response = client.get("/api/generation/capabilities")
            capabilities_response.raise_for_status()
            families = capabilities_response.json().get("families", {})
            for family in ("sdxl", "flux", "zimage"):
                if not families.get(family, {}).get("supported"):
                    raise RuntimeError(f"{family} generation capability is missing or disabled")

            console_response = client.get("/api/console?limit=10")
            console_response.raise_for_status()
            if not isinstance(console_response.json().get("events"), list):
                raise RuntimeError("console endpoint did not return an events list")

        write_install_manifest({"self_test": "passed"})
    except Exception as exc:
        print(f"Morphorum self-test failed: {exc}", file=sys.stderr)
        return 1
    print("Morphorum self-test passed: API, frontend, settings, animation projects, managed models, model index, generation capabilities, and console OK.")
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
