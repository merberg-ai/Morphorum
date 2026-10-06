from __future__ import annotations

import hashlib
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
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
from .system_info import doctor_report, install_manifest, live_telemetry

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
