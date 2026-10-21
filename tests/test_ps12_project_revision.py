from __future__ import annotations

from fastapi.testclient import TestClient

import morphorum.animation_projects as projects
from morphorum.app import app


def test_ps12_timeline_etag_chaining_and_stale_rejection(tmp_path, monkeypatch):
    monkeypatch.setattr(projects,"PROJECTS_DIR",tmp_path/"projects")
    with TestClient(app) as client:
        new=client.post("/api/animation/projects",json={"name":"PS1.2 revisions"})
        assert new.status_code==201,new.text
        project_id=new.json()["project"]["id"]
        url=f"/api/animation/projects/{project_id}"
        initial=client.get(url).headers["etag"]
        timeline=url+"/timeline/tracks/prompts/positive/keyframes/30"
        first=client.put(timeline,headers={"If-Match":initial},
                         json={"value":"<lora:Test:1> new frame"})
        assert first.status_code==200,first.text
        advanced=first.headers["etag"]
        assert advanced!=initial
        assert first.json()["project"]["prompts"]["30"]=="<lora:Test:1> new frame"
        rejected=client.put(timeline,headers={"If-Match":initial},
                            json={"value":"SHOULD NOT REPLACE"})
        assert rejected.status_code==412,rejected.text
        assert client.get(url).json()["project"]["prompts"]["30"]=="<lora:Test:1> new frame"
        move=client.post(timeline+"/move",headers={"If-Match":advanced},
                         json={"frame":35,"overwrite":False})
        assert move.status_code==200,move.text
        after_move=move.headers["etag"]
        assert after_move!=advanced
        assert client.delete(url+"/timeline/tracks/prompts/positive/keyframes/35",
            headers={"If-Match":advanced}).status_code==412
        mode=client.put(url+"/timeline/tracks/prompts/negative/interpolation",
            headers={"If-Match":after_move},json={"interpolation":"hold"})
        assert mode.status_code==200,mode.text
        assert mode.json()["project"]["tracks"]["prompts"]["negative"]["interpolation"]=="hold"
        assert mode.headers["etag"]!=after_move
        assert client.delete(url+"/timeline/tracks/prompts/positive/keyframes/35",
            headers={"If-Match":mode.headers["etag"]}).status_code==200


def test_ps12_invalid_etag_and_intervening_project_save_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(projects,"PROJECTS_DIR",tmp_path/"projects")
    with TestClient(app) as client:
        created=client.post("/api/animation/projects",json={"name":"Two editors"}).json()["project"]
        url=f"/api/animation/projects/{created['id']}"
        old=client.get(url).headers["etag"]
        bad=client.put(url+"/timeline/tracks/prompts/positive/keyframes/30",
                       headers={"If-Match":"not-a-sha"},json={"value":"bad"})
        assert bad.status_code==400
        project=client.get(url).json()["project"]
        project["prompts"]["0"]="another browser"
        saved=client.put(url,headers={"If-Match":old},json=project)
        assert saved.status_code==200,saved.text
        assert client.put(url,headers={"If-Match":old},json=created).status_code==412
        assert client.get(url).json()["project"]["prompts"]["0"]=="another browser"
