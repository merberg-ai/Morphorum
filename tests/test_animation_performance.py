from __future__ import annotations

import json

import pytest

from morphorum.animation_performance import (
    AnimationPerformance,
    append_performance_record,
    load_performance_records,
    performance_record,
    summarize_records,
)


def _record(frame: int, *, diffused: bool = True, seconds: float = 5.0,
            allocation: float = 10.0, loras: int = 2):
    return performance_record(
        frame=frame, diffused=diffused,
        timings={
            "total": seconds, "diffusion": seconds - 1 if diffused else 0,
            "prepare": 0.25 if diffused else 0, "conditioning": 0.15,
            "memory": 0.001, "warp": 0.06, "depth": 0.45,
        },
        cuda_before={"allocated_gib": allocation - 0.1, "reserved_gib": allocation},
        cuda_after={
            "free_gib": 16.0 - allocation,
            "total_gib": 16.0,
            "allocated_gib": allocation,
            "reserved_gib": allocation + 0.25,
            "peak_allocated_gib": allocation + 0.5,
            "peak_reserved_gib": allocation + 0.75,
            "active_gib": allocation - 0.2,
            "inactive_split_gib": 0.1,
            "allocator_backend": "native",
            "device_index": 0,
            "device_name": "Test GPU",
            "allocation_retries": 2,
            "oom_count": 0,
        },
        model_status={
            "device": "cuda", "optimization": "native-gpu", "task": "img2img",
            "loras": [{"id": x} for x in range(loras)],
            "active_loras": [
                {"adapter_name": "adapter-1", "weight": 0.25 + frame * 0.02}
            ] if loras else [],
        },
        conditioning_cache_entries=min(frame, 8),
        phase_memory={
            "frame_start": {
                "allocated_gib": allocation - 0.1,
                "allocator_backend": "native",
            },
            "post_diffusion_decode": {
                "allocated_gib": allocation,
                "peak_allocated_gib": allocation + 0.5,
                "allocator_backend": "native",
            },
        },
    )


def test_b55_performance_observes_gpu_and_adapter_lifecycle() -> None:
    tracker = AnimationPerformance()
    tracker.observe(_record(1, seconds=3, allocation=10, loras=1))
    tracker.observe(_record(2, diffused=False, seconds=0.5, allocation=10, loras=1))
    tracker.observe(_record(3, seconds=8, allocation=11, loras=3))
    result = tracker.public()
    assert result["frames_observed"] == 3
    assert result["diffusion_anchors"] == 2
    assert result["average_anchor_diffusion_seconds"] == 4.5
    assert result["maximum_allocated_gib"] == 11
    assert result["maximum_reserved_gib"] == 11.25
    assert result["maximum_peak_allocated_gib"] == 11.5
    assert result["maximum_peak_reserved_gib"] == 11.75
    assert result["maximum_active_gib"] == 10.8
    assert result["allocator_backend"] == "native"
    assert result["allocation_retries"] == 2
    assert result["oom_count"] == 0
    assert result["maximum_resident_loras"] == 3
    assert result["pipeline_device"] == "cuda"
    assert result["optimization"] == "native-gpu"
    assert result["latest_frame"] == 3
    assert result["slow_anchor_frames"] == []


def test_b55_slow_anchor_warning_tracking_is_bounded() -> None:
    tracker = AnimationPerformance()
    for frame in range(40):
        tracker.observe(_record(frame, seconds=77, allocation=13.5))
    summary = tracker.public()
    assert summary["diffusion_anchors"] == 40
    assert summary["slow_anchor_frames"] == list(range(16, 40))


def test_b55_resume_restores_and_deduplicates_completed_frames(tmp_path) -> None:
    path = tmp_path / "render" / "performance.jsonl"
    first = _record(1, loras=1)
    append_performance_record(path, first)
    append_performance_record(path, _record(2, loras=2))
    # Crashed mid-record; reader must not drop earlier correct records.
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{\"frame\":3")
    records = load_performance_records(path)
    assert [record["frame"] for record in records] == [1, 2]
    # Rerun/resume may re-observe the last frame. Newest record wins.
    append_performance_record(path, _record(2, loras=3))
    result = summarize_records(load_performance_records(path))
    assert result["frames_observed"] == 2
    assert result["maximum_resident_loras"] == 3


def test_b55_profile_capture_is_read_only_and_handles_no_cuda() -> None:
    record = performance_record(
        frame=4, diffused=False, timings={"total": 0.5},
        cuda_before=None, cuda_after=None, model_status=None,
        conditioning_cache_entries=0,
    )
    assert record["cuda_before"] is None
    assert record["cuda_after"] is None
    assert record["pipeline_device"] is None
    assert record["resident_loras"] == 0
    assert record["phase_memory"] == {}
    assert record["timings"]["diffusion"] == 0
    tracker = summarize_records([record])
    assert tracker["maximum_allocated_gib"] == 0
    assert tracker["pipeline_device"] is None


def test_b55_profile_does_not_store_tensor_or_prompts(tmp_path) -> None:
    record = _record(9, loras=3)
    text = json.dumps(record)
    assert "adapter-1" in text
    assert "prompt" not in text
    assert not any(key.startswith("_pipeline") for key in record)
    location = tmp_path / "perf.jsonl"
    append_performance_record(location, record)
    assert load_performance_records(location)[0]["frame"] == 9


