"""About / current-branch updater guards. No network or OS installer is executed."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from morphorum import git_updates
from morphorum.app import app


def test_update_check_fetches_only_current_branch(monkeypatch):
    calls = []
    monkeypatch.setattr(git_updates, "_identity", lambda: {
        "branch": "dev-webui", "head": "a" * 40, "dirty": False,
    })
    def git(*args, **kwargs):
        calls.append(args)
        if args[0] == "rev-parse":
            return "b" * 40
        if args[0] == "rev-list":
            return "0\t3"
        return ""
    monkeypatch.setattr(git_updates, "_git", git)
    checked = git_updates.GitUpdateManager().check()
    assert checked["branch"] == "dev-webui"
    assert checked["behind"] == 3 and checked["can_apply"]
    assert ("fetch", "--no-tags", "origin",
            "refs/heads/dev-webui:refs/remotes/origin/dev-webui") in calls
    assert not any("switch" in args or "checkout" in args for args in calls)


def test_update_refuses_dirty_or_busy_worktree(monkeypatch):
    update = git_updates.GitUpdateManager()
    update._checked = {
        "branch": "dev-webui", "head": "a" * 40, "remote_head": "b" * 40,
        "can_apply": True,
    }
    monkeypatch.setattr(git_updates, "_identity", lambda: {
        "branch": "dev-webui", "head": "a" * 40, "dirty": True,
    })
    with pytest.raises(git_updates.GitUpdateError, match="changed"):
        update.start(expected_branch="dev-webui", expected_head="a"*40,
                     expected_remote_head="b"*40, work_is_busy=lambda: False)
    with pytest.raises(git_updates.GitUpdateError, match="generation or animation"):
        update.start(expected_branch="dev-webui", expected_head="a"*40,
                     expected_remote_head="b"*40, work_is_busy=lambda: True)


def test_remote_browser_cannot_apply_updates():
    with patch("morphorum.app.git_update_manager.start") as start:
        with TestClient(app) as client:
            response = client.post("/api/about/update", json={},
                                   headers={"Origin": "http://testserver"})
        assert response.status_code == 403
        start.assert_not_called()


def test_cross_origin_browser_cannot_check_updates():
    with patch("morphorum.app.git_update_manager.check") as check:
        with TestClient(app) as client:
            response = client.post("/api/about/check", json={},
                                   headers={"Origin": "https://unrelated.example"})
        assert response.status_code == 403
        check.assert_not_called()
