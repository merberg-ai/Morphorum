from __future__ import annotations

import argparse

import morphorum.cli as cli


def _args(**overrides):
    values = {
        "host": None,
        "port": None,
        "access_log": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_serve_disables_uvicorn_access_log_by_default(monkeypatch) -> None:
    captured = {}

    def fake_run(app, **kwargs):
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setattr(cli, "ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    monkeypatch.delenv("MORPHORUM_ACCESS_LOG", raising=False)

    assert cli.command_serve(_args()) == 0
    assert captured["access_log"] is False


def test_serve_can_enable_uvicorn_access_log(monkeypatch) -> None:
    captured = {}

    def fake_run(app, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(cli, "ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr(cli.uvicorn, "run", fake_run)

    cli.command_serve(_args(access_log=True))
    assert captured["access_log"] is True

    captured.clear()
    monkeypatch.setenv("MORPHORUM_ACCESS_LOG", "1")
    cli.command_serve(_args())
    assert captured["access_log"] is True



def test_seed_example_command_reports_creation_and_existing_library(
    monkeypatch, capsys
) -> None:
    command = cli.build_parser().parse_args(["seed-example"])
    assert command.func is cli.command_seed_example
    example = {"name": "Default", "animation": {"mode": "3d", "max_frames": 120}}
    monkeypatch.setattr(cli, "seed_example_animation_project", lambda: example)
    assert command.func(command) == 0
    assert "Created starter project: Default (3D, 120 frames)" in capsys.readouterr().out

    monkeypatch.setattr(cli, "seed_example_animation_project", lambda: None)
    assert command.func(command) == 0
    assert "Existing animation projects preserved" in capsys.readouterr().out


def test_seed_example_command_surfaces_template_errors(monkeypatch, capsys) -> None:
    def broken():
        raise RuntimeError("template malformed")
    monkeypatch.setattr(cli, "seed_example_animation_project", broken)
    assert cli.command_seed_example(argparse.Namespace()) == 1
    assert "template malformed" in capsys.readouterr().err
