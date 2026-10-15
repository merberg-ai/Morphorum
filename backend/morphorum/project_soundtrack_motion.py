"""Use a project's attached soundtrack as Motion Lab audio without browser re-upload.

Never rewrite the render soundtrack, offset, project JSON, camera schedules or
manual cue documents. The verified attached file is the only conversion input.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile

from .animation_video import ffmpeg_executable
from .audio_motion import AudioMotionError
from .audio_motion_upload import MAX_AUDIO_BYTES, analyze_managed_wav
from .imported_soundtrack import MAX_IMPORT_AUDIO_BYTES
from .project_assets import ProjectAssetError, digest_file, soundtrack_path


def _convert_attached_audio(source: Path) -> bytes:
    executable = ffmpeg_executable()
    if not executable:
        raise AudioMotionError(
            "The attached soundtrack is not a compatible PCM WAV. Install FFmpeg "
            "on the Morphorum host or set MORPHORUM_FFMPEG to convert MP3/OGG/FLAC."
        )
    # A maximum of 181 seconds is decoded so a track exceeding 3 minutes
    # fails normal analysis rather than silently cutting off a longer track.
    # 22.05 kHz, stereo, 16-bit is under 20 MiB for that full duration.
    with tempfile.TemporaryDirectory(prefix=".motion-audio-", dir=source.parent) as directory:
        output = Path(directory) / "converted.wav"
        args = [
            executable, "-hide_banner", "-loglevel", "error", "-nostdin",
            "-i", str(source), "-map", "0:a:0", "-vn",
            "-t", "181", "-ac", "2", "-ar", "22050",
            "-c:a", "pcm_s16le", "-f", "wav", "-y", str(output),
        ]
        try:
            result = subprocess.run(
                args, check=False, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AudioMotionError("FFmpeg could not convert the saved soundtrack.") from exc
        if result.returncode or not output.is_file():
            raise AudioMotionError(
                "FFmpeg could not decode the saved soundtrack into PCM WAV."
            )
        if not 0 < output.stat().st_size <= MAX_AUDIO_BYTES:
            raise AudioMotionError(
                "The saved soundtrack exceeds Motion Studio's 20 MiB PCM WAV limit."
            )
        return output.read_bytes()


def analyze_project_soundtrack(project_id: str, *, fps: float, frames: int) -> dict:
    """Verify project soundtrack bytes and attach a managed Motion Lab WAV.

    Any conversion is bounded and does not modify the attached soundtrack.
    Existing source-bound layers remain untouched; analysis is idempotent.
    """
    path, record = soundtrack_path(project_id)
    if path.is_symlink():
        raise ProjectAssetError("Attached soundtrack must be a regular file.")
    actual, size = digest_file(path, max_bytes=MAX_IMPORT_AUDIO_BYTES)
    if actual != record["sha256"]:
        raise ProjectAssetError("Attached soundtrack checksum mismatch. Reattach the audio.")
    if not 0 < size <= MAX_IMPORT_AUDIO_BYTES:
        raise ProjectAssetError("Attached soundtrack size is invalid.")

    if record["format"] == "wav" and size <= MAX_AUDIO_BYTES:
        pcm = path.read_bytes()
        try:
            analysis = analyze_managed_wav(project_id, pcm, fps=fps, frames=frames)
            converted = False
        except AudioMotionError:
            pcm = _convert_attached_audio(path)
            analysis = analyze_managed_wav(project_id, pcm, fps=fps, frames=frames)
            converted = True
    else:
        pcm = _convert_attached_audio(path)
        analysis = analyze_managed_wav(project_id, pcm, fps=fps, frames=frames)
        converted = True

    # Keep source provenance distinct from WAV's own content digest; its
    # checksum may differ after FFmpeg conversion, and that is expected.
    return {
        "analysis": analysis,
        "soundtrack": {
            "filename": record["filename"],
            "format": record["format"],
            "sha256": record["sha256"],
            "offset_seconds": record["offset_seconds"],
        },
        "converted_to_pcm": converted,
    }
