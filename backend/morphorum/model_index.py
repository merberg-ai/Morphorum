from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .console import emit_console
from .paths import MODEL_INDEX_DB, ensure_runtime_dirs
from .settings import MODEL_FAMILIES, MODEL_PATH_KEYS, load_settings

CHECKPOINT_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf"}
LORA_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".pth"}
PREVIEW_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
_DB_LOCK = threading.RLock()


def _connect() -> sqlite3.Connection:
    ensure_runtime_dirs()
    connection = sqlite3.connect(MODEL_INDEX_DB, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    return connection


def init_model_index() -> None:
    with _DB_LOCK, _connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS models (
                id TEXT PRIMARY KEY,
                family TEXT NOT NULL,
                kind TEXT NOT NULL,
                name TEXT NOT NULL,
                filename TEXT NOT NULL,
                path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                extension TEXT NOT NULL,
                variant TEXT,
                preview_path TEXT,
                indexed_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_models_family_kind ON models(family, kind);
            CREATE INDEX IF NOT EXISTS idx_models_name ON models(name COLLATE NOCASE);
            """
        )

        columns = {row["name"] for row in db.execute("PRAGMA table_info(models)").fetchall()}
        if "variant" not in columns:
            db.execute("ALTER TABLE models ADD COLUMN variant TEXT")

        stale_rows = db.execute(
            "SELECT id, family, path FROM models WHERE variant IS NULL OR variant = ''"
        ).fetchall()
        for row in stale_rows:
            variant = _infer_variant(str(row["family"]), Path(str(row["path"])))
            if variant:
                db.execute("UPDATE models SET variant = ? WHERE id = ?", (variant, row["id"]))


def _model_id(family: str, kind: str, path: Path) -> str:
    normalized = os.path.normcase(os.path.abspath(str(path)))
    source = f"{family}|{kind}|{normalized}".encode("utf-8", errors="surrogatepass")
    return hashlib.blake2b(source, digest_size=12).hexdigest()


def _infer_variant(family: str, path: Path) -> str | None:
    name = path.stem.lower()
    if family == "flux":
        return "schnell" if "schnell" in name else "dev"
    if family == "sdxl":
        return "sdxl"
    if family == "zimage":
        return "zimage"
    return None


def _preview_for(path: Path) -> str | None:
    for extension in PREVIEW_EXTENSIONS:
        candidate = path.with_suffix(extension)
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return None


def _iter_files(root: Path, recursive: bool):
    try:
        iterator = root.rglob("*") if recursive else root.glob("*")
        for item in iterator:
            try:
                if item.is_file():
                    yield item
            except OSError:
                continue
    except OSError:
        return


def scan_models() -> dict[str, Any]:
    init_model_index()
    settings = load_settings()
    recursive = bool(settings.get("scan", {}).get("recursive", True))
    model_settings = settings.get("models", {})
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows: list[tuple[Any, ...]] = []
    seen_ids: set[str] = set()
    warnings: list[str] = []
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    scanned_roots = 0

    emit_console("info", "model", "Scanning configured model and LoRA directories…")

    for family in MODEL_FAMILIES:
        family_settings = model_settings.get(family, {}) if isinstance(model_settings, dict) else {}
        if not isinstance(family_settings, dict):
            continue
        for kind in MODEL_PATH_KEYS:
            extensions = CHECKPOINT_EXTENSIONS if kind == "checkpoints" else LORA_EXTENSIONS
            configured = family_settings.get(kind, []) or []
            for raw_root in configured:
                root = Path(os.path.expandvars(os.path.expanduser(str(raw_root)))).resolve(strict=False)
                if not root.exists() or not root.is_dir():
                    warning = f"Skipping unavailable {family} {kind} directory: {root}"
                    warnings.append(warning)
                    emit_console("warning", "model", warning)
                    continue
                if not os.access(root, os.R_OK):
                    warning = f"Skipping unreadable {family} {kind} directory: {root}"
                    warnings.append(warning)
                    emit_console("warning", "model", warning)
                    continue

                scanned_roots += 1
                emit_console("info", "model", f"Scanning {family} {kind}: {root}")
                for path in _iter_files(root, recursive):
                    extension = path.suffix.lower()
                    if extension not in extensions:
                        continue
                    record_id = _model_id(family, kind, path)
                    if record_id in seen_ids:
                        continue
                    try:
                        stat = path.stat()
                    except OSError:
                        continue
                    seen_ids.add(record_id)
                    rows.append(
                        (
                            record_id,
                            family,
                            kind,
                            path.stem,
                            path.name,
                            str(path),
                            int(stat.st_size),
                            int(stat.st_mtime_ns),
                            extension,
                            _infer_variant(family, path),
                            _preview_for(path),
                            now,
                        )
                    )
                    counts[family][kind] += 1

    with _DB_LOCK, _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM models")
        if rows:
            db.executemany(
                """
                INSERT INTO models (
                    id, family, kind, name, filename, path, size_bytes,
                    mtime_ns, extension, variant, preview_path, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        db.commit()

    total = len(rows)
    emit_console(
        "info",
        "model",
        f"Model scan complete: {total} file(s) indexed from {scanned_roots} configured directorie(s).",
    )
    return {
        "status": "complete",
        "total": total,
        "scanned_roots": scanned_roots,
        "warnings": warnings,
        "counts": {family: dict(kinds) for family, kinds in counts.items()},
        "indexed_at": now,
    }


def list_models(
    *,
    family: str | None = None,
    kind: str | None = None,
    search: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    init_model_index()
    clauses: list[str] = []
    params: list[Any] = []
    if family:
        clauses.append("family = ?")
        params.append(family)
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    if search:
        clauses.append("(name LIKE ? OR filename LIKE ? OR path LIKE ?)")
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern])

    sql = "SELECT * FROM models"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY family, kind, name COLLATE NOCASE LIMIT ?"
    params.append(max(1, min(int(limit), 2000)))

    with _DB_LOCK, _connect() as db:
        rows = db.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_model(model_id: str) -> dict[str, Any] | None:
    init_model_index()
    with _DB_LOCK, _connect() as db:
        row = db.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
    return dict(row) if row else None


def model_summary() -> dict[str, Any]:
    init_model_index()
    with _DB_LOCK, _connect() as db:
        rows = db.execute(
            "SELECT family, kind, COUNT(*) AS count FROM models GROUP BY family, kind"
        ).fetchall()
        total = db.execute("SELECT COUNT(*) AS count FROM models").fetchone()["count"]
    counts: dict[str, dict[str, int]] = defaultdict(dict)
    for row in rows:
        counts[row["family"]][row["kind"]] = int(row["count"])
    return {"total": int(total), "counts": {family: dict(kinds) for family, kinds in counts.items()}}
