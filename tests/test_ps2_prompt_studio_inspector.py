"""PS2: read-only native prompt frame inspector parity and safety."""
from __future__ import annotations

from copy import deepcopy
from fastapi.testclient import TestClient

import morphorum.animation_projects as projects
from morphorum.app import app
from morphorum.schedules import resolve_prompt_transition


def tracks():
    return {
      "positive":{"kind":"prompt","interpolation":"blend",
        "keyframes":[{"frame":0,"value":"<lora:Style:1> Alpha  "},
          {"frame":40,"value":"Beta"}]},
      "negative":{"kind":"prompt","interpolation":"hold",
        "keyframes":[{"frame":0,"value":"blur"}, {"frame":20,"value":"bad hands"}]},
    }


def test_ps2_inspector_matches_native_prompt_resolver_without_saving(tmp_path,monkeypatch):
    monkeypatch.setattr(projects,"PROJECTS_DIR",tmp_path/"projects")
    with TestClient(app) as client:
        created=client.post("/api/animation/projects",json={"name":"PS2 resolver"}).json()["project"]
        pid=created["id"]
        url=f"/api/animation/projects/{pid}"
        old=client.get(url).headers["ETag"]
        for frame in (0,10,20,39,40,119):
            response=client.post(url+"/prompt-studio/inspect-frame",
                json={"max_frames":120,"frame":frame,"tracks":tracks()})
            assert response.status_code==200,response.text
            result=response.json()
            for lane,track in tracks().items():
                expected=resolve_prompt_transition(
                    {str(k["frame"]):k["value"] for k in track["keyframes"]},
                    frame=frame,max_frames=120,mode=track["interpolation"])
                assert result[lane]==expected.to_dict()
        assert client.get(url).headers["ETag"]==old


def test_ps2_inspector_rejects_invalid_unsaved_timeline_data(tmp_path,monkeypatch):
    monkeypatch.setattr(projects,"PROJECTS_DIR",tmp_path/"projects")
    with TestClient(app) as client:
        pid=client.post("/api/animation/projects",json={"name":"PS2 bad frames"}).json()["project"]["id"]
        endpoint=f"/api/animation/projects/{pid}/prompt-studio/inspect-frame"
        good={"max_frames":120,"frame":0,"tracks":tracks()}
        for malformed in [
            {**good,"frame":120},
            {**good,"max_frames":0},
            {**good,"frame":-1},
            {**good,"frame":0.5},
            {**good,"tracks":{}},
        ]:
            response=client.post(endpoint,json=malformed)
            assert response.status_code==400,response.text
        invalid=deepcopy(good)
        invalid["tracks"]["positive"]["keyframes"][1]["frame"]=0
        assert client.post(endpoint,json=invalid).status_code==400
        invalid=deepcopy(good)
        invalid["tracks"]["negative"]["keyframes"][0]["frame"]=2
        assert client.post(endpoint,json=invalid).status_code==400
        assert client.post("/api/animation/projects/does-not-exist/prompt-studio/inspect-frame",
            json=good).status_code==404
