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
