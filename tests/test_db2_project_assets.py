"""DB2.3 project asset integrity, conditional saves, legacy compatibility."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import morphorum.animation_projects as animation_projects
import morphorum.app as app_import
from morphorum.app import app


def _wav_bytes() -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(8000)
        writer.writeframes(b"\x00\x00" * 800)
    return out.getvalue()


def _image_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "navy").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def project_test(tmp_path, monkeypatch):
    monkeypatch.setattr(animation_projects, "PROJECTS_DIR", tmp_path / "projects")
    with TestClient(app) as client:
        created = client.post("/api/animation/projects", json={"name": "DB2 Asset Fixture"})
        assert created.status_code == 201, created.text
        yield client, created.json()["project"]["id"], tmp_path


def test_project_assets_and_verified_round_trip(project_test):
    client, pid, _ = project_test
    root = f"/api/animation/projects/{pid}"
    assert client.get(root + "/assets").json()["assets"] == []
    img = _image_bytes()
    image = client.post(
        root + "/source-image", content=img,
        headers={"X-Content-SHA256": hashlib.sha256(img).hexdigest(),
                 "X-Filename": "test.png"},
    )
    assert image.status_code == 201, image.text
    source_descriptor = image.json()["asset"]
    assert source_descriptor["kind"] == "source_image"
    assert source_descriptor["filename"] == "source.png"
    assert source_descriptor["bytes"] >= 1
    get_image = client.get(source_descriptor["url"])
    assert get_image.status_code == 200
    assert hashlib.sha256(get_image.content).hexdigest() == source_descriptor["sha256"]
    audio = _wav_bytes()
    attached = client.post(
        root + "/motion-import/soundtrack", content=audio,
        headers={
            "X-Content-SHA256": hashlib.sha256(audio).hexdigest(),
            "X-Audio-Filename": "my-track.wav",
            "X-Audio-Offset-Seconds": "0.5",
        },
    )
    assert attached.status_code == 200, attached.text
    audio_asset = attached.json()["asset"]
    assert audio_asset["kind"] == "soundtrack"
    assert audio_asset["sha256"] == hashlib.sha256(audio).hexdigest()
    assert audio_asset["filename"] == "my-track.wav"
    assert attached.json()["soundtrack"]["offset_seconds"] == 0.5
    audio_download = client.get(audio_asset["url"])
    assert audio_download.status_code == 200
    assert audio_download.content == audio
    assert audio_download.headers["x-content-sha256"] == audio_asset["sha256"]
    assert audio_download.headers["cache-control"] == "private, no-store"
    ranged = client.get(audio_asset["url"], headers={"Range": "bytes=0-15"})
    assert ranged.status_code == 206
    assert ranged.content == audio[:16]
    analyzed = client.post(root + "/motion-lab/audio-analyze", content=audio)
    assert analyzed.status_code == 200, analyzed.text
    digest = analyzed.json()["analysis"]["source_sha256"]
    catalog = client.get(root + "/assets")
    assert catalog.status_code == 200
    assets = catalog.json()["assets"]
    assert sorted(item["kind"] for item in assets) == [
        "motion_lab_wav", "soundtrack", "source_image"
    ]
    wav = next(a for a in assets if a["kind"] == "motion_lab_wav")
    assert wav["sha256"] == digest
    assert client.get(wav["url"]).content == audio
    assert all(a["url"].startswith(f"/api/animation/projects/{pid}/") for a in assets)
    assert all("path" not in a for a in assets)
    assert client.get(root + "/motion-lab/audio/" + "f" * 64).status_code == 404


def test_upload_validation_preserves_existing_assets(project_test, monkeypatch):
    client, pid, _ = project_test
    root = f"/api/animation/projects/{pid}"
    img = _image_bytes()
    assert client.post(root + "/source-image", content=img).status_code == 201
    original = client.get(root + "/source-image").content
    wrong = "0" * 64
    assert client.post(root + "/source-image", content=img,
                       headers={"X-Content-SHA256": wrong}).status_code == 400
    assert client.get(root + "/source-image").content == original
    bad = client.post(root + "/motion-import/soundtrack", content=b"not a wave",
                      headers={"X-Audio-Filename": "bad.wav"})
    assert bad.status_code == 400
    # The route's bounded reader rejects oversized payloads before decoding.
    from importlib import import_module
    app_module = import_module("morphorum.app")
    monkeypatch.setattr(app_module, "SOURCE_MAX_BYTES", 64)
    too_big = client.post(root + "/source-image", content=img)
    assert too_big.status_code == 413
    assert client.get(root + "/source-image").content == original


def test_etag_conditional_save_rejects_stale_without_impacting_browser(project_test):
    client, pid, _ = project_test
    url = f"/api/animation/projects/{pid}"
    first = client.get(url)
    assert first.status_code == 200
    etag = first.headers["etag"]
    assert etag.startswith('"') and len(etag) == 66
    a = first.json()["project"]
    a["notes"] = "First Editor"
    changed = client.put(url, json=a, headers={"If-Match": etag})
    assert changed.status_code == 200, changed.text
    new_tag = changed.headers["etag"]
    assert new_tag != etag
    a["notes"] = "Stale editor"
    stale = client.put(url, json=a, headers={"If-Match": etag})
    assert stale.status_code == 412
    assert stale.json()["error"]["code"] in ("HTTP_ERROR", "PRECONDITION_FAILED")
    assert client.get(url).json()["project"]["notes"] == "First Editor"
    assert client.put(url, json=a, headers={"If-Match": "*"}).status_code == 400
    # Legacy browser clients that do not send If-Match can still save.
    a["notes"] = "Browser legacy save"
    legacy = client.put(url, json=a)
    assert legacy.status_code == 200
    assert client.get(url).json()["project"]["notes"] == "Browser legacy save"


def test_checked_reference_client_download_leaves_no_corrupt_output(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "morphorum_client.py"
    spec = importlib.util.spec_from_file_location("db2_asset_client", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    client = mod.MorphorumClient("http://127.0.0.1:7866", "redacted-secret")

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, *unused):
            pass
        def read(self, n=-1):
            data, self.data = self.data[:n], self.data[n:]
            return data
        def __init__(self, value):
            self.data = value
    class FakeOpener:
        def open(self, request, timeout):
            return FakeResponse(b"GIF89a" + b"\x00" * 40)
    client._opener = FakeOpener()
    final = tmp_path / "preview.gif"
    final.write_bytes(b"original")
    with pytest.raises(mod.ClientError, match="SHA-256"):
        client.download("/api/animation/test/preview", final, file_type="gif",
                        expected_sha256="0" * 64)
    assert final.read_bytes() == b"original"
    assert not (tmp_path / "preview.gif.part").exists()