def test_b55_performance_api_is_read_only_and_reports_missing_render(monkeypatch) -> None:
    from fastapi.testclient import TestClient
    from morphorum.app import app
    from morphorum.animation_render import (
        AnimationRenderError, animation_render_manager,
    )

    seen = []

    def fake_report(project_id, render_id):
        seen.append((project_id, render_id))
        if render_id == "missing":
            raise AnimationRenderError("Animation render manifest not found.")
        return {
            "project_id": project_id, "render_id": render_id,
            "status": "completed", "summary": {"frames_observed": 4},
            "frames": [{"frame": 1}, {"frame": 2}, {"frame": 3}, {"frame": 4}],
        }

    monkeypatch.setattr(animation_render_manager, "performance_report", fake_report)
    with TestClient(app) as client:
        response = client.get("/api/animation/renders/test-project/test-run/performance")
        assert response.status_code == 200
        assert response.json()["summary"]["frames_observed"] == 4
        assert len(response.json()["frames"]) == 4
        missing = client.get("/api/animation/renders/test-project/missing/performance")
        assert missing.status_code == 404
    assert seen == [("test-project", "test-run"), ("test-project", "missing")]


def test_b60p_phase_memory_preserves_allocator_context() -> None:
    record = _record(12, allocation=12.5, loras=3)
    phases = record["phase_memory"]
    assert phases["frame_start"]["allocator_backend"] == "native"
    assert phases["post_diffusion_decode"]["peak_allocated_gib"] == 13.0
    assert "prompt" not in json.dumps(phases)


def test_ml42_stable_memory_and_cadence_does_not_warn():
    tracker = AnimationPerformance()
    for frame in range(72):
        tracker.observe(_record(frame, diffused=frame % 3 == 0,
                                seconds=5.0, allocation=8.0 + (frame % 3) * .05))
    stability = tracker.public()["stability"]
    assert stability["memory_delta_gib"] == pytest.approx(0, abs=.1)
    assert stability["warnings"] == []
    assert stability["anchor_diffusion_slowdown_ratio"] == 1.0


def test_ml42_sustained_drift_and_slow_anchors_get_observational_warnings():
    tracker = AnimationPerformance()
    for frame in range(90):
        tracker.observe(_record(frame, seconds=4.0 if frame < 45 else 9.0,
                                allocation=8.0 + frame * .03))
    result = tracker.public()["stability"]
    assert result["memory_delta_gib"] > 1
    assert result["anchor_diffusion_slowdown_ratio"] >= 1.8
    assert len(result["warnings"]) == 2
    assert len(tracker._recent_allocated) == 12
    assert len(tracker._recent_anchor_times) == 8
    restored = summarize_records([_record(frame, allocation=8 + frame * .03,
                                          seconds=4 if frame < 45 else 9)
                                  for frame in range(90)])
    assert restored["stability"] == result


def test_ml42_short_or_cpu_only_runs_do_not_invent_gpu_drift():
    tracker = AnimationPerformance()
    for frame in range(11):
        tracker.observe(_record(frame, allocation=11 + frame * .4))
    assert tracker.public()["stability"]["memory_delta_gib"] is None
    no_cuda = summarize_records([performance_record(
        frame=n, diffused=False, timings={"total":1},
        cuda_before=None, cuda_after=None, model_status=None,
        conditioning_cache_entries=0) for n in range(50)])
    assert no_cuda["stability"]["memory_delta_gib"] is None
    assert no_cuda["stability"]["warnings"] == []


def test_g52_conditioning_cache_hit_miss_telemetry_survives_records_and_resume(tmp_path):
    tracker = AnimationPerformance()
    path = tmp_path / "performance.jsonl"
    for frame, hits, misses in ((1, 0, 1), (2, 1, 0), (3, 2, 0)):
        record = performance_record(
            frame=frame, diffused=True, timings={"conditioning": 0.002},
            cuda_before=None, cuda_after=None, model_status={},
            conditioning_cache_entries=1,
            conditioning_cache_hits=hits,
            conditioning_cache_misses=misses,
        )
        assert record["conditioning_cache_hits"] == hits
        assert record["conditioning_cache_misses"] == misses
        append_performance_record(path, record)
        tracker.observe(record)
    assert tracker.public()["conditioning_cache_hits"] == 3
    assert tracker.public()["conditioning_cache_misses"] == 1
    restored = summarize_records(load_performance_records(path))
    assert restored["conditioning_cache_hits"] == 3
    assert restored["conditioning_cache_misses"] == 1
    assert restored["total_conditioning_seconds"] == pytest.approx(0.006)


def test_g52_older_performance_records_default_missing_cache_counters_to_zero():
    tracker = AnimationPerformance()
    prior = _record(1)
    assert prior["conditioning_cache_hits"] == 0
    assert prior["conditioning_cache_misses"] == 0
    del prior["conditioning_cache_hits"]
    del prior["conditioning_cache_misses"]
    tracker.observe(prior)
    assert tracker.public()["conditioning_cache_hits"] == 0
    assert tracker.public()["conditioning_cache_misses"] == 0
