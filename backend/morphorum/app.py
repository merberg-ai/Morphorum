from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from . import __version__
from .paths import ROOT, ensure_runtime_dirs
from .system_info import doctor_report, install_manifest


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_runtime_dirs()
    yield


app = FastAPI(
    title="Morphorum",
    version=__version__,
    description="Morphorum local AI image and animation studio.",
    lifespan=lifespan,
)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root() -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Morphorum</title>
  <style>
    :root {{ color-scheme: dark; }}
    body {{ margin:0; min-height:100vh; display:grid; place-items:center;
      font-family:system-ui,sans-serif; background:#0d0f13; color:#edf3f7; }}
    main {{ width:min(680px,calc(100% - 32px)); padding:28px; border-radius:18px;
      background:rgba(24,27,34,.72); border:1px solid rgba(255,255,255,.08);
      box-shadow:0 18px 60px rgba(0,0,0,.35); backdrop-filter:blur(14px); }}
    h1 {{ margin-top:0; }}
    code {{ color:#41d9ff; }}
    .ok {{ color:#72e6a7; }}
  </style>
</head>
<body><main>
  <h1>Morphorum</h1>
  <p class="ok">Runtime foundation is installed and the API is alive.</p>
  <p>Version <code>{__version__}</code></p>
  <p>The full UI is the next milestone. Health endpoint: <code>/api/health</code></p>
</main></body>
</html>"""


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": "Morphorum",
        "version": __version__,
        "root": str(ROOT),
    }


@app.get("/api/system")
def system() -> dict:
    return doctor_report()


@app.get("/api/install")
def installed() -> dict:
    return install_manifest()
