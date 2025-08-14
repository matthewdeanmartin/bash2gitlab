from __future__ import annotations

import os
from pathlib import Path

import pytest

# Adjust if your module path differs:
import bash2gitlab.commands.precommit as mod

# ---------- Helpers ----------


def write_pyproject(path: Path, input_dir: str = "ci", output_dir: str = "compiled") -> None:
    content = f"""
[tool.bash2gitlab]
input_dir = "{input_dir}"
output_dir = "{output_dir}"
"""
    (path / "pyproject.toml").write_text(content.strip() + "\n", encoding="utf-8")


def make_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    return repo


def make_git_repo_with_gitdir_file(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    real_git = tmp_path / "gitdir"
    real_git.mkdir()
    (real_git / "config").write_text("[core]\n", encoding="utf-8")
    (repo / ".git").write_text(f"gitdir: {real_git.as_posix()}\n", encoding="utf-8")
    return repo


def set_core_hooks_path(repo: Path, hooks_path: str) -> None:
    cfg = mod.resolve_git_dir(repo) / "config"
    cfg.write_text(f"[core]\n\thooksPath = {hooks_path}\n", encoding="utf-8")


class DummyCfg:
    """Minimal stand-in for the config singleton."""

    def __init__(self, input_dir: str | None, output_dir: str | None):
        self._input_dir = input_dir
        self._output_dir = output_dir

    @property
    def input_dir(self) -> str | None:
        return self._input_dir

    @property
    def output_dir(self) -> str | None:
        return self._output_dir


# ---------- Fixtures ----------


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # Ensure tests explicitly decide whether config comes from env
    for k in list(os.environ.keys()):
        if k.startswith("BASH2GITLAB_"):
            monkeypatch.delenv(k, raising=False)
    yield


@pytest.fixture
def swap_config(monkeypatch):
    """Temporarily replace the module's config object."""
    original = mod.config

    def _set(new_cfg):
        monkeypatch.setattr(mod, "config", new_cfg, raising=True)
        return new_cfg

    yield _set
    monkeypatch.setattr(mod, "config", original, raising=True)


# ---------- Tests (no importlib) ----------


def test_install_requires_git_repo(tmp_path, swap_config):
    repo_root = tmp_path / "not_a_repo"
    repo_root.mkdir()
    swap_config(DummyCfg("ci", "compiled"))  # even with config, not a repo should fail
    with pytest.raises(mod.PrecommitHookError):
        mod.install(repo_root)


def test_install_requires_config_when_missing(tmp_path, swap_config):
    repo = make_git_repo(tmp_path)
    swap_config(DummyCfg(None, None))  # simulate no TOML and no env
    with pytest.raises(mod.PrecommitHookError) as ei:
        mod.install(repo)
    assert "Missing bash2gitlab input/output" in str(ei.value)


def test_install_with_env_vars_only(tmp_path, monkeypatch, swap_config):
    repo = make_git_repo(tmp_path)
    # config object can be anything; env takes precedence
    swap_config(DummyCfg(None, None))
    monkeypatch.setenv("BASH2GITLAB_INPUT_DIR", "ci")
    monkeypatch.setenv("BASH2GITLAB_OUTPUT_DIR", "compiled")

    mod.install(repo)
    hook = mod.hook_path(repo)
    assert hook.is_file()
    assert hook.read_text(encoding="utf-8") == mod.HOOK_CONTENT

    # idempotent without force
    mod.install(repo)
    assert hook.read_text(encoding="utf-8") == mod.HOOK_CONTENT


def test_install_with_dummy_config_object(tmp_path, swap_config):
    repo = make_git_repo(tmp_path)
    swap_config(DummyCfg("ci", "compiled"))  # emulate TOML via dummy
    mod.install(repo)
    hook = mod.hook_path(repo)
    assert hook.is_file()
    assert hook.read_text(encoding="utf-8") == mod.HOOK_CONTENT


def test_install_conflict_requires_force(tmp_path, swap_config):
    repo = make_git_repo(tmp_path)
    swap_config(DummyCfg("ci", "compiled"))

    hp = mod.hook_path(repo)
    hp.parent.mkdir(parents=True, exist_ok=True)
    hp.write_text("# something else\n", encoding="utf-8")

    with pytest.raises(mod.PrecommitHookError):
        mod.install(repo, force=False)

    mod.install(repo, force=True)
    assert hp.read_text(encoding="utf-8") == mod.HOOK_CONTENT


def test_uninstall_when_missing_logs_warning(tmp_path, caplog, swap_config):
    repo = make_git_repo(tmp_path)
    swap_config(DummyCfg("ci", "compiled"))
    mod.uninstall(repo)
    text = "\n".join(rec.message for rec in caplog.records)
    assert "No pre-commit hook to uninstall" in text


def test_uninstall_conflict_requires_force(tmp_path, swap_config):
    repo = make_git_repo(tmp_path)
    swap_config(DummyCfg("ci", "compiled"))

    hp = mod.hook_path(repo)
    hp.parent.mkdir(parents=True, exist_ok=True)
    hp.write_text("# other hook\n", encoding="utf-8")

    with pytest.raises(mod.PrecommitHookError):
        mod.uninstall(repo)

    mod.uninstall(repo, force=True)
    assert not hp.exists()


def test_respects_core_hooksPath_relative(tmp_path, swap_config):
    repo = make_git_repo(tmp_path)
    swap_config(DummyCfg("ci", "compiled"))

    # put hooks under .githooks and point core.hooksPath there
    set_core_hooks_path(repo, ".githooks")
    target = repo / ".githooks" / "pre-commit"

    mod.install(repo)
    assert target.is_file()
    assert target.read_text(encoding="utf-8") == mod.HOOK_CONTENT


def test_hook_hash_changes_on_content_change():
    a = mod.hook_hash("hello")
    b = mod.hook_hash("hello!")
    assert a != b
