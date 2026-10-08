from __future__ import annotations

from copy import deepcopy
from typing import Any

from .schedules import ScheduleError, parse_schedule, validate_numeric_schedule

TIMELINE_SCHEMA_VERSION = 1

NUMERIC_TRACK_DEFS: dict[str, dict[str, str]] = {
    "motion.angle": {
        "group": "camera_2d",
        "name": "angle",
        "legacy_section": "motion",
        "legacy_key": "angle",
        "value_type": "float",
        "default_schedule": "0:(0)",
    },
    "motion.zoom": {
        "group": "camera_2d",
        "name": "zoom",
        "legacy_section": "motion",
        "legacy_key": "zoom",
        "value_type": "float",
        "default_schedule": "0:(1.0)",
    },
    "motion.translation_x": {
        "group": "camera_2d",
        "name": "translation_x",
        "legacy_section": "motion",
        "legacy_key": "translation_x",
        "value_type": "float",
        "default_schedule": "0:(0)",
    },
    "motion.translation_y": {
        "group": "camera_2d",
        "name": "translation_y",
        "legacy_section": "motion",
        "legacy_key": "translation_y",
        "value_type": "float",
        "default_schedule": "0:(0)",
    },
    "generation.strength": {
        "group": "generation",
        "name": "strength",
        "legacy_section": "generation",
        "legacy_key": "strength",
        "value_type": "float",
        "default_schedule": "0:(0.65)",
    },
    "generation.noise": {
        "group": "generation",
        "name": "noise",
        "legacy_section": "generation",
        "legacy_key": "noise",
        "value_type": "float",
        "default_schedule": "0:(0.02)",
    },
    "generation.steps": {
        "group": "generation",
        "name": "steps",
        "legacy_section": "generation",
        "legacy_key": "steps",
        "value_type": "integer",
        "default_schedule": "0:(20)",
    },
    "generation.guidance": {
        "group": "generation",
        "name": "guidance",
        "legacy_section": "generation",
        "legacy_key": "guidance",
        "value_type": "float",
        "default_schedule": "0:(0)",
    },
}

PROMPT_TRACK_DEFS: dict[str, dict[str, str]] = {
    "positive": {
        "legacy_key": "prompts",
        "default_interpolation": "blend",
    },
    "negative": {
        "legacy_key": "negative_prompts",
        "default_interpolation": "blend",
    },
}

RESERVED_TRACK_GROUPS = ("camera_3d", "cadence", "loras")


def _project_context(project: dict[str, Any]) -> tuple[int, float, int]:
    animation = project.get("animation", {})
    generation = project.get("generation", {})
    max_frames = max(1, int(animation.get("max_frames", 120)))
    fps = max(1.0, float(animation.get("fps", 24.0)))
    seed = int(generation.get("seed", -1))
    return max_frames, fps, seed if seed >= 0 else 0


def _normalize_prompt_keyframes(
    value: Any,
    *,
    max_frames: int,
) -> list[dict[str, Any]]:
    source = value if isinstance(value, list) else []
    normalized: dict[int, str] = {}
    for item in source:
        if not isinstance(item, dict):
            continue
        try:
            frame = int(item.get("frame", 0))
        except (TypeError, ValueError):
            continue
        if 0 <= frame < max_frames:
            normalized[frame] = str(item.get("value", item.get("text", "")) or "")
    if 0 not in normalized:
        normalized[0] = ""
    return [
        {"frame": frame, "value": normalized[frame]}
        for frame in sorted(normalized)
    ]


def _prompt_keyframes_from_map(
    value: Any,
    *,
    max_frames: int,
) -> list[dict[str, Any]]:
    source = value if isinstance(value, dict) else {}
    normalized: dict[int, str] = {}
    for raw_frame, raw_text in source.items():
        try:
            frame = int(str(raw_frame).strip())
        except (TypeError, ValueError):
            continue
        if 0 <= frame < max_frames:
            normalized[frame] = str(raw_text or "")
    if 0 not in normalized:
        normalized[0] = ""
    return [
        {"frame": frame, "value": normalized[frame]}
        for frame in sorted(normalized)
    ]


