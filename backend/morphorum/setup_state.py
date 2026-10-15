"""MS6.1 server-owned first-run setup lifecycle.

A fresh install is identified ONLY by an explicit installer prepare/ready
handshake before the installer creates the default settings and starter project.
Missing state on an older installation is treated as legacy and never auto-opens.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from .paths import DATA_DIR, PROJECTS_DIR, USER_CONFIG, INSTALL_MANIFEST, ensure_runtime_dirs

SETUP_STATE_FILE = DATA_DIR / "setup-state.json"
STEPS = ("welcome", "modes", "models", "loras", "zimage", "examples", "finish")
STATUSES = ("not_started", "in_progress", "completed", "skipped")
_PROVENANCES = ("fresh_installer", "manual_existing")
_LOCK = threading.RLock()


class SetupStateError(ValueError):
    pass


class SetupStateConflict(SetupStateError):
    pass


def _check(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise SetupStateError("Unknown setup state schema. Inspect data/setup-state.json before continuing.")
    if raw.get("provenance") not in _PROVENANCES or type(raw.get("ready")) is not bool:
        raise SetupStateError("Invalid setup state provenance/readiness.")
    if raw.get("status") not in STATUSES or raw.get("step") not in STEPS:
        raise SetupStateError("Invalid setup state status or step.")
    if type(raw.get("revision")) is not int or not 0 <= raw["revision"] < 2**31:
        raise SetupStateError("Invalid setup state revision.")
    example = raw.get("example_project_id")
    if example is not None and (not isinstance(example, str) or len(example) > 128):
        raise SetupStateError("Invalid setup state example project.")
    return raw


def _read() -> dict[str, Any] | None:
    if not SETUP_STATE_FILE.exists():
        return None
    try:
        return _check(json.loads(SETUP_STATE_FILE.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, ValueError) as exc:
        raise SetupStateError("Unreadable or invalid data/setup-state.json; existing state was preserved.") from exc


def _write(raw: dict[str, Any]) -> None:
    _check(raw)
    SETUP_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix="setup-state-", suffix=".tmp",
                                dir=str(SETUP_STATE_FILE.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(raw, handle, indent=2)
            handle.write("\n")
        os.replace(temp, SETUP_STATE_FILE)
    finally:
        Path(temp).unlink(missing_ok=True)


def _initial(provenance: str, *, ready: bool) -> dict[str, Any]:
    return dict(schema_version=1, provenance=provenance, ready=ready,
                status="not_started", step="welcome", revision=0,
                example_project_id=None)


def prepare_install() -> dict[str, Any] | None:
    """Run ONLY from installer before writing user config or seeding Default."""
    with _LOCK:
        existing = _read()
        if existing is not None:
            return existing
        # An interrupted old install is conservatively treated as legacy,
        # even if the model index is empty. No project or setting is touched.
        if USER_CONFIG.exists() or INSTALL_MANIFEST.exists() or (PROJECTS_DIR.exists() and
                                     any(PROJECTS_DIR.iterdir())):
            return None
        ensure_runtime_dirs()
        state = _initial("fresh_installer", ready=False)
        _write(state)
        return state


def mark_install_ready() -> dict[str, Any] | None:
    """Complete only a prepared fresh-install handshake, after installer checks."""
    with _LOCK:
        state = _read()
        if state is None or state["provenance"] != "fresh_installer" or state["ready"]:
            return state
        state = {**state, "ready": True, "revision": state["revision"] + 1}
        _write(state)
        return state


def setup_status(*, forced: bool = False, backend_only: bool = False) -> dict[str, Any]:
    """A pure read: never generates a state file, project, download or scan."""
    with _LOCK:
        try:
            state = _read()
        except SetupStateError as exc:
            return dict(schema_version=1, eligible=False, show_wizard=False,
                        forced_for_launch=False, status="error", step="welcome",
                        revision=None, mode="backend-only" if backend_only else "webui",
                        warning=str(exc))
        status = state["status"] if state else "legacy"
        ready = bool(state and state["ready"])
        auto = bool(ready and state["provenance"] == "fresh_installer" and
                    status in {"not_started", "in_progress"})
        force = bool(forced and not backend_only)
        return dict(schema_version=1, eligible=auto, show_wizard=not backend_only and
                    (auto or force), forced_for_launch=force,
                    status=status, step=state["step"] if state else "welcome",
                    revision=state["revision"] if state else 0,
                    mode="backend-only" if backend_only else "webui",
                    ready=ready, provenance=state["provenance"] if state else "legacy")


def update_setup(*, action: str, step: str | None, revision: int,
                 forced: bool = False) -> dict[str, Any]:
    """Explicit user action, optimistic revision; no model/project side effects."""
    if action not in {"advance", "skip"}:
        raise SetupStateError("MS6.1 allows only advance and skip; completion arrives in MS6.4.")
    if type(revision) is not int:
        raise SetupStateError("Setup revision must be an integer.")
    if action == "advance" and step not in STEPS:
        raise SetupStateError("Unknown setup step.")
    with _LOCK:
        state = _read()
        if state is None:
            if not forced:
                raise SetupStateError("Existing install needs explicit wizard launch.")
            state = _initial("manual_existing", ready=True)
        if not state["ready"] and state["provenance"] == "fresh_installer":
            raise SetupStateError("Install is incomplete; finish or repair Morphorum first.")
        if state["revision"] != revision:
            raise SetupStateConflict("Setup changed in another tab. Refresh before continuing.")
        if state["status"] in {"completed", "skipped"} and not forced:
            raise SetupStateError("Setup already ended. Relaunch the setup wizard explicitly.")
        if action == "skip":
            state = {**state, "status": "skipped"}
        else:
            state = {**state, "status": "in_progress", "step": step}
        state["revision"] += 1
        _write(state)
        return state
