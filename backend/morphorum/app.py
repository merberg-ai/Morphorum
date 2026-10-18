from __future__ import annotations

import hashlib
import math
import os
import re
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .backend_access import authorized_backend_request
from .animation_projects import (
    AnimationProjectConflict,
    AnimationProjectError,
    project_etag,
    animation_project_directory,
    animation_project_path,
    create_animation_project,
    list_animation_projects,
    load_animation_project,
    normalize_animation_project,
    new_animation_project_template,
    save_animation_project,
    trash_animation_project,
)
from .project_assets import (
    ProjectAssetError, ProjectAssetTooLarge, catalog as project_asset_catalog,
    read_bounded, source_descriptor, soundtrack_descriptor, soundtrack_path,
    motion_wav_descriptor, motion_wav_path, catalog_with_warnings as project_media_catalog,
)
from .animation_motion import SOURCE_MAX_BYTES
from .imported_soundtrack import MAX_IMPORT_AUDIO_BYTES

from .animation_resolution import (
    project_schedule_series,
    resolve_project_frame,
    resolve_project_timeline,
    validate_project_schedules,
)
from .animation_timeline import (
    TimelineError,
    delete_track_keyframe,
    get_timeline_track,
    move_track_keyframe,
    set_track_interpolation,
    timeline_snapshot,
    timeline_track_descriptors,
    upsert_track_keyframe,
)
from .animation_depth import (
    DepthError,
    clear_project_depth_manifest,
    depth_manager,
    depth_model_catalog,
    load_project_depth_manifest,
    save_project_depth_manifest,
)
from .animation_motion import (
    MotionPreviewError,
    motion_preview_manager,
    save_source_image,
)
from .animation_render import (
    AnimationRenderError,
    animation_render_manager,
)
from .animation_preflight import check_animation_render_preflight
from .motion_lab import MotionLabError, PRESETS as MOTION_LAB_PRESETS, compile_motion_lab
from .motion_studio_presets import (
    CustomPresetError, CustomPresetConflict, CustomPresetMissing,
    list_custom_presets, create_custom_preset, update_custom_preset,
    delete_custom_preset,
)
from .audio_motion import AudioMotionError
from .audio_motion_upload import MAX_AUDIO_BYTES, analyze_managed_wav
from .animation_hybrid_extract import hybrid_extraction_manager
from .animation_hybrid_source import (
    HybridSourceError, managed_video_path, probe_managed_video, store_managed_video,
)
from .animation_video import (
    VideoExportError,
    video_export_manager,
)
from .schedules import ScheduleError
from .client_protocol import capabilities as client_capabilities, error_response
from .client_submissions import SubmissionConflict, submit_once
from .client_events import job_event_stream
from .client_protocol import BOOT_ID
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from starlette.exceptions import HTTPException as StarletteHTTPException
from .console import (
    clear_console,
    emit_console,
    install_logging_handler,
    snapshot,
    sse_events,
)
from .generation import GenerationError, generation_manager
from .deforum_import import (
    DeforumImportError,
    create_deforum_import,
    preview_deforum_import,
)
from .loras import LoRAError
from .lora_inspector import LoRAInspectionError, inspect_lora
from .civitai import CivitaiLookupError, lookup_civitai
from .civitai_search import CivitaiSearchError, search_models
from .civitai_detail import model_details
from .civitai_download import start_download, list_jobs, cancel_download, resume_download, retry_download, remove_download
from .civitai_auth import get_token, token_status, store_token, clear_token
from .civitai_identify import identify_model
from .civitai_updates import check_model_update
from .civitai_library import cached_metadata, sync_metadata, preview_path
from .civitai_installed import installed_versions
from .managed_models import ManagedModelError, managed_model_manager
from .model_index import get_model, list_models, model_summary, scan_models
from .zimage_standalone import resolve_standalone_dependencies
from .paths import ROOT, ensure_runtime_dirs
from .settings import load_settings, model_family_definitions, save_settings, validate_model_paths, validate_path
from .ffmpeg_tools import ffmpeg_status, normalize_ffmpeg_settings
from .managed_ffmpeg import managed_ffmpeg_manager, ManagedFFmpegError
from .system_info import (
    doctor_report,
    git_branch,
    git_commit,
    git_commit_full,
    install_manifest,
    live_telemetry,
    windows_gpu_process_memory,
)

from .setup_state import SetupStateError, SetupStateConflict, setup_status, update_setup
from .setup_folders import (
    SetupFolderError, SetupFolderConflict, inspect_folder, save_setup_folders,
)
from .setup_examples import example_catalog, instantiate_example

BACKEND_ONLY = os.getenv("MORPHORUM_BACKEND_ONLY", "") == "1"

FRONTEND_DIR = ROOT / "frontend" / "dist"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"
ASSET_DIR = FRONTEND_DIR / "assets"


def _frontend_asset_version() -> str:
    digest = hashlib.sha256()
    if ASSET_DIR.exists():
        for path in sorted(item for item in ASSET_DIR.rglob("*") if item.is_file()):
            digest.update(path.relative_to(ASSET_DIR).as_posix().encode("utf-8"))
            try:
                digest.update(path.read_bytes())
            except OSError:
                continue
    return digest.hexdigest()[:12]


FRONTEND_ASSET_VERSION = None if BACKEND_ONLY else _frontend_asset_version()


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_runtime_dirs()
    install_logging_handler()
    emit_console("info", "server", f"Morphorum {__version__} runtime starting.")
    yield
    emit_console("info", "server", "Morphorum runtime stopping.")


app = FastAPI(
    title="Morphorum",
    version=__version__,
    description="Morphorum local AI image and animation studio.",
    lifespan=lifespan,
    docs_url=None if BACKEND_ONLY else "/docs",
    redoc_url=None if BACKEND_ONLY else "/redoc",
    openapi_url=None if BACKEND_ONLY else "/openapi.json",
)

if not BACKEND_ONLY and ASSET_DIR.exists():
    app.mount("/assets", StaticFiles(directory=ASSET_DIR), name="assets")


@app.exception_handler(StarletteHTTPException)
async def client_http_exception(request: Request, exc: StarletteHTTPException):
    return error_response(
        request, status_code=exc.status_code, detail=jsonable_encoder(exc.detail),
        headers=dict(exc.headers or {}),
    )


@app.exception_handler(RequestValidationError)
async def client_validation_exception(request: Request, exc: RequestValidationError):
    return error_response(
        request, status_code=422, detail=jsonable_encoder(exc.errors()),
        message="Request payload validation failed.",
    )


@app.middleware("http")
async def api_console_middleware(request: Request, call_next):
    # API-only mode has no browser shell; every API endpoint (including SSE,
    # preview files, settings and status) requires the shared bearer token.
    if BACKEND_ONLY and request.url.path.startswith("/api/"):
        if request.headers.get("origin") is not None:
            return error_response(
                request, status_code=403,
                code="BROWSER_ORIGIN_FORBIDDEN",
                detail="Browser-origin API requests are disabled.",
            )
        if not authorized_backend_request(request.headers.get("authorization")):
            return error_response(
                request, status_code=401,
                detail="Backend API authentication required.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        if request.url.path != "/api/console/stream":
            elapsed = (time.perf_counter() - started) * 1000
            emit_console(
                "error",
                "api",
                f"{request.method} {request.url.path} -> 500 ({elapsed:.0f} ms): {exc}",
            )
        raise

    if request.url.path != "/api/console/stream":
        elapsed = (time.perf_counter() - started) * 1000
        level = "warning" if response.status_code >= 400 else "info"
        emit_console(
            level,
            "api",
            f"{request.method} {request.url.path} -> {response.status_code} ({elapsed:.0f} ms)",
        )

    if request.url.path == "/" or request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    return response


def root():
    if FRONTEND_INDEX.exists():
        html = FRONTEND_INDEX.read_text(encoding="utf-8")
        html = html.replace("__MORPHORUM_ASSET_VERSION__", FRONTEND_ASSET_VERSION)
        return HTMLResponse(html)
    return HTMLResponse(
        "<h1>Morphorum</h1><p>Frontend assets are missing. Run the Morphorum repair command.</p>",
        status_code=503,
    )


if not BACKEND_ONLY:
    app.add_api_route("/", root, methods=["GET"], include_in_schema=False)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": "Morphorum",
        "version": __version__,
        "git_branch": git_branch(),
        "git_commit": git_commit(),
        "git_commit_full": git_commit_full(),
        "frontend_asset_version": FRONTEND_ASSET_VERSION,
        "mode": "backend-only" if BACKEND_ONLY else "standard",
        "api_contract_version": 1,
        "root": str(ROOT),
    }


@app.get("/api/client/capabilities")
def api_client_capabilities() -> dict[str, Any]:
    """DB2.1 additive feature/identity handshake for native clients."""
    return client_capabilities(
        mode="backend-only" if BACKEND_ONLY else "standard",
        video_export=video_export_manager.available(),
    )


@app.get("/api/system")
def system() -> dict:
    return doctor_report()


@app.get("/api/system/telemetry")
def system_telemetry() -> dict:
    return live_telemetry()


