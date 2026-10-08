from __future__ import annotations

import argparse
import json
import os
import sys

import uvicorn
from fastapi.testclient import TestClient
from PIL import Image

from . import __version__
from .animation_motion import _frame_transform_matrix, render_affine
from .app import app
from .paths import ensure_runtime_dirs
from .system_info import doctor_report, write_install_manifest


def command_serve(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    host = args.host or os.getenv("MORPHORUM_HOST_OVERRIDE", "127.0.0.1")
    port = args.port or int(os.getenv("MORPHORUM_PORT_OVERRIDE", "7865"))
    env_access_log = str(os.getenv("MORPHORUM_ACCESS_LOG", "")).strip().lower()
    access_log = bool(args.access_log) or env_access_log in {"1", "true", "yes", "on"}
    uvicorn.run(
        "morphorum.app:app",
        host=host,
        port=port,
        reload=False,
        access_log=access_log,
    )
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
        try:
            import peft  # noqa: F401
        except Exception as exc:
            raise RuntimeError(f"PEFT LoRA backend is unavailable: {exc}") from exc
        try:
            import torchvision  # noqa: F401
        except Exception as exc:
            raise RuntimeError(f"torchvision image backend is unavailable: {exc}") from exc

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

            depth_response = client.get("/api/animation/depth/models")
            depth_response.raise_for_status()
            depth_models = depth_response.json().get("models", [])
            if not any(
                item.get("id") == "depth-anything-v2-small"
                and item.get("depth_type") == "relative"
                for item in depth_models
            ):
                raise RuntimeError("depth model catalog is missing Depth Anything V2 Small")

            animation_projects_response = client.get("/api/animation/projects")
            animation_projects_response.raise_for_status()
            if not isinstance(animation_projects_response.json().get("projects"), list):
                raise RuntimeError("animation projects endpoint did not return a projects list")

            preview_project = {
                "schema_version": 1,
                "id": "self-test-animation",
                "name": "Self Test Animation",
                "animation": {
                    "max_frames": 11,
                    "fps": 24,
                    "width": 512,
                    "height": 512,
                    "prompt_transition": "blend",
                    "mode": "2d",
                },
                "model": {"model_id": "", "family": "", "variant": ""},
                "prompts": {"0": "start", "10": "end"},
                "negative_prompts": {"0": ""},
                "motion": {
                    "angle": "0:(0), 10:(10)",
                    "zoom": "0:(1.0), 10:(1.1)",
                    "translation_x": "0:(0)",
                    "translation_y": "0:(0)",
                },
                "generation": {
                    "strength": "0:(0.6)",
                    "noise": "0:(0.02)",
                    "steps": "0:(9)",
                    "guidance": "0:(0)",
                    "sampler": "flowmatch_euler",
                    "seed": 123,
                    "seed_behavior": "fixed",
                    "seed_increment": 1,
                },
            }
            resolved_response = client.post(
                "/api/animation/resolve-frame",
                json={"project": preview_project, "frame": 5},
            )
            resolved_response.raise_for_status()
            resolved = resolved_response.json().get("resolved", {})
            if abs(float(resolved.get("motion", {}).get("angle", -999)) - 5.0) > 1e-6:
                raise RuntimeError("animation schedule resolver returned an unexpected frame state")
            if abs(float(resolved.get("camera_3d", {}).get("fov", -999)) - 40.0) > 1e-6:
                raise RuntimeError("3D camera resolver returned an unexpected default FOV")

            motion_source = Image.new("RGB", (16, 16), "black")
            motion_matrix = _frame_transform_matrix(
                width=16,
                height=16,
                angle=0,
                zoom=1,
                translation_x=1,
                translation_y=0,
            )
            motion_result = render_affine(
                motion_source,
                motion_matrix,
                border_mode="replicate",
            )
            if motion_result.size != (16, 16):
                raise RuntimeError("2D motion transform returned an unexpected image size")

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
    print("Morphorum self-test passed: API, frontend, settings, animation mode/schedules, 2D/3D render state, PEFT LoRA backend, torchvision image backend, depth registry, managed models, model index, generation capabilities, and console OK.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="morphorum")
    parser.add_argument("--version", action="version", version=f"Morphorum {__version__}")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Start the Morphorum API server.")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.add_argument(
        "--access-log",
        action="store_true",
        help="Enable Uvicorn per-request access logging in the terminal.",
    )
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
