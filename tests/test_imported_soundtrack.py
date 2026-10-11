"""DMI3: attached audio persistence and validation never mutate project.json."""
import hashlib
import pytest

from morphorum import imported_soundtrack as audio


def test_attach_and_reopen_wav_without_touching_project(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "animation_project_directory", lambda project_id: tmp_path)
    wav = b"RIFF" + b"\0"*4 + b"WAVE" + b"data" + b"\0"*8
    record=audio.store_soundtrack("test",wav,filename=r"C:\\Music\\song.wav",offset_seconds=0.125)
    assert record["filename"]=="song.wav"
    assert record["sha256"]==hashlib.sha256(wav).hexdigest()
    assert audio.read_soundtrack("test")==record
    updated=audio.update_offset("test",-0.5)
    assert updated["offset_seconds"]==-0.5
    assert audio.read_soundtrack("test")["offset_seconds"]==-0.5
    assert (tmp_path/"imported_soundtrack"/(record["sha256"]+".wav")).read_bytes()==wav


@pytest.mark.parametrize("filename,data",[
    ("bad.wav",b"garbage"),
    ("bad.mp3",b"not an mp3"),
    ("bad.exe",b"RIFF"+b"\0"*4+b"WAVE"),
    ("bad.flac",b"not flac"),
])
def test_invalid_audio_does_not_create_attachment(tmp_path,monkeypatch,filename,data):
    monkeypatch.setattr(audio,"animation_project_directory",lambda project_id:tmp_path)
    with pytest.raises(audio.ImportedSoundtrackError):
        audio.store_soundtrack("test",data,filename=filename,offset_seconds=0)
    assert not (tmp_path/"imported_soundtrack"/"attachment.json").exists()


@pytest.mark.parametrize("offset",[float("nan"),float("inf"),31,-31,True,"abc"])
def test_invalid_offset_rejected(tmp_path,monkeypatch,offset):
    monkeypatch.setattr(audio,"animation_project_directory",lambda project_id:tmp_path)
    with pytest.raises(audio.ImportedSoundtrackError):
        audio.store_soundtrack("test",b"OggS"+b"\0"*12,filename="sound.ogg",offset_seconds=offset)


def test_missing_audio_rejected(tmp_path,monkeypatch):
    monkeypatch.setattr(audio,"animation_project_directory",lambda project_id:tmp_path)
    with pytest.raises(audio.ImportedSoundtrackError):
        audio.update_offset("test",0)


def test_freeze_soundtrack_pins_attachment_and_offset_for_render(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "animation_project_directory", lambda project_id: tmp_path)
    original = b"ID3" + b"original-audio" * 8
    first = audio.store_soundtrack(
        "test", original, filename="first.mp3", offset_seconds=1.25
    )
    render_dir = tmp_path / "render"
    snapshot = audio.freeze_soundtrack("test", render_dir)
    assert snapshot["sha256"] == first["sha256"]
    assert snapshot["offset_seconds"] == pytest.approx(1.25)
    frozen = render_dir / snapshot["render_filename"]
    assert frozen.read_bytes() == original

    replacement = b"ID3" + b"replacement-audio" * 8
    audio.store_soundtrack(
        "test", replacement, filename="second.mp3", offset_seconds=-0.75
    )
    assert frozen.read_bytes() == original
    assert snapshot["offset_seconds"] == pytest.approx(1.25)


def test_freeze_soundtrack_rejects_changed_attachment_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "animation_project_directory", lambda project_id: tmp_path)
    record = audio.store_soundtrack(
        "test", b"fLaC" + b"audio" * 8, filename="clip.flac", offset_seconds=0
    )
    path = tmp_path / "imported_soundtrack" / (record["sha256"] + ".flac")
    path.write_bytes(b"fLaC" + b"tampered")
    with pytest.raises(audio.ImportedSoundtrackError, match="checksum changed"):
        audio.freeze_soundtrack("test", tmp_path / "render")