def _prompt_map_from_keyframes(value: Any) -> dict[str, str]:
    source = value if isinstance(value, list) else []
    normalized: dict[int, str] = {}
    for item in source:
        if not isinstance(item, dict):
            continue
        try:
            frame = int(item.get("frame", 0))
        except (TypeError, ValueError):
            continue
        if frame >= 0:
            normalized[frame] = str(item.get("value", "") or "")
    if 0 not in normalized:
        normalized[0] = ""
    return {str(frame): normalized[frame] for frame in sorted(normalized)}


def _schedule_from_keyframes(value: Any, default_schedule: str) -> str:
    source = value if isinstance(value, list) else []
    normalized: dict[int, tuple[str, str]] = {}
    for item in source:
        if not isinstance(item, dict):
            continue
        try:
            frame = int(item.get("frame", 0))
        except (TypeError, ValueError):
            continue
        if frame < 0:
            continue
        frame_expression = str(item.get("frame_expression") or frame).strip()
        expression = str(item.get("value", item.get("expression", "")) or "").strip()
        if not frame_expression or not expression:
            continue
        normalized[frame] = (frame_expression, expression)
    if not normalized:
        return default_schedule
    return ", ".join(
        f"{normalized[frame][0]}:({normalized[frame][1]})"
        for frame in sorted(normalized)
    )


def _parsed_numeric_keyframes(
    schedule: str,
    *,
    max_frames: int,
    fps: float,
    seed: int,
) -> list[dict[str, Any]]:
    try:
        parsed = parse_schedule(
            schedule,
            max_frames=max_frames,
            seed=seed,
            fps=fps,
        )
    except ScheduleError:
        return []
    return [
        {
            "frame": item.frame,
            "frame_expression": item.frame_expression,
            "value": item.expression,
        }
        for item in parsed
    ]


def _normalize_numeric_track(
    value: Any,
    *,
    definition: dict[str, str],
    max_frames: int,
    fps: float,
    seed: int,
) -> dict[str, Any]:
    source = deepcopy(value) if isinstance(value, dict) else {}
    interpolation = str(source.get("interpolation") or "linear").strip().lower()
    if interpolation not in {"linear", "hold"}:
        interpolation = "linear"

    schedule = str(source.get("schedule") or "").strip()
    if not schedule:
        schedule = _schedule_from_keyframes(
            source.get("keyframes"),
            definition["default_schedule"],
        )

    source["kind"] = "numeric"
    source["value_type"] = definition["value_type"]
    source["interpolation"] = interpolation
    source["schedule"] = schedule
    source["keyframes"] = _parsed_numeric_keyframes(
        schedule,
        max_frames=max_frames,
        fps=fps,
        seed=seed,
    )
    return source


def _normalize_prompt_track(
    value: Any,
    *,
    fallback_keyframes: list[dict[str, Any]],
    default_interpolation: str,
    max_frames: int,
) -> dict[str, Any]:
    source = deepcopy(value) if isinstance(value, dict) else {}
    interpolation = str(
        source.get("interpolation") or default_interpolation
    ).strip().lower()
    if interpolation not in {"blend", "hold"}:
        interpolation = default_interpolation

    if isinstance(source.get("keyframes"), list):
        keyframes = _normalize_prompt_keyframes(
            source.get("keyframes"),
            max_frames=max_frames,
        )
    else:
        keyframes = deepcopy(fallback_keyframes)

    source["kind"] = "prompt"
    source["interpolation"] = interpolation
    source["keyframes"] = keyframes
    return source


def build_tracks_from_legacy(project: dict[str, Any]) -> dict[str, Any]:
    max_frames, fps, seed = _project_context(project)
    animation = project.get("animation", {})
    prompt_mode = str(
        animation.get("prompt_transition", "blend") or "blend"
    ).strip().lower()
    if prompt_mode not in {"blend", "hold"}:
        prompt_mode = "blend"

    tracks: dict[str, Any] = {
        "schema_version": TIMELINE_SCHEMA_VERSION,
        "prompts": {},
        "camera_2d": {},
        "camera_3d": {},
        "generation": {},
        "cadence": {},
        "loras": {},
    }

    for name, definition in PROMPT_TRACK_DEFS.items():
        fallback = _prompt_keyframes_from_map(
            project.get(definition["legacy_key"], {}),
            max_frames=max_frames,
        )
        tracks["prompts"][name] = _normalize_prompt_track(
            {"interpolation": prompt_mode, "keyframes": fallback},
            fallback_keyframes=fallback,
            default_interpolation=prompt_mode,
            max_frames=max_frames,
        )

    for field, definition in NUMERIC_TRACK_DEFS.items():
        legacy_section = project.get(definition["legacy_section"], {})
        legacy_section = legacy_section if isinstance(legacy_section, dict) else {}
        schedule = str(
            legacy_section.get(
                definition["legacy_key"],
                definition["default_schedule"],
            )
            or definition["default_schedule"]
        ).strip()
        tracks[definition["group"]][definition["name"]] = _normalize_numeric_track(
            {"schedule": schedule, "interpolation": "linear"},
            definition=definition,
            max_frames=max_frames,
            fps=fps,
            seed=seed,
        )

    return tracks


