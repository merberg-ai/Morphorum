from __future__ import annotations

import hashlib
import math
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .animation_projects import (
    AnimationProjectError,
    animation_project_directory,
    animation_project_path,
    create_animation_project,
    list_animation_projects,
    load_animation_project,
    normalize_animation_project,
    save_animation_project,
)
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
from .animation_video import (
    VideoExportError,
    video_export_manager,
)
from .schedules import ScheduleError
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
from .managed_models import ManagedModelError, managed_model_manager
from .model_index import get_model, list_models, model_summary, scan_models
from .paths import ROOT, ensure_runtime_dirs
from .settings import load_settings, model_family_definitions, save_settings, validate_model_paths, validate_path
from .system_info import doctor_report, git_branch, git_commit, install_manifest, live_telemetry

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


FRONTEND_ASSET_VERSION = _frontend_asset_version()


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
)

if ASSET_DIR.exists():
    app.mount("/assets", StaticFiles(directory=ASSET_DIR), name="assets")


@app.middleware("http")
async def api_console_middleware(request: Request, call_next):
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


@app.get("/", include_in_schema=False)
def root():
    if FRONTEND_INDEX.exists():
        html = FRONTEND_INDEX.read_text(encoding="utf-8")
        html = html.replace("__MORPHORUM_ASSET_VERSION__", FRONTEND_ASSET_VERSION)
        return HTMLResponse(html)
    return HTMLResponse(
        "<h1>Morphorum</h1><p>Frontend assets are missing. Run the Morphorum repair command.</p>",
        status_code=503,
    )


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": "Morphorum",
        "version": __version__,
        "git_branch": git_branch(),
        "git_commit": git_commit(),
        "frontend_asset_version": FRONTEND_ASSET_VERSION,
        "root": str(ROOT),
    }


@app.get("/api/system")
def system() -> dict:
    return doctor_report()


@app.get("/api/system/telemetry")
def system_telemetry() -> dict:
    return live_telemetry()


@app.get("/api/system/gpu-memory")
def system_gpu_memory() -> dict[str, Any]:
    """Read Morphorum's own CUDA allocator state without changing it."""
    return generation_manager.memory_profile()


@app.get("/api/install")
def installed() -> dict:
    return install_manifest()


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    settings = load_settings()
    return {
        "settings": settings,
        "validation": validate_model_paths(settings),
        "model_families": model_family_definitions(),
    }


@app.get("/api/animation/projects")
def api_animation_projects() -> dict[str, Any]:
    return {"projects": list_animation_projects()}


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
def api_animation_project(project_id: str) -> dict[str, Any]:
    try:
        project = load_animation_project(project_id)
        return {
            "project": project,
            "path": animation_project_path(project_id),
        }
    except AnimationProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/api/animation/projects/{project_id}")
def api_save_animation_project(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        project = save_animation_project(project_id, payload)
        return {
            "status": "saved",
            "project": project,
            "path": animation_project_path(project_id),
        }
    except AnimationProjectError as exc:
        message = str(exc)
        status = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status, detail=message) from exc


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


@app.post("/api/animation/projects/{project_id}/source-image", status_code=201)
async def api_upload_animation_source_image(project_id: str, request: Request) -> dict[str, Any]:
    try:
        project = load_animation_project(project_id)
        data = await request.body()
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
        }
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
        return motion_preview_manager.start(
            project=normalized,
            source_path=source_path,
            highlight_holes=bool(options.get("highlight_holes", False)),
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


@app.post("/api/animation/renders", status_code=202)
def api_start_animation_render(payload: dict[str, Any]) -> dict[str, Any]:
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
        return animation_render_manager.submit(
            project=normalized,
            source_path=source_path,
        )
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
    project_id: str, render_id: str, payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        return video_export_manager.start(
            project_id, render_id,
            format=str(payload.get("format") or "mp4"),
            quality=str(payload.get("quality") or "balanced"),
            fps=payload.get("fps"),
        )
    except VideoExportError as exc:
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
        return FileResponse(
            path,
            media_type="video/mp4" if format == "mp4" else "video/webm",
            filename=path.name,
            content_disposition_type="inline" if inline else "attachment",
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
    settings = save_settings(payload)
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
def create_generation_job(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return generation_manager.submit(payload)
    except GenerationError as exc:
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
    return {"events": snapshot(after_id=after_id, limit=limit)}


@app.get("/api/console/stream")
def stream_console(after_id: int = 0):
    return StreamingResponse(
        sse_events(after_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.delete("/api/console")
def delete_console() -> dict[str, str]:
    clear_console()
    return {"status": "cleared"}
