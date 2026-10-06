from __future__ import annotations

import fnmatch
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .console import emit_console
from .model_index import remove_managed_model, upsert_managed_model
from .settings import managed_model_location

_IGNORE_PATTERNS = [
    "README.md",
    ".gitattributes",
    "assets/*",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.webp",
    "*.pdf",
]

MANAGED_MODEL_CATALOG: dict[str, dict[str, Any]] = {
    "zimage-turbo": {
        "id": "zimage-turbo",
        "index_id": "managed:zimage-turbo",
        "family": "zimage",
        "variant": "turbo",
        "name": "Z-Image-Turbo",
        "repo_id": "Tongyi-MAI/Z-Image-Turbo",
        "directory_name": "Z-Image-Turbo",
        "license": "Apache-2.0",
        "description": "Official distilled Z-Image model for fast text-to-image generation.",
        "advertised_size_bytes": 32_900_000_000,
        "recommended_steps": 8,
        "recommended_guidance": 0.0,
    },
}


@dataclass
class DownloadState:
    model_id: str
    status: str = "not_installed"
    expected_bytes: int = 0
    downloaded_bytes: int = 0
    error: str | None = None
    thread: threading.Thread | None = field(default=None, repr=False)


class ManagedModelError(RuntimeError):
    pass


class ManagedModelManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._states: dict[str, DownloadState] = {}

    @staticmethod
    def _entry(model_id: str) -> dict[str, Any]:
        entry = MANAGED_MODEL_CATALOG.get(model_id)
        if entry is None:
            raise ManagedModelError(f"Unknown managed model: {model_id}")
        return entry

    @staticmethod
    def _destination(entry: dict[str, Any]) -> Path:
        return managed_model_location(str(entry["family"])) / str(entry["directory_name"])

    @staticmethod
    def _is_ignored(relative: str) -> bool:
        normalized = relative.replace("\\", "/")
        return any(fnmatch.fnmatch(normalized, pattern) for pattern in _IGNORE_PATTERNS)

    @classmethod
    def _installed(cls, destination: Path) -> bool:
        required = (
            destination / "model_index.json",
            destination / "scheduler",
            destination / "text_encoder",
            destination / "tokenizer",
            destination / "transformer",
            destination / "vae",
        )
        return all(path.exists() for path in required)

    @classmethod
    def _materialized_size(cls, destination: Path) -> int:
        if not destination.exists():
            return 0
        total = 0
        try:
            for path in destination.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    relative = path.relative_to(destination).as_posix()
                except ValueError:
                    relative = path.name
                if relative.startswith(".cache/"):
                    if path.suffix == ".incomplete":
                        try:
                            total += int(path.stat().st_size)
                        except OSError:
                            pass
                    continue
                if cls._is_ignored(relative):
                    continue
                try:
                    total += int(path.stat().st_size)
                except OSError:
                    pass
        except OSError:
            pass
        return total

    def _sync_index(self, entry: dict[str, Any], destination: Path) -> None:
        index_id = str(entry["index_id"])
        if self._installed(destination):
            upsert_managed_model(
                model_id=index_id,
                family=str(entry["family"]),
                name=str(entry["name"]),
                path=destination,
                variant=str(entry["variant"]),
                size_bytes=self._materialized_size(destination),
            )
        else:
            remove_managed_model(index_id)

    def status(self, model_id: str) -> dict[str, Any]:
        entry = self._entry(model_id)
        destination = self._destination(entry)

        with self._lock:
            state = self._states.setdefault(model_id, DownloadState(model_id=model_id))
            thread_alive = bool(state.thread and state.thread.is_alive())
            installed = self._installed(destination)

            if installed and not thread_alive:
                state.status = "installed"
                state.error = None
            elif not installed and not thread_alive and state.status not in {"failed", "checking"}:
                state.status = "not_installed"

            state.downloaded_bytes = self._materialized_size(destination)
            expected = state.expected_bytes or int(entry["advertised_size_bytes"])
            progress = (
                min(100.0, (state.downloaded_bytes / expected) * 100.0)
                if expected > 0
                else 0.0
            )

            payload = {
                **entry,
                "destination": str(destination),
                "status": state.status,
                "installed": installed,
                "expected_bytes": expected,
                "downloaded_bytes": state.downloaded_bytes,
                "progress_percent": progress,
                "error": state.error,
            }

        if installed:
            self._sync_index(entry, destination)
        return payload

    def catalog(self) -> list[dict[str, Any]]:
        return [self.status(model_id) for model_id in MANAGED_MODEL_CATALOG]

    def start_download(self, model_id: str) -> dict[str, Any]:
        entry = self._entry(model_id)
        destination = self._destination(entry)

        with self._lock:
            state = self._states.setdefault(model_id, DownloadState(model_id=model_id))
            if state.thread and state.thread.is_alive():
                return self.status(model_id)
            if self._installed(destination):
                state.status = "installed"
                state.error = None
                self._sync_index(entry, destination)
                return self.status(model_id)

            state.status = "checking"
            state.error = None
            state.expected_bytes = 0
            state.downloaded_bytes = self._materialized_size(destination)
            thread = threading.Thread(
                target=self._download_worker,
                args=(model_id,),
                name=f"managed-model-{model_id}",
                daemon=True,
            )
            state.thread = thread
            thread.start()

        return self.status(model_id)

    def _download_worker(self, model_id: str) -> None:
        entry = self._entry(model_id)
        destination = self._destination(entry)
        destination.mkdir(parents=True, exist_ok=True)

        emit_console(
            "info",
            "model",
            f"Preparing managed model download: {entry['name']} -> {destination}",
        )

        try:
            from huggingface_hub import snapshot_download

            dry_run = snapshot_download(
                repo_id=str(entry["repo_id"]),
                local_dir=destination,
                ignore_patterns=_IGNORE_PATTERNS,
                dry_run=True,
            )
            expected = sum(
                int(item.file_size or 0)
                for item in dry_run
                if not self._is_ignored(str(item.filename))
            )
            if expected <= 0:
                expected = int(entry["advertised_size_bytes"])

            free = shutil.disk_usage(destination).free
            current = self._materialized_size(destination)
            remaining = max(0, expected - current)
            reserve = 2 * 1024**3
            if free < remaining + reserve:
                raise ManagedModelError(
                    "Not enough free disk space for this model. "
                    f"Need about {(remaining + reserve) / 1024**3:.1f} GiB including safety reserve, "
                    f"but only {free / 1024**3:.1f} GiB is free."
                )

            with self._lock:
                state = self._states[model_id]
                state.expected_bytes = expected
                state.status = "downloading"

            emit_console(
                "info",
                "model",
                f"Downloading {entry['name']} from {entry['repo_id']} "
                f"({expected / 1024**3:.1f} GiB runtime snapshot).",
            )

            snapshot_download(
                repo_id=str(entry["repo_id"]),
                local_dir=destination,
                ignore_patterns=_IGNORE_PATTERNS,
                max_workers=8,
            )

            if not self._installed(destination):
                raise ManagedModelError(
                    "Download completed but the managed model package is incomplete. "
                    "Use Download again to resume/repair it."
                )

            self._sync_index(entry, destination)
            with self._lock:
                state = self._states[model_id]
                state.downloaded_bytes = self._materialized_size(destination)
                state.status = "installed"
                state.error = None

            emit_console(
                "info",
                "model",
                f"Managed model ready: {entry['name']} at {destination}",
            )
        except Exception as exc:
            with self._lock:
                state = self._states[model_id]
                state.downloaded_bytes = self._materialized_size(destination)
                state.status = "failed"
                state.error = str(exc)
            emit_console(
                "error",
                "model",
                f"Managed model download failed for {entry['name']}: {exc}",
            )


managed_model_manager = ManagedModelManager()
