from __future__ import annotations

import json
import pytest

from morphorum.animation_hybrid_source import (
    HybridSourceError, managed_video_path, parse_ffprobe_json,
)


def test_managed_path_prevents_traversal(tmp_path, monkeypatch):
    import morphorum.animation_hybrid_source as source
    monkeypatch.setattr(source, "animation_project_directory", lambda _id: tmp_path)
    for name in ("../evil.mp4", r"C:\\evil.mp4", "bad.py"):
        with pytest.raises(HybridSourceError):
            managed_video_path("project", name)
    assert managed_video_path("project", "holiday.MP4") == (
        tmp_path / "assets" / "hybrid" / "source.mp4"
    )


def test_probe_parses_video_stream_and_audio():
    payload = {
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1920,
             "height": 1080, "avg_frame_rate": "30000/1001",
             "disposition": {"attached_pic": 0}},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
        "format": {"duration": "4.25"},
    }
    result = parse_ffprobe_json(json.dumps(payload))
    assert result["width"] == 1920
    assert result["fps"] == pytest.approx(29.97003)
    assert result["estimated_frames"] == 128
    assert result["has_audio"] is True


@pytest.mark.parametrize("value", [
    '{"streams":[]}', '{"streams":[{"codec_type":"audio"}]}', "bad json",
    '{"streams":[{"codec_type":"video","width":0,"height":100,"avg_frame_rate":"24"}],"format":{"duration":"2"}}',
])
def test_probe_rejects_bad_media_metadata(value):
    with pytest.raises(HybridSourceError):
        parse_ffprobe_json(value)
