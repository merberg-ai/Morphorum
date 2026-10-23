"""PS1.4 project-owned Prompt Studio draft API and portability acceptance tests."""
from __future__ import annotations

import io
import json
import zipfile
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

import morphorum.animation_projects as projects
import morphorum.prompt_studio_drafts as studio
from morphorum.app import app
from morphorum.project_archive import export_project_archive, import_project_archive, save_project_as


def payload(pid: str) -> dict:
    return {
        "format": "morphorum.prompt-studio-draft", "schema_version": 1,
        "project_id": pid, "name": "Storyboard A",
        "project_context": {
            "model": {"model_id": "synthetic-checkpoint", "family": "sdxl", "variant": ""},
            "fps": 24.0, "max_frames": 120, "start_mode": "prompt", "source_image_name": "",
        },
        "original_tracks": {
            "positive": {"kind": "prompt", "interpolation": "blend",
                         "keyframes": [{"frame": 0, "value": "<lora:Demo:1> exact"},
                                       {"frame": 80, "value": "forest"}]},
            "negative": {"kind": "prompt", "interpolation": "hold",
                         "keyframes": [{"frame": 0, "value": "blurry"},
                                       {"frame": 32, "value": "fuzzy"}]},
        },
        "prompt_tracks": {
            "positive": {"kind": "prompt", "interpolation": "blend",
                         "keyframes": [{"frame": 0, "value": "<lora:Demo:1>  exact"},
                                       {"frame": 80, "value": "night forest"}]},
            "negative": {"kind": "prompt", "interpolation": "hold",
                         "keyframes": [{"frame": 0, "value": "blurry"},
                                       {"frame": 32, "value": "fuzzy"}]},
        },
    }


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    with TestClient(app) as client:
        new = client.post("/api/animation/projects", json={"name": "Persistent Drafts"})
        assert new.status_code == 201, new.text
        pid = new.json()["project"]["id"]
        yield client, pid, tmp_path


def test_draft_api_crud_preserves_project_etag_and_exact_prompt_bytes(project):
    client, pid, _ = project
    base = f"/api/animation/projects/{pid}"
    before = client.get(base).headers["etag"]
    p = payload(pid)
    created = client.post(base + "/prompt-studio/drafts", json=p)
    assert created.status_code == 201, created.text
    record = created.json()["draft"]
    etag = created.headers["etag"]
    assert record["prompt_tracks"]["positive"]["keyframes"][0]["value"] == "<lora:Demo:1>  exact"
    assert len(record["draft_id"]) == 32
    assert client.get(base).headers["etag"] == before
    api = base + "/prompt-studio/drafts/" + record["draft_id"]
    got = client.get(api)
    assert got.status_code == 200 and got.headers["etag"] == etag
    listed = client.get(base + "/prompt-studio/drafts").json()["drafts"]
    assert len(listed) == 1 and listed[0]["etag"] == etag
    changed = deepcopy(p)
    changed["name"] = "Renamed draft"
    changed["prompt_tracks"]["negative"]["interpolation"] = "blend"
    assert client.put(api, json=changed).status_code == 428
    saved = client.put(api, json=changed, headers={"If-Match": etag})
    assert saved.status_code == 200, saved.text
    updated_etag = saved.headers["etag"]
    assert updated_etag != etag
    assert saved.json()["draft"]["created_at"] == record["created_at"]
    assert client.put(api, json=p, headers={"If-Match": etag}).status_code == 412
    assert client.delete(api, headers={"If-Match": etag}).status_code == 412
    assert client.delete(api).status_code == 428
    assert client.get(api).json()["draft"]["name"] == "Renamed draft"
    assert client.delete(api, headers={"If-Match": updated_etag}).status_code == 200
    assert client.get(api).status_code == 404
    assert client.get(base).headers["etag"] == before


def test_invalid_schema_baseline_lanes_and_unsafe_id_rejected(project):
    client, pid, _ = project
    base = f"/api/animation/projects/{pid}/prompt-studio/drafts"
    for change in (
        lambda x: x.update(schema_version=2),
        lambda x: x.update(project_id="someone-else"),
        lambda x: x["prompt_tracks"]["negative"]["keyframes"][0].update(frame=1),
        lambda x: x["prompt_tracks"]["positive"]["keyframes"][1].update(frame=0),
        lambda x: x["original_tracks"]["positive"]["keyframes"][0].update(value=123),
        lambda x: x["project_context"].update(max_frames=5),
    ):
        bad = payload(pid)
        change(bad)
        assert client.post(base, json=bad).status_code == 400
    assert client.get(base + "/../../etc/passwd").status_code != 200


def test_draft_limit_enforced_without_affecting_project(project, monkeypatch):
    client, pid, _ = project
    monkeypatch.setattr(studio, "MAX_DRAFTS", 2)
    url = f"/api/animation/projects/{pid}/prompt-studio/drafts"
    assert client.post(url, json=payload(pid)).status_code == 201
    assert client.post(url, json=payload(pid)).status_code == 201
    third = client.post(url, json=payload(pid))
    assert third.status_code == 400 and "limit" in third.text.lower()


