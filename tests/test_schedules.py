from __future__ import annotations

import math

import pytest

from morphorum.schedules import (
    ScheduleError,
    evaluate_expression,
    parse_schedule,
    resolve_numeric_schedule,
    resolve_prompt_transition,
    sample_schedule,
    validate_numeric_schedule,
)


def test_linear_numeric_schedule() -> None:
    schedule = "0:(0), 10:(10)"
    assert resolve_numeric_schedule(schedule, frame=0, max_frames=11) == pytest.approx(0)
    assert resolve_numeric_schedule(schedule, frame=5, max_frames=11) == pytest.approx(5)
    assert resolve_numeric_schedule(schedule, frame=10, max_frames=11) == pytest.approx(10)


def test_single_expression_is_evaluated_for_each_frame() -> None:
    schedule = "0:(1.0 + 0.1*sin(t/10))"
    value = resolve_numeric_schedule(schedule, frame=20, max_frames=120)
    assert value == pytest.approx(1.0 + 0.1 * math.sin(2.0))


def test_expression_keyframe_blends_toward_next_keyframe() -> None:
    schedule = "0:(sin(t)), 100:(4)"
    value = resolve_numeric_schedule(schedule, frame=50, max_frames=101)
    expected = 0.5 * math.sin(50) + 0.5 * 4
    assert value == pytest.approx(expected)


def test_nested_functions_and_max_frame_variables() -> None:
    schedule = '0:(max(0, sin(t/5))), "max_f-1":(2)'
    keyframes = parse_schedule(schedule, max_frames=100)
    assert [item.frame for item in keyframes] == [0, 98]
    value = resolve_numeric_schedule(schedule, frame=49, max_frames=100)
    left = max(0, math.sin(49 / 5))
    expected = left * 0.5 + 2 * 0.5
    assert value == pytest.approx(expected)


def test_frame_expression_must_resolve_to_integer() -> None:
    with pytest.raises(ScheduleError, match="non-integer"):
        parse_schedule("max_f/2:(1)", max_frames=100)


def test_hold_schedule_keeps_previous_keyframe() -> None:
    schedule = "0:(10), 10:(20)"
    assert resolve_numeric_schedule(
        schedule,
        frame=5,
        max_frames=11,
        interpolation="hold",
    ) == pytest.approx(10)


def test_safe_expression_engine_rejects_python_access() -> None:
    with pytest.raises(
        ScheduleError,
        match="Unknown schedule function|Unsupported|must be called by name",
    ):
        evaluate_expression(
            "__import__('os').system('echo nope')",
            t=0,
            max_f=10,
        )

    with pytest.raises(ScheduleError, match="Unsupported"):
        evaluate_expression(
            "(1).__class__",
            t=0,
            max_f=10,
        )


def test_expression_helpers() -> None:
    value = evaluate_expression(
        "lerp(0, 10, clamp(t/max_f, 0, 1))",
        t=5,
        max_f=10,
    )
    assert value == pytest.approx(5)


def test_prompt_transition_blends_between_keyframes() -> None:
    transition = resolve_prompt_transition(
        {"0": "forest", "100": "city"},
        frame=25,
        max_frames=101,
        mode="blend",
    )
    assert transition.from_text == "forest"
    assert transition.to_text == "city"
    assert transition.from_weight == pytest.approx(0.75)
    assert transition.to_weight == pytest.approx(0.25)


def test_prompt_transition_hold_mode() -> None:
    transition = resolve_prompt_transition(
        {"0": "forest", "100": "city"},
        frame=99,
        max_frames=101,
        mode="hold",
    )
    assert transition.from_text == "forest"
    assert transition.from_weight == 1
    assert transition.to_weight == 0


def test_schedule_validation_warns_about_future_keyframes() -> None:
    result = validate_numeric_schedule(
        "0:(1), 200:(2)",
        max_frames=120,
    )
    assert result["valid"] is True
    assert any(issue["severity"] == "warning" for issue in result["issues"])


def test_schedule_validation_reports_expression_errors() -> None:
    result = validate_numeric_schedule(
        "0:(not_a_function(t))",
        max_frames=120,
    )
    assert result["valid"] is False
    assert result["issues"][0]["severity"] == "error"


def test_sample_schedule_includes_first_and_last_frame() -> None:
    samples = sample_schedule(
        "0:(0), 119:(1)",
        max_frames=120,
        sample_count=20,
    )
    assert samples[0]["frame"] == 0
    assert samples[-1]["frame"] == 119
    assert len(samples) <= 20
