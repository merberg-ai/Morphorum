"""DB2.4 idempotent submissions, event recovery and durable native sessions."""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

import morphorum.app as application
from morphorum import client_events, client_protocol, client_submissions, console
from morphorum.app import app


@pytest.fixture
def journal(monkeypatch, tmp_path):
    monkeypatch.setattr(client_submissions, "JOURNAL_DIR", tmp_path / "journal")
    return tmp_path


def _request(token="test-token", key="db2-render-retry-1"):
    headers = [
        (b"authorization", ("Bearer " + token).encode()),
        (b"idempotency-key", key.encode()),
    ]
    return Request({"type": "http", "method": "POST", "path": "/api/animation/renders",
                    "headers": headers, "query_string": b"", "scheme": "http",
                    "server": ("testserver", 80)})


def test_idempotent_journal_replays_exact_job_and_fails_safe(journal):
    calls = []
    payload = {"project": {"id": "safe-project", "animation": {"max_frames": 8}}}
    def create():
        calls.append("submitted")
        return {"id": "anim-1", "status": "queued"}
    first = client_submissions.submit_once(
        _request(), operation="animation-render", payload=payload, submit=create
    )
    assert first["id"] == "anim-1"
    second = client_submissions.submit_once(
        _request(), operation="animation-render", payload=payload,
        submit=create, lookup=lambda rid: {"id": rid, "status": "completed"}
    )
    assert second["id"] == "anim-1"
    assert second["idempotency_replayed"] is True
    assert second["status"] == "completed"
    assert calls == ["submitted"]
    assert list((journal / "journal").glob("*.json"))
    contents = next((journal / "journal").glob("*.json")).read_text()
    assert "test-token" not in contents and "safe-project" not in contents
    with pytest.raises(client_submissions.SubmissionConflict, match="different"):
        client_submissions.submit_once(
            _request(), operation="animation-render",
            payload={"project": {"id": "another"}}, submit=create
        )
    assert len(calls) == 1
    other = client_submissions.submit_once(
        _request(token="other-client"), operation="animation-render",
        payload=payload, submit=create
    )
    assert other["id"] == first["id"]
    assert len(calls) == 2


def test_pending_reservation_is_never_reexecuted(journal):
    calls = []
    def uncertain():
        calls.append("unknown")
        raise RuntimeError("lost outcome after enqueue")
    with pytest.raises(RuntimeError):
        client_submissions.submit_once(
            _request(key="pending-uncertain-1"), operation="generation-image",
            payload={"model_id": "test"}, submit=uncertain
        )
    with pytest.raises(client_submissions.SubmissionPending, match="uncertain"):
        client_submissions.submit_once(
            _request(key="pending-uncertain-1"), operation="generation-image",
            payload={"model_id": "test"}, submit=uncertain
        )
    assert len(calls) == 1


def test_server_api_submission_idempotency_without_gpu(monkeypatch, journal):
    submitted = []
    def fake_submit(body):
        submitted.append(body)
        return {"id": f"img-test-{len(submitted)}", "status": "queued"}
    monkeypatch.setattr(application.generation_manager, "submit", fake_submit)
    monkeypatch.setattr(application.generation_manager, "get",
                        lambda ident: {"id": ident, "status": "generating"})
    payload = {"model_id": "fake", "prompt": "a test"}
    with TestClient(app) as client:
        h = {"Idempotency-Key": "image-request-safe-1"}
        first = client.post("/api/generation/jobs", json=payload, headers=h)
        assert first.status_code == 202
        second = client.post("/api/generation/jobs", json=payload, headers=h)
        assert second.status_code == 202
        assert first.json()["id"] == second.json()["id"]
        assert second.json()["idempotency_replayed"]
        assert len(submitted) == 1
        mismatch = client.post("/api/generation/jobs", json={**payload, "prompt": "other"},
                               headers=h)
        assert mismatch.status_code == 409
        assert mismatch.json()["error"]["code"] == "CONFLICT"
        assert len(submitted) == 1
        # No header preserves legacy browser semantics.
        assert client.post("/api/generation/jobs", json=payload).status_code == 202
        assert len(submitted) == 2