@app.get("/api/system/gpu-memory")
def system_gpu_memory() -> dict[str, Any]:
    """Read Morphorum's own CUDA allocator state plus on-demand WDDM counters."""
    profile = generation_manager.memory_profile()
    profile["windows_wddm"] = windows_gpu_process_memory()
    return profile


@app.get("/api/install")
def installed() -> dict:
    return install_manifest()


@app.get("/api/setup/status")
def api_setup_status() -> dict[str, Any]:
    return setup_status(
        forced=os.getenv("MORPHORUM_SETUP_WIZARD", "") == "1",
        backend_only=BACKEND_ONLY,
    )


@app.post("/api/setup/progress")
def api_setup_progress(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    if BACKEND_ONLY:
        raise HTTPException(status_code=409, detail="First-run setup requires WebUI mode.")
    # Explicit user-interaction header prevents cross-origin HTML form posts;
    # browsers cannot send it cross-site without a CORS preflight.
    if request.headers.get("x-morphorum-setup") != "1":
        raise HTTPException(status_code=403, detail="Setup action header required.")
    origin = request.headers.get("origin")
    expected = str(request.base_url).rstrip("/")
    if origin and origin.rstrip("/") != expected:
        raise HTTPException(status_code=403, detail="Setup requires a same-origin WebUI request.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(status_code=403, detail="Cross-site setup requests are forbidden.")
    forced = os.getenv("MORPHORUM_SETUP_WIZARD", "") == "1"
    manual = payload.get("manual") is True
    try:
        updated = update_setup(action=payload.get("action"),
                               step=payload.get("step"),
                               revision=payload.get("revision"),
                               forced=forced or manual,
                               template_id=payload.get('template_id'),
                               model_id=payload.get('model_id'),
                               without_example=payload.get('without_example') is True)
    except SetupStateConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SetupStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated["status"] in {"skipped", "completed"} and forced:
        # Explicit Skip or Finish dismisses the launch-only wizard override.
        os.environ.pop("MORPHORUM_SETUP_WIZARD", None)
    return setup_status(forced=os.getenv("MORPHORUM_SETUP_WIZARD", "") == "1",
                        backend_only=False)


def _require_webui_setup_action(request: Request) -> None:
    """Explicit same-origin browser-only configuration step."""
    if BACKEND_ONLY:
        raise HTTPException(status_code=409, detail="Setup folder configuration requires WebUI mode.")
    if request.headers.get("x-morphorum-setup") != "1":
        raise HTTPException(status_code=403, detail="Setup action header required.")
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(status_code=403, detail="Setup requires a same-origin WebUI request.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(status_code=403, detail="Cross-site setup requests are forbidden.")


@app.get("/api/setup/examples")
def api_setup_examples() -> dict[str, Any]:
    """Read-only bundled example metadata. Never creates a project."""
    try:
        catalog = example_catalog()
        return {
            "version": catalog["version"],
            "examples": catalog["examples"],
            "animation": catalog["animation"],
        }
    except SetupStateError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/setup/example", status_code=201)
def api_setup_example(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    """Explicit once-only project creation with durable retry reservation."""
    _require_webui_setup_action(request)
    try:
        project, reservation = instantiate_example(
            template_id=payload.get("template_id"),
            model_id=payload.get("model_id") or "",
            revision=payload.get("revision"),
            forced=(os.getenv("MORPHORUM_SETUP_WIZARD", "") == "1"
                    or payload.get("manual") is True),
        )
        return {
            "status": "created",
            "project": project,
            "revision": reservation["revision"],
            "render_ready": bool(project.get("model", {}).get("model_id")),
        }
    except SetupStateConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SetupStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AnimationProjectError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/setup/folders/check")
def api_setup_folder_check(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    _require_webui_setup_action(request)
    try:
        return inspect_folder(
            family=payload.get("family"), kind=payload.get("kind"),
            path=payload.get("path"),
        )
    except SetupFolderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/setup/folders/save")
def api_setup_folder_save(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    _require_webui_setup_action(request)
    try:
        return save_setup_folders(
            kind=payload.get("kind"), paths=payload.get("paths"),
            expected=payload.get("expected"),
        )
    except SetupFolderConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SetupFolderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    settings = load_settings()
    return {
        "settings": settings,
        "validation": validate_model_paths(settings),
        "model_families": model_family_definitions(),
    }


@app.get("/api/civitai/installed/{model_id}")
def api_civitai_installed(model_id: int) -> dict[str, Any]:
    try:
        return installed_versions(model_id)
    except CivitaiSearchError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@app.get("/api/civitai/library/{model_id}")
def api_civitai_cached_metadata(model_id: str) -> dict[str, Any]:
    try:
        return cached_metadata(model_id)
    except CivitaiSearchError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@app.post("/api/civitai/library/{model_id}/sync")
def api_civitai_sync_metadata(model_id: str) -> dict[str, Any]:
    try:
        return sync_metadata(model_id)
    except CivitaiSearchError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@app.get("/api/civitai/library/{model_id}/preview")
def api_civitai_cached_preview(model_id: str):
    try:
        path = preview_path(model_id)
        return FileResponse(path)
    except CivitaiSearchError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@app.post("/api/civitai/updates/{model_id}")
def api_civitai_check_update(model_id: str) -> dict[str, Any]:
    try:
        return check_model_update(model_id)
    except CivitaiSearchError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@app.post("/api/civitai/identify/{model_id}")
def api_civitai_identify(model_id: str) -> dict[str, Any]:
    try:
        return identify_model(model_id)
    except CivitaiSearchError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@app.get("/api/civitai/models")
def api_civitai_models(query: str = "", tag: str = "", username: str = "",
                       model_type: str = "", base_model: str = "",
                       sort: str = "Most Downloaded", period: str = "AllTime",
                       cursor: str = "", limit: int = 20, allow_mature: bool = False) -> dict[str, Any]:
    """Read-only, opt-in discovery API. Search credentials never leave the backend."""
    try:
        return search_models(query=query, tag=tag, username=username,
                             model_type=model_type, base_model=base_model,
                             sort=sort, period=period, cursor=cursor, limit=limit,
                             allow_mature=allow_mature)
    except CivitaiSearchError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@app.get("/api/civitai/models/{model_id}")
def api_civitai_model_details(model_id: int) -> dict[str, Any]:
    try:
        return model_details(model_id)
    except CivitaiSearchError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@app.get("/api/civitai/downloads")
def api_civitai_downloads() -> dict[str, Any]:
    if not load_settings().get("civitai", {}).get("enabled"):
        raise HTTPException(status_code=403, detail="Civitai Hub disabled.")
    return {"jobs": list_jobs()}


@app.post("/api/civitai/downloads", status_code=202)
def api_civitai_create_download(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return start_download(int(payload["model_id"]), int(payload["version_id"]), str(payload["file_name"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/civitai/downloads/{job_id}/cancel")
def api_civitai_cancel_download(job_id: str) -> dict[str, Any]:
    try:
        return cancel_download(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Download not found.") from exc


@app.delete("/api/civitai/downloads/{job_id}")
def api_civitai_remove_download(job_id: str) -> dict[str, Any]:
    if not load_settings().get("civitai", {}).get("enabled"):
        raise HTTPException(status_code=403, detail="Civitai Hub disabled.")
    try:
        return remove_download(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Download not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/civitai/downloads/{job_id}/resume")
def api_civitai_resume_download(job_id: str) -> dict[str, Any]:
    if not load_settings().get("civitai", {}).get("enabled"):
        raise HTTPException(status_code=403, detail="Civitai Hub disabled.")
    try:
        return resume_download(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Download not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/civitai/auth")
def api_civitai_auth() -> dict[str, Any]:
    return token_status()


@app.put("/api/civitai/auth")
def api_civitai_auth_save(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return store_token(payload.get("token"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/civitai/auth")
def api_civitai_auth_clear() -> dict[str, Any]:
    return clear_token()


@app.post("/api/civitai/downloads/{job_id}/retry")
def api_civitai_retry_download(job_id: str) -> dict[str, Any]:
    if not load_settings().get("civitai", {}).get("enabled"):
        raise HTTPException(status_code=403, detail="Civitai Hub disabled.")
    try:
        return retry_download(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Download not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/civitai/test-connection")
def api_civitai_test_connection() -> dict[str, Any]:
    """Test authenticated account access, not merely public API reachability."""
    import httpx
    if not load_settings().get("civitai", {}).get("enabled"):
        raise HTTPException(status_code=403, detail="Enable and save Civitai Hub first.")
    token = get_token()
    if not token:
        return {"ok": True, "authenticated": False, "message": "Public API access only. Add an API key to test authenticated downloads."}
    try:
        with httpx.Client(timeout=12, follow_redirects=False, trust_env=False) as client:
            response = client.get("https://civitai.com/api/v1/me",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        if response.status_code == 200:
            return {"ok": True, "authenticated": True, "status": 200, "message": "API key verified with Civitai account endpoint."}
        return {"ok": False, "authenticated": False, "status": response.status_code,
                "message": "API key was rejected or account verification unavailable."}
    except httpx.RequestError:
        return {"ok": False, "authenticated": False, "message": "Unable to contact Civitai authentication service."}


@app.get("/api/tools/ffmpeg/status")
def api_ffmpeg_status() -> dict[str, Any]:
    return ffmpeg_status()


@app.post("/api/tools/ffmpeg/check")
def api_ffmpeg_check(payload: dict[str, Any]) -> dict[str, Any]:
    """Test a proposed selection without saving or changing a binary."""
    try:
        config = normalize_ffmpeg_settings(payload, strict=True)
        return ffmpeg_status({"tools": {"ffmpeg": config}})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _ffmpeg_binary_busy() -> bool:
    """Refuse replacing/removing binaries used by live encoding jobs."""
    with video_export_manager._lock:
        if video_export_manager._active_outputs:
            return True
    with hybrid_extraction_manager._lock:
        if any(job.get("status") in {"queued", "running"}
               for job in hybrid_extraction_manager._jobs.values()):
            return True
    return False


@app.get("/api/tools/ffmpeg/managed")
def api_managed_ffmpeg_status() -> dict[str, Any]:
    return managed_ffmpeg_manager.status()


@app.post("/api/tools/ffmpeg/managed/install", status_code=202)
def api_managed_ffmpeg_install() -> dict[str, Any]:
    if _ffmpeg_binary_busy():
        raise HTTPException(status_code=409, detail=
            "Wait for active video exports and hybrid extractions before changing FFmpeg.")
    try:
        job = managed_ffmpeg_manager.start(busy_check=_ffmpeg_binary_busy)
        emit_console("info", "runtime", "Managed FFmpeg installation requested.")
        return job
    except ManagedFFmpegError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/tools/ffmpeg/managed/cancel")
def api_managed_ffmpeg_cancel() -> dict[str, Any]:
    try:
        return managed_ffmpeg_manager.cancel()
    except ManagedFFmpegError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/tools/ffmpeg/managed")
def api_managed_ffmpeg_remove() -> dict[str, Any]:
    if _ffmpeg_binary_busy():
        raise HTTPException(status_code=409, detail=
            "Wait for active video exports and hybrid extractions before removing FFmpeg.")
    try:
        result = managed_ffmpeg_manager.remove()
        emit_console("info", "runtime", "Morphorum-managed FFmpeg removed.")
        return result
    except ManagedFFmpegError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/animation/projects")
def api_animation_projects() -> dict[str, Any]:
    return {"projects": list_animation_projects()}


@app.post("/api/animation/projects/{project_id}/motion-import/preview")
def api_preview_project_motion_import(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Read-only Deforum motion inspection; never changes project or loads WAV paths."""
    from .deforum_motion_import import preview_motion_settings
    try:
        project = load_animation_project(project_id)
        return preview_motion_settings(
            payload.get("content"), filename=str(payload.get("filename") or ""),
            project=project,
        )
    except (AnimationProjectError, DeforumImportError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/animation/projects/{project_id}/motion-import/soundtrack")
def api_get_imported_soundtrack(project_id: str) -> dict[str, Any]:
    from .imported_soundtrack import read_soundtrack, ImportedSoundtrackError
    try:
        load_animation_project(project_id)
        return {"soundtrack": read_soundtrack(project_id)}
    except (AnimationProjectError, ImportedSoundtrackError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/animation/projects/{project_id}/motion-import/soundtrack")
async def api_attach_imported_soundtrack(project_id: str, request: Request) -> dict[str, Any]:
    from .imported_soundtrack import (
        store_soundtrack, ImportedSoundtrackError, MAX_IMPORT_AUDIO_BYTES,
    )
    try:
        load_animation_project(project_id)
        from urllib.parse import unquote
        filename = unquote(request.headers.get("x-audio-filename", ""))
        offset = request.headers.get("x-audio-offset-seconds", "0")
        data = await read_bounded(
            request.stream(), limit=MAX_IMPORT_AUDIO_BYTES,
            expected_digest=request.headers.get("x-content-sha256"),
        )
        record = store_soundtrack(project_id, data, filename=filename,
                                 offset_seconds=offset)
        return {
            "status": "attached", "soundtrack": record,
            "asset": soundtrack_descriptor(project_id),
        }
    except ProjectAssetTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except (AnimationProjectError, ImportedSoundtrackError, ProjectAssetError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/animation/projects/{project_id}/motion-import/soundtrack-offset")
def api_update_imported_soundtrack_offset(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    from .imported_soundtrack import update_offset, ImportedSoundtrackError
    try:
        load_animation_project(project_id)
        return {"soundtrack": update_offset(project_id, payload.get("offset_seconds"))}
    except (AnimationProjectError, ImportedSoundtrackError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/animation/projects/{project_id}/motion-import/prepare")
def api_prepare_project_motion_import(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    import json
    from .deforum_motion_import import prepare_motion_import
    try:
        current = load_animation_project(project_id)
        candidate, report = prepare_motion_import(
            payload.get("content"), filename=str(payload.get("filename") or ""),
            project=current, options=payload.get("conversion"),
        )
        digest = hashlib.sha256(json.dumps(
            current, sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest()
        return {
            "can_apply": True, "project_sha256": digest,
            "source_sha256": report["source_sha256"],
            "conversion_sha256": report["conversion_sha256"],
            "conversion": report["conversion"],
            "converted_schedules": report["converted_schedules"],
            "changed_axes": report["changed_axes"],
            "warnings": report["warnings"], "read_only": True,
        }
    except (AnimationProjectError, DeforumImportError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/animation/projects/{project_id}/motion-import/apply")
def api_apply_project_motion_import(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    from .deforum_motion_import import apply_motion_import
    try:
        saved, report = apply_motion_import(
            project_id, payload.get("content"),
            filename=str(payload.get("filename") or ""),
            expected_source_sha256=str(payload.get("source_sha256") or ""),
            expected_project_sha256=str(payload.get("project_sha256") or ""),
            options=payload.get("conversion"),
            expected_conversion_sha256=str(payload.get("conversion_sha256") or ""),
        )
        return {"status": "applied", "project": saved,
                "path": animation_project_path(project_id),
                "changed_axes": report["changed_axes"]}
    except (AnimationProjectError, DeforumImportError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/animation/import/deforum/preview")
def api_preview_deforum_import(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return preview_deforum_import(
            payload.get("content"),
            filename=str(payload.get("filename") or ""),
            model_id=payload.get("model_id"),
            project_name=payload.get("name"),
        )
    except DeforumImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/animation/import/deforum/create", status_code=201)
def api_create_deforum_import(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        project, report = create_deforum_import(
            payload.get("content"),
            filename=str(payload.get("filename") or ""),
            model_id=payload.get("model_id"),
            project_name=payload.get("name"),
        )
        return {
            "status": "created",
            "project": project,
            "path": animation_project_path(project["id"]),
            "import": {
                "importer_version": report["importer_version"],
                "source_filename": report["source_filename"],
                "source_sha256": report["source_sha256"],
                "warnings": report["warnings"],
                "unsupported_keys": report["unsupported_keys"],
                "unmapped_keys": report["unmapped_keys"],
            },
        }
    except DeforumImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/animation/project-template")
def api_animation_project_template() -> dict[str, Any]:
    """Read-only canonical defaults used by the new project wizard."""
    return {"project": new_animation_project_template()}


@app.post("/api/animation/projects", status_code=201)
def api_create_animation_project(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        project = create_animation_project(payload)
        return {
            "status": "created",
            "project": project,
            "path": animation_project_path(project["id"]),
        }
    except AnimationProjectError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/animation/projects/{project_id}")
def api_animation_project(project_id: str, response: Response) -> dict[str, Any]:
    try:
        project = load_animation_project(project_id)
        response.headers["ETag"] = project_etag(project_id)
        return {
            "project": project,
            "path": animation_project_path(project_id),
        }
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/api/animation/projects/{project_id}")
def api_save_animation_project(
    project_id: str, payload: dict[str, Any], request: Request, response: Response,
) -> dict[str, Any]:
    match = request.headers.get("if-match")
    if match is not None and not re.fullmatch(r'"[0-9a-f]{64}"', match):
        raise HTTPException(status_code=400, detail="If-Match must be one quoted project ETag.")
    try:
        project = save_animation_project(project_id, payload, expected_etag=match)
        response.headers["ETag"] = project_etag(project_id)
        return {
            "status": "saved",
            "project": project,
            "path": animation_project_path(project_id),
        }
    except AnimationProjectConflict as exc:
        raise HTTPException(status_code=412, detail=str(exc)) from exc
    except AnimationProjectError as exc:
        message = str(exc)
        status = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status, detail=message) from exc


@app.delete("/api/animation/projects/{project_id}")
def api_trash_animation_project(project_id: str) -> dict[str, Any]:
    # Never relocate a project while a live worker may read its sources.
    # Render outputs live elsewhere and are intentionally not deleted.
    try:
        load_animation_project(project_id)
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    workers = (
        (animation_render_manager, {"queued", "loading_model", "rendering", "finalizing"}),
        (motion_preview_manager, {"queued", "running", "rendering", "processing"}),
        (video_export_manager, {"queued", "encoding", "running"}),
        (hybrid_extraction_manager, {"queued", "running"}),
    )
    for manager, busy in workers:
        with manager._lock:
            for job in manager._jobs.values():
                owner = job.get("project_id") if isinstance(job, dict) else job.project_id
                status = job.get("status") if isinstance(job, dict) else job.status
                if owner == project_id and status in busy:
                    raise HTTPException(
                        status_code=409,
                        detail="This project has an active operation. Wait for it to finish before moving to Trash.",
                    )
    try:
        moved = trash_animation_project(project_id)
        return {"status": "trashed", **moved}
    except AnimationProjectError as exc:
        message = str(exc)
        code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=code, detail=message) from exc


@app.get("/api/animation/motion-lab/presets")
def api_motion_lab_presets() -> dict[str, Any]:
    return {"presets": list(MOTION_LAB_PRESETS)}


def _motion_studio_preset_error(exc: CustomPresetError) -> HTTPException:
    if isinstance(exc, CustomPresetConflict):
        code = 409
    elif isinstance(exc, CustomPresetMissing):
        code = 404
    else:
        code = 400
    return HTTPException(status_code=code, detail=str(exc))


@app.get("/api/animation/motion-studio/custom-presets")
def api_motion_studio_custom_presets() -> dict[str, Any]:
    try:
        return {"presets": list_custom_presets()}
    except CustomPresetError as exc:
        raise _motion_studio_preset_error(exc) from exc


@app.post("/api/animation/motion-studio/custom-presets", status_code=201)
def api_create_motion_studio_custom_preset(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return {"preset": create_custom_preset(payload)}
    except CustomPresetError as exc:
        raise _motion_studio_preset_error(exc) from exc


@app.put("/api/animation/motion-studio/custom-presets/{preset_id}")
def api_update_motion_studio_custom_preset(
    preset_id: str, payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        return {"preset": update_custom_preset(preset_id, payload)}
    except CustomPresetError as exc:
        raise _motion_studio_preset_error(exc) from exc


@app.delete("/api/animation/motion-studio/custom-presets/{preset_id}")
def api_delete_motion_studio_custom_preset(preset_id: str) -> dict[str, str]:
    try:
        delete_custom_preset(preset_id)
        return {"status": "removed"}
    except CustomPresetError as exc:
        raise _motion_studio_preset_error(exc) from exc


@app.get("/api/animation/projects/{project_id}/motion-lab/audio-cues/{source_sha256}")
def api_get_audio_cues(project_id: str, source_sha256: str) -> dict[str, Any]:
    from .audio_motion_cues import load_motion_cues
    try:
        load_animation_project(project_id)
        return {"cues": load_motion_cues(project_id, source_sha256)}
    except (AnimationProjectError, AudioMotionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/animation/projects/{project_id}/motion-lab/audio-cues")
def api_save_audio_cues(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    from .audio_motion_cues import save_motion_cues
    try:
        load_animation_project(project_id)
        return {"status": "saved", "cues": save_motion_cues(project_id, payload)}
    except (AnimationProjectError, AudioMotionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/animation/projects/{project_id}/motion-lab/audio-markers/{source_sha256}")
def api_get_audio_markers(project_id: str, source_sha256: str) -> dict[str, Any]:
    from .audio_marker_overrides import read_marker_overrides
    try:
        load_animation_project(project_id)
        return {"markers": read_marker_overrides(project_id, source_sha256)}
    except (AnimationProjectError, AudioMotionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/animation/projects/{project_id}/motion-lab/audio-markers")
def api_save_audio_markers(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    from .audio_marker_overrides import write_marker_overrides
    try:
        load_animation_project(project_id)
        return {"status": "saved", "markers": write_marker_overrides(project_id, payload)}
    except (AnimationProjectError, AudioMotionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/animation/projects/{project_id}/motion-lab/use-soundtrack")
def api_use_project_soundtrack_for_motion(project_id: str) -> dict[str, Any]:
    """Analyze an attached soundtrack as a managed Motion Lab WAV.

    Converts compressed audio with the host FFmpeg when needed. Does not
    change the soundtrack, source project, FPS, frame count or camera tracks.
    """
    from .project_soundtrack_motion import analyze_project_soundtrack
    try:
        project = load_animation_project(project_id)
        animation = project["animation"]
        result = analyze_project_soundtrack(
            project_id, fps=float(animation["fps"]),
            frames=int(animation["max_frames"]),
        )
        return {
            "status": "analyzed", **result,
            "asset": motion_wav_descriptor(
                project_id, result["analysis"]["source_sha256"]),
        }
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectAssetError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (AudioMotionError, OSError, ValueError, OverflowError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/animation/projects/{project_id}/motion-lab/audio-analyze")
async def api_motion_lab_audio_analyze(project_id: str, request: Request) -> dict[str, Any]:
    """Decode and retain bounded project-owned WAV, without modifying camera tracks."""
    try:
        project = load_animation_project(project_id)
        if request.headers.get("content-length"):
            if int(request.headers["content-length"]) > MAX_AUDIO_BYTES:
                raise AudioMotionError("Audio file exceeds 20 MiB.")
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_AUDIO_BYTES:
                raise AudioMotionError("Audio file exceeds 20 MiB.")
        animation = project.get("animation") or {}
        analysis = analyze_managed_wav(
            project_id, bytes(data), fps=float(animation.get("fps", 12)),
            frames=int(animation.get("max_frames", 120)),
        )
        return {"status": "analyzed", "analysis": analysis}
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (AudioMotionError, ValueError, OverflowError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/animation/projects/{project_id}/motion-lab/preview")
def api_motion_lab_compose_preview(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        project = load_animation_project(project_id)
        # Optional unsaved Editor draft is accepted for PREVIEW only. Never
        # persist changes or rely on the client snapshot for Apply.
        editor_draft = payload.get("project")
        if editor_draft is not None:
            if not isinstance(editor_draft, dict):
                raise MotionLabError("Motion Lab preview project must be an object.")
            project = normalize_animation_project(
                editor_draft, existing=project, project_id=project_id,
            )
        layers = payload.get("layers")
        if not isinstance(layers, list):
            raise MotionLabError("Motion Lab preview requires a list of layers.")
        compiled, diagnostics = compile_motion_lab(
            project, layers=layers, conflict_policy="use-current",
            include_series=True,
        )
        return {
            "status": "preview",
            "diagnostics": diagnostics,
            "layers": compiled["motion_lab"]["layers"],
            "project": compiled,
        }
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (MotionLabError, ScheduleError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/animation/projects/{project_id}/motion-lab/apply")
def api_motion_lab_apply(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        project = load_animation_project(project_id)
        layers = payload.get("layers")
        if not isinstance(layers, list):
            raise MotionLabError("Motion Lab apply requires a list of layers.")
        compiled, diagnostics = compile_motion_lab(
            project, layers=layers,
            conflict_policy=("use-current" if payload.get("rebase_current") is True else "reject"),
        )
        saved = save_animation_project(project_id, compiled, prefer_tracks=True)
        return {
            "status": "applied", "project": saved, "diagnostics": diagnostics,
        }
    except AnimationProjectError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except (MotionLabError, ScheduleError) as exc:
        status = 409 if "Camera schedules changed since Motion Lab" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@app.get("/api/animation/timeline/descriptors")
def api_animation_timeline_descriptors() -> dict[str, Any]:
    return timeline_track_descriptors()


@app.get("/api/animation/projects/{project_id}/timeline")
def api_animation_project_timeline(project_id: str) -> dict[str, Any]:
    try:
        project = load_animation_project(project_id)
        return timeline_snapshot(project)
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(
    "/api/animation/projects/{project_id}/timeline/tracks/{group}/{name}"
)
def api_animation_timeline_track(
    project_id: str,
    group: str,
    name: str,
) -> dict[str, Any]:
    try:
        project = load_animation_project(project_id)
        return get_timeline_track(project, group, name)
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TimelineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put(
    "/api/animation/projects/{project_id}/timeline/tracks/"
    "{group}/{name}/keyframes/{frame}"
)
def api_upsert_animation_timeline_keyframe(
    project_id: str,
    group: str,
    name: str,
    frame: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        project = load_animation_project(project_id)
        edited = upsert_track_keyframe(
            project,
            group,
            name,
            frame=frame,
            value=payload.get("value"),
        )
        saved = save_animation_project(
            project_id,
            edited,
            prefer_tracks=True,
        )
        return {
            "status": "saved",
            "project": saved,
            **get_timeline_track(saved, group, name),
        }
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TimelineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete(
    "/api/animation/projects/{project_id}/timeline/tracks/"
    "{group}/{name}/keyframes/{frame}"
)
def api_delete_animation_timeline_keyframe(
    project_id: str,
    group: str,
    name: str,
    frame: int,
) -> dict[str, Any]:
    try:
        project = load_animation_project(project_id)
        edited = delete_track_keyframe(
            project,
            group,
            name,
            frame=frame,
        )
        saved = save_animation_project(
            project_id,
            edited,
            prefer_tracks=True,
        )
        return {
            "status": "saved",
            "project": saved,
            **get_timeline_track(saved, group, name),
        }
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TimelineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/api/animation/projects/{project_id}/timeline/tracks/"
    "{group}/{name}/keyframes/{frame}/move"
)
def api_move_animation_timeline_keyframe(
    project_id: str,
    group: str,
    name: str,
    frame: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        project = load_animation_project(project_id)
        edited = move_track_keyframe(
            project,
            group,
            name,
            source_frame=frame,
            target_frame=payload.get("frame"),
            overwrite=bool(payload.get("overwrite", False)),
        )
        saved = save_animation_project(
            project_id,
            edited,
            prefer_tracks=True,
        )
        return {
            "status": "saved",
            "project": saved,
            **get_timeline_track(saved, group, name),
        }
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TimelineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put(
    "/api/animation/projects/{project_id}/timeline/tracks/"
    "{group}/{name}/interpolation"
)
def api_set_animation_timeline_interpolation(
    project_id: str,
    group: str,
    name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        project = load_animation_project(project_id)
        edited = set_track_interpolation(
            project,
            group,
            name,
            interpolation=payload.get("interpolation"),
        )
        saved = save_animation_project(
            project_id,
            edited,
            prefer_tracks=True,
        )
        return {
            "status": "saved",
            "project": saved,
            **get_timeline_track(saved, group, name),
        }
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TimelineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/animation/projects/{project_id}/hybrid-video", status_code=201)
async def api_upload_hybrid_video(project_id: str, request: Request) -> dict[str, Any]:
    """B6.2 managed video upload only; does not change active render semantics."""
    try:
        load_animation_project(project_id)
        filename = str(request.headers.get("x-filename") or "source.mp4")
        info = await store_managed_video(project_id, filename, request.stream())
        emit_console("info", "animation",
                     f"Source video uploaded and inspected for project {project_id}.")
        return {"status": "uploaded", "video": info, "render_enabled": False}
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HybridSourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/animation/projects/{project_id}/hybrid-video")
def api_hybrid_video_status(project_id: str, filename: str = "source.mp4") -> dict[str, Any]:
    try:
        load_animation_project(project_id)
        return {
            "video": probe_managed_video(project_id, filename),
            "render_enabled": False,
        }
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HybridSourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/animation/projects/{project_id}/hybrid-extraction", status_code=202)
def api_start_hybrid_extraction(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        load_animation_project(project_id)
        return hybrid_extraction_manager.start(
            project_id, str(payload.get("filename", "source.mp4")),
            payload.get("start"), payload.get("end"), payload.get("fps"))
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HybridSourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/animation/projects/{project_id}/hybrid-extraction/{job_id}")
def api_hybrid_extraction_status(project_id: str, job_id: str) -> dict[str, Any]:
    try:
        load_animation_project(project_id)
        return hybrid_extraction_manager.status(project_id, job_id)
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HybridSourceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/animation/projects/{project_id}/hybrid-extraction/{job_id}/cancel")
def api_cancel_hybrid_extraction(project_id: str, job_id: str) -> dict[str, Any]:
    try:
        load_animation_project(project_id)
        return hybrid_extraction_manager.cancel(project_id, job_id)
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HybridSourceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/animation/projects/{project_id}/hybrid-frames")
def api_hybrid_frames(project_id: str, response: Response) -> dict[str, Any]:
    try:
        load_animation_project(project_id)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return hybrid_extraction_manager.manifest(project_id)
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HybridSourceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/animation/projects/{project_id}/hybrid-frames/{frame_number}")
def api_hybrid_frame_file(project_id: str, frame_number: int):
    try:
        load_animation_project(project_id)
        manifest = hybrid_extraction_manager.manifest(project_id)
        if frame_number < 1 or frame_number > manifest["frames"]:
            raise HybridSourceError("Frame number out of bounds.")
        filename = manifest["filenames"][frame_number - 1]
        path = animation_project_directory(project_id) / "assets" / "hybrid" / "frames" / filename
        return FileResponse(
            path, media_type="image/png",
            headers={"Cache-Control": "no-store, max-age=0"},
        )
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HybridSourceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/animation/projects/{project_id}/assets")
def api_project_assets(project_id: str) -> dict[str, Any]:
    """DB2.3 read-only project-owned media catalog. No server file paths."""
    try:
        load_animation_project(project_id)
        return {"schema_version": 1, "assets": project_asset_catalog(project_id)}
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectAssetError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/animation/projects/{project_id}/media-inventory")
def api_project_media_inventory(project_id: str) -> dict[str, Any]:
    """WebUI-specific partial recovery inventory; does not alter strict assets API."""
    try:
        project = load_animation_project(project_id)
        return project_media_catalog(project_id, project)
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/animation/projects/{project_id}/motion-import/soundtrack/file")
def api_download_attached_soundtrack(project_id: str):
    try:
        load_animation_project(project_id)
        asset = soundtrack_descriptor(project_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="No project soundtrack attached.")
        path, record = soundtrack_path(project_id)
        return FileResponse(
            path, media_type=asset["media_type"], filename=record["filename"],
            headers={
                "Cache-Control": "private, no-store",
                "ETag": '"' + asset["sha256"] + '"',
                "X-Content-SHA256": asset["sha256"],
            },
        )
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectAssetError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/animation/projects/{project_id}/motion-lab/audio/{sha256}/spectrum")
def api_motion_lab_frequency_spectrum(project_id: str, sha256: str) -> dict[str, Any]:
    """Read a checksum-verified saved WAV for bounded log-scale spectrum display."""
    from .audio_channel_bands import analyze_frequency_spectrum
    try:
        load_animation_project(project_id)
        data = motion_wav_path(project_id, sha256).read_bytes()
        return {"source_sha256": sha256, "analysis": analyze_frequency_spectrum(data)}
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectAssetError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (AudioMotionError, OSError, ValueError, TypeError, OverflowError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/animation/projects/{project_id}/motion-lab/audio/{sha256}/bands")
def api_motion_lab_frequency_channels(project_id: str, sha256: str,
                                      payload: dict[str, Any]) -> dict[str, Any]:
    """Analyze custom channel ranges without modifying project camera tracks."""
    from .audio_channel_bands import analyze_frequency_bands
    try:
        project = load_animation_project(project_id)
        data = motion_wav_path(project_id, sha256).read_bytes()
        animation = project["animation"]
        response = analyze_frequency_bands(
            data, fps=float(animation["fps"]), frames=int(animation["max_frames"]),
            ranges=payload.get("ranges"),
        )
        return {"source_sha256": sha256, "analysis": response}
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectAssetError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (AudioMotionError, OSError, ValueError, TypeError, OverflowError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/animation/projects/{project_id}/motion-lab/audio/{sha256}/analysis")
def api_restore_motion_lab_audio_analysis(project_id: str, sha256: str) -> dict[str, Any]:
    """Reanalyze a verified project-owned WAV for the currently saved FPS/frames.

    A browser reopening the project must not need to re-upload its local file.
    This uses the same bounded decoder as the original analysis endpoint.
    """
    try:
        project = load_animation_project(project_id)
        path = motion_wav_path(project_id, sha256)
        animation = project.get("animation") or {}
        result = analyze_managed_wav(
            project_id, path.read_bytes(),
            fps=float(animation.get("fps", 12)),
            frames=int(animation.get("max_frames", 120)),
        )
        return {"status": "analyzed", "analysis": result}
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ProjectAssetError, AudioMotionError, OSError, ValueError, OverflowError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/animation/projects/{project_id}/motion-lab/audio/{sha256}")
def api_download_motion_lab_wav(project_id: str, sha256: str):
    try:
        load_animation_project(project_id)
        asset = motion_wav_descriptor(project_id, sha256)
        path = motion_wav_path(project_id, sha256)
        return FileResponse(
            path, media_type="audio/wav", filename=asset["filename"],
            headers={
                "Cache-Control": "private, no-store",
                "ETag": '"' + asset["sha256"] + '"',
                "X-Content-SHA256": asset["sha256"],
            },
        )
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectAssetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/animation/projects/{project_id}/source-image", status_code=201)
async def api_upload_animation_source_image(project_id: str, request: Request) -> dict[str, Any]:
    try:
        project = load_animation_project(project_id)
        data = await read_bounded(
            request.stream(), limit=SOURCE_MAX_BYTES,
            expected_digest=request.headers.get("x-content-sha256"),
        )
        destination = animation_project_directory(project_id) / "assets" / "source.png"
        info = save_source_image(data, destination)
        filename = str(request.headers.get("x-filename") or "source-image").strip()[:255]
        project.setdefault("animation", {})["source_image"] = "assets/source.png"
        project["animation"]["source_image_name"] = filename
        saved = save_animation_project(project_id, project)
        clear_project_depth_manifest(animation_project_directory(project_id))
        emit_console(
            "info",
            "animation",
            f"Updated source image for animation project {project_id}: "
            f"{info['width']}x{info['height']}.",
        )
        return {
            "status": "uploaded",
            "source": {
                "url": f"/api/animation/projects/{project_id}/source-image",
                "name": filename,
                "width": info["width"],
                "height": info["height"],
                "bytes": info["bytes"],
            },
            "project": saved,
            "asset": source_descriptor(project_id),
        }
    except ProjectAssetTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ProjectAssetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MotionPreviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/animation/projects/{project_id}/source-image")
def api_animation_source_image(project_id: str):
    try:
        load_animation_project(project_id)
        path = animation_project_directory(project_id) / "assets" / "source.png"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Animation source image not found.")
        return FileResponse(path, media_type="image/png", filename="source.png")
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/animation/projects/{project_id}/source-image")
def api_delete_animation_source_image(project_id: str) -> dict[str, Any]:
    try:
        project = load_animation_project(project_id)
        path = animation_project_directory(project_id) / "assets" / "source.png"
        path.unlink(missing_ok=True)
        project.setdefault("animation", {})["source_image"] = ""
        project["animation"]["source_image_name"] = ""
        clear_project_depth_manifest(animation_project_directory(project_id))
        saved = save_animation_project(project_id, project)
        emit_console("info", "animation", f"Cleared source image for animation project {project_id}.")
        return {"status": "cleared", "project": saved}
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/animation/depth/models")
def api_animation_depth_models() -> dict[str, Any]:
    return {
        "models": depth_model_catalog(),
        "status": depth_manager.status(),
    }


@app.get("/api/animation/projects/{project_id}/depth-preview/status")
def api_animation_depth_preview_status(project_id: str) -> dict[str, Any]:
    try:
        project_dir = animation_project_directory(project_id)
        load_animation_project(project_id)
        manifest = load_project_depth_manifest(project_dir)
        if not manifest:
            return {
                "available": False,
                "preview": None,
                "manager": depth_manager.status(),
            }
        cache_key = str(manifest.get("cache_key") or "")
        cached = depth_manager.cached(cache_key) if cache_key else None
        return {
            "available": bool(cached),
            "preview": ({**manifest, "cache_hit": True} if cached else manifest),
            "manager": depth_manager.status(),
        }
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DepthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/animation/projects/{project_id}/depth-preview")
def api_generate_animation_depth_preview(
    project_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        project = load_animation_project(project_id)
        project_dir = animation_project_directory(project_id)
        source_rel = str(project.get("animation", {}).get("source_image") or "").strip()
        if not source_rel:
            raise DepthError(
                "Upload an animation source image before generating a depth preview."
            )
        source_path = (project_dir / source_rel).resolve(strict=False)
        project_root = project_dir.resolve(strict=False)
        if source_path != project_root and project_root not in source_path.parents:
            raise DepthError("Animation source image path escaped the project directory.")
        if not source_path.is_file():
            raise DepthError("Animation source image not found.")

        result = depth_manager.estimate_path(
            source_path,
            model_id=payload.get("model_id"),
            device=str(payload.get("device") or "auto"),
            force=bool(payload.get("force", False)),
            release_after=True,
        )
        save_project_depth_manifest(project_dir, result)
        return {
            "status": "ready",
            "preview": {
                **{
                    key: value
                    for key, value in result.items()
                    if key not in {"data_path", "preview_path", "metadata_path"}
                },
                "url": f"/api/animation/projects/{project_id}/depth-preview/image?v={result['cache_key'][:12]}",
            },
            "manager": depth_manager.status(),
        }
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DepthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/animation/projects/{project_id}/depth-preview/image")
def api_animation_depth_preview_image(project_id: str):
    try:
        project_dir = animation_project_directory(project_id)
        load_animation_project(project_id)
        manifest = load_project_depth_manifest(project_dir)
        cache_key = str((manifest or {}).get("cache_key") or "")
        if not cache_key:
            raise DepthError("No depth preview has been generated for this project.")
        return FileResponse(
            depth_manager.preview_path(cache_key),
            media_type="image/png",
            filename="depth-preview.png",
        )
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DepthError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/animation/projects/{project_id}/depth-preview")
def api_clear_animation_depth_preview(project_id: str) -> dict[str, Any]:
    try:
        project_dir = animation_project_directory(project_id)
        load_animation_project(project_id)
        clear_project_depth_manifest(project_dir)
        return {"status": "cleared"}
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/animation/motion-preview", status_code=202)
def api_start_motion_preview(payload: dict[str, Any]) -> dict[str, Any]:
    project_payload = payload.get("project")
    if not isinstance(project_payload, dict):
        raise HTTPException(status_code=400, detail="Animation project payload is required.")
    project_id = str(project_payload.get("id") or "").strip().lower()
    if not project_id:
        raise HTTPException(status_code=400, detail="Save the animation project before previewing motion.")

    try:
        normalized = normalize_animation_project(
            project_payload,
            existing=project_payload,
            project_id=project_id,
        )
        validation = validate_project_schedules(normalized)
        if not validation["valid"]:
            first = next(
                issue for issue in validation["issues"] if issue["severity"] == "error"
            )
            raise MotionPreviewError(
                f"Cannot preview invalid schedule {first['field']}: {first['message']}"
            )
        source_path = animation_project_directory(project_id) / "assets" / "source.png"
        options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
        # Motion Lab can preview a built-in calibration grid even when the
        # animation has no uploaded starting/reference image.
        if not source_path.is_file():
            source_path = None
        return motion_preview_manager.start(
            project=normalized,
            source_path=source_path,
            highlight_holes=bool(options.get("highlight_holes", False)),
            quality=str(options.get("quality", "balanced")),
        )
    except (AnimationProjectError, MotionPreviewError, ScheduleError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/animation/motion-preview/{job_id}")
def api_motion_preview_job(job_id: str) -> dict[str, Any]:
    try:
        return motion_preview_manager.get(job_id)
    except MotionPreviewError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/animation/motion-preview/{job_id}/image")
def api_motion_preview_image(job_id: str):
    try:
        path = motion_preview_manager.result_path(job_id)
        return FileResponse(path, media_type="image/gif", filename="motion-preview.gif")
    except MotionPreviewError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/animation/motion-preview/{job_id}/frames/{index}")
def api_motion_preview_frame(job_id: str, index: int):
    try:
        return FileResponse(
            motion_preview_manager.frame_path(job_id, index),
            media_type="image/png",
        )
    except MotionPreviewError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/animation/renders/preflight")
def api_animation_render_preflight(payload: dict[str, Any]) -> dict[str, Any]:
    """Read-only validation for the exact browser project about to be rendered."""
    project_payload = payload.get("project")
    if not isinstance(project_payload, dict):
        raise HTTPException(status_code=400, detail="Animation project payload is required.")
    project_id = str(project_payload.get("id") or "").strip().lower()
    if not project_id:
        raise HTTPException(status_code=400, detail="Save the animation project before rendering.")
    try:
        normalized = normalize_animation_project(
            project_payload, existing=project_payload, project_id=project_id,
        )
        source_path = animation_project_directory(project_id) / "assets" / "source.png"
        return check_animation_render_preflight(normalized, source_path)
    except (AnimationProjectError, ScheduleError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/animation/renders", status_code=202)
def api_start_animation_render(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    project_payload = payload.get("project")
    if not isinstance(project_payload, dict):
        raise HTTPException(status_code=400, detail="Animation project payload is required.")
    project_id = str(project_payload.get("id") or "").strip().lower()
    if not project_id:
        raise HTTPException(status_code=400, detail="Save the animation project before rendering.")

    try:
        normalized = normalize_animation_project(
            project_payload,
            existing=project_payload,
            project_id=project_id,
        )
        source_path = animation_project_directory(project_id) / "assets" / "source.png"
        return submit_once(
            request, operation="animation-render", payload=payload,
            submit=lambda: animation_render_manager.submit(
                project=normalized, source_path=source_path,
            ),
            lookup=animation_render_manager.get,
        )
    except SubmissionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (AnimationProjectError, AnimationRenderError, ScheduleError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/animation/renders/{render_id}")
def api_animation_render(render_id: str) -> dict[str, Any]:
    try:
        return animation_render_manager.get(render_id)
    except AnimationRenderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/animation/renders/{render_id}/cancel")
def api_cancel_animation_render(render_id: str) -> dict[str, Any]:
    try:
        return animation_render_manager.cancel(render_id)
    except AnimationRenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/animation/projects/{project_id}/renders")
def api_animation_project_renders(project_id: str) -> dict[str, Any]:
    try:
        load_animation_project(project_id)
        return {"renders": animation_render_manager.list_project(project_id)}
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/animation/renders/{project_id}/{render_id}/resume", status_code=202)
def api_resume_animation_render(project_id: str, render_id: str) -> dict[str, Any]:
    try:
        load_animation_project(project_id)
        return animation_render_manager.resume(project_id, render_id)
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AnimationRenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/animation/renders/{project_id}/{render_id}/review-metadata")
def api_animation_render_review_metadata(
    project_id: str, render_id: str,
) -> dict[str, Any]:
    try:
        load_animation_project(project_id)
        return animation_render_manager.review_metadata(project_id, render_id)
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AnimationRenderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/animation/renders/{project_id}/{render_id}/frames/{frame}")
def api_animation_render_frame(project_id: str, render_id: str, frame: int):
    try:
        path = animation_render_manager.frame_path(
            project_id,
            render_id,
            frame,
        )
        return FileResponse(
            path,
            media_type="image/png",
            filename=path.name,
        )
    except AnimationRenderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/animation/renders/{project_id}/{render_id}/preview")
def api_animation_render_preview(project_id: str, render_id: str):
    try:
        path = animation_render_manager.preview_path(project_id, render_id)
        return FileResponse(
            path,
            media_type="image/gif",
            filename="animation-preview.gif",
        )
    except AnimationRenderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/animation/renders/{project_id}/{render_id}/performance")
def api_animation_render_performance(project_id: str, render_id: str) -> dict[str, Any]:
    try:
        return animation_render_manager.performance_report(project_id, render_id)
    except AnimationRenderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/animation/video/availability")
def api_animation_video_availability() -> dict[str, Any]:
    return video_export_manager.available()


@app.post(
    "/api/animation/renders/{project_id}/{render_id}/video",
    status_code=202,
)
def api_start_animation_video_export(
    project_id: str, render_id: str, payload: dict[str, Any], request: Request,
) -> dict[str, Any]:
    try:
        return submit_once(
            request, operation=f"video-export:{project_id}:{render_id}",
            payload=payload,
            submit=lambda: video_export_manager.start(
                project_id, render_id,
                format=str(payload.get("format") or "mp4"),
                quality=str(payload.get("quality") or "balanced"),
                fps=payload.get("fps"),
            ),
            lookup=video_export_manager.get,
        )
    except SubmissionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (VideoExportError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/animation/video/jobs/{job_id}")
def api_animation_video_export_job(job_id: str) -> dict[str, Any]:
    try:
        return video_export_manager.get(job_id)
    except VideoExportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/animation/renders/{project_id}/{render_id}/videos")
def api_animation_render_video_exports(project_id: str, render_id: str) -> dict[str, Any]:
    try:
        return {"exports": video_export_manager.list(project_id, render_id)}
    except VideoExportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/animation/renders/{project_id}/{render_id}/video/{format}/{quality}/{fps}")
def api_download_animation_video(
    project_id: str, render_id: str, format: str, quality: str, fps: int,
    inline: bool = False,
):
    try:
        path = video_export_manager.file(project_id, render_id, format, quality, fps)
        digest = video_export_manager.checksum(path)
        return FileResponse(
            path,
            media_type="video/mp4" if format == "mp4" else "video/webm",
            filename=path.name,
            content_disposition_type="inline" if inline else "attachment",
            headers={
                "X-Content-SHA256": digest,
                "ETag": '"' + digest + '"',
                "Cache-Control": "private, no-store",
            },
        )
    except VideoExportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/animation/resolve-frame")
def api_resolve_animation_frame(payload: dict[str, Any]) -> dict[str, Any]:
    project_payload = payload.get("project")
    if not isinstance(project_payload, dict):
        raise HTTPException(status_code=400, detail="Animation project payload is required.")
    project_id = str(project_payload.get("id") or "preview-project").strip().lower()
    try:
        normalized = normalize_animation_project(
            project_payload,
            existing=project_payload,
            project_id=project_id,
        )
        frame = int(payload.get("frame", 0))
        return {"resolved": resolve_project_frame(normalized, frame)}
    except (
        AnimationProjectError,
        ScheduleError,
        TimelineError,
        LoRAError,
        TypeError,
        ValueError,
    ) as exc:
        emit_console(
            "warning",
            "animation",
            f"Resolved-frame preview failed for {project_id}: {exc}",
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/animation/resolve-timeline")
def api_resolve_animation_timeline(payload: dict[str, Any]) -> dict[str, Any]:
    project_payload = payload.get("project")
    if not isinstance(project_payload, dict):
        raise HTTPException(status_code=400, detail="Animation project payload is required.")
    project_id = str(project_payload.get("id") or "preview-project").strip().lower()
    try:
        normalized = normalize_animation_project(
            project_payload,
            existing=project_payload,
            project_id=project_id,
        )
        return resolve_project_timeline(
            normalized,
            start_frame=payload.get("start_frame", 0),
            end_frame=payload.get("end_frame"),
            step=payload.get("step", 1),
        )
    except (AnimationProjectError, ScheduleError, TimelineError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/animation/validate-schedules")
def api_validate_animation_schedules(payload: dict[str, Any]) -> dict[str, Any]:
    project_payload = payload.get("project")
    if not isinstance(project_payload, dict):
        raise HTTPException(status_code=400, detail="Animation project payload is required.")
    project_id = str(project_payload.get("id") or "preview-project").strip().lower()
    try:
        normalized = normalize_animation_project(
            project_payload,
            existing=project_payload,
            project_id=project_id,
        )
        return validate_project_schedules(normalized)
    except (AnimationProjectError, ScheduleError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/animation/schedule-series")
def api_animation_schedule_series(payload: dict[str, Any]) -> dict[str, Any]:
    project_payload = payload.get("project")
    if not isinstance(project_payload, dict):
        raise HTTPException(status_code=400, detail="Animation project payload is required.")
    field = str(payload.get("field") or "").strip()
    project_id = str(project_payload.get("id") or "preview-project").strip().lower()
    try:
        normalized = normalize_animation_project(
            project_payload,
            existing=project_payload,
            project_id=project_id,
        )
        return project_schedule_series(
            normalized,
            field,
            sample_count=int(payload.get("sample_count", 120)),
        )
    except (AnimationProjectError, ScheduleError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/loras")
def api_lora_library(family: str | None = None, search: str | None = None) -> dict[str, Any]:
    """List LoRAs already indexed from configured directories."""
    supported = {"sdxl", "flux", "zimage"}
    if family is not None and family not in supported:
        raise HTTPException(status_code=400, detail="Unsupported LoRA family.")
    records = list_models(family=family, kind="loras", search=search, limit=2000)
    counts = {key: sum(item.get("family") == key for item in records) for key in sorted(supported)}
    emit_console(
        "info", "lora",
        f"LoRA Manager library ready: {len(records)} indexed item(s), "
        + ", ".join(f"{name}={count}" for name, count in counts.items())
        + ("; filtered by " + family if family else "") + ".",
    )
    return {"loras": records}


@app.get("/api/loras/{model_id}/inspect")
def api_lora_inspect(model_id: str) -> dict[str, Any]:
    """Inspect the file referenced by an indexed LoRA ID, never an arbitrary path."""
    try:
        detail = inspect_lora(model_id)
    except LoRAInspectionError as exc:
        emit_console("warning", "lora", f"LoRA inspection refused for ID {model_id[:32]}: {exc}")
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    summary = str(detail.get("name") or "")[:130].replace("\n", " ").replace("\r", " ")
    components = detail.get("components") or {}
    ranks = detail.get("ranks") or []
    rank_text = ", ".join(f"{item['rank']}x{item['modules']}" for item in ranks[:10]) or "unknown"
    emit_console(
        "info", "lora",
        f"Inspected [{detail.get('family')}] {summary}: "
        f"format={detail.get('adapter_format')}, tensors={detail.get('tensor_count')}, "
        f"UNet={components.get('unet', 0)}, transformer={components.get('transformer', 0)}, "
        f"TE1={components.get('text_encoder', 0)}, TE2={components.get('text_encoder_2', 0)}, "
        f"ranks={rank_text}.",
    )
    emit_console(
        "info", "lora",
        f"Metadata for {summary}: base_model={str(detail.get('metadata_base_model') or 'not recorded')[:120]}, "
        f"trigger_source={detail.get('trigger_source')}, trigger_count={len(detail.get('trigger_words') or [])}, "
        f"sidecar_json={detail.get('sidecar') or 'none'}, "
        f"sidecar_html={(detail.get('html_sidecar') or {}).get('filename') or 'none'}.",
    )
    for warning in (detail.get("warnings") or [])[:8]:
        emit_console("warning", "lora", f"{summary}: {str(warning)[:220]}")
    for error in (detail.get("errors") or [])[:6]:
        emit_console("warning", "lora", f"{summary}: {str(error)[:220]}")
    return detail


@app.post("/api/loras/{model_id}/civitai-lookup")
def api_lora_civitai_lookup(model_id: str) -> dict[str, Any]:
    """Network lookup is opt-in; the indexed file SHA-256 is sent to Civitai."""
    indexed = get_model(model_id)
    display = (str(indexed.get("name") or "")[:130].replace("\n", " ").replace("\r", " ")
               if indexed and indexed.get("kind") == "loras" else model_id[:32])
    emit_console("info", "lora", f"Civitai lookup requested for {display}: hashing local LoRA file.")
    try:
        result = lookup_civitai(model_id)
    except CivitaiLookupError as exc:
        emit_console("warning", "lora", f"Civitai lookup failed for {display}: {exc}")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result.get("found"):
        emit_console(
            "info", "lora",
            f"Civitai matched {display}: {result.get('confidence')}, "
            f"model={result.get('model_id')}, version={result.get('version_id')}, "
            f"base={result.get('base_model') or 'unknown'}, "
            f"trained_words={len(result.get('trained_words') or [])}, "
            f"sha256={str(result.get('sha256') or '')[:12]}…",
        )
    else:
        emit_console(
            "warning", "lora", f"No Civitai version match for {display}, "
            f"sha256={str(result.get('sha256') or '')[:12]}…",
        )
    return result


@app.post("/api/loras/{model_id}/runtime-audit")
def api_lora_runtime_audit(model_id: str) -> dict[str, Any]:
    """Record an explicit read-only snapshot of LoRA state on the live pipeline."""
    record = get_model(model_id)
    if not record or record.get("kind") != "loras":
        raise HTTPException(status_code=404, detail="Indexed LoRA not found.")
    status = generation_manager.model_status()
    entry = next((item for item in status.get("loras", []) if item.get("id") == model_id), None)
    active = next(
        (item for item in status.get("active_loras", [])
         if entry and item.get("adapter_name") == entry.get("adapter_name")),
        None,
    )
    name = str(record.get("name") or "")[:130].replace("\n", " ").replace("\r", " ")
    diagnostics = (entry or {}).get("diagnostics") or {}
    emit_console(
        "info", "lora",
        f"Runtime audit [{record.get('family')}] {name}: "
        f"checkpoint={status.get('model_name') or 'none'}, "
        f"family={status.get('family') or 'none'}, task={status.get('task') or 'none'}, "
        f"attached={'yes' if entry else 'no'}, "
        f"active_weight={active.get('weight') if active else 'none'}, "
        f"compatibility={(entry or {}).get('compatibility') or 'unspecified'}, "
        f"injected_modules={diagnostics.get('modules', 'unknown')}, "
        f"tensor_abs_sum={diagnostics.get('abs_sum', 'unknown')}. "
        "Adapter registration does not establish pixel-level influence.",
    )
    return status


@app.post("/api/loras/{model_id}/activity")
def api_lora_manager_activity(model_id: str, payload: dict[str, Any]) -> dict[str, str]:
    """Record prompt insertion outcomes without accepting arbitrary log messages."""
    record = get_model(model_id)
    if record is None or record.get("kind") != "loras":
        raise HTTPException(status_code=404, detail="Indexed LoRA not found.")
    event = str(payload.get("event") or "")
    if event not in {"prompt_inserted", "prompt_rejected"}:
        raise HTTPException(status_code=400, detail="Invalid LoRA Manager event.")
    reason = str(payload.get("reason") or "")
    allowed_reasons = {"", "no_model", "wrong_family", "not_indexed",
                       "invalid_strength", "invalid_name"}
    if reason not in allowed_reasons:
        raise HTTPException(status_code=400, detail="Invalid LoRA Manager reason.")
    weight = payload.get("weight")
    if not isinstance(weight, (int, float)) or isinstance(weight, bool) or not math.isfinite(weight):
        raise HTTPException(status_code=400, detail="A finite LoRA weight is required.")
    family = str(payload.get("image_family") or "")
    if family not in {"", "sdxl", "flux", "zimage"}:
        raise HTTPException(status_code=400, detail="Invalid image model family.")
    try:
        count = int(payload.get("trigger_count", 0))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid trigger word count.") from exc
    if count < 0 or count > 64:
        raise HTTPException(status_code=400, detail="Invalid trigger word count.")
    if event == "prompt_inserted" and reason:
        raise HTTPException(status_code=400, detail="An inserted LoRA cannot have a rejection reason.")
    if event == "prompt_rejected" and not reason:
        raise HTTPException(status_code=400, detail="A rejected LoRA must have a reason.")
    display = str(record.get("name") or "")[:130].replace("\n", " ").replace("\r", " ")
    emit_console(
        "info" if event == "prompt_inserted" else "warning", "lora",
        f"Image prompt {'insertion succeeded' if event == 'prompt_inserted' else 'insertion rejected'} "
        f"for [{record.get('family')}] {display}: "
        f"weight={weight:.3g}, image_family={family or 'none'}, trigger_words={count}"
        + (f", reason={reason}" if reason else "") + ".",
    )
    return {"status": "recorded"}


@app.get("/api/models/families")
def api_model_families() -> dict[str, Any]:
    return {"families": model_family_definitions()}


@app.get("/api/managed-models")
def api_managed_models() -> dict[str, Any]:
    return {"models": managed_model_manager.catalog()}


@app.get("/api/managed-models/{model_id}")
def api_managed_model(model_id: str) -> dict[str, Any]:
    try:
        return managed_model_manager.status(model_id)
    except ManagedModelError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/managed-models/{model_id}/download", status_code=202)
def api_managed_model_download(model_id: str) -> dict[str, Any]:
    try:
        return managed_model_manager.start_download(model_id)
    except ManagedModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/settings")
def put_settings(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        settings = save_settings(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    validation = validate_model_paths(settings)
    bad = sum(1 for item in validation if not item.get("is_directory") or not item.get("readable"))
    if bad:
        emit_console("warning", "runtime", f"Settings saved with {bad} model path warning(s).")
    else:
        emit_console("info", "runtime", "Settings saved successfully.")
    return {"status": "saved", "settings": settings, "validation": validation}


@app.post("/api/settings/validate-path")
def post_validate_path(payload: dict[str, Any]) -> dict[str, Any]:
    return validate_path(str(payload.get("path", "")))


@app.post("/api/settings/validate")
def post_validate_settings() -> dict[str, Any]:
    return {"validation": validate_model_paths()}


@app.get("/api/models")
def api_models(
    family: str | None = None,
    kind: str | None = None,
    search: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    return {"models": list_models(family=family, kind=kind, search=search, limit=limit)}


@app.get("/api/models/summary")
def api_models_summary() -> dict[str, Any]:
    return model_summary()


@app.post("/api/models/scan")
def api_models_scan() -> dict[str, Any]:
    return scan_models()


@app.get("/api/models/{model_id}/standalone-dependencies")
def api_zimage_standalone_dependencies(model_id: str) -> dict[str, Any]:
    """Read-only Z2 dependency inventory. Never approves generation."""
    model = get_model(model_id)
    if not model or model.get("family") != "zimage" or model.get("kind") != "checkpoints" or model.get("source") != "external":
        raise HTTPException(status_code=404, detail="External Z-Image checkpoint not found.")
    components = list_models(family="zimage", kind="components", limit=2000)
    return resolve_standalone_dependencies(model["path"], components)


@app.get("/api/models/{model_id}")
def api_model_detail(model_id: str) -> dict[str, Any]:
    model = get_model(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model entry not found")
    return model


@app.get("/api/generation/capabilities")
def generation_capabilities() -> dict[str, Any]:
    return {"families": generation_manager.capabilities()}


@app.get("/api/generation/model")
def generation_model_status() -> dict[str, Any]:
    return generation_manager.model_status()


@app.post("/api/generation/model/unload")
def generation_model_unload() -> dict[str, Any]:
    try:
        return generation_manager.unload_model()
    except GenerationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/generation/jobs")
def generation_jobs(limit: int = 50) -> dict[str, Any]:
    return {"jobs": generation_manager.list(limit=limit)}


@app.post("/api/generation/jobs", status_code=202)
def create_generation_job(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        return submit_once(
            request, operation="generation-image", payload=payload,
            submit=lambda: generation_manager.submit(payload),
            lookup=generation_manager.get,
        )
    except SubmissionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (GenerationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/generation/jobs/{job_id}")
def generation_job(job_id: str) -> dict[str, Any]:
    job = generation_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Generation job not found")
    return job


@app.post("/api/generation/jobs/{job_id}/cancel")
def cancel_generation_job(job_id: str) -> dict[str, Any]:
    job = generation_manager.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Generation job not found")
    return job


@app.get("/api/generation/jobs/{job_id}/images/{filename}")
def generation_image(job_id: str, filename: str):
    if "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid image filename")
    path = generation_manager.result_path(job_id, filename)
    if path is None:
        raise HTTPException(status_code=404, detail="Generated image not found")
    return FileResponse(path, media_type="image/png", filename=filename)


@app.get("/api/console")
def get_console(after_id: int = 0, limit: int = 500) -> dict[str, Any]:
    return {"events": snapshot(after_id=after_id, limit=limit), "boot_id": BOOT_ID}


@app.get("/api/console/stream")
def stream_console(after_id: int = 0, boot_id: str | None = None):
    return StreamingResponse(
        sse_events(after_id, previous_boot_id=boot_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Backend-Boot-ID": BOOT_ID,
        },
    )


@app.get("/api/client/jobs/{kind}/{job_id}/events")
def api_client_job_events(kind: str, job_id: str, boot_id: str | None = None):
    if kind == "animation":
        def get_job():
            try:
                return animation_render_manager.get(job_id)
            except AnimationRenderError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
    elif kind == "image":
        def get_job():
            job = generation_manager.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Generation job not found")
            return job
    elif kind == "video":
        def get_job():
            try:
                return video_export_manager.get(job_id)
            except VideoExportError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
    else:
        raise HTTPException(status_code=400, detail="Unsupported job kind.")
    get_job()  # Return 404 before streaming rather than after response starts.
    return StreamingResponse(
        job_event_stream(kind, get_job, previous_boot_id=boot_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Backend-Boot-ID": BOOT_ID,
        },
    )


@app.delete("/api/console")
def delete_console() -> dict[str, str]:
    clear_console()
    return {"status": "cleared"}
