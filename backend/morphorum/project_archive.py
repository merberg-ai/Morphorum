"""Portable Morphorum project archives (settings and attached input media only).

Never extract arbitrary zip members or include render/cache/output directories.
Archives contain a small hashed manifest; import is validated before replacing
any saved project and replacement keeps the old copy in project Trash.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import stat
import uuid
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import animation_projects as projects
from .project_assets import ProjectAssetError, catalog_with_warnings

ARCHIVE_FORMAT = "morphorum.project.archive"
ARCHIVE_VERSION = 1
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_PROJECT_JSON_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_FILES = 128
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MOTION_FILE = re.compile(r"^motion_lab_audio/[0-9a-f]{64}\.wav$")
_SOUND_FILE = re.compile(r"^imported_soundtrack/[0-9a-f]{64}\.(wav|mp3|ogg|flac)$")
_PS_DRAFT_FILE = re.compile(r"^prompt_studio/drafts/[0-9a-f]{32}\.json$")
_ALLOWED_FIXED = {"project.json", "assets/source.png",
                  "imported_soundtrack/attachment.json"}


class ProjectArchiveError(ValueError):
    pass


class ProjectArchiveConflict(ProjectArchiveError):
    pass


def _safe_member(name: str) -> bool:
    return (name in _ALLOWED_FIXED
            or bool(_MOTION_FILE.fullmatch(name))
            or bool(_SOUND_FILE.fullmatch(name))
            or bool(_PS_DRAFT_FILE.fullmatch(name)))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _input_files(project_id: str) -> dict[str, Path]:
    """Enumerate only verified project-owned inputs, never arbitrary files."""
    project = projects.load_animation_project(project_id)
    root = projects.animation_project_directory(project_id)
    if (projects.PROJECTS_DIR / project_id).is_symlink() or not root.is_dir():
        raise ProjectArchiveError("Project directory is unsafe or missing.")
    inventory = catalog_with_warnings(project_id, project)
    if inventory["warnings"]:
        raise ProjectArchiveError(
            "Repair missing or damaged input media before export: " +
            "; ".join(inventory["warnings"][:3]))
    files: dict[str, Path] = {"project.json": root / "project.json"}
    for asset in inventory["assets"]:
        if asset["kind"] == "source_image":
            relative = "assets/source.png"
        elif asset["kind"] == "soundtrack":
            # Original user filename may have a different extension case;
            # stored metadata is the authoritative format.
            from .imported_soundtrack import read_soundtrack
            record = read_soundtrack(project_id)
            if record is None:
                raise ProjectArchiveError("Soundtrack metadata is missing.")
            relative = "imported_soundtrack/" + record["sha256"] + "." + record["format"]
            files["imported_soundtrack/attachment.json"] = root / "imported_soundtrack" / "attachment.json"
        elif asset["kind"] == "motion_lab_wav":
            relative = "motion_lab_audio/" + asset["sha256"] + ".wav"
        else:
            raise ProjectArchiveError("Unsupported input asset type.")
        files[relative] = root / relative
    # Only validated project-owned Studio drafts are eligible. No cache/output files.
    from .prompt_studio_drafts import draft_files
    files.update(draft_files(project_id))
    if len(files) > MAX_ARCHIVE_FILES:
        raise ProjectArchiveError("Project contains too many input assets.")
    for name, path in files.items():
        if not _safe_member(name) or path.is_symlink() or not path.is_file():
            raise ProjectArchiveError("Unsafe or missing project input: " + name)
    return files


def _archive_bytes(project_id: str, *, project_override: dict | None = None) -> bytes:
    files = _input_files(project_id)
    project = project_override or projects.load_animation_project(project_id)
    payloads: dict[str, bytes] = {}
    total = 0
    for name, path in files.items():
        data = (json.dumps(project, indent=2, ensure_ascii=False).encode("utf-8")
                if name == "project.json" and project_override is not None else path.read_bytes())
        if not data or (name == "project.json" and len(data) > MAX_PROJECT_JSON_BYTES):
            raise ProjectArchiveError("Invalid project configuration.")
        total += len(data)
        if total > MAX_EXPANDED_BYTES:
            raise ProjectArchiveError("Project inputs exceed the 512 MiB archive limit.")
        payloads[name] = data
    manifest = {
        "format": ARCHIVE_FORMAT, "version": ARCHIVE_VERSION,
        "project_id": project["id"], "project_name": project["name"],
        "files": [{"path": n, "size": len(payloads[n]), "sha256": _sha(payloads[n])}
                  for n in sorted(payloads)],
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=4, allowZip64=False) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))
        for name in sorted(payloads):
            archive.writestr(name, payloads[name])
    if stream.tell() > MAX_ARCHIVE_BYTES:
        raise ProjectArchiveError("Archive exceeds the 256 MiB download/upload limit.")
    return stream.getvalue()


def export_project_archive(project_id: str) -> bytes:
    try:
        return _archive_bytes(project_id)
    except (ProjectAssetError, OSError, ValueError, zipfile.BadZipFile) as exc:
        raise ProjectArchiveError(str(exc)) from exc


def _verified_archive(data: bytes) -> tuple[dict, dict[str, bytes]]:
    if not data or len(data) > MAX_ARCHIVE_BYTES:
        raise ProjectArchiveError("Archive must be a ZIP at most 256 MiB.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data), "r")
        with archive:
            infos = archive.infolist()
            names = [i.filename for i in infos]
            if len(names) < 2 or len(names) > MAX_ARCHIVE_FILES + 1 or len(set(names)) != len(names):
                raise ProjectArchiveError("Invalid or duplicate archive members.")
            if "manifest.json" not in names or "project.json" not in names:
                raise ProjectArchiveError("Not a Morphorum project archive.")
            total = 0
            for info in infos:
                name = info.filename
                if (name != "manifest.json" and not _safe_member(name)) or (
                        info.is_dir() or info.flag_bits & 1 or
                        (info.create_system == 3 and
                         stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK)):
                    raise ProjectArchiveError("Unsafe or unsupported ZIP entry: " + name)
                if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise ProjectArchiveError("Unsupported ZIP compression.")
                from .prompt_studio_drafts import MAX_DRAFT_BYTES
                limit = (MAX_DRAFT_BYTES if _PS_DRAFT_FILE.fullmatch(name)
                         else MAX_PROJECT_JSON_BYTES if name in ("manifest.json", "project.json")
                         else 40 * 1024 * 1024)
                if info.file_size < 1 or info.file_size > limit:
                    raise ProjectArchiveError("Invalid ZIP entry size: " + name)
                total += info.file_size
                if total > MAX_EXPANDED_BYTES:
                    raise ProjectArchiveError("ZIP exceeds allowed expanded size.")
            manifest = json.loads(archive.read("manifest.json"))
            if not isinstance(manifest, dict) or manifest.get("format") != ARCHIVE_FORMAT or (
                    manifest.get("version") != ARCHIVE_VERSION):
                raise ProjectArchiveError("Not a supported Morphorum project archive.")
            records = manifest.get("files")
            if not isinstance(records, list) or len(records) != len(names) - 1:
                raise ProjectArchiveError("Archive manifest file count does not match.")
            metadata: dict[str, dict] = {}
            for record in records:
                if not isinstance(record, dict):
                    raise ProjectArchiveError("Invalid manifest entry.")
                path = record.get("path")
                if not isinstance(path, str) or not _safe_member(path) or path in metadata:
                    raise ProjectArchiveError("Invalid manifest path.")
                if not isinstance(record.get("size"), int) or not (
                        isinstance(record.get("sha256"), str) and _DIGEST.fullmatch(record["sha256"])):
                    raise ProjectArchiveError("Invalid archive file digest.")
                metadata[path] = record
            if set(names) != set(metadata) | {"manifest.json"}:
                raise ProjectArchiveError("ZIP entries do not match archive manifest.")
            files = {}
            for name, record in metadata.items():
                raw = archive.read(name)
                if len(raw) != record["size"] or _sha(raw) != record["sha256"]:
                    raise ProjectArchiveError("File integrity check failed: " + name)
                files[name] = raw
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError, OSError,
            ValueError, TypeError, KeyError, RuntimeError) as exc:
        if isinstance(exc, ProjectArchiveError):
            raise
        raise ProjectArchiveError("Archive ZIP is malformed or corrupt.") from exc

    try:
        project = json.loads(files["project.json"])
        if not isinstance(project, dict) or project.get("schema_version") != projects.ANIMATION_PROJECT_SCHEMA:
            raise ProjectArchiveError("Unsupported project schema in archive.")
        name = str(project.get("name") or "").strip()
        project_id = str(project.get("id") or "")
        if not name or len(name) > 120 or not projects._PROJECT_ID.fullmatch(project_id):
            raise ProjectArchiveError("Project identity in archive is invalid.")
        if project_id != manifest.get("project_id") or name != manifest.get("project_name"):
            raise ProjectArchiveError("Project identity does not match archive manifest.")
        image_reference = (project.get("animation") or {}).get("source_image")
        if image_reference not in ("", None, "assets/source.png") or (
                ("assets/source.png" in files) != bool(image_reference)):
            raise ProjectArchiveError("Start image reference and included file do not match.")
        if "assets/source.png" in files:
            import io as image_io
            from PIL import Image, UnidentifiedImageError
            try:
                with Image.open(image_io.BytesIO(files["assets/source.png"])) as image:
                    if image.format != "PNG" or not all(1 <= size <= 8192 for size in image.size):
                        raise ProjectArchiveError("Invalid PNG start image.")
                    image.verify()
            except (UnidentifiedImageError, OSError, ValueError) as exc:
                raise ProjectArchiveError("Invalid PNG start image.") from exc
        if "imported_soundtrack/attachment.json" in files:
            attachment = json.loads(files["imported_soundtrack/attachment.json"])
            if not isinstance(attachment, dict) or not _DIGEST.fullmatch(str(attachment.get("sha256") or "")):
                raise ProjectArchiveError("Attached soundtrack metadata is invalid.")
            media = "imported_soundtrack/" + attachment["sha256"] + "." + str(attachment.get("format") or "")
            if media not in files or _sha(files[media]) != attachment["sha256"]:
                raise ProjectArchiveError("Attached soundtrack is missing or damaged.")
            raw_audio = files[media]
            fmt = attachment["format"]
            valid_audio = (
                (fmt == "wav" and raw_audio[:4] == b"RIFF" and raw_audio[8:12] == b"WAVE")
                or (fmt == "flac" and raw_audio.startswith(b"fLaC"))
                or (fmt == "ogg" and raw_audio.startswith(b"OggS"))
                or (fmt == "mp3" and (
                    raw_audio.startswith(b"ID3") or (
                        len(raw_audio) > 2 and raw_audio[0] == 0xff
                        and raw_audio[1] & 0xe0 == 0xe0)))
            )
            if not valid_audio:
                raise ProjectArchiveError("Attached soundtrack does not match its format.")
        elif any(n.startswith("imported_soundtrack/") for n in files):
            raise ProjectArchiveError("Soundtrack metadata is missing.")
        from .prompt_studio_drafts import validate_draft
        for path, raw in files.items():
            if _PS_DRAFT_FILE.fullmatch(path):
                try:
                    payload = json.loads(raw)
                    validated = validate_draft(payload, project_id, stored=True)
                    if path != f"prompt_studio/drafts/{validated['draft_id']}.json":
                        raise ProjectArchiveError("Prompt Studio draft ID does not match archive filename.")
                except (ValueError, UnicodeError, TypeError) as exc:
                    raise ProjectArchiveError("Invalid Prompt Studio draft in archive.") from exc
            if _MOTION_FILE.fullmatch(path) and (
                    _sha(raw) != Path(path).stem or
                    raw[:4] != b"RIFF" or raw[8:12] != b"WAVE"):
                raise ProjectArchiveError("Motion Lab WAV checksum or format mismatch.")
    except (ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, ProjectArchiveError):
            raise
        raise ProjectArchiveError("Invalid project configuration or media metadata.") from exc
    return project, files


def inspect_project_archive(data: bytes) -> dict[str, Any]:
    project, files = _verified_archive(data)
    dest = projects.animation_project_directory(project["id"])
    return {
        "valid": True, "project": {"id": project["id"], "name": project["name"]},
        "conflict": dest.exists(), "input_files": len(files) - 1,
        "input_bytes": sum(len(v) for n, v in files.items() if n != "project.json"),
    }


def import_project_archive(data: bytes, *, overwrite: bool = False) -> dict[str, Any]:
    project, files = _verified_archive(data)
    project_id = project["id"]
    root = projects.PROJECTS_DIR
    with projects._PROJECT_SAVE_LOCK:
        root.mkdir(parents=True, exist_ok=True)
        destination = projects.animation_project_directory(project_id)
        if destination.exists() and not overwrite:
            raise ProjectArchiveConflict("This project already exists. Confirm overwrite to replace it.")
        if (root / project_id).is_symlink() or (destination.exists() and not destination.is_dir()):
            raise ProjectArchiveError("Existing project folder is unsafe.")
        stage = root / (".archive-stage-" + uuid.uuid4().hex)
        backup: Path | None = None
        stage.mkdir()
        try:
            for name, raw in files.items():
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            if destination.exists():
                trash = root / ".trash"
                if trash.is_symlink():
                    raise ProjectArchiveError("Project Trash folder is unsafe.")
                trash.mkdir(exist_ok=True)
                backup = trash / (project_id + "-archive-backup-" + uuid.uuid4().hex[:12])
                destination.rename(backup)
            try:
                stage.rename(destination)
            except OSError:
                if backup is not None:
                    backup.rename(destination)
                raise
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
    return {"status": "overwritten" if backup else "imported",
            "project": projects.load_animation_project(project_id),
            "backup": bool(backup)}


def save_project_as(source_id: str, new_name: str, *,
                    draft: dict | None = None) -> dict[str, Any]:
    title = str(new_name or "").strip()
    if not title or len(title) > 120:
        raise ProjectArchiveError("New project name must be 1–120 characters.")
    with projects._PROJECT_SAVE_LOCK:
        existing = projects.load_animation_project(source_id)
        project = (projects.normalize_animation_project(
            draft, existing=existing, project_id=source_id, prefer_tracks=None)
            if draft is not None else deepcopy(existing))
        new_id = projects._slugify(title) + "-" + uuid.uuid4().hex[:8]
        project["id"] = new_id
        project["name"] = title
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        project["created_at"] = timestamp
        project["updated_at"] = timestamp
        assets = _input_files(source_id)
        root = projects.PROJECTS_DIR
        root.mkdir(parents=True, exist_ok=True)
        stage = root / (".archive-stage-" + uuid.uuid4().hex)
        destination = projects.animation_project_directory(new_id)
        stage.mkdir()
        try:
            for name, origin in assets.items():
                if name == "project.json":
                    continue
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if _PS_DRAFT_FILE.fullmatch(name):
                    from .prompt_studio_drafts import rewrite_draft_project
                    target.write_bytes(rewrite_draft_project(origin.read_bytes(), source_id, new_id))
                else:
                    shutil.copyfile(origin, target)
            (stage / "project.json").write_text(
                json.dumps(project, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            stage.rename(destination)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        return projects.load_animation_project(new_id)
