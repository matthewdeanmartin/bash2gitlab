# tests/test_show_config.py
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

# Import the module under test.
# If your module lives elsewhere, adjust this import.
from bash2gitlab.commands import show_config as show_mod
from bash2gitlab.config import _Config as ConfigClass
from bash2gitlab.config import reset_for_testing

# ------------------------- helpers -------------------------


def _set_module_config(monkeypatch: pytest.MonkeyPatch, cfg: ConfigClass) -> None:
    """
    The show_config module holds its own 'config' reference imported at import-time.
    Rebind it to a fresh _Config for each test so we don't rely on global state.
    """
    reset_for_testing()
    monkeypatch.setattr(show_mod, "config", cfg, raising=False)


def _write_pyproject(tmp: Path, body: str) -> Path:
    p = tmp / "pyproject.toml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


# ------------------------- tests ---------------------------


def test_get_value_and_source_from_env(monkeypatch: pytest.MonkeyPatch):
    # Prepare env override for multiple types
    monkeypatch.setenv("BASH2GITLAB_INPUT_DIR", "/env/input")
    monkeypatch.setenv("BASH2GITLAB_PARALLELISM", "8")
    monkeypatch.setenv("BASH2GITLAB_DRY_RUN", "true")

    cfg = ConfigClass()  # loads env_config

    # string
    value, src, detail = show_mod.get_value_and_source("input_dir", cfg)
    assert value == "/env/input"
    assert src == "Environment Variable"
    assert detail.endswith("BASH2GITLAB_INPUT_DIR")

    # int coercion
    value, src, detail = show_mod.get_value_and_source("parallelism", cfg)
    assert value == 8
    assert src == "Environment Variable"
    assert detail.endswith("BASH2GITLAB_PARALLELISM")

    # bool coercion
    value, src, detail = show_mod.get_value_and_source("dry_run", cfg)
    assert value is True
    assert src == "Environment Variable"
    assert detail.endswith("BASH2GITLAB_DRY_RUN")


def test_get_value_and_source_from_file_pyproject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)

    # Real pyproject with [tool.bash2gitlab]
    pyproject = _write_pyproject(
        tmp_path,
        """
        [tool.bash2gitlab]
        input_dir = "from-file/input"
        output_dir = "from-file/out"
        parallelism = 3
        verbose = true
        """,
    )

    cfg = ConfigClass(config_path_override=pyproject)  # loads file_config
    _set_module_config(monkeypatch, cfg)  # not strictly needed for get_value_and_source, but consistent

    value, src, detail = show_mod.get_value_and_source("input_dir", cfg)
    assert value == "from-file/input"
    assert src == "Configuration File"
    # shown path should be relative to cwd
    assert detail == "pyproject.toml"

    # check a few other keys
    assert show_mod.get_value_and_source("output_dir", cfg)[0] == "from-file/out"
    assert show_mod.get_value_and_source("parallelism", cfg)[0] == 3
    assert show_mod.get_value_and_source("verbose", cfg)[0] is True


def test_get_value_and_source_default_when_unset(monkeypatch: pytest.MonkeyPatch):
    # No env, no file -> defaults (None)
    # Ensure related env vars are absent
    for key in ("INPUT_DIR", "OUTPUT_DIR", "PARALLELISM", "DRY_RUN"):
        monkeypatch.delenv(f"BASH2GITLAB_{key}", raising=False)

    cfg = ConfigClass()
    value, src, detail = show_mod.get_value_and_source("input_dir", cfg)
    assert value is None
    assert src == "Default"
    assert detail is None


def test_run_show_config_with_file_and_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(tmp_path)

    # File config
    pyproject = _write_pyproject(
        tmp_path,
        """
        [tool.bash2gitlab]
        input_dir = "from-file/input"
        output_dir = "from-file/out"
        parallelism = 2
        """,
    )

    # Env var should take precedence over file for output_dir
    monkeypatch.setenv("BASH2GITLAB_OUTPUT_DIR", "/env/out")

    cfg = ConfigClass(config_path_override=pyproject)
    _set_module_config(monkeypatch, cfg)

    rc = show_mod.run_show_config()
    assert rc == 0
    out = capsys.readouterr().out

    # Header present
    assert "bash2gitlab Configuration:" in out

    # input_dir should say "Configuration File" and show relative file name
    assert "input_dir" in out
    assert "from-file/input" in out
    assert "(Configuration File" in out
    assert ": pyproject.toml" in out

    # output_dir should say "Environment Variable"
    assert "output_dir" in out
    assert "/env/out" in out
    assert "(Environment Variable" in out

    # A key not set anywhere should read as Not Set (colored), but check the phrase
    assert "input_file" in out
    assert "Not Set" in out

    # No "Note: No ... config file found" because we provided one
    assert "No 'bash2gitlab.toml' or 'pyproject.toml' config file found" not in out


def test_run_show_config_when_no_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    # Empty cwd, no config present and no env
    monkeypatch.chdir(tmp_path)
    for k in ("INPUT_DIR", "OUTPUT_DIR", "PARALLELISM", "DRY_RUN", "VERBOSE", "QUIET"):
        monkeypatch.delenv(f"BASH2GITLAB_{k}", raising=False)

    cfg = ConfigClass()  # no config_path_override, no file discovered
    _set_module_config(monkeypatch, cfg)

    rc = show_mod.run_show_config()
    assert rc == 0
    out = capsys.readouterr().out

    # Should display the note about missing config files
    assert "No 'bash2gitlab.toml' or 'pyproject.toml' config file found" in out
