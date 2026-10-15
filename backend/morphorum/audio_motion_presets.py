"""DA4.3 standalone deterministic camera cue presets.

Outputs native six-axis *per-frame increments*. Integration into Motion Lab
and rendering happens separately in DA4.5, after physical acceptance.
"""
from __future__ import annotations

import math

from .audio_motion import AudioMotionError
from .audio_motion_cues import cue_frame_index, validate_cues
from .motion_lab import AMPLITUDE, AXES

def _smooth(t: float) -> float:
    return t * t * (3 - 2 * t)

def _ease(t: float, kind: str) -> float:
    t = max(0.,min(1.,t))
    if kind == "linear": return t
    if kind == "ease_in": return t*t
    if kind == "ease_out": return 1-(1-t)*(1-t)
    return _smooth(t)

def _position(cue: dict, progress: float) -> dict[str, float]:
    """Camera offset in natural relative amplitude units at normalized cue time."""
    preset=cue["preset"]
    curve=_ease(progress,cue["easing"])
    intensity=cue["intensity"]
    if preset in ("push_zoom_in","dolly_out"):
        return {"translation_z":(1 if preset=="push_zoom_in" else -1)*intensity*curve}
    if preset=="push_return":
        phase=_smooth(progress*2) if progress<=.5 else _smooth((1-progress)*2)
        return {"translation_z":intensity*phase}
    if preset in ("roll_right_left","roll_left_right"):
        # Return to zero after a clockwise/counterclockwise excursion.
        sign=1 if preset=="roll_right_left" else -1
        return {"rotation_z":sign*intensity*math.sin(2*math.pi*progress)}
    if preset=="shake":
        return {"translation_x":intensity*(1-progress)*math.sin(8*math.pi*progress)}
    if preset=="ripple":
        return {"translation_z":intensity*math.exp(-4*progress)*math.sin(8*math.pi*progress)}
    if preset=="reveal_drift":
        return {"translation_z":intensity*(math.cos(2*math.pi*progress)-1)/2,
                "translation_x":intensity*.25*math.sin(2*math.pi*progress)}
    if preset=="fly_through":
        return {"translation_z":intensity*curve,
                "translation_x":intensity*.2*math.sin(2*math.pi*progress)}
    raise AudioMotionError("Unknown motion cue preset.")

def cue_velocity_tracks(document: dict, fps: float, frames: int) -> dict[str,list[float]]:
    """Compile isolated cue motion only; never mutate animation or base tracks.

    Each cue returns to its underlying path except deliberate step/forward
    presets. Last frame of a finishing return is sampled at progress=1.
    """
    doc=validate_cues(document)
    if not math.isfinite(fps) or not 1<=fps<=240 or type(frames) is not int or not 1<=frames<=3000:
        raise AudioMotionError("Invalid cue timeline FPS or frame count.")
    tracks={axis:[0.0]*frames for axis in AXES}
    for cue in doc["cues"]:
        if not cue["enabled"] or cue["intensity"]<=0: continue
        start=cue_frame_index(cue["time_seconds"],fps,frames)
        span=max(1,math.ceil(cue["duration_seconds"]*fps))
        prev={axis:0.0 for axis in AXES}
        for step in range(span+1):
            frame=start+step
            if frame>=frames: break
            progress=step/span
            now=_position(cue,progress)
            for axis in set(now)|set(prev):
                delta=(now.get(axis,0.0)-prev.get(axis,0.0))*AMPLITUDE[axis]*8
                tracks[axis][frame]+=delta
            prev=now
    return tracks
