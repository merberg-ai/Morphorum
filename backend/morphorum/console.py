from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from itertools import count
from typing import Iterator

_MAX_EVENTS = 1500
_events: deque["ConsoleEvent"] = deque(maxlen=_MAX_EVENTS)
_lock = threading.RLock()
_ids = count(1)
_handler_installed = False


@dataclass(frozen=True)
class ConsoleEvent:
    id: int
    timestamp: str
    level: str
    category: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def emit_console(level: str, category: str, message: str) -> ConsoleEvent:
    event = ConsoleEvent(
        id=next(_ids),
        timestamp=_now(),
        level=(level or "info").lower(),
        category=(category or "runtime").lower(),
        message=str(message).rstrip(),
    )
    with _lock:
        _events.append(event)
    return event


def snapshot(after_id: int = 0, limit: int = 500, *, from_start: bool = False) -> list[dict]:
    limit = max(1, min(int(limit), _MAX_EVENTS))
    with _lock:
        selected = [event for event in _events if event.id > after_id]
    return [event.to_dict() for event in (selected[:limit] if from_start else selected[-limit:])]


def console_bounds() -> tuple[int, int]:
    with _lock:
        if not _events:
            return 0, 0
        return _events[0].id, _events[-1].id


def clear_console() -> None:
    with _lock:
        _events.clear()
    emit_console("info", "runtime", "Console display buffer cleared.")


def _category_for_logger(name: str) -> str:
    lowered = (name or "").lower()
    if lowered.startswith("uvicorn.access"):
        return "api"
    if lowered.startswith("uvicorn"):
        return "server"
    if lowered.startswith("morphorum.model"):
        return "model"
    if lowered.startswith("morphorum.generation"):
        return "generation"
    if lowered.startswith("morphorum"):
        return "runtime"
    return "system"


class ConsoleLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            # Morphorum API middleware creates cleaner API entries, so suppress
            # Uvicorn's duplicate access-log line.
            if record.name.startswith("uvicorn.access"):
                return
            emit_console(
                record.levelname.lower(),
                _category_for_logger(record.name),
                self.format(record),
            )
        except Exception:
            self.handleError(record)


def install_logging_handler() -> None:
    global _handler_installed
    if _handler_installed:
        return
    handler = ConsoleLogHandler()
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(handler)
    _handler_installed = True
    emit_console("info", "runtime", "Morphorum console event stream initialized.")


async def sse_events(after_id: int = 0, *, previous_boot_id: str | None = None) -> Iterator[str]:
    from .client_protocol import BOOT_ID

    cursor = max(0, int(after_id))
    last_heartbeat = time.monotonic()
    first, newest = console_bounds()
    if (previous_boot_id and previous_boot_id != BOOT_ID) or cursor > newest:
        yield ("event: console_reset\n"
               "data: " + json.dumps({"boot_id": BOOT_ID, "reason": "backend_restarted",
                                        "action": "reload_console_cursor"}) + "\n\n")
        cursor = 0
    elif cursor and first and cursor < first - 1:
        yield ("event: console_gap\n"
               "data: " + json.dumps({"boot_id": BOOT_ID, "first_available": first,
                                        "after_id": cursor}) + "\n\n")
        cursor = first - 1

    while True:
        first, _ = console_bounds()
        if cursor and first and cursor < first - 1:
            yield ("event: console_gap\n"
                   "data: " + json.dumps({"boot_id": BOOT_ID, "first_available": first,
                                            "after_id": cursor}) + "\n\n")
            cursor = first - 1
        batch = snapshot(cursor, limit=250, from_start=True)
        if batch:
            for event in batch:
                cursor = max(cursor, int(event["id"]))
                yield f"id: {event['id']}\nevent: console\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        elif time.monotonic() - last_heartbeat >= 15:
            yield ": heartbeat\n\n"
            last_heartbeat = time.monotonic()
        await asyncio.sleep(0.35)
