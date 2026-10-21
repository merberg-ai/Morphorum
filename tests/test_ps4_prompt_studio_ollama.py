"""PS4 local/LAN Ollama provider tests. All network calls are mocked."""
from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

import morphorum.animation_projects as projects
import morphorum.prompt_studio_ollama as ollama
from morphorum.app import app


def tracks():
    return {
      "positive":{"kind":"prompt","interpolation":"blend",
        "keyframes":[{"frame":0,"value":"  <lora:Horror Style ZIT:1>  fog, night "},
                     {"frame":24,"value":"<lora:Art:0.75> haunted forest"}]},
      "negative":{"kind":"prompt","interpolation":"hold",
        "keyframes":[{"frame":0,"value":"bad anatomy"},
                     {"frame":13,"value":"blurry"}]}
    }


def req(mode="create",scene_count=3,negatives=False):
    return {
      "endpoint":"http://127.0.0.1:11434", "allow_lan":False,
      "model":"qwen3:4b", "mode":mode,
      "idea":"A dark cinematic horror story moving from the forest to a ruined city.",
      "scene_count":scene_count, "include_negative":negatives,
      "family":"zimage", "fps":24.0, "max_frames":72, "tracks":tracks()
    }


def fake_scenes(count=3):
    return {"scenes":[{"title":f"Scene {i+1}","positive":f"Scene image {i+1}",
                       "negative":f"avoid item {i+1}"} for i in range(count)]}


@pytest.mark.parametrize("endpoint,allow_lan,allowed",[
    ("http://localhost:11434",False,True),
    ("http://127.0.0.1:11434",False,True),
    ("http://192.168.1.4:11434",False,False),
    ("http://192.168.1.4:11434",True,True),
    ("http://10.3.4.5:11434",True,True),
    ("http://172.30.1.2:11434",True,True),
    ("http://8.8.8.8:11434",True,False),
    ("http://169.254.0.10:11434",True,False),
    ("http://example.com:11434",True,False),
    ("https://127.0.0.1:11434",True,False),
    ("http://user:pass@127.0.0.1:11434",True,False),
    ("http://127.0.0.1:11434/api/chat",True,False),
    ("http://127.0.0.1:11434/?model=x",False,False),
    ("http://[::1]:11434",False,True),
    ("http://[fd00::1]:11434",True,True),
])
def test_ollama_endpoint_is_local_or_opt_in_private_ip(endpoint,allow_lan,allowed):
    if allowed:
        assert ollama.endpoint_url(endpoint,allow_lan).startswith("http://")
    else:
        with pytest.raises(ollama.OllamaStoryError):
            ollama.endpoint_url(endpoint,allow_lan)


def test_new_storyboard_uses_deterministic_frames_without_mutating_native_state():
    body=req()
    before=deepcopy(body)
    plan=ollama.validate_story_request(body)
    assert plan["scene_frames"]==[0,24,48]
    result=ollama.compile_result(plan,fake_scenes())
    assert [p["frame"] for p in result["tracks"]["positive"]["keyframes"]]==[0,24,48]
    assert result["tracks"]["negative"]==body["tracks"]["negative"]
    assert result["provenance"]["profile"]=="ps4-generic-v1"
    assert result["scenes"][2]["time_seconds"]==2
    assert body==before
    assert "Horror Style ZIT" not in result["tracks"]["positive"]["keyframes"][0]["value"]


def test_refine_keeps_existing_frame_positions_exact_lora_tag_bytes_and_independent_negatives():
    body=req(mode="refine",scene_count=12)
    plan=ollama.validate_story_request(body)
    assert plan["scene_frames"]==[0,24]
    result=ollama.compile_result(plan,fake_scenes(2))
    assert [p["frame"] for p in result["tracks"]["positive"]["keyframes"]]==[0,24]
    assert result["tracks"]["positive"]["keyframes"][0]["value"].startswith(
        "<lora:Horror Style ZIT:1>")
    assert result["tracks"]["positive"]["keyframes"][1]["value"].startswith(
        "<lora:Art:0.75>")
    assert result["tracks"]["negative"]==body["tracks"]["negative"]
    assert "LoRA tags" in " ".join(result["warnings"])


def test_negative_generation_is_always_explicit_and_replaces_lane_only_when_selected():
    plan=ollama.validate_story_request(req(negatives=True))
    result=ollama.compile_result(plan,fake_scenes())
    assert [p["frame"] for p in result["tracks"]["negative"]["keyframes"]]==[0,24,48]
    assert result["tracks"]["negative"]["keyframes"][1]["value"]=="avoid item 2"


