#!/usr/bin/env python3
r"""P4.4.4 host acceptance: exercise FFmpeg/FFprobe with real temporary media.

No GPU, downloads, project writes, or system changes. Only the selected
FFmpeg/FFprobe are executed. Outputs are created under TemporaryDirectory
and automatically removed after the checks complete.

Windows: .\.venv\Scripts\python.exe scripts\ffmpeg_acceptance.py --mode managed
Linux:   ./.venv/bin/python scripts/ffmpeg_acceptance.py --mode managed
Use --mode auto or --mode custom --custom-path PATH to test other selections.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import subprocess
import sys
import tempfile
import wave
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.morphorum.ffmpeg_tools import ffmpeg_status

FPS = 8
FRAME_COUNT = 8
SIZE = 64
TIMEOUT = 45


class AcceptanceFailure(RuntimeError):
    pass


def _command(argv: list[str], label: str) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            argv, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=TIMEOUT, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AcceptanceFailure(label + ": " + str(exc)) from exc
    if result.returncode:
        raise AcceptanceFailure(
            label + " failed (" + str(result.returncode) + "): " +
            (result.stderr or result.stdout)[-1500:]
        )
    return result


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload)) + kind + payload +
        struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _write_png(path: Path, frame: int) -> None:
    rows = []
    for y in range(SIZE):
        row = bytearray([0])
        for x in range(SIZE):
            row.extend(((x * 3 + frame * 17) % 256,
                        (y * 3 + frame * 31) % 256,
                        ((x + y) * 2 + frame * 9) % 256))
        rows.append(bytes(row))
    bitmap = b"".join(rows)
    data = (
        b"\x89PNG\r\n\x1a\n" +
        _chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 2, 0, 0, 0)) +
        _chunk(b"IDAT", zlib.compress(bitmap, level=6)) +
        _chunk(b"IEND", b"")
    )
    path.write_bytes(data)


def _write_wave(path: Path) -> None:
    rate = 24000
    samples = [
        int(12000 * math.sin(2 * math.pi * 220 * i / rate))
        for i in range(rate)
    ]
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(struct.pack("<" + "h" * len(samples), *samples))


def _probe(probe: str, media: Path) -> dict:
    reply = _command(
        [probe, "-v", "error", "-show_streams", "-show_format",
         "-of", "json", str(media)], "FFprobe inspect " + media.name
    )
    try:
        content = json.loads(reply.stdout)
    except ValueError as exc:
        raise AcceptanceFailure("FFprobe produced invalid JSON.") from exc
    if not isinstance(content, dict) or not content.get("streams"):
        raise AcceptanceFailure("FFprobe returned no streams for " + media.name)
    return content


def _video(ffmpeg: str, probe: str, root: Path, extension: str,
           codec: str, audio_codec: str) -> None:
    frames = root / "frames"
    destination = root / ("acceptance." + extension)
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-framerate", str(FPS), "-start_number", "0",
        "-i", str(frames / "frame_%06d.png"),
        "-i", str(root / "source.wav"),
        "-map", "0:v:0", "-frames:v", str(FRAME_COUNT),
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-pix_fmt", "yuv420p",
        "-map", "1:a:0", "-af", "apad", "-t", "1.000000",
    ]
    if extension == "mp4":
        command.extend(["-c:v", codec, "-preset", "medium", "-crf", "23",
                        "-movflags", "+faststart", "-f", "mp4"])
    else:
        command.extend(["-c:v", codec, "-deadline", "good",
                        "-cpu-used", "4", "-b:v", "0", "-crf", "32", "-f", "webm"])
    command.extend(["-c:a", audio_codec, "-b:a", "128k",
                    "-progress", "pipe:1", str(destination)])
    result = _command(command, extension.upper() + " encode")
    if "progress=end" not in result.stdout:
        raise AcceptanceFailure(extension.upper() + " encoding did not report completion.")
    if not destination.is_file() or destination.stat().st_size == 0:
        raise AcceptanceFailure(extension.upper() + " file was empty.")
    info = _probe(probe, destination)
    video = [s for s in info["streams"] if s.get("codec_type") == "video"]
    audio = [s for s in info["streams"] if s.get("codec_type") == "audio"]
    expected = "h264" if extension == "mp4" else "vp9"
    if not video or video[0].get("codec_name") != expected or not audio:
        raise AcceptanceFailure(extension.upper() + " decoded streams do not match expected output.")

    # Hybrid video extraction uses FFmpeg to read the video and create PNGs.
    if extension == "mp4":
        extracted = root / "extracted"
        extracted.mkdir()
        _command(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
             "-ss", "0", "-i", str(destination), "-t", "0.5",
             "-vf", "fps=4", "-frames:v", "4", "-y",
             str(extracted / "frame_%06d.png")], "Hybrid frame extraction"
        )
        if not list(extracted.glob("frame_*.png")):
            raise AcceptanceFailure("Hybrid extraction produced no PNG frames.")
        print("PASS  Hybrid-video extraction")

    print("PASS  " + extension.upper() + " video + audio, FFprobe streams")


def _audio(ffmpeg: str, probe: str, root: Path) -> None:
    for extension, encoder in (
        ("mp3", "libmp3lame"), ("ogg", "libvorbis"), ("flac", "flac")
    ):
        encoded = root / ("input." + extension)
        converted = root / ("decoded-" + extension + ".wav")
        _command(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
             "-y", "-i", str(root / "source.wav"), "-c:a", encoder,
             str(encoded)], extension.upper() + " audio encode"
        )
        _probe(probe, encoded)
        _command(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
             "-y", "-i", str(encoded), "-ac", "1", "-ar", "16000",
             "-acodec", "pcm_s16le", str(converted)],
            extension.upper() + " soundtrack conversion"
        )
        with wave.open(str(converted), "rb") as audio:
            if (audio.getnchannels() != 1 or audio.getsampwidth() != 2
                    or audio.getframerate() != 16000
                    or audio.getnframes() < 8000):
                raise AcceptanceFailure(extension.upper() + " PCM WAV conversion failed.")
        print("PASS  " + extension.upper() + " audio -> 16 kHz mono PCM WAV")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["saved", "auto", "custom", "managed"],
                        default="saved", help="Which host FFmpeg selection to exercise.")
    parser.add_argument("--custom-path", type=str, default="",
                        help="Full path to ffmpeg or ffmpeg.exe for --mode custom.")
    args = parser.parse_args(argv)
    if args.mode == "custom" and not args.custom_path:
        parser.error("--custom-path is required for --mode custom")
    selected = None if args.mode == "saved" else {
        "tools": {"ffmpeg": {
            "mode": args.mode, "custom_path": args.custom_path
        }}
    }
    status = ffmpeg_status(selected)
    print("Selected source:", status["source"])
    print("FFmpeg:", status["ffmpeg_path"] or "unavailable")
    print("FFprobe:", status["ffprobe_path"] or "unavailable")
    if not status["available"] or not status["probe_available"]:
        print("FAIL  " + status["message"])
        return 1
    print("PASS  FFmpeg and FFprobe version checks")
    try:
        with tempfile.TemporaryDirectory(prefix="morphorum-ffmpeg-acceptance-") as directory:
            root = Path(directory)
            frames = root / "frames"
            frames.mkdir()
            for index in range(FRAME_COUNT):
                _write_png(frames / ("frame_" + str(index).zfill(6) + ".png"), index)
            _write_wave(root / "source.wav")
            ffmpeg = status["ffmpeg_path"]
            probe = status["ffprobe_path"]
            _video(ffmpeg, probe, root, "mp4", "libx264", "aac")
            _video(ffmpeg, probe, root, "webm", "libvpx-vp9", "libopus")
            _audio(ffmpeg, probe, root)
    except AcceptanceFailure as exc:
        print("FAIL  " + str(exc))
        return 1
    print("PASS  P4.4.4 media smoke tests (no GPU, no project files modified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
