from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version

import psutil

from . import __version__
from .paths import INSTALL_MANIFEST, ROOT, ensure_runtime_dirs


def _run(command: list[str], timeout: int = 8) -> str | None:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or result.stderr).strip() or None


def _pkg(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def git_commit() -> str | None:
    return _run(["git", "-C", str(ROOT), "rev-parse", "--short=12", "HEAD"])


def gpu_info() -> dict:
    if not shutil.which("nvidia-smi"):
        return {"backend": None, "devices": []}
    query = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    devices = []
    if query:
        for line in query.splitlines():
            fields = [item.strip() for item in line.split(",")]
            if len(fields) >= 3:
                devices.append(
                    {
                        "name": fields[0],
                        "memory_mib": fields[1],
                        "driver": fields[2],
                    }
                )
    return {"backend": "nvidia", "devices": devices}


def doctor_report() -> dict:
    ensure_runtime_dirs()
    checks: list[Check] = []

    checks.append(Check("python", sys.version_info[:2] == (3, 12), platform.python_version()))
    checks.append(Check("git", shutil.which("git") is not None, _run(["git", "--version"]) or "not found"))
    checks.append(
        Check(
            "ffmpeg",
            shutil.which("ffmpeg") is not None,
            ((_run(["ffmpeg", "-version"]) or "not found").splitlines() or ["not found"])[0],
        )
    )
    checks.append(
        Check(
            "runtime directories",
            all(path.exists() for path in (ROOT / "data", ROOT / "projects", ROOT / "outputs", ROOT / "logs")),
            str(ROOT),
        )
    )

    free = psutil.disk_usage(str(ROOT)).free
    checks.append(Check("disk space", free >= 2 * 1024**3, f"{free / 1024**3:.1f} GiB free"))

    try:
        import fastapi  # noqa: F401
        fastapi_ok = True
    except Exception:
        fastapi_ok = False
    checks.append(Check("FastAPI", fastapi_ok, _pkg("fastapi") or "not installed"))

    try:
        import uvicorn  # noqa: F401
        uvicorn_ok = True
    except Exception:
        uvicorn_ok = False
    checks.append(Check("Uvicorn", uvicorn_ok, _pkg("uvicorn") or "not installed"))

    torch_version = _pkg("torch")
    if torch_version:
        try:
            import torch

            checks.append(Check("PyTorch", True, torch_version))
            checks.append(Check("CUDA", bool(torch.cuda.is_available()), str(torch.cuda.is_available())))
        except Exception as exc:
            checks.append(Check("PyTorch", False, f"import failed: {exc}"))

    return {
        "ok": all(check.ok for check in checks if check.name not in {"ffmpeg", "CUDA"}),
        "version": __version__,
        "commit": git_commit(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "root": str(ROOT),
        "checks": [asdict(check) for check in checks],
        "gpu": gpu_info(),
    }


def install_manifest() -> dict:
    if INSTALL_MANIFEST.exists():
        try:
            return json.loads(INSTALL_MANIFEST.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def write_install_manifest(extra: dict | None = None) -> None:
    ensure_runtime_dirs()
    payload = {
        "morphorum_version": __version__,
        "git_commit": git_commit(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "root": str(ROOT),
        "fastapi": _pkg("fastapi"),
        "uvicorn": _pkg("uvicorn"),
        "torch": _pkg("torch"),
        "gpu": gpu_info(),
    }
    if extra:
        payload.update(extra)
    INSTALL_MANIFEST.write_text(json.dumps(payload, indent=2) + os.linesep, encoding="utf-8")
