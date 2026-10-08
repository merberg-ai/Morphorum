from __future__ import annotations

import hashlib
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
from .animation_motion import (
    MotionPreviewError,
    motion_preview_manager,
    save_source_image,
)
from .animation_render import (
    AnimationRenderError,
    animation_render_manager,
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
        saved = save_animation_project(project_id, project)
        emit_console("info", "animation", f"Cleared source image for animation project {project_id}.")
        return {"status": "cleared", "project": saved}
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
        return motion_preview_manager.start(project=normalized, source_path=source_path)
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
    except (AnimationProjectError, ScheduleError, TypeError, ValueError) as exc:
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
