from __future__ import annotations

# Import the module under test
import importlib
import os
from pathlib import Path

import pytest

# We'll import config and the precommit module explicitly so we can reset config between tests
from bash2gitlab import config as cfg_module


def write_pyproject(path: Path, input_dir: str = "ci", output_dir: str = "compiled") -> None:
    content = f"""
[tool.bash2gitlab]
input_dir = "{input_dir}"
output_dir = "{output_dir}"
"""
    (path / "pyproject.toml").write_text(content.strip() + "\n", encoding="utf-8")


def make_git_repo(tmp_path: Path) -> Path:
    """Create a bare-minimum git working tree structure that our code accepts."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    # create minimal config
    (repo / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    return repo


def make_git_repo_with_gitdir_file(tmp_path: Path) -> Path:
    """Simulate a worktree: .git is a file pointing to real dir."""
    repo = tmp_path / "repo"
    repo.mkdir()
    real_git = tmp_path / "gitdir"
    (real_git).mkdir()
    (real_git / "config").write_text("[core]\n", encoding="utf-8")
    (repo / ".git").write_text(f"gitdir: {real_git.as_posix()}\n", encoding="utf-8")
    return repo


def reload_precommit_module():
    # Ensure module picks up the latest config singleton
    return importlib.import_module("bash2gitlab.commands.precommit")  # adjust to your module path


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # Remove env so tests control presence explicitly
    for k in list(os.environ.keys()):
        if k.startswith("BASH2GITLAB_"):
            monkeypatch.delenv(k, raising=False)
    yield


def test_install_requires_git_repo(tmp_path):
    repo_root = tmp_path / "not_a_repo"
    repo_root.mkdir()
    # reset config singleton with no file present
    cfg_module.reset_for_testing(config_path_override=None)
    mod = reload_precommit_module()
    with pytest.raises(mod.PrecommitHookError):
        mod.install(repo_root)


def test_install_requires_config_when_missing(tmp_path):
    repo = make_git_repo(tmp_path)
    cfg_module.reset_for_testing(config_path_override=None)
    mod = reload_precommit_module()

    with pytest.raises(mod.PrecommitHookError) as ei:
        mod.install(repo)
    assert "Missing bash2gitlab input/output" in str(ei.value)


def test_install_with_env_vars(tmp_path, monkeypatch):
    repo = make_git_repo(tmp_path)
    cfg_module.reset_for_testing(config_path_override=None)
    mod = reload_precommit_module()

    monkeypatch.setenv("BASH2GITLAB_INPUT_DIR", "ci")
    monkeypatch.setenv("BASH2GITLAB_OUTPUT_DIR", "compiled")

    mod.install(repo)
    hook = mod.hook_path(repo)
    assert hook.is_file()
    assert hook.read_text(encoding="utf-8") == mod.HOOK_CONTENT

    # idempotent
    mod.install(repo)
    assert hook.read_text(encoding="utf-8") == mod.HOOK_CONTENT


def test_uninstall_when_missing_is_ok(tmp_path, caplog):
    repo = make_git_repo(tmp_path)
    write_pyproject(repo)
    cfg_module.reset_for_testing(config_path_override=None)
    mod = reload_precommit_module()

    mod.uninstall(repo)  # should not raise
    assert "No pre-commit hook to uninstall" in "\n".join(m for _, _, m in caplog.record_tuples)


def test_uninstall_conflict_requires_force(tmp_path):
    repo = make_git_repo(tmp_path)
    write_pyproject(repo)
    cfg_module.reset_for_testing(config_path_override=None)
    mod = reload_precommit_module()

    # write a non-matching hook
    hp = mod.hook_path(repo)
    hp.parent.mkdir(parents=True, exist_ok=True)
    hp.write_text("# other hook\n", encoding="utf-8")

    with pytest.raises(mod.PrecommitHookError):
        mod.uninstall(repo)

    # force works
    mod.uninstall(repo, force=True)
    assert not hp.exists()
