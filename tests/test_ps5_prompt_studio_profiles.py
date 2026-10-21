"""PS5.1 family-aware profiles, exact continuity locks and targeted scene refinement."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

import morphorum.prompt_studio_ollama as ai
import morphorum.prompt_studio_profiles as profiles
from morphorum.app import app
from test_ps4_prompt_studio_ollama import req, tracks, fake_scenes


def test_ps51_profile_catalog_is_versioned_and_profile_guidance_not_renderer_claim():
    catalog=profiles.profile_catalog()
    assert catalog["schema_version"]==1
    assert {p["family"] for p in catalog["profiles"]}=={"sdxl","flux","zimage"}
    assert {p["id"] for p in catalog["profiles"]}==set(profiles.PROFILE_IDS.values())
    assert "not tokenizer" in catalog["warning"]
    with TestClient(app) as client:
        result=client.get("/api/prompt-studio/profiles")
        assert result.status_code==200
        assert result.json()["profiles"]==catalog["profiles"]


def test_ps51_profile_guidance_is_family_specific_and_versioned():
    for family in ("sdxl","flux","zimage"):
        payload={**req(),"family":family,"profile":profiles.PROFILE_IDS[family]}
        plan=ai.validate_story_request(payload)
        assert plan["profile"]==profiles.PROFILE_IDS[family]
        messages=ai._prompt_messages(plan)
        assert profiles.PROFILE_DESCRIPTIONS[family]["guidance"] in messages[0]["content"]
        assert profiles.PROFILE_IDS[family] in messages[1]["content"]
        result=ai.compile_result(plan,fake_scenes())
        assert result["provenance"]["profile"]==profiles.PROFILE_IDS[family]
        assert result["diagnostics"][0]["words_approx"]>=1
    # PS4 clients and pre-PS5 provenance remain valid.
    assert ai.validate_story_request(req())["profile"]=="ps4-generic-v1"


def test_ps51_refine_selected_keyframe_preserves_unselected_lanes_and_lora_exactly():
    payload={**req(mode="refine",scene_count=1),
       "profile":"ps5-zimage-v1","target_frame":24,
       "continuity":{"subject":"same pale astronaut in a red jacket",
                     "style":"low-key 1970s analog film"}}
    original=deepcopy(payload["tracks"])
    plan=ai.validate_story_request(payload)
    assert plan["scene_frames"]==[24]
    result=ai.compile_result(plan,fake_scenes(1))
    assert result["scenes"][0]["frame"]==24
    assert result["tracks"]["positive"]["keyframes"][0]==original["positive"]["keyframes"][0]
    changed=result["tracks"]["positive"]["keyframes"][1]
    assert changed["frame"]==24
    assert "same pale astronaut in a red jacket" in changed["value"]
    assert "low-key 1970s analog film" in changed["value"]
    assert "<lora:Art:0.75>" in changed["value"]
    assert result["tracks"]["negative"]==original["negative"]
    assert original==payload["tracks"]
    assert result["provenance"]["scene_count"]==1


def test_ps51_targeted_negative_generation_preserves_other_negative_keyframes():
    payload={**req(mode="refine",scene_count=1,negatives=True),
             "profile":"ps5-sdxl-v1","family":"sdxl","target_frame":24}
    result=ai.compile_result(ai.validate_story_request(payload),fake_scenes(1))
    assert result["tracks"]["negative"]["keyframes"]==[
        {"frame":0,"value":"bad anatomy"},
        {"frame":13,"value":"blurry"},
        {"frame":24,"value":"avoid item 1"},
    ]


def test_ps51_locked_continuity_is_not_duplicated_if_model_reuses_phrase():
    payload={**req(),"profile":"ps5-zimage-v1",
       "continuity":{"subject":"the same cat","style":"grainy VHS"}}
    plan=ai.validate_story_request(payload)
    raw={"scenes":[{"positive":"The Same Cat on a couch, grainy VHS","negative":""},
                   *fake_scenes()["scenes"][1:]]}
    result=ai.compile_result(plan,raw)
    assert result["tracks"]["positive"]["keyframes"][0]["value"].lower().count("the same cat")==1
    assert result["tracks"]["positive"]["keyframes"][0]["value"].lower().count("grainy vhs")==1
    assert result["tracks"]["positive"]["keyframes"][1]["value"].startswith("the same cat, grainy VHS")


@pytest.mark.parametrize("change",[
    {"profile":"ps5-flux-v1"},
    {"profile":"unsupported"},
    {"target_frame":13},
    {"target_frame":-1},
    {"target_frame":"24"},
    {"continuity":{"subject":"x"*1001}},
    {"continuity":{"style":12}},
    {"continuity":{"secret":"no"}},
])
def test_ps51_strict_rejection_of_cross_family_or_invalid_locks(change):
    payload={**req(mode="refine"),"profile":"ps5-zimage-v1",**change}
    with pytest.raises(ai.OllamaStoryError):
        ai.validate_story_request(payload)


def test_ps51_target_in_create_mode_rejected():
    with pytest.raises(ai.OllamaStoryError):
        ai.validate_story_request({**req(),"target_frame":24})


def test_ps51_diagnostics_are_honest_heuristics_with_no_universal_token_limit():
    text="cinematic "*270
    d=tracks()
    d["positive"]["keyframes"][1]["value"]=text
    output, warnings=profiles.diagnostics(d,"sdxl")
    assert output[1]["long_prompt"]
    assert output[1]["words_approx"]==270
    assert any("not CLIP tokens" in w for w in warnings)
    assert profiles.continuity_prefix("The BLUE CAT sleeps",{"subject":"the blue cat","style":"painting"})=="painting"


def test_ps51_draft_provenance_accepts_versioned_profiles_and_old_ps4():
    from morphorum.prompt_studio_drafts import _validate_ai_provenance
    old={"provider":"ollama","model":"qwen3:4b","mode":"refine",
         "scene_count":1,"family":"zimage","profile":"ps4-generic-v1",
         "created_at":"2026-10-21T10:00:00Z"}
    assert _validate_ai_provenance(old)==old
    fresh={**old,"profile":"ps5-zimage-v1"}
    assert _validate_ai_provenance(fresh)==fresh
    from morphorum.prompt_studio_drafts import PromptDraftError
    with pytest.raises(PromptDraftError):
        _validate_ai_provenance({**fresh,"profile":"ps5-flux-v1"})
