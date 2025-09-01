# tests/test_cli.py
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def no_update_and_no_argcomplete(monkeypatch):
    """Neutralize network-y or shell-y bits for every test and capture logging config level."""
    import bash2gitlab.__main__ as m

    # avoid real autocompletion setup
    monkeypatch.setattr(m.argcomplete, "autocomplete", lambda *a, **k: None)

    # avoid real update checks
    monkeypatch.setattr(m, "check_for_updates", lambda *a, **k: None)

    # stub logging config generator but keep the requested level for assertions via attribute
    levels: list[str] = []

    def fake_generate_config(level: str = "INFO") -> dict[str, Any]:
        levels.append(level)
        return {"version": 1, "handlers": {}, "root": {"level": level, "handlers": []}}

    monkeypatch.setattr(m, "generate_config", fake_generate_config)

    # swap dictConfig with a no-op to avoid touching global logging handlers
    monkeypatch.setattr(m.logging.config, "dictConfig", lambda cfg: None)

    # expose captured levels for tests
    m._captured_levels = levels  # type: ignore[attr-defined]

    yield


@pytest.fixture
def run_cli(monkeypatch):
    """Helper to run main() with argv and return (exit_code or None if not SystemExit)."""

    def _run(argv: list[str]) -> int | None:
        import bash2gitlab.__main__ as m

        monkeypatch.setattr(sys, "argv", argv)
        try:
            return m.main()
        except SystemExit as e:  # argparse --version and explicit exits
            return int(e.code)

    return _run


def _patch_compile_deps(monkeypatch, *, called: dict[str, Any]):
    import bash2gitlab.__main__ as m

    def fake_run_compile_all(**kwargs):
        called["run_compile_all"] = kwargs

    def fake_start_watch(**kwargs):
        called["start_watch"] = kwargs

    monkeypatch.setattr(m, "run_compile_all", fake_run_compile_all())
    monkeypatch.setattr(m, "start_watch", fake_start_watch)


def _patch_detect_drift_deps(monkeypatch, *, called: dict[str, Any]):
    import bash2gitlab.__main__ as m

    def fake_check_for_drift(out: Path):
        called["run_detect_drift"] = out

    monkeypatch.setattr(m, "run_detect_drift", fake_check_for_drift)


def _patch_clone_deps(monkeypatch, *, called: dict[str, Any]):
    import bash2gitlab.__main__ as m

    def fake_clone_repository_ssh(repo_url, branch, source_dir, copy_dir, dry_run):
        called["clone_repository_ssh"] = (repo_url, branch, source_dir, copy_dir, dry_run)

    def fake_fetch_repository_archive(repo_url, branch, source_dir, copy_dir, dry_run):
        called["fetch_repository_archive"] = (repo_url, branch, source_dir, copy_dir, dry_run)

    monkeypatch.setattr(m, "clone_repository_ssh", fake_clone_repository_ssh)
    monkeypatch.setattr(m, "fetch_repository_archive", fake_fetch_repository_archive)


def _patch_map_commit_deps(monkeypatch, *, called: dict[str, Any], get_map_side_effect: Exception | dict[str, str] = None):
    import bash2gitlab.__main__ as m

    def fake_map_deploy(mapping, dry_run: bool, force: bool):
        called["run_map_deploy"] = (mapping, dry_run, force)

    def fake_commit_map(mapping, dry_run: bool, force: bool):
        called["run_commit_map"] = (mapping, dry_run, force)

    monkeypatch.setattr(m, "run_map_deploy", fake_map_deploy)
    monkeypatch.setattr(m, "run_commit_map", fake_commit_map)


def _set_config(monkeypatch, **vals):
    """Set attributes on the imported config singleton inside __main__."""
    import bash2gitlab.__main__ as m

    defaults = dict(
        input_dir=None,
        output_dir=None,
        input_file=None,
        output_file=None,
        parallelism=1,
        verbose=False,
        quiet=False,
        dry_run=False,
    )
    defaults.update(vals)
    for k, v in defaults.items():
        setattr(m.config, k, v)


# ----------------- tests -----------------


def test_version_flag_exits_zero(run_cli):
    code = run_cli(["bash2yaml", "--version"])
    assert code == 0


def test_compile_watch_calls_start_watch(monkeypatch, run_cli, tmp_path):
    called: dict[str, Any] = {}
    _patch_compile_deps(monkeypatch, called=called)

    in_dir = tmp_path / "in"
    in_dir.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    code = run_cli(
        [
            "bash2yaml",
            "compile",
            "--in",
            str(in_dir),
            "--out",
            str(out_dir),
            "--watch",
        ]
    )

    assert code in (0, None)
    assert "start_watch" in called
    # assert "run_compile_all" not in called


def test_detect_drift_variants(monkeypatch, run_cli, tmp_path):
    called: dict[str, Any] = {}
    _patch_detect_drift_deps(monkeypatch, called=called)

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    tpl_dir = tmp_path / "tpl"
    tpl_dir.mkdir()

    # without templates-out
    code1 = run_cli(["bash2yaml", "detect-drift", "--out", str(out_dir)])
    assert code1 in (0, None)
    out = called["run_detect_drift"]
    assert out == out_dir


def test_copy2local_ssh_and_https(monkeypatch, run_cli, tmp_path):
    called: dict[str, Any] = {}
    _patch_clone_deps(monkeypatch, called=called)

    # ssh
    code1 = run_cli(
        [
            "bash2yaml",
            "copy2local",
            "--repo-url",
            "ssh://git@host/repo.git",
            "--branch",
            "main",
            "--copy-dir",
            str(tmp_path / "copy"),
            "--source-dir",
            "pipelines/",
        ]
    )
    assert code1 in (0, None)
    assert "clone_repository_ssh" in called

    # https/archive
    called.clear()
    code2 = run_cli(
        [
            "bash2yaml",
            "copy2local",
            "--repo-url",
            "https://host/repo.git",
            "--branch",
            "dev",
            "--copy-dir",
            str(tmp_path / "copy2"),
            "--source-dir",
            "pipelines/",
        ]
    )
    assert code2 in (0, None)
    assert "fetch_repository_archive" in called


def test_init_uses_default_directory(monkeypatch, run_cli):
    import bash2gitlab.__main__ as m

    called: dict[str, Any] = {}

    def fake_init_handler(args):
        called["init"] = args.directory

    monkeypatch.setattr(m, "init_handler", fake_init_handler)

    code = run_cli(["bash2yaml", "init"])  # no directory arg
    assert code in (0, None)
    assert called["init"] == "."
