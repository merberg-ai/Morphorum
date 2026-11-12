"""Schedules are parsed once, and resolving a frame gives the same answer as before."""
from __future__ import annotations

import random
import time

import pytest

from morphorum import schedules
from morphorum.schedules import (
    ScheduleError,
    evaluate_expression,
    parse_schedule,
    resolve_numeric_schedule,
    validate_numeric_schedule,
)


def _reference_resolve(schedule, *, frame, max_frames, seed=0, fps=24, interpolation="linear"):
    """The original algorithm: a linear scan over freshly parsed keyframes."""
    keyframes = schedules._parse_schedule_text(str(schedule).strip(), max_frames, seed, fps)
    keyframes = sorted({k.frame: k for k in keyframes}.values(), key=lambda k: k.frame)

    def value(keyframe):
        return evaluate_expression(keyframe.expression, t=frame, max_f=max_frames - 1, seed=seed, fps=fps)

    previous, following = keyframes[0], keyframes[-1]
    for keyframe in keyframes:
        if keyframe.frame <= frame:
            previous = keyframe
        if keyframe.frame >= frame:
            following = keyframe
            break
    if frame <= keyframes[0].frame:
        return value(keyframes[0])
    if frame >= keyframes[-1].frame:
        return value(keyframes[-1])
    before = value(previous)
    if interpolation == "hold" or previous.frame == following.frame:
        return before
    amount = (frame - previous.frame) / (following.frame - previous.frame)
    return before + (value(following) - before) * amount


@pytest.mark.parametrize("interpolation", ["linear", "hold"])
def test_resolving_matches_the_original_algorithm(interpolation):
    rng = random.Random(11)
    max_frames = 240
    for _ in range(40):
        frames = rng.sample(range(0, 300), rng.randint(1, 30))  # unsorted, some past the end
        parts = []
        for at in frames:
            expression = rng.choice([
                f"{rng.uniform(-5, 5):.4f}", "sin(t/10)*2", "t*0.01+1", "max_f-t", f"({rng.randint(1, 9)}+s)",
            ])
            parts.append(f"{at}:({expression})")
        if rng.random() < 0.3:
            parts.append("max_f-39:(3.5)")  # frame given as an expression
        schedule = ", ".join(parts)
        for frame in [0, 1, max_frames // 2, max_frames - 1, *rng.sample(range(max_frames), 12)]:
            got = resolve_numeric_schedule(
                schedule, frame=frame, max_frames=max_frames, seed=3, fps=30, interpolation=interpolation,
            )
            want = _reference_resolve(
                schedule, frame=frame, max_frames=max_frames, seed=3, fps=30, interpolation=interpolation,
            )
            assert got == pytest.approx(want, rel=1e-12, abs=1e-12), (schedule, frame)


def test_parse_depends_on_every_argument_and_returns_independent_lists():
    schedule = "0:(1), max_f:(2)"
    short = parse_schedule(schedule, max_frames=10)
    long = parse_schedule(schedule, max_frames=100)
    assert [k.frame for k in short] == [0, 9]
    assert [k.frame for k in long] == [0, 99]
    first = parse_schedule(schedule, max_frames=10)
    first.append("mutated by a caller")
    assert len(parse_schedule(schedule, max_frames=10)) == 2
    assert [k.frame for k in parse_schedule("0:(1), s+1:(2)", max_frames=10, seed=4)] == [0, 5]
    assert [k.frame for k in parse_schedule("0:(1), s+1:(2)", max_frames=10, seed=2)] == [0, 3]


def test_errors_are_raised_every_time_not_cached_away():
    for _ in range(2):
        with pytest.raises(ScheduleError, match="empty"):
            parse_schedule("   ", max_frames=10)
        with pytest.raises(ScheduleError):
            parse_schedule("0:(1), nonsense", max_frames=10)
        with pytest.raises(ScheduleError, match="Invalid schedule expression"):
            resolve_numeric_schedule("0:(1 +* 2)", frame=0, max_frames=10)
        with pytest.raises(ScheduleError, match="outside the animation range"):
            resolve_numeric_schedule("0:(1)", frame=10, max_frames=10)


def test_a_keyframe_per_frame_schedule_is_parsed_once_and_validates_quickly(monkeypatch):
    """Motion Lab writes one keyframe per frame; that must not cost frames x keyframes."""
    frames = 1500
    schedule = ", ".join(f"{frame}:({(frame % 37) * 0.013:.5f})" for frame in range(frames))
    schedules._parse_schedule_cached.cache_clear()
    parses = []
    original = schedules._parse_schedule_text

    def counted(*args):
        parses.append(1)
        return original(*args)

    monkeypatch.setattr(schedules, "_parse_schedule_text", counted)
    started = time.perf_counter()
    report = validate_numeric_schedule(schedule, max_frames=frames, fps=30)
    for frame in range(frames):
        resolve_numeric_schedule(schedule, frame=frame, max_frames=frames, fps=30)
    elapsed = time.perf_counter() - started
    assert report["valid"] is True
    assert len(parses) == 1
    # The old code needed well over ten seconds for this; allow generous slack.
    assert elapsed < 5.0, f"took {elapsed:.1f}s"
    assert resolve_numeric_schedule(schedule, frame=40, max_frames=frames, fps=30) == pytest.approx(3 * 0.013)
