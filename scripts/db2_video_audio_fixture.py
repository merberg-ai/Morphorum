#!/usr/bin/env python3
"""DB2.5 GPU-free Windows backend audio/video export fixture.

Local administrator use only. Creates a labeled disposable Morphorum project,
12 PNG frames, a real PCM WAV and a frozen soundtrack render manifest.
Does not invoke inference or require a checkpoint. Cleanup is explicit and
checks a marker before removing anything.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import shutil
import struct
import uuid
import wave
from pathlib import Path

from PIL import Image

from morphorum.animation_projects import (
    animation_project_directory, create_animation_project,
    load_animation_project, trash_animation_project,
)
from morphorum.animation_render import _render_dir
from morphorum.imported_soundtrack import freeze_soundtrack, store_soundtrack
from morphorum.paths import DATA_DIR

RECEIPT = DATA_DIR / "db25-acceptance-fixture.json"
MARK = "morphorum-db25-audio-test-v1"


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("x", encoding="utf-8") as file:
            json.dump(data, file, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _wav() -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        samples = bytearray()
        for n in range(16000):
            sample = int(7000 * math.sin(2 * math.pi * 330 * n / 16000))
            samples.extend(struct.pack("<h", sample))
        stream.writeframes(samples)
    return out.getvalue()


def create() -> int:
    if RECEIPT.exists():
        raise RuntimeError(
            "A DB2.5 fixture receipt already exists. Reuse it or run cleanup explicitly."
        )
    name = "DB25 Audio Fixture " + uuid.uuid4().hex[:8]
    project = create_animation_project({"name": name})
    project_id = project["id"]
    render_id = "anim-db25-fixture-" + uuid.uuid4().hex[:12]
    output = _render_dir(project_id, render_id)
    if output.exists():
        raise RuntimeError("Refusing to overwrite an existing render.")
    output.mkdir(parents=True)
    try:
        frames = output / "frames"
        frames.mkdir()
        for i in range(12):
            Image.new("RGB", (64, 64), (15 + i * 12, 45, 110)).save(
                frames / f"frame_{i:06d}.png"
            )
        sound = _wav()
        store_soundtrack(project_id, sound, filename="db25-tone.wav", offset_seconds=0.0)
        frozen = freeze_soundtrack(project_id, output)
        if frozen is None:
            raise RuntimeError("Fixture failed to freeze its synthetic soundtrack.")
        project["animation"]["fps"] = 12
        project["animation"]["max_frames"] = 12
        project["_imported_soundtrack_snapshot"] = frozen
        manifest = {
            "schema_version": 1,
            "id": render_id, "project_id": project_id, "status": "completed",
            "message": "Synthetic completed render for DB2.5 FFmpeg acceptance",
            "total_frames": 12, "progress": 1.0,
            "results": [{"frame": i} for i in range(12)],
            "project": project,
            "db25_fixture": MARK,
        }
        _write_json(output / "render-manifest.json", manifest)
        Image.open(frames / "frame_000000.png").save(
            output / "preview.gif", format="GIF"
        )
        _write_json(RECEIPT, {
            "fixture": MARK, "project_id": project_id, "render_id": render_id
        })
    except BaseException:
        shutil.rmtree(output, ignore_errors=True)
        trash_animation_project(project_id)
        raise
    print("[PASS] Synthetic audio and 12 PNG frames created")
    print("[PASS] Frozen soundtrack snapshot saved (no GPU)")
    print("PROJECT_ID=" + project_id)
    print("RENDER_ID=" + render_id)
    print("RESULT: 2/2 PASSED")
    return 0


def cleanup() -> int:
    if not RECEIPT.is_file():
        raise RuntimeError("No DB2.5 fixture receipt found.")
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    if receipt.get("fixture") != MARK:
        raise RuntimeError("Refusing to clean up an unrecognized fixture receipt.")
    project_id = str(receipt["project_id"])
    render_id = str(receipt["render_id"])
    if not project_id.startswith("db25-audio-fixture-") or not render_id.startswith("anim-db25-fixture-"):
        raise RuntimeError("Fixture IDs are not in the expected disposable namespace.")
    output = _render_dir(project_id, render_id)
    manifest = json.loads((output / "render-manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("db25_fixture") != MARK or
            manifest.get("project_id") != project_id or manifest.get("id") != render_id):
        raise RuntimeError("Fixture render verification failed; no files removed.")
    project = load_animation_project(project_id)
    if not str(project["name"]).startswith("DB25 Audio Fixture "):
        raise RuntimeError("Fixture project name verification failed.")
    # The project remains recoverable from Trash; remove only proven fixture render outputs.
    trash_animation_project(project_id)
    shutil.rmtree(output)
    RECEIPT.unlink()
    print("[PASS] Only marked test render outputs removed")
    print("[PASS] Test project moved to Morphorum Trash")
    print("RESULT: 2/2 PASSED")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("create", "show", "cleanup"))
    args = parser.parse_args()
    try:
        if args.action == "create":
            return create()
        if args.action == "cleanup":
            return cleanup()
        if not RECEIPT.exists():
            raise RuntimeError("No fixture receipt exists. Run create first.")
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        if receipt.get("fixture") != MARK:
            raise RuntimeError("Invalid fixture receipt.")
        print("PROJECT_ID=" + receipt["project_id"])
        print("RENDER_ID=" + receipt["render_id"])
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print("[FAIL] " + str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
