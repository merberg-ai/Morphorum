"""DB2.1 additive native-client contract helpers.

This module does not grant authorization; API-only authentication remains in
backend_access.py. Instance/boot IDs are for client reconnect diagnostics,
not credentials or proof of machine identity.
"""
from __future__ import annotations

import os
import secrets
import stat
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from .paths import DATA_DIR, ensure_runtime_dirs

CLIENT_PROTOCOL_VERSION = 1
BACKEND_INSTANCE_PATH = DATA_DIR / "backend-instance-id"
BOOT_ID = uuid4().hex

ERROR_CODES = {
    400: "INVALID_REQUEST",
    401: "AUTH_REQUIRED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


@lru_cache(maxsize=1)
def backend_instance_id() -> str:
    """Persist a non-secret installation identifier, independently of the token.

    O_EXCL makes concurrent startup safe. POSIX file permissions match the
    existing token's owner-only policy. Never return the absolute file path.
    """
    ensure_runtime_dirs()
    path = Path(BACKEND_INSTANCE_PATH)
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        try:
            with os.fdopen(fd, "w", encoding="ascii") as stream:
                stream.write(uuid4().hex + "\n")
        except BaseException:
            path.unlink(missing_ok=True)
            raise
    if not path.is_file():
        raise RuntimeError("Backend instance identifier could not be created.")
    if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise RuntimeError("Backend instance identifier file permissions are too broad.")
    value = path.read_text(encoding="ascii").strip()
    if len(value) != 32 or any(c not in "0123456789abcdef" for c in value):
        raise RuntimeError("Backend instance identifier is invalid.")
    return value


def capabilities(*, mode: str, video_export: dict) -> dict:
    """Describe *currently available* DB1/DB2.1 APIs; no aspirational claims."""
    from .animation_motion import SOURCE_MAX_BYTES
    from .audio_motion_upload import MAX_AUDIO_BYTES, MAX_SECONDS
    from .imported_soundtrack import MAX_IMPORT_AUDIO_BYTES

    return {
        "schema_version": 1,
        "api_contract_version": 1,
        "client_protocol_version": CLIENT_PROTOCOL_VERSION,
        "instance_id": backend_instance_id(),
        "boot_id": BOOT_ID,
        "mode": mode,
        "authentication": {
            "required": mode == "backend-only",
            "methods": ["bearer"] if mode == "backend-only" else [],
            "per_client_pairing": False,
        },
        "features": {
            "model_discovery": True,
            "sdxl_generation": True,
            "animation_render": True,
            "project_crud": True,
            "timeline": True,
            "gpu_telemetry": True,
            "console_sse": True,
            "render_progress_polling": True,
            "completed_frame_download": True,
            "animation_gif_download": True,
            "video_export": bool(video_export.get("available")),
            "animation_resume": True,
            "source_image_upload": True,
            "motion_lab_wav_analysis_upload": True,
            "soundtrack_attachment_upload": True,
            "soundtrack_attachment_download": False,
            "job_events_sse": False,
            "idempotent_submissions": False,
            "conditional_project_saves": False,
        },
        "transfers": {
            "source_image": {
                "upload": "/api/animation/projects/{project_id}/source-image",
                "download": "/api/animation/projects/{project_id}/source-image",
                "max_bytes": SOURCE_MAX_BYTES,
                "formats": ["png", "jpeg", "webp"],
            },
            "motion_lab_audio": {
                "upload": "/api/animation/projects/{project_id}/motion-lab/audio-analyze",
                "download": None,
                "max_bytes": MAX_AUDIO_BYTES,
                "max_duration_seconds": MAX_SECONDS,
                "formats": ["pcm-wav"],
            },
            "soundtrack_attachment": {
                "upload": "/api/animation/projects/{project_id}/motion-import/soundtrack",
                "metadata": "/api/animation/projects/{project_id}/motion-import/soundtrack",
                "download": None,
                "max_bytes": MAX_IMPORT_AUDIO_BYTES,
                "formats": ["wav", "mp3", "ogg", "flac"],
            },
        },
        "video": {
            "available": bool(video_export.get("available")),
            "formats": video_export.get("formats", []),
            "qualities": video_export.get("qualities", []),
        },
        "models": {"families": ["sdxl", "flux", "zimage"]},
        "events": {"console": "/api/console/stream", "job_events": None},
    }


def error_response(
    request: Request,
    *,
    status_code: int,
    detail: object,
    code: str | None = None,
    message: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Keep FastAPI's legacy detail field and add machine-readable diagnostics."""
    request_id = secrets.token_hex(12)
    safe_message = message or (detail if isinstance(detail, str) else "Invalid request.")
    response_headers = {**(headers or {}), "X-Request-ID": request_id}
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,
            "error": {
                "code": code or ERROR_CODES.get(status_code, "HTTP_ERROR"),
                "message": safe_message,
                "request_id": request_id,
            },
        },
        headers=response_headers,
    )
