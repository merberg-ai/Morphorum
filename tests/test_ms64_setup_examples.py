"""MS6.4 starter project: zero side effects until confirmation, idempotent save."""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

import morphorum.animation_projects as projects
import morphorum.setup_examples as examples
import morphorum.setup_state as setup
from morphorum.animation_resolution import validate_project_schedules

app_module = importlib.import_module("morphorum.app")


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "SETUP_STATE_FILE", tmp_path / "setup-state.json")
    monkeypatch.setattr(setup, "USER_CONFIG", tmp_path / "config.yaml")
    monkeypatch.setattr(setup, "INSTALL_MANIFEST", tmp_path / "install.json")
    monkeypatch.setattr(setup, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(setup, "ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(projects, "ensure_runtime_dirs", lambda: None)
    monkeypatch.delenv("MORPHORUM_SETUP_WIZARD", raising=False)
    return tmp_path


def _prepare():
    setup.prepare_install()
    setup.mark_install_ready()
    status = setup.setup_status()
    return setup.update_setup(
        action="advance", step="finish", revision=status["revision"],
        template_id="gentle-dolly-in", model_id="",
    )


def test_exactly_two_static_examples_and_opposite_native_tracks(isolated):
    catalog = examples.example_catalog()
    assert catalog["schema_version"] == 1
    assert len(catalog["examples"]) == 2
    assert catalog["animation"] == {
        "max_frames": 48, "fps": 12, "width": 512, "height": 512, "mode": "3d"
    }
    inward = projects.normalize_animation_project(examples.build_example("gentle-dolly-in", ""))
    outward = projects.normalize_animation_project(examples.build_example("gentle-dolly-out", ""))
    for project in (inward, outward):
        assert project["model"]["model_id"] == ""
        assert project["animation"]["mode"] == "3d"
        assert project["generation"]["seed"] == 123456
        assert project["generation"]["seed_behavior"] == "fixed"
        assert project["prompts"]["0"]
        assert project["tracks"]["camera_3d"]["translation_z"]["schedule"] == project["camera_3d"]["translation_z"]
        assert project["tracks"]["camera_3d"]["translation_z"]["keyframes"][-1]["frame"] == 47
        for field in ("translation_x", "translation_y", "rotation_x", "rotation_y", "rotation_z"):
            assert project["camera_3d"][field] == "0:(0)"
            assert project["tracks"]["camera_3d"][field]["schedule"] == "0:(0)"
        assert project["motion"]["zoom"] == "0:(1.0)"
        assert project["generation"]["strength"] == "0:(0.65)"
        check=validate_project_schedules(project)
        assert check["valid"], check.get("issues")
    assert inward["camera_3d"]["translation_z"] == "0:(0), 47:(0.6)"
    assert outward["camera_3d"]["translation_z"] == "0:(0), 47:(-0.6)"


@pytest.mark.parametrize("family,variant,steps,guidance,sampler", [
    ("sdxl", "", "0:(25)", "0:(6)", "euler"),
    ("flux", "dev", "0:(28)", "0:(1)", "flowmatch_euler"),
    ("flux", "schnell", "0:(4)", "0:(0)", "flowmatch_euler"),
    ("zimage", "turbo", "0:(9)", "0:(0)", "flowmatch_euler"),
])
def test_family_defaults_honor_variant_without_changing_small_size(
    isolated, monkeypatch, family, variant, steps, guidance, sampler,
):
    record={"id": "external-test", "family": family, "variant": variant,
            "kind": "checkpoints", "name": "Test model"}
    monkeypatch.setattr(examples, "get_model", lambda model_id: record)
    project=examples.build_example("gentle-dolly-in", "external-test")
    assert project["generation"]["steps"] == steps
    assert project["generation"]["guidance"] == guidance
    assert project["generation"]["sampler"] == sampler
    assert project["animation"]["width"] == project["animation"]["height"] == 512


def test_setup_catalog_is_read_only_and_creation_requires_explicit_same_origin_post(isolated):
    with TestClient(app_module.app) as client:
        before=client.get("/api/setup/examples")
        assert before.status_code==200
        assert [x["id"] for x in before.json()["examples"]] == [
            "gentle-dolly-in", "gentle-dolly-out"
        ]
        assert not list((isolated / "projects").glob("*/project.json"))
        state=_prepare()
        body={"template_id":"gentle-dolly-in","model_id":"",
              "revision":state["revision"]}
        assert client.post("/api/setup/example",json=body).status_code==403
        assert client.post("/api/setup/example",json=body,headers={
            "X-Morphorum-Setup":"1", "Origin":"https://elsewhere.example"
        }).status_code==403
        assert not list((isolated / "projects").glob("*/project.json"))
        response=client.post("/api/setup/example",json=body,headers={
            "X-Morphorum-Setup":"1", "Origin":"http://testserver"
        })
        assert response.status_code==201,response.text
        saved=response.json()
        assert saved["render_ready"] is False
        assert saved["project"]["model"]["model_id"] == ""
        assert len(list((isolated / "projects").glob("*/project.json"))) == 1
        project_id=saved["project"]["id"]
        assert client.get("/api/animation/projects/"+project_id).status_code==200
        # An interrupted browser handoff can retry without making a duplicate.
        body["revision"]=saved["revision"]
        projects.save_animation_project(project_id,{"notes":"user changed this already"})
        again=client.post("/api/setup/example",json=body,headers={
            "X-Morphorum-Setup":"1"
        })
        assert again.status_code==201,again.text
        assert again.json()["project"]["notes"] == "user changed this already"
        assert len(list((isolated / "projects").glob("*/project.json"))) == 1
        assert setup.setup_status()["status"] == "in_progress"
        finish=client.post("/api/setup/progress",json={
            "action":"complete", "step":"finish", "revision":saved["revision"]
        },headers={"X-Morphorum-Setup":"1"})
        assert finish.status_code==200,finish.text
        assert finish.json()["status"]=="completed"
        assert finish.json()["show_wizard"] is False


def test_finish_without_example_and_conflicting_reservation(isolated):
    state=_prepare()
    # Explicit no-example completion is allowed.
    done=setup.update_setup(action="complete",step="finish",revision=state["revision"])
    assert done["status"]=="completed"
    assert done["example_project_id"] is None
    assert not list((isolated / "projects").glob("*/project.json"))


def test_conflicting_idempotent_retry_does_not_create_new_project(isolated):
    state=_prepare()
    project,reservation=examples.instantiate_example(
        template_id="gentle-dolly-in",model_id="",
        revision=state["revision"],forced=False,
    )
    assert projects.load_animation_project(project["id"])["id"]==project["id"]
    with pytest.raises(setup.SetupStateConflict):
        examples.instantiate_example(
            template_id="gentle-dolly-out",model_id="",
            revision=reservation["revision"],forced=False,
        )
    assert len(list((isolated / "projects").glob("*/project.json"))) == 1



def test_ms65_orphaned_reservation_has_explicit_non_destructive_exit(isolated):
    state = _prepare()
    reservation = setup.reserve_setup_example(
        template_id="gentle-dolly-in", model_id="",
        revision=state["revision"], forced=False,
    )
    assert reservation["example_project_id"]
    assert not list((isolated / "projects").glob("*/project.json"))
    with pytest.raises(setup.SetupStateError, match="not saved"):
        setup.update_setup(
            action="complete", step="finish", revision=reservation["revision"],
        )
    # An interrupted disk write must not trap the user in onboarding.
    with TestClient(app_module.app) as client:
        completed = client.post("/api/setup/progress", json={
            "action": "complete", "step": "finish",
            "revision": reservation["revision"], "without_example": True,
        }, headers={"X-Morphorum-Setup": "1"})
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "completed"
        assert completed.json()["example_project_id"] == reservation["example_project_id"]
        assert client.get("/api/setup/status").json()["show_wizard"] is False
    assert not list((isolated / "projects").glob("*/project.json"))


def test_ms65_setup_completion_respects_current_revision_and_preserves_existing_data(isolated):
    state = _prepare()
    project, reserved = examples.instantiate_example(
        template_id="gentle-dolly-in", model_id="",
        revision=state["revision"], forced=False,
    )
    path = isolated / "projects" / project["id"] / "project.json"
    before = path.read_bytes()
    with pytest.raises(setup.SetupStateConflict):
        setup.update_setup(action="complete", step="finish", revision=state["revision"])
    assert path.read_bytes() == before
    completed = setup.update_setup(
        action="complete", step="finish", revision=reserved["revision"],
    )
    assert completed["status"] == "completed"
    assert path.read_bytes() == before
    assert setup.setup_status()["show_wizard"] is False