def normalize_tracks(
    value: Any,
    *,
    project: dict[str, Any],
) -> dict[str, Any]:
    max_frames, fps, seed = _project_context(project)
    baseline = build_tracks_from_legacy(project)
    source = deepcopy(value) if isinstance(value, dict) else {}
    result = deepcopy(source)
    result["schema_version"] = TIMELINE_SCHEMA_VERSION

    prompt_source = source.get("prompts", {})
    prompt_source = prompt_source if isinstance(prompt_source, dict) else {}
    prompt_result = deepcopy(prompt_source)
    for name, definition in PROMPT_TRACK_DEFS.items():
        fallback = baseline["prompts"][name]["keyframes"]
        default_interpolation = baseline["prompts"][name]["interpolation"]
        prompt_result[name] = _normalize_prompt_track(
            prompt_source.get(name),
            fallback_keyframes=fallback,
            default_interpolation=default_interpolation,
            max_frames=max_frames,
        )
    result["prompts"] = prompt_result

    for group in ("camera_2d", "generation"):
        group_source = source.get(group, {})
        group_source = group_source if isinstance(group_source, dict) else {}
        group_result = deepcopy(group_source)
        for field, definition in NUMERIC_TRACK_DEFS.items():
            if definition["group"] != group:
                continue
            track_source = group_source.get(definition["name"])
            if not isinstance(track_source, dict):
                track_source = baseline[group][definition["name"]]
            group_result[definition["name"]] = _normalize_numeric_track(
                track_source,
                definition=definition,
                max_frames=max_frames,
                fps=fps,
                seed=seed,
            )
        result[group] = group_result

    for group in RESERVED_TRACK_GROUPS:
        group_value = source.get(group, baseline.get(group, {}))
        result[group] = deepcopy(group_value) if isinstance(group_value, dict) else {}

    return result


