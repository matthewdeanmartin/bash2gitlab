# tests/test_autogit.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import bash2gitlab.commands.autogit as autogit_mod
from bash2gitlab.commands.autogit import run_autogit
from bash2gitlab.errors.exceptions import ConfigInvalid


@dataclass
class FakeConfig:
    # only the attributes that run_autogit touches
    autogit_mode: str | None = None
    input_dir: str | None = None
    output_dir: str | None = None
    autogit_commit_message: str | None = None
    autogit_remote: str | None = None
    autogit_branch: str | None = None


class FakeCompleted:
    def __init__(self, stdout: str = "", stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = 0


def _fake_git_factory(
    *,
    repo_root: Path,
    has_changes: bool = False,
    current_branch: str = "feature/fake",
    fail_on: tuple[str, ...] = (),
):
    """
    Returns a (fake_run, calls) tuple.
    fake_run emulates subprocess.run used by autogit._run_git_command.
    'calls' captures each invocation for assertions.
    """
    calls: list[dict[str, Any]] = []

    def fake_run(args, capture_output, text, check, cwd, encoding):
        # Record the call
        calls.append(
            {
                "args": list(args),
                "cwd": Path(cwd) if cwd is not None else None,
                "check": check,
            }
        )

        assert args[0] == "git", "autogit should be invoking 'git'"
        cmd = args[1:]

        # Simulate explicit failures
        if any(cmd[: len(f)] == list(f.split()) for f in fail_on):
            from subprocess import CalledProcessError

            raise CalledProcessError(returncode=1, cmd=args, stderr="boom")

        # Map a few specific commands
        if cmd == ["rev-parse", "--show-toplevel"]:
            return FakeCompleted(stdout=str(repo_root))
        if cmd == ["status", "--porcelain"]:
            return FakeCompleted(stdout="M something\n" if has_changes else "")
        if cmd == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return FakeCompleted(stdout=current_branch)
        # For add/commit/push, just succeed
        return FakeCompleted(stdout="ok")

    return fake_run, calls


def _mk_paths(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    input_dir = repo / "in"
    output_dir = repo / "out"
    input_dir.mkdir()
    output_dir.mkdir()
    # Put a file in there so relative paths are non-empty and realistic
    (input_dir / "a.txt").write_text("x", encoding="utf-8")
    (output_dir / "b.txt").write_text("y", encoding="utf-8")
    return repo, input_dir, output_dir


def test_autogit_off_returns_0(monkeypatch, tmp_path):
    repo, in_dir, out_dir = _mk_paths(tmp_path)
    cfg = FakeConfig(
        autogit_mode="off",
        input_dir=str(in_dir),
        output_dir=str(out_dir),
    )

    # Ensure no git process is attempted
    def sentinel(*a, **k):
        raise AssertionError("git should not run when autogit is 'off'")

    monkeypatch.setattr(autogit_mod.subprocess, "run", sentinel)

    assert run_autogit(cfg) == 0


def test_autogit_stage_no_changes(monkeypatch, tmp_path):
    repo, in_dir, out_dir = _mk_paths(tmp_path)
    fake_run, calls = _fake_git_factory(repo_root=repo, has_changes=False)
    monkeypatch.setattr(autogit_mod.subprocess, "run", fake_run)

    cfg = FakeConfig(
        autogit_mode="stage",
        input_dir=str(in_dir),
        output_dir=str(out_dir),
    )

    rc = run_autogit(cfg)
    assert rc == 0

    # Expected sequence: rev-parse, add, status
    seq = [c["args"][1:] for c in calls]
    assert ["rev-parse", "--show-toplevel"] in seq
    assert ["status", "--porcelain"] in seq
    # Confirm add used relative paths from repo root
    add_idx = next(i for i, c in enumerate(calls) if c["args"][1] == "add")
    add_args = calls[add_idx]["args"][2:]  # after 'git add'
    assert set(add_args) == {'-A', '--', 'in', 'out'}
    # cwd should be repo root for all calls
    # assert all(c["cwd"] == repo for c in calls)


def test_autogit_commit_with_changes_and_custom_message(monkeypatch, tmp_path):
    repo, in_dir, out_dir = _mk_paths(tmp_path)
    fake_run, calls = _fake_git_factory(repo_root=repo, has_changes=True)
    monkeypatch.setattr(autogit_mod.subprocess, "run", fake_run)

    cfg = FakeConfig(
        autogit_mode="commit",
        input_dir=str(in_dir),
        output_dir=str(out_dir),
        autogit_commit_message="chore: from config",
    )

    rc = run_autogit(cfg, commit_message="feat: override from arg")
    assert rc == 0

    # Ensure commit used the override message
    commit = next(c for c in calls if c["args"][1] == "commit")
    assert commit["args"][2:] == ["-m", "feat: override from arg"]


def test_autogit_push_with_explicit_branch(monkeypatch, tmp_path):
    repo, in_dir, out_dir = _mk_paths(tmp_path)
    fake_run, calls = _fake_git_factory(repo_root=repo, has_changes=True)
    monkeypatch.setattr(autogit_mod.subprocess, "run", fake_run)

    cfg = FakeConfig(
        autogit_mode="push",
        input_dir=str(in_dir),
        output_dir=str(out_dir),
        autogit_commit_message="msg",
        autogit_remote="origin",
        autogit_branch="main",
    )

    rc = run_autogit(cfg)
    assert rc == 0

    # Should NOT call 'rev-parse --abbrev-ref HEAD' because branch is provided
    assert all(c["args"][1:4] != ["rev-parse", "--abbrev-ref", "HEAD"] for c in calls)
    # Should push origin main
    push = next(c for c in calls if c["args"][1] == "push")
    assert push["args"][2:] == ["origin", "main"]


def test_autogit_push_without_branch_uses_current(monkeypatch, tmp_path):
    repo, in_dir, out_dir = _mk_paths(tmp_path)
    fake_run, calls = _fake_git_factory(repo_root=repo, has_changes=True, current_branch="dev-123")
    monkeypatch.setattr(autogit_mod.subprocess, "run", fake_run)

    cfg = FakeConfig(
        autogit_mode="push",
        input_dir=str(in_dir),
        output_dir=str(out_dir),
        autogit_commit_message="msg",
        autogit_remote="origin",
        autogit_branch=None,  # force lookup
    )

    rc = run_autogit(cfg)
    assert rc == 0

    # Confirm branch discovery and push to that branch
    assert any(c["args"][1:4] == ["rev-parse", "--abbrev-ref", "HEAD"] for c in calls)
    push = next(c for c in calls if c["args"][1] == "push")
    assert push["args"][2:] == ["origin", "dev-123"]


def test_autogit_missing_dirs_raises(monkeypatch, tmp_path):
    # No need to monkeypatch git because it should fail before any git call
    cfg1 = FakeConfig(autogit_mode="stage", input_dir=None, output_dir="/x")
    cfg2 = FakeConfig(autogit_mode="stage", input_dir="/x", output_dir=None)

    with pytest.raises(ConfigInvalid):
        run_autogit(cfg1)
    with pytest.raises(ConfigInvalid):
        run_autogit(cfg2)


def test_autogit_git_not_found_returns_1(monkeypatch, tmp_path):
    repo, in_dir, out_dir = _mk_paths(tmp_path)

    def fake_run(*a, **k):
        raise FileNotFoundError("git not installed")

    monkeypatch.setattr(autogit_mod.subprocess, "run", fake_run)

    cfg = FakeConfig(autogit_mode="stage", input_dir=str(in_dir), output_dir=str(out_dir))
    assert run_autogit(cfg) == 1
