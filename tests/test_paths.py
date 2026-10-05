from morphorum.paths import (
    BACKUPS_DIR,
    CACHE_DIR,
    DATA_DIR,
    LOGS_DIR,
    OUTPUTS_DIR,
    PROJECTS_DIR,
    ROOT,
)


def test_runtime_paths_live_under_repository_root() -> None:
    for path in (DATA_DIR, PROJECTS_DIR, OUTPUTS_DIR, LOGS_DIR, CACHE_DIR, BACKUPS_DIR):
        assert path.parent == ROOT


def test_runtime_paths_are_distinct() -> None:
    paths = {DATA_DIR, PROJECTS_DIR, OUTPUTS_DIR, LOGS_DIR, CACHE_DIR, BACKUPS_DIR}
    assert len(paths) == 6