def sync_legacy_from_tracks(
    project: dict[str, Any],
    tracks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bundle = normalize_tracks(
        tracks if isinstance(tracks, dict) else project.get("tracks"),
        project=project,
    )
    project["tracks"] = bundle

    prompts = bundle.get("prompts", {})
    positive = prompts.get("positive", {}) if isinstance(prompts, dict) else {}
    negative = prompts.get("negative", {}) if isinstance(prompts, dict) else {}
    project["prompts"] = _prompt_map_from_keyframes(positive.get("keyframes"))
    project["negative_prompts"] = _prompt_map_from_keyframes(
        negative.get("keyframes")
    )

    animation = project.setdefault("animation", {})
    animation["prompt_transition"] = str(
        positive.get("interpolation") or "blend"
    ).strip().lower()

    for field, definition in NUMERIC_TRACK_DEFS.items():
        group = bundle.get(definition["group"], {})
        group = group if isinstance(group, dict) else {}
        track = group.get(definition["name"], {})
        track = track if isinstance(track, dict) else {}
        section = project.setdefault(definition["legacy_section"], {})
        section[definition["legacy_key"]] = str(
            track.get("schedule") or definition["default_schedule"]
        ).strip()

    return project


def numeric_track(
    project: dict[str, Any],
    field: str,
) -> dict[str, Any]:
    definition = NUMERIC_TRACK_DEFS.get(field)
    if definition is None:
        raise ScheduleError(f"Unknown animation schedule field '{field}'.")

    tracks = project.get("tracks", {})
    if isinstance(tracks, dict):
        group = tracks.get(definition["group"], {})
        if isinstance(group, dict):
            track = group.get(definition["name"])
            if isinstance(track, dict):
                return track

    return build_tracks_from_legacy(project)[definition["group"]][definition["name"]]


def prompt_track(
    project: dict[str, Any],
    name: str,
) -> dict[str, Any]:
    if name not in PROMPT_TRACK_DEFS:
        raise ScheduleError(f"Unknown prompt track '{name}'.")

    tracks = project.get("tracks", {})
    if isinstance(tracks, dict):
        prompts = tracks.get("prompts", {})
        if isinstance(prompts, dict):
            track = prompts.get(name)
            if isinstance(track, dict):
                return track

    return build_tracks_from_legacy(project)["prompts"][name]


def prompt_track_map(track: dict[str, Any]) -> dict[str, str]:
    return _prompt_map_from_keyframes(track.get("keyframes"))


def track_keyframe_count(
    project: dict[str, Any],
    *,
    group: str,
    name: str,
) -> int:
    tracks = project.get("tracks", {})
    if not isinstance(tracks, dict):
        return 0
    group_value = tracks.get(group, {})
    if not isinstance(group_value, dict):
        return 0
    track = group_value.get(name, {})
    if not isinstance(track, dict):
        return 0
    keyframes = track.get("keyframes", [])
    return len(keyframes) if isinstance(keyframes, list) else 0


class TimelineError(ValueError):
    pass


TRACK_GROUP_DEFS: dict[str, dict[str, Any]] = {
    "prompts": {"label": "Prompts", "order": 0, "reserved": False},
    "camera_2d": {"label": "2D Camera", "order": 10, "reserved": False},
    "camera_3d": {"label": "3D Camera", "order": 20, "reserved": True},
    "generation": {"label": "Generation", "order": 30, "reserved": False},
    "cadence": {"label": "Cadence", "order": 40, "reserved": True},
    "loras": {"label": "LoRAs", "order": 50, "reserved": True},
}

_TRACK_META: dict[tuple[str, str], dict[str, Any]] = {
    ("prompts", "positive"): {
        "label": "Positive Prompt",
        "kind": "prompt",
        "value_type": "text",
        "unit": None,
        "interpolation_modes": ["blend", "hold"],
        "required_frame_zero": True,
    },
    ("prompts", "negative"): {
        "label": "Negative Prompt",
        "kind": "prompt",
        "value_type": "text",
        "unit": None,
        "interpolation_modes": ["blend", "hold"],
        "required_frame_zero": True,
    },
    ("camera_2d", "angle"): {
        "label": "Angle",
        "kind": "numeric",
        "value_type": "float",
        "unit": "deg",
        "interpolation_modes": ["linear", "hold"],
        "legacy_field": "motion.angle",
    },
    ("camera_2d", "zoom"): {
        "label": "Zoom",
        "kind": "numeric",
        "value_type": "float",
        "unit": "scale",
        "interpolation_modes": ["linear", "hold"],
        "legacy_field": "motion.zoom",
    },
    ("camera_2d", "translation_x"): {
        "label": "Translate X",
        "kind": "numeric",
        "value_type": "float",
        "unit": "px",
        "interpolation_modes": ["linear", "hold"],
        "legacy_field": "motion.translation_x",
    },
    ("camera_2d", "translation_y"): {
        "label": "Translate Y",
        "kind": "numeric",
        "value_type": "float",
        "unit": "px",
        "interpolation_modes": ["linear", "hold"],
        "legacy_field": "motion.translation_y",
    },
    ("generation", "strength"): {
        "label": "Strength",
        "kind": "numeric",
        "value_type": "float",
        "unit": None,
        "interpolation_modes": ["linear", "hold"],
        "legacy_field": "generation.strength",
    },
    ("generation", "noise"): {
        "label": "Noise",
        "kind": "numeric",
        "value_type": "float",
        "unit": None,
        "interpolation_modes": ["linear", "hold"],
        "legacy_field": "generation.noise",
    },
    ("generation", "steps"): {
        "label": "Steps",
        "kind": "numeric",
        "value_type": "integer",
        "unit": None,
        "interpolation_modes": ["linear", "hold"],
        "legacy_field": "generation.steps",
    },
    ("generation", "guidance"): {
        "label": "Guidance",
        "kind": "numeric",
        "value_type": "float",
        "unit": None,
        "interpolation_modes": ["linear", "hold"],
        "legacy_field": "generation.guidance",
    },
}


def timeline_track_descriptors() -> dict[str, Any]:
    groups = [
        {
            "id": group,
            **deepcopy(metadata),
        }
        for group, metadata in sorted(
            TRACK_GROUP_DEFS.items(),
            key=lambda item: int(item[1].get("order", 0)),
        )
    ]
    tracks = []
    for (group, name), metadata in _TRACK_META.items():
        tracks.append(
            {
                "id": f"{group}.{name}",
                "group": group,
                "name": name,
                "editable": True,
                "keyframe_editable": True,
                **deepcopy(metadata),
            }
        )
    return {
        "schema_version": TIMELINE_SCHEMA_VERSION,
        "groups": groups,
        "tracks": tracks,
    }


def _track_descriptor(group: str, name: str) -> dict[str, Any]:
    key = (str(group or "").strip(), str(name or "").strip())
    metadata = _TRACK_META.get(key)
    if metadata is None:
        raise TimelineError(f"Unknown timeline track '{key[0]}.{key[1]}'.")
    return {
        "id": f"{key[0]}.{key[1]}",
        "group": key[0],
        "name": key[1],
        "editable": True,
        "keyframe_editable": True,
        **deepcopy(metadata),
    }


def _frame_in_range(project: dict[str, Any], frame: Any) -> int:
    max_frames, _fps, _seed = _project_context(project)
    try:
        value = int(frame)
    except (TypeError, ValueError) as exc:
        raise TimelineError("Timeline keyframe must use an integer frame.") from exc
    if value < 0 or value >= max_frames:
        raise TimelineError(
            f"Frame {value} is outside the animation range 0..{max_frames - 1}."
        )
    return value


def _mutable_track(
    project: dict[str, Any],
    group: str,
    name: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    descriptor = _track_descriptor(group, name)
    bundle = normalize_tracks(project.get("tracks"), project=project)
    group_value = bundle.get(group)
    if not isinstance(group_value, dict):
        raise TimelineError(f"Timeline group '{group}' is not available.")
    track = group_value.get(name)
    if not isinstance(track, dict):
        raise TimelineError(f"Timeline track '{group}.{name}' is not available.")
    return descriptor, bundle, deepcopy(track)


def get_timeline_track(
    project: dict[str, Any],
    group: str,
    name: str,
) -> dict[str, Any]:
    descriptor, _bundle, track = _mutable_track(project, group, name)
    return {
        "descriptor": descriptor,
        "track": track,
    }


def timeline_snapshot(project: dict[str, Any]) -> dict[str, Any]:
    max_frames, fps, _seed = _project_context(project)
    bundle = normalize_tracks(project.get("tracks"), project=project)
    return {
        "schema_version": TIMELINE_SCHEMA_VERSION,
        "project_id": str(project.get("id") or ""),
        "max_frames": max_frames,
        "fps": fps,
        "duration_seconds": max_frames / fps,
        "descriptors": timeline_track_descriptors(),
        "tracks": bundle,
    }


def _store_track(
    project: dict[str, Any],
    *,
    group: str,
    name: str,
    bundle: dict[str, Any],
    track: dict[str, Any],
) -> dict[str, Any]:
    descriptor = _track_descriptor(group, name)
    if descriptor["kind"] == "numeric":
        field = str(descriptor.get("legacy_field") or "")
        definition = NUMERIC_TRACK_DEFS.get(field)
        if definition is None:
            raise TimelineError(f"Numeric track '{group}.{name}' has no field definition.")
        track["schedule"] = _schedule_from_keyframes(
            track.get("keyframes"),
            definition["default_schedule"],
        )
        max_frames, fps, seed = _project_context(project)
        interpolation = str(track.get("interpolation") or "linear").strip().lower()
        validation = validate_numeric_schedule(
            track["schedule"],
            max_frames=max_frames,
            seed=seed,
            fps=fps,
            interpolation=interpolation,
        )
        if not validation["valid"]:
            first = next(
                issue for issue in validation["issues"]
                if issue.get("severity") == "error"
            )
            raise TimelineError(
                f"Invalid keyframe for '{group}.{name}': {first['message']}"
            )

    group_value = bundle.setdefault(group, {})
    group_value[name] = track
    project["tracks"] = normalize_tracks(bundle, project=project)
    sync_legacy_from_tracks(project, project["tracks"])
    return project


def upsert_track_keyframe(
    project: dict[str, Any],
    group: str,
    name: str,
    *,
    frame: Any,
    value: Any,
) -> dict[str, Any]:
    descriptor, bundle, track = _mutable_track(project, group, name)
    frame_value = _frame_in_range(project, frame)
    keyframes = [
        deepcopy(item)
        for item in track.get("keyframes", [])
        if isinstance(item, dict)
    ]

    raw_value = str(value if value is not None else "")
    if descriptor["kind"] == "numeric":
        raw_value = raw_value.strip()
        if not raw_value:
            raise TimelineError("Numeric keyframe value cannot be empty.")

    replacement: dict[str, Any] = {
        "frame": frame_value,
        "value": raw_value,
    }
    if descriptor["kind"] == "numeric":
        replacement["frame_expression"] = str(frame_value)

    by_frame: dict[int, dict[str, Any]] = {}
    for item in keyframes:
        try:
            item_frame = int(item.get("frame", 0))
        except (TypeError, ValueError):
            continue
        by_frame[item_frame] = item
    by_frame[frame_value] = replacement
    track["keyframes"] = [
        by_frame[item_frame]
        for item_frame in sorted(by_frame)
    ]

    return _store_track(
        project,
        group=group,
        name=name,
        bundle=bundle,
        track=track,
    )


def delete_track_keyframe(
    project: dict[str, Any],
    group: str,
    name: str,
    *,
    frame: Any,
) -> dict[str, Any]:
    descriptor, bundle, track = _mutable_track(project, group, name)
    frame_value = _frame_in_range(project, frame)
    keyframes = [
        deepcopy(item)
        for item in track.get("keyframes", [])
        if isinstance(item, dict)
    ]
    matching = [
        item for item in keyframes
        if int(item.get("frame", -1)) == frame_value
    ]
    if not matching:
        raise TimelineError(
            f"Track '{group}.{name}' has no keyframe at frame {frame_value}."
        )
    if descriptor.get("required_frame_zero") and frame_value == 0:
        raise TimelineError(
            f"Track '{group}.{name}' requires a frame 0 keyframe."
        )
    if descriptor["kind"] == "numeric" and len(keyframes) <= 1:
        raise TimelineError(
            f"Numeric track '{group}.{name}' must contain at least one keyframe."
        )

    track["keyframes"] = [
        item for item in keyframes
        if int(item.get("frame", -1)) != frame_value
    ]
    return _store_track(
        project,
        group=group,
        name=name,
        bundle=bundle,
        track=track,
    )


def move_track_keyframe(
    project: dict[str, Any],
    group: str,
    name: str,
    *,
    source_frame: Any,
    target_frame: Any,
    overwrite: bool = False,
) -> dict[str, Any]:
    descriptor, bundle, track = _mutable_track(project, group, name)
    source = _frame_in_range(project, source_frame)
    target = _frame_in_range(project, target_frame)

    if source == target:
        return project
    if descriptor.get("required_frame_zero") and source == 0:
        raise TimelineError(
            f"Track '{group}.{name}' requires its frame 0 keyframe."
        )

    keyframes = [
        deepcopy(item)
        for item in track.get("keyframes", [])
        if isinstance(item, dict)
    ]
    by_frame: dict[int, dict[str, Any]] = {}
    for item in keyframes:
        try:
            item_frame = int(item.get("frame", -1))
        except (TypeError, ValueError):
            continue
        by_frame[item_frame] = item

    if source not in by_frame:
        raise TimelineError(
            f"Track '{group}.{name}' has no keyframe at frame {source}."
        )
    if target in by_frame and not overwrite:
        raise TimelineError(
            f"Track '{group}.{name}' already has a keyframe at frame {target}."
        )

    moved = by_frame.pop(source)
    moved["frame"] = target
    if descriptor["kind"] == "numeric":
        moved["frame_expression"] = str(target)
    by_frame[target] = moved
    track["keyframes"] = [
        by_frame[item_frame]
        for item_frame in sorted(by_frame)
    ]

    return _store_track(
        project,
        group=group,
        name=name,
        bundle=bundle,
        track=track,
    )


def set_track_interpolation(
    project: dict[str, Any],
    group: str,
    name: str,
    *,
    interpolation: Any,
) -> dict[str, Any]:
    descriptor, bundle, track = _mutable_track(project, group, name)
    mode = str(interpolation or "").strip().lower()
    supported = descriptor.get("interpolation_modes", [])
    if mode not in supported:
        raise TimelineError(
            f"Track '{group}.{name}' does not support interpolation mode '{mode}'."
        )
    track["interpolation"] = mode
    return _store_track(
        project,
        group=group,
        name=name,
        bundle=bundle,
        track=track,
    )
