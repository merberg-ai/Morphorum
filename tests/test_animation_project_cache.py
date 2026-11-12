"""Loaded projects are cached while the file is unchanged, and never go stale."""
from __future__ import annotations

import json
import os

import pytest

from morphorum import animation_projects as ap


@pytest.fixture()
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(ap, "_LOADED_PROJECTS", {})
    created = ap.create_animation_project({"name": "Cache test"})
    return created["id"]


def _count_normalizations(monkeypatch) -> list[int]:
    calls: list[int] = []
    original = ap.normalize_animation_project

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(ap, "normalize_animation_project", counted)
    return calls


def test_repeat_loads_reuse_the_normalized_project(project, monkeypatch):
    calls = _count_normalizations(monkeypatch)
    first = ap.load_animation_project(project)
    second = ap.load_animation_project(project)
    third = ap.load_animation_project(project)
    assert len(calls) == 1
    assert first == second == third
    # Each caller gets its own object and may mutate it freely.
    assert second is not third
    second["name"] = "mutated by a caller"
    second["animation"]["max_frames"] = 7
    assert ap.load_animation_project(project) == first
    # The project list loads every project and benefits from the same cache.
    assert [item["id"] for item in ap.list_animation_projects()] == [project]
    assert len(calls) == 1


def test_saving_is_visible_on_the_next_load(project, monkeypatch):
    before = ap.load_animation_project(project)
    saved = ap.save_animation_project(project, {**before, "name": "Renamed"})
    assert saved["name"] == "Renamed"
    calls = _count_normalizations(monkeypatch)
    assert ap.load_animation_project(project)["name"] == "Renamed"
    assert ap.load_animation_project(project)["name"] == "Renamed"
    assert len(calls) == 1


def test_an_outside_edit_to_the_file_is_picked_up(project):
    path = ap._project_file(project)
    assert ap.load_animation_project(project)["name"] == "Cache test"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["name"] = "Edited outside the app"
    path.write_text(json.dumps(payload), encoding="utf-8")
    # Guarantee a different timestamp even on coarse-resolution filesystems.
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    assert ap.load_animation_project(project)["name"] == "Edited outside the app"


def test_errors_and_missing_projects_are_not_cached(project):
    path = ap._project_file(project)
    ap.load_animation_project(project)
    path.write_text("{ not json", encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    with pytest.raises(ap.AnimationProjectError):
        ap.load_animation_project(project)
    path.unlink()
    with pytest.raises(ap.AnimationProjectError, match="not found"):
        ap.load_animation_project(project)


def test_cache_is_bounded(project, monkeypatch):
    monkeypatch.setattr(ap, "_LOADED_PROJECTS_MAX", 2)
    ids = [project] + [ap.create_animation_project({"name": f"Extra {n}"})["id"] for n in range(3)]
    for project_id in ids:
        ap.load_animation_project(project_id)
    assert len(ap._LOADED_PROJECTS) == 2
    assert all(ap.load_animation_project(project_id)["id"] == project_id for project_id in ids)
