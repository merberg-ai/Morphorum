"""P4.4: One host-side FFmpeg/FFprobe resolver for all multimedia features.

No installation, PATH mutations, network access or shell commands here.
Configured custom and managed choices are strict: never silently substitute a
different binary, even when a system copy is available.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .paths import ROOT

MODES = ("auto", "custom", "managed")
MANAGED_BIN = ROOT / "tools" / "ffmpeg" / "current" / "bin"
MAX_PATH_LENGTH = 4096
VERSION_TIMEOUT = 5


def normalize_ffmpeg_settings(value: Any, *, strict: bool = False) -> dict[str, str]:
    """Normalize storage settings, rejecting malformed user changes."""
    config = value if isinstance(value, dict) else {}
    mode = str(config.get("mode") or "auto").strip().lower()
    path = str(config.get("custom_path") or "").strip()
    if mode not in MODES:
        if strict:
            raise ValueError("FFmpeg mode must be auto, custom, or managed.")
        mode = "auto"
    if len(path) > MAX_PATH_LENGTH or any(ord(ch) < 32 for ch in path):
        if strict:
            raise ValueError("FFmpeg executable path is invalid.")
        path = ""
    if mode == "custom" and not path and strict:
        raise ValueError("Select an FFmpeg executable before using Custom mode.")
    return {"mode": mode, "custom_path": path}


def _bin_name(tool: str) -> str:
    return tool + (".exe" if os.name == "nt" else "")


def _sibling(ffmpeg: str) -> str | None:
    executable = Path(ffmpeg).with_name(_bin_name("ffprobe"))
    return str(executable) if executable.is_file() and os.access(executable, os.X_OK) else None


def _custom_candidate(raw_path: str) -> str | None:
    path = Path(raw_path).expanduser()
    if not path.is_absolute() or path.name.lower() not in {"ffmpeg", "ffmpeg.exe"}:
        return None
    if not path.is_file() or not os.access(path, os.X_OK):
        return None
    return str(path.resolve())


def select_ffmpeg(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Select binaries cheaply, leaving -version verification to status()."""
    if settings is None:
        from .settings import load_settings
        settings = load_settings()
    tool_settings = settings.get("tools", {}) if isinstance(settings, dict) else {}
    config = normalize_ffmpeg_settings(
        tool_settings.get("ffmpeg", {}) if isinstance(tool_settings, dict) else {})
    mode = config["mode"]
    source = mode
    ffmpeg = None
    if mode == "custom":
        ffmpeg = _custom_candidate(config["custom_path"])
    elif mode == "managed":
        ffmpeg = _custom_candidate(str(MANAGED_BIN / _bin_name("ffmpeg")))
    else:
        env_path = os.environ.get("MORPHORUM_FFMPEG", "").strip()
        if env_path:
            source = "environment"
            ffmpeg = shutil.which(env_path)
        else:
            source = "system"
            ffmpeg = shutil.which("ffmpeg")
    # An explicit custom/managed choice requires a matching sibling. For the
    # system/legacy environment mode, normal ffprobe PATH resolution works.
    ffprobe = _sibling(ffmpeg) if ffmpeg else None
    if not ffprobe and mode == "auto":
        ffprobe = shutil.which("ffprobe")
    return {
        "mode": mode, "source": source,
        "ffmpeg_path": ffmpeg, "ffprobe_path": ffprobe,
        "custom_path": config["custom_path"],
        "managed_path": str(MANAGED_BIN),
    }


def _version(path: str | None, command: str) -> tuple[str | None, str | None]:
    if not path:
        return None, command + " executable is unavailable."
    try:
        completed = subprocess.run(
            [path, "-version"], stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=VERSION_TIMEOUT, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, command + " could not run (" + type(exc).__name__ + ")."
    first = (completed.stdout or "").splitlines()
    heading = first[0].strip()[:180] if first else ""
    if completed.returncode != 0 or not re.match(r"^" + command + r" version\s+", heading, re.I):
        return None, command + " did not return a valid version."
    return heading, None


def ffmpeg_status(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    selection = select_ffmpeg(settings)
    version, error = _version(selection["ffmpeg_path"], "ffmpeg")
    probe_version, probe_error = _version(selection["ffprobe_path"], "ffprobe")
    mode = selection["mode"]
    if error:
        message = {
            "auto": "No usable FFmpeg detected. Install it on the host or select a custom executable.",
            "custom": "Custom FFmpeg is unavailable or invalid. Check the path and permissions.",
            "managed": "Managed FFmpeg is not installed yet. Install a verified local package first.",
        }[mode]
    elif probe_error:
        message = "FFmpeg works, but FFprobe is missing or invalid. Video import requires both tools."
    else:
        message = "FFmpeg and FFprobe are ready on this host."
    return {
        **selection, "available": bool(version), "probe_available": bool(probe_version),
        "version": version, "probe_version": probe_version,
        "message": message, "error": error, "probe_error": probe_error,
        "formats": ["mp4", "webm"], "qualities": ["high", "balanced", "compact"],
    }


def ffmpeg_executable() -> str | None:
    return select_ffmpeg()["ffmpeg_path"]


def ffprobe_executable() -> str | None:
    return select_ffmpeg()["ffprobe_path"]