def test_archive_and_save_as_copy_portable_drafts_with_rewritten_owner(project):
    client, pid, tmp = project
    url = f"/api/animation/projects/{pid}/prompt-studio/drafts"
    created = client.post(url, json=payload(pid))
    assert created.status_code == 201, created.text
    draft_id = created.json()["draft"]["draft_id"]
    path = f"prompt_studio/drafts/{draft_id}.json"
    archive_bytes = export_project_archive(pid)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        assert path in archive.namelist()
        copied = json.loads(archive.read(path))
        assert copied["project_id"] == pid
        assert "generated_output.mp4" not in archive.namelist()
    clone = save_project_as(pid, "Copy with Draft")
    clone_record, _ = studio.read_draft(clone["id"], draft_id)
    assert clone_record["project_id"] == clone["id"]
    assert clone_record["prompt_tracks"] == copied["prompt_tracks"]
    # Verified export contains draft files, and import into a clean data root retains them.
    projects.PROJECTS_DIR = tmp / "imported" / "projects"
    imported = import_project_archive(archive_bytes)
    assert imported["project"]["id"] == pid
    imported_record, _ = studio.read_draft(pid, draft_id)
    assert imported_record["prompt_tracks"] == copied["prompt_tracks"]


def test_archive_rejects_tampered_draft_and_unsupported_version(project):
    client, pid, _ = project
    assert client.post(f"/api/animation/projects/{pid}/prompt-studio/drafts",
                       json=payload(pid)).status_code == 201
    raw = export_project_archive(pid)
    with zipfile.ZipFile(io.BytesIO(raw)) as original:
        names = original.namelist()
        paths = [n for n in names if n.startswith("prompt_studio/drafts/")]
        assert len(paths) == 1
        changed = io.BytesIO()
        with zipfile.ZipFile(changed, "w") as tampered:
            for name in names:
                value = original.read(name)
                if name == paths[0]:
                    doc = json.loads(value)
                    doc["schema_version"] = 999
                    value = json.dumps(doc).encode()
                tampered.writestr(name, value)
    from morphorum.project_archive import ProjectArchiveError, inspect_project_archive
    with pytest.raises(ProjectArchiveError):
        inspect_project_archive(changed.getvalue())


def test_ps3_saved_composer_roundtrip_and_legacy_defaults(project):
    client, pid, _ = project
    record=payload(pid)
    record["composer"]={"schema_version":1,"blocks":[
      {"id":"block1","scope":"global","frame":None,"lane":"positive",
       "kind":"text","placement":"before","enabled":True,
       "label":"Continuity","text":"  preserve exact typography  "},
      {"id":"lora1","scope":"frame","frame":0,"lane":"positive",
       "kind":"lora","placement":"after","enabled":True,
       "label":"Style","model_id":"synthetic-id","name":"Horror Style ZIT",
       "family":"sdxl","weight":1.0,"triggers":["h0rr0rstyl3"]}
    ]}
    response=client.post(f"/api/animation/projects/{pid}/prompt-studio/drafts",json=record)
    assert response.status_code==201,response.text
    saved=response.json()["draft"]
    assert saved["composer"]["blocks"][0]["text"]=="  preserve exact typography  "
    loaded=studio.read_draft(pid,saved["draft_id"])[0]
    assert loaded["composer"]==saved["composer"]
    legacy=payload(pid)
    assert studio.validate_draft(legacy,pid)["composer"]=={"schema_version":1,"blocks":[]}


def test_ps3_invalid_composer_is_rejected_before_disk_write(project):
    client,pid,_=project
    url=f"/api/animation/projects/{pid}/prompt-studio/drafts"
    good={"schema_version":1,"blocks":[
      {"id":"block1","scope":"frame","frame":40,"lane":"positive",
       "kind":"text","placement":"after","enabled":True,
       "label":"Scene action","text":"night"}]}
    import copy
    def assert_bad(composer):
        record=payload(pid);record["composer"]=composer
        res=client.post(url,json=record)
        assert res.status_code==400,res.text
    for c in [
      {"schema_version":2,"blocks":[]},
      {"schema_version":1,"blocks":[good["blocks"][0]]*2},
      {"schema_version":1,"blocks":[dict(good["blocks"][0],frame=120)]},
      {"schema_version":1,"blocks":[dict(good["blocks"][0],enabled="true")]},
      {"schema_version":1,"blocks":[dict(good["blocks"][0],lane="invalid")]},
      {"schema_version":1,"blocks":[dict(good["blocks"][0],text="x"*32769)]},
    ]:assert_bad(c)
    lora=dict(good["blocks"][0],kind="lora",model_id="indexed",name="test",
        family="zimage",weight=1,triggers=["test"])
    assert_bad({"schema_version":1,"blocks":[dict(lora,lane="negative")]})
    assert client.get(url).json()["drafts"]==[]



def test_ps62_audio_alignment_provenance_round_trip_is_optional_and_checked(project):
    client, pid, _ = project
    path = f"/api/animation/projects/{pid}/prompt-studio/drafts"
    item = payload(pid)
    item["audio_alignment"] = {
        "schema_version": 1,
        "source_sha256": "a" * 64,
        "stamp": "b" * 64,
        "fps": 24.0,
        "max_frames": 120,
        "marker_mode": "saved-edits",
        "selected_event_ids": ["kick-1", "snare-1"],
        "moves": [{"from": 80, "to": 86, "beat_id": "kick-1"}],
        "staged_at": "2026-10-23T14:00:00.000Z",
    }
    saved = client.post(path, json=item)
    assert saved.status_code == 201, saved.text
    assert saved.json()["draft"]["audio_alignment"] == item["audio_alignment"]
    malformed = payload(pid)
    malformed["audio_alignment"] = {**item["audio_alignment"], "stamp": "evil"}
    assert client.post(path, json=malformed).status_code == 400
    malformed = payload(pid)
    malformed["audio_alignment"] = {**item["audio_alignment"], "fps": 30}
    assert client.post(path, json=malformed).status_code == 400
    assert client.post(path, json=payload(pid)).json()["draft"]["audio_alignment"] is None
