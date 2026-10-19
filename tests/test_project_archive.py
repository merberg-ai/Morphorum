"""Portable project ZIP and full-copy regression tests."""
from __future__ import annotations

import hashlib
import io
import json
import wave
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import morphorum.animation_projects as projects
from morphorum.app import app
from morphorum.project_archive import (
    ARCHIVE_FORMAT, export_project_archive, inspect_project_archive,
    import_project_archive, ProjectArchiveConflict, ProjectArchiveError,
    save_project_as,
)


def _wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\x00\x00" * 800)
    return output.getvalue()


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (24, 24), "purple").save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture
def media_project(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    with TestClient(app) as client:
        created = client.post("/api/animation/projects", json={"name": "Archive Test"})
        assert created.status_code == 201, created.text
        project = created.json()["project"]
        pid = project["id"]
        root = tmp_path / "projects" / pid
        image = _png()
        response = client.post(f"/api/animation/projects/{pid}/source-image",
                               content=image, headers={"X-Filename": "start.png"})
        assert response.status_code == 201, response.text
        wav = _wav()
        response = client.post(f"/api/animation/projects/{pid}/motion-import/soundtrack",
                               content=wav,
                               headers={"X-Audio-Filename": "music.wav"})
        assert response.status_code == 200, response.text
        digest = hashlib.sha256(wav).hexdigest()
        folder = root / "motion_lab_audio"
        folder.mkdir(parents=True)
        (folder / f"{digest}.wav").write_bytes(wav)
        (root / "generated_output.mp4").write_bytes(b"render-not-allowed")
        (root / "random-extra.json").write_text('{"ignored":true}')
        yield client, pid, root, wav, image


def test_export_contains_manifest_settings_inputs_not_generated(media_project):
    client, pid, root, wav, image = media_project
    response = client.get(f"/api/animation/projects/{pid}/archive")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["format"] == ARCHIVE_FORMAT
        assert "project.json" in names
        assert "assets/source.png" in names
        assert "imported_soundtrack/attachment.json" in names
        assert any(n.startswith("imported_soundtrack/") and n.endswith(".wav") for n in names)
        assert any(n.startswith("motion_lab_audio/") and n.endswith(".wav") for n in names)
        assert archive.read("assets/source.png") == (root / "assets" / "source.png").read_bytes()
        assert not any("render" in n or "output" in n for n in names)
        assert "random-extra.json" not in names
    inspected = client.post("/api/animation/projects/archive/inspect",
                            content=response.content, headers={"Content-Type": "application/zip"})
    assert inspected.status_code == 200, inspected.text
    assert inspected.json()["conflict"] is True


def test_import_conflict_and_backup_preserve_original(media_project):
    client, pid, root, wav, image = media_project
    archive = export_project_archive(pid)
    url = "/api/animation/projects/archive/import"
    assert client.post(url, content=archive).status_code == 409
    assert (root / "project.json").is_file()
    result = client.post(url, content=archive,
                         headers={"X-Morphorum-Overwrite": "true"})
    assert result.status_code == 201, result.text
    assert result.json()["status"] == "overwritten"
    assert result.json()["backup"] is True
    assert (root / "assets" / "source.png").read_bytes() == (root.parent / ".trash" / next(x.name for x in (root.parent / ".trash").iterdir() if x.name.startswith(pid + "-archive-backup-")) / "assets" / "source.png").read_bytes()
    assert list((root.parent / ".trash").glob(pid + "-archive-backup-*"))
    assert not (root / "generated_output.mp4").exists()


def test_fresh_archive_import_on_empty_library(media_project, tmp_path, monkeypatch):
    _, pid, root, wav, image = media_project
    archive = export_project_archive(pid)
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "other" / "projects")
    info = inspect_project_archive(archive)
    assert info["conflict"] is False
    result = import_project_archive(archive)
    assert result["status"] == "imported"
    new_root = tmp_path / "other" / "projects" / pid
    assert projects.load_animation_project(pid)["id"] == pid
    assert (new_root / "assets" / "source.png").read_bytes() == (root / "assets" / "source.png").read_bytes()
    assert (new_root / "imported_soundtrack" / "attachment.json").exists()


def test_save_as_new_identity_full_settings_inputs_without_generated(media_project):
    client, pid, root, wav, image = media_project
    original = projects.load_animation_project(pid)
    draft = json.loads(json.dumps(original))
    draft["prompts"]["0"] = "A new, unsaved scene"
    result = client.post(f"/api/animation/projects/{pid}/save-as",
                         json={"name": "New Copy", "project": draft})
    assert result.status_code == 201, result.text
    new = result.json()["project"]
    assert new["id"] != pid
    assert new["name"] == "New Copy"
    assert new["prompts"]["0"] == "A new, unsaved scene"
    assert projects.load_animation_project(pid)["prompts"]["0"] != "A new, unsaved scene"
    copied = root.parent / new["id"]
    assert (copied / "assets" / "source.png").read_bytes() == (root / "assets" / "source.png").read_bytes()
    assert (copied / "imported_soundtrack" / "attachment.json").exists()
    assert list((copied / "motion_lab_audio").glob("*.wav"))
    assert not (copied / "generated_output.mp4").exists()


def test_reject_plain_zip_and_traversal_and_unlisted_members(media_project):
    _, pid, root, wav, image = media_project
    for members in (
        {"random.txt": b"hello"},
        {"manifest.json": b"{}", "../escape.txt": b"bad"},
        {"manifest.json": b"{}", "project.json": b"{}", "renders/frame.png": b"bad"},
    ):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for name, data in members.items():
                archive.writestr(name, data)
        with pytest.raises(ProjectArchiveError):
            inspect_project_archive(stream.getvalue())


def test_reject_digest_tampering_without_changing_saved_project(media_project):
    _, pid, root, wav, image = media_project
    base = export_project_archive(pid)
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(base)) as inp, zipfile.ZipFile(output, "w") as out:
        for name in inp.namelist():
            raw = inp.read(name)
            if name == "assets/source.png":
                raw = b"fake PNG"
            out.writestr(name, raw)
    with pytest.raises(ProjectArchiveError, match="integrity"):
        import_project_archive(output.getvalue(), overwrite=True)
    assert (root / "assets" / "source.png").read_bytes() == (root / "assets" / "source.png").read_bytes()