def test_job_event_stream_terminal_and_boot_reset():
    calls = []
    def getter():
        calls.append(1)
        return {"id": "anim-test", "project_id": "p", "status": "completed",
                "progress": 1, "latest_completed_frame": 2,
                "latest_frame_url": "/api/animation/renders/p/anim-test/frames/2",
                "preview_url": "/api/animation/renders/p/anim-test/preview"}
    async def collect():
        return [x async for x in client_events.job_event_stream(
            "animation", getter, previous_boot_id="a" * 32, poll_seconds=0.01
        )]
    parts = asyncio.run(collect())
    assert [x.splitlines()[1] for x in parts] == [
        "event: stream_reset", "event: job_snapshot", "event: frame_ready",
        "event: job_completed",
    ]
    assert '"boot_id":' in parts[0]
    assert '"latest_completed_frame":2' in parts[2]
    assert len(calls) == 1


def test_job_event_endpoint_has_auth_and_event_body(monkeypatch):
    monkeypatch.setattr(application.animation_render_manager, "get",
                        lambda rid: {"id": rid, "status": "completed",
                                     "progress": 1, "project_id": "p"})
    with TestClient(app) as client:
        response = client.get("/api/client/jobs/animation/an-example/events")
        assert response.status_code == 200
        assert "event: job_snapshot" in response.text
        assert "event: job_completed" in response.text
        assert response.headers["x-backend-boot-id"] == client_protocol.BOOT_ID
        assert client.get("/api/client/jobs/unsupported/id/events").status_code == 400


def test_console_reconnect_reset_and_gap():
    previous = [console.emit_console("info", "test", f"log-{i}") for i in range(10)]
    async def first_notice(after, boot):
        iterator = console.sse_events(after, previous_boot_id=boot)
        try:
            return await anext(iterator)
        finally:
            await iterator.aclose()
    reset = asyncio.run(first_notice(999999999, client_protocol.BOOT_ID))
    assert "event: console_reset" in reset
    changed_boot = asyncio.run(first_notice(1, "f" * 32))
    assert "event: console_reset" in changed_boot
    oldest = previous[0].id
    with console._lock:
        preserved = list(console._events)
        console._events.clear()
        console._events.extend(preserved[-2:])
    try:
        gap = asyncio.run(first_notice(oldest, client_protocol.BOOT_ID))
        assert "event: console_gap" in gap
    finally:
        with console._lock:
            console._events.clear()
            console._events.extend(preserved)


@pytest.fixture
def recovery_modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    from morphorum_recovery import RecoveryError, SessionFile, prepare, attach
    return RecoveryError, SessionFile, prepare, attach


def test_native_session_prepares_before_submit_and_recovers_lost_response(
    tmp_path, recovery_modules
):
    RecoveryError, SessionFile, prepare, attach = recovery_modules
    calls = []
    class FakeClient:
        base_url = "http://localhost:7866"
        def __init__(self):
            self.sends = 0
            self.boot = "b" * 32
        def handshake(self):
            return {"instance_id": "a" * 32, "boot_id": self.boot}
        def request(self, method, path, *, payload=None, headers=None):
            if method == "GET" and "/projects/" in path:
                return {"project": {"id": "camera-verified", "name": "safe"}}
            if method == "POST":
                calls.append((headers["Idempotency-Key"], payload))
                self.sends += 1
                if self.sends == 1:
                    raise RuntimeError("network response lost")
                return {"id": "anim-same", "status": "rendering"}
            if method == "GET" and "/renders/" in path:
                return {"id": "anim-same", "status": "completed"}
            raise AssertionError(path)
    cli = FakeClient()
    state = SessionFile(tmp_path / "session.json")
    prepare(cli, "camera-verified", state)
    assert state.path.is_file()
    assert state.load()["render_id"] is None
    if os.name != "nt":
        assert state.path.stat().st_mode & 0o077 == 0
    with pytest.raises(RuntimeError, match="lost"):
        attach(cli, state)
    sess, job, restarted = attach(cli, state)
    assert job["id"] == "anim-same"
    assert not restarted
    assert calls[0] == calls[1]
    assert len(calls) == 2
    cli.boot = "c" * 32
    sess, job, restarted = attach(cli, state)
    assert restarted
    assert job["status"] == "completed"
    assert len(calls) == 2  # never posts after ID is known


def test_native_session_refuses_changed_backend(tmp_path, recovery_modules):
    RecoveryError, SessionFile, prepare, attach = recovery_modules
    class Client:
        base_url = "http://localhost:7866"
        def __init__(self): self.identity = "a" * 32
        def handshake(self):
            return {"instance_id": self.identity, "boot_id": "b" * 32}
        def request(self, method, path, **unused):
            return {"project": {"id": "camera-verified"}}
    client = Client()
    sess = SessionFile(tmp_path / "state.json")
    prepare(client, "camera-verified", sess)
    client.identity = "c" * 32
    with pytest.raises(RecoveryError, match="instance changed"):
        attach(client, sess)
