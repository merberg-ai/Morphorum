from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
PROJECTS_DIR = ROOT / "projects"
OUTPUTS_DIR = ROOT / "outputs"
LOGS_DIR = ROOT / "logs"
CACHE_DIR = ROOT / "cache"
BACKUPS_DIR = ROOT / "backups"
RUNTIME_DIR = ROOT / ".runtime"
USER_CONFIG = DATA_DIR / "config.yaml"
DEFAULT_CONFIG = ROOT / "config" / "default.yaml"
INSTALL_MANIFEST = DATA_DIR / "install.json"
MODEL_INDEX_DB = DATA_DIR / "model-index.db"

RUNTIME_DIRS = (
    DATA_DIR,
    PROJECTS_DIR,
    OUTPUTS_DIR,
    LOGS_DIR,
    CACHE_DIR,
    BACKUPS_DIR,
)


def ensure_runtime_dirs() -> None:
    for path in RUNTIME_DIRS:
        path.mkdir(parents=True, exist_ok=True)
