from __future__ import annotations

import json

import morphorum.system_info as system_info


def test_windows_gpu_process_memory_is_explicitly_unavailable_off_windows(monkeypatch) -> None:
    monkeypatch.setattr(system_info.platform, "system", lambda: "Linux")
    result = system_info.windows_gpu_process_memory(pid=123)
    assert result["available"] is False
    assert result["pid"] == 123
    assert result["source"] == "windows-performance-counters"
    assert "only available on Windows" in result["reason"]


def test_windows_gpu_process_memory_parses_dedicated_and_shared_bytes(monkeypatch) -> None:
    monkeypatch.setattr(system_info.platform, "system", lambda: "Windows")
    monkeypatch.setattr(system_info.shutil, "which", lambda name: "powershell.exe" if name == "powershell.exe" else None)

    captured = {}

    def fake_run(command, timeout=8):
        captured["command"] = command
        captured["timeout"] = timeout
        return json.dumps({
            "pid": 456,
            "dedicated_bytes": 12 * 1024**3,
            "shared_bytes": 1536 * 1024**2,
            "sample_count": 4,
        })

    monkeypatch.setattr(system_info, "_run", fake_run)
    result = system_info.windows_gpu_process_memory(pid=456)

    assert result["available"] is True
    assert result["dedicated_gib"] == 12.0
    assert result["shared_gib"] == 1.5
    assert result["sample_count"] == 4
    assert result["process_instances_found"] is True
    assert result["diagnostic_only"] is True
    assert captured["timeout"] == 5
    assert "GPU Process Memory" in captured["command"][-1]
    assert "pid_' + $targetPid" in captured["command"][-1]


def test_windows_gpu_process_memory_handles_counter_failure(monkeypatch) -> None:
    monkeypatch.setattr(system_info.platform, "system", lambda: "Windows")
    monkeypatch.setattr(system_info.shutil, "which", lambda _name: "powershell.exe")
    monkeypatch.setattr(system_info, "_run", lambda *_args, **_kwargs: None)

    result = system_info.windows_gpu_process_memory(pid=789)
    assert result["available"] is False
    assert "could not be read" in result["reason"]


def test_windows_gpu_process_memory_handles_unreadable_output(monkeypatch) -> None:
    monkeypatch.setattr(system_info.platform, "system", lambda: "Windows")
    monkeypatch.setattr(system_info.shutil, "which", lambda _name: "powershell.exe")
    monkeypatch.setattr(system_info, "_run", lambda *_args, **_kwargs: "not-json")

    result = system_info.windows_gpu_process_memory(pid=999)
    assert result["available"] is False
    assert "unreadable" in result["reason"]
