"""Branch-pinned, host-local source updater used by the About page.

Only an explicitly confirmed update on the host may launch the existing installer
update scripts. No HTTP caller can supply a branch, executable, or Git arguments.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import threading
from pathlib import Path

from .paths import ROOT


class GitUpdateError(RuntimeError):
    pass


def _git(*args: str, timeout: int = 30) -> str:
    try:
        process = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True, text=True, errors="replace", timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitUpdateError(f"Git could not finish: {exc}") from exc
    if process.returncode:
        detail = (process.stderr or process.stdout or "Git returned an error.").strip()
        raise GitUpdateError(detail[:700])
    return process.stdout.strip()


def _identity() -> dict:
    if not (ROOT / ".git").exists():
        raise GitUpdateError("This is not a Git installation. Use the regular installer to update.")
    head = _git("rev-parse", "HEAD")
    branch = _git("branch", "--show-current")
    if not branch or branch == "HEAD":
        raise GitUpdateError("Detached HEAD: switch to a named branch outside the WebUI first.")
    _git("check-ref-format", "--branch", branch)
    return {"branch": branch, "head": head, "dirty": bool(
        _git("status", "--porcelain", "--untracked-files=no")
    )}


def _remote_branch(branch: str) -> str:
    return "refs/remotes/origin/" + branch


def _log_excerpt(path: Path | None) -> str:
    if not path or not path.is_file():
        return ""
    try:
        with path.open("rb") as stream:
            stream.seek(max(0, stream.seek(0, os.SEEK_END) - 6000))
            return stream.read().decode("utf-8", errors="replace")[-3500:]
    except OSError:
        return ""


class GitUpdateManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._process: subprocess.Popen | None = None
        self._log_file: Path | None = None
        self._update_branch: str | None = None
        self._checked: dict | None = None

    def _process_status(self) -> dict:
        process = self._process
        code = process.poll() if process else None
        return {
            "running": process is not None and code is None,
            "exit_code": code,
            "branch": self._update_branch,
            "log_tail": _log_excerpt(self._log_file),
            "restart_required": process is not None and code == 0,
        }

    def status(self) -> dict:
        with self._lock:
            result: dict = {
                "platform": "windows" if os.name == "nt" else "linux",
                "repository": "https://github.com/merberg-ai/Morphorum",
                "update": self._process_status(),
                "check": self._checked,
                "supported": False,
            }
            try:
                identity = _identity()
                result.update(identity)
                result["supported"] = True
                if self._checked and (
                    identity["branch"] != self._checked["branch"]
                    or identity["head"] != self._checked["head"]
                ):
                    result["check"] = None
            except GitUpdateError as exc:
                result["message"] = str(exc)
            return result

    def check(self) -> dict:
        with self._lock:
            if self._process_status()["running"]:
                raise GitUpdateError("An update is already running.")
            identity = _identity()
            branch = identity["branch"]
            # Fetch exactly the checked-out branch. Never change the working branch.
            _git("fetch", "--no-tags", "origin",
                 "refs/heads/" + branch + ":" + _remote_branch(branch), timeout=90)
            remote_head = _git("rev-parse", _remote_branch(branch))
            counts = _git("rev-list", "--left-right", "--count",
                          "HEAD..." + _remote_branch(branch)).split()
            if len(counts) != 2:
                raise GitUpdateError("Could not compare local and remote commits.")
            ahead, behind = map(int, counts)
            state = ("diverged" if ahead and behind else
                     "ahead" if ahead else "behind" if behind else "current")
            checked = {
                **identity, "remote_head": remote_head, "ahead": ahead,
                "behind": behind, "state": state,
                "can_apply": behind > 0 and ahead == 0 and not identity["dirty"],
            }
            self._checked = checked
            return checked

    def start(self, *, expected_branch: str, expected_head: str,
              expected_remote_head: str, work_is_busy) -> dict:
        with self._lock:
            if self._process_status()["running"]:
                raise GitUpdateError("An update is already in progress.")
            if work_is_busy():
                raise GitUpdateError("A generation or animation is running. Finish it before updating.")
            if not self._checked or not self._checked["can_apply"]:
                raise GitUpdateError("Check for updates again before applying.")
            checked = self._checked
            identity = _identity()
            if (identity["branch"] != expected_branch or
                identity["head"] != expected_head or
                checked["remote_head"] != expected_remote_head or
                checked["branch"] != expected_branch or
                checked["head"] != expected_head or identity["dirty"]):
                raise GitUpdateError("Branch, commit, or worktree changed. Check again.")
            if work_is_busy():
                raise GitUpdateError("A render started during the update check.")
            if os.name == "nt":
                shell = shutil.which("powershell.exe") or shutil.which("powershell")
                script = ROOT / "scripts" / "update_windows.ps1"
                command = [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
            else:
                shell = shutil.which("bash")
                script = ROOT / "scripts" / "update_linux.sh"
                command = [shell, str(script)]
            if not shell or not script.is_file():
                raise GitUpdateError("The platform updater script or its shell is missing.")
            logs = ROOT / "data" / "update-logs"
            logs.mkdir(parents=True, exist_ok=True)
            import datetime
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
            path = logs / f"about-update-{stamp}-{os.getpid()}.log"
            # Run the existing backup/rollback updater with *no branch argument*.
            # That script independently reads the active branch and uses ff-only.
            with path.open("wb") as output:
                try:
                    self._process = subprocess.Popen(
                        command, cwd=str(ROOT), stdout=output,
                        stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                        **({"creationflags": subprocess.CREATE_NO_WINDOW}
                           if os.name == "nt" else {}),
                    )
                except OSError as exc:
                    raise GitUpdateError(f"Could not start the updater: {exc}") from exc
            self._log_file = path
            self._update_branch = expected_branch
            self._checked = None
            return self._process_status()


git_update_manager = GitUpdateManager()