@pytest.mark.parametrize("raw",[
    {"scenes":[]},
    {"scenes":[{"positive":"hello"}]},
    {"scenes":[{"positive":"<lora:Hacked:1> trap","negative":""} for _ in range(3)]},
    {"scenes":[{"positive":"x"*4001,"negative":""} for _ in range(3)]},
    {"scenes":[{"positive":"image","negative":0} for _ in range(3)]},
    {"scenes":[{"positive":"image","negative":"","frame":999} for _ in range(3)]},
])
def test_invalid_model_output_is_rejected_without_mutation(raw):
    body=req()
    before=deepcopy(body)
    with pytest.raises(ollama.OllamaStoryError):
        ollama.compile_result(ollama.validate_story_request(body),raw)
    assert body==before


@pytest.mark.parametrize("change",[
    {"scene_count":17}, {"scene_count":0}, {"scene_count":1.5},
    {"mode":"delete_project"}, {"family":"invalid"},
    {"model":"bad model\n"}, {"fps":0},
    {"idea":"x"}, {"max_frames":0},
    {"include_negative":"yes"},
    {"endpoint":"http://169.254.169.254/latest/meta-data", "allow_lan":True},
])
def test_invalid_storyboard_requests_fail_before_network(change):
    bad={**req(),**change}
    with pytest.raises(ollama.OllamaStoryError):
        ollama.validate_story_request(bad)


def test_prompt_messages_keep_paths_and_model_settings_out():
    plan=ollama.validate_story_request(req(mode="refine"))
    messages=ollama._prompt_messages(plan)
    assert [m["role"] for m in messages]==["system","user"]
    assert "LoRA" in messages[1]["content"]
    assert "/home/" not in messages[1]["content"]
    assert "http://" not in messages[1]["content"]


def test_api_models_generation_provenance_and_project_etag_are_read_only(tmp_path,monkeypatch):
    monkeypatch.setattr(projects,"PROJECTS_DIR",tmp_path/"projects")
    calls=[]
    async def stub(endpoint,route,**options):
        calls.append((endpoint,route,options.get("body")))
        if route=="/api/tags":
            return {"models":[{"name":"qwen3:4b","size":1234,
                               "details":{"family":"qwen3","parameter_size":"4.0B"}}]}
        return {"message":{"content":__import__("json").dumps(fake_scenes())}}
    monkeypatch.setattr(ollama,"_http_json",stub)
    with TestClient(app) as client:
        created=client.post("/api/animation/projects",json={"name":"Ollama read-only"})
        assert created.status_code==201,created.text
        pid=created.json()["project"]["id"]
        etag=client.get(f"/api/animation/projects/{pid}").headers["etag"]
        models=client.post("/api/prompt-studio/ollama/models",
                           json={"endpoint":"http://127.0.0.1:11434"})
        assert models.status_code==200,models.text
        assert models.json()["models"][0]["name"]=="qwen3:4b"
        response=client.post("/api/prompt-studio/ollama/generate",json=req())
        assert response.status_code==200,response.text
        assert response.json()["scenes"][0]["frame"]==0
        assert response.json()["provenance"]["provider"]=="ollama"
        assert calls[1][2]["stream"] is False
        assert calls[1][2]["format"]=="json"
        assert calls[1][2]["keep_alive"]=="0"
        assert client.get(f"/api/animation/projects/{pid}").headers["etag"]==etag


def test_api_invalid_provider_and_invalid_json_are_visible_errors(monkeypatch):
    async def bad(endpoint,route,**options):
        return {"message":{"content":"not json"}}
    monkeypatch.setattr(ollama,"_http_json",bad)
    with TestClient(app) as client:
        denied=client.post("/api/prompt-studio/ollama/generate",
                          json={**req(),"endpoint":"https://example.com"})
        assert denied.status_code==400
        malformed=client.post("/api/prompt-studio/ollama/generate",json=req())
        assert malformed.status_code==422


def test_saved_draft_validates_optional_ai_provenance_without_breaking_older_version():
    from morphorum.prompt_studio_drafts import _validate_ai_provenance
    assert _validate_ai_provenance(None) is None
    good={"provider":"ollama","model":"qwen3:4b","mode":"create",
          "scene_count":3,"family":"zimage","profile":"ps4-generic-v1",
          "created_at":"2026-10-21T08:00:00Z"}
    assert _validate_ai_provenance(good)==good
    for wrong in [{**good,"provider":"not-ollama"},{**good,"scene_count":200},
                  {**good,"model":"x"*300},{**good,"url":"http://example.com"}]:
        with pytest.raises(ValueError):_validate_ai_provenance(wrong)
