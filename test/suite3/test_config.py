"""Tests for bash2gitlab.config.Config — TOML loading, env-var override, type coercion.

Focus areas for the upcoming rewrite:
- A new `target` config key needs to slot cleanly into the existing loading hierarchy.
- Config priority: env > file-section > file-top-level > default.
- reset_for_testing() isolates each test from the singleton.
- Type coercion edge cases that would break a new `target` string property.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bash2gitlab.config import Config, reset_for_testing
from bash2gitlab.errors.exceptions import ConfigInvalid

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_toml(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Empty / missing config
# ---------------------------------------------------------------------------


class TestEmptyConfig:
    def test_no_config_file_returns_none_for_properties(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)  # no .bash2gitlab.toml here
        cfg = Config(config_path_override=None)
        assert cfg.input_dir is None
        assert cfg.output_dir is None
        assert cfg.parallelism is None

    def test_empty_toml_is_valid(self, tmp_path):
        cfg_file = _write_toml(tmp_path / ".bash2gitlab.toml", "")
        cfg = Config(config_path_override=cfg_file)
        assert cfg.input_dir is None

    def test_custom_header_defaults_to_none(self, tmp_path):
        cfg_file = _write_toml(tmp_path / ".bash2gitlab.toml", "")
        cfg = Config(config_path_override=cfg_file)
        assert cfg.custom_header is None


# ---------------------------------------------------------------------------
# Top-level string keys
# ---------------------------------------------------------------------------


class TestTopLevelKeys:
    def test_input_dir_read(self, tmp_path):
        cfg_file = _write_toml(tmp_path / ".bash2gitlab.toml", 'input_dir = "src"\n')
        cfg = Config(config_path_override=cfg_file)
        assert cfg.input_dir == "src"

    def test_output_dir_read(self, tmp_path):
        cfg_file = _write_toml(tmp_path / ".bash2gitlab.toml", 'output_dir = "dist"\n')
        cfg = Config(config_path_override=cfg_file)
        assert cfg.output_dir == "dist"

    def test_custom_header_read(self, tmp_path):
        cfg_file = _write_toml(tmp_path / ".bash2gitlab.toml", 'custom_header = "# generated"\n')
        cfg = Config(config_path_override=cfg_file)
        assert cfg.custom_header == "# generated"

    def test_parallelism_read_as_int(self, tmp_path):
        cfg_file = _write_toml(tmp_path / ".bash2gitlab.toml", "parallelism = 4\n")
        cfg = Config(config_path_override=cfg_file)
        assert cfg.parallelism == 4

    def test_dry_run_bool_true(self, tmp_path):
        cfg_file = _write_toml(tmp_path / ".bash2gitlab.toml", "dry_run = true\n")
        cfg = Config(config_path_override=cfg_file)
        assert cfg.dry_run is True

    def test_dry_run_bool_false(self, tmp_path):
        cfg_file = _write_toml(tmp_path / ".bash2gitlab.toml", "dry_run = false\n")
        cfg = Config(config_path_override=cfg_file)
        assert cfg.dry_run is False


# ---------------------------------------------------------------------------
# Section-specific keys
# ---------------------------------------------------------------------------


class TestSectionKeys:
    def test_compile_section_input_dir(self, tmp_path):
        cfg_file = _write_toml(
            tmp_path / ".bash2gitlab.toml",
            '[compile]\ninput_dir = "ci-src"\n',
        )
        cfg = Config(config_path_override=cfg_file)
        assert cfg.compile_input_dir == "ci-src"

    def test_compile_falls_back_to_global_input_dir(self, tmp_path):
        cfg_file = _write_toml(tmp_path / ".bash2gitlab.toml", 'input_dir = "global-src"\n')
        cfg = Config(config_path_override=cfg_file)
        assert cfg.compile_input_dir == "global-src"

    def test_lint_section_gitlab_url(self, tmp_path):
        cfg_file = _write_toml(
            tmp_path / ".bash2gitlab.toml",
            '[lint]\ngitlab_url = "https://gitlab.example.com"\n',
        )
        cfg = Config(config_path_override=cfg_file)
        assert cfg.lint_gitlab_url == "https://gitlab.example.com"

    def test_lint_project_id_as_int(self, tmp_path):
        cfg_file = _write_toml(
            tmp_path / ".bash2gitlab.toml",
            "[lint]\nproject_id = 42\n",
        )
        cfg = Config(config_path_override=cfg_file)
        assert cfg.lint_project_id == 42

    def test_lint_ref(self, tmp_path):
        cfg_file = _write_toml(
            tmp_path / ".bash2gitlab.toml",
            '[lint]\nref = "main"\n',
        )
        cfg = Config(config_path_override=cfg_file)
        assert cfg.lint_ref == "main"

    def test_decompile_section(self, tmp_path):
        cfg_file = _write_toml(
            tmp_path / ".bash2gitlab.toml",
            '[decompile]\ninput_file = "ci.yml"\noutput_dir = "scripts"\n',
        )
        cfg = Config(config_path_override=cfg_file)
        assert cfg.decompile_input_file == "ci.yml"
        assert cfg.decompile_output_dir == "scripts"

    def test_autogit_mode_valid(self, tmp_path):
        for mode in ["off", "stage", "commit", "push"]:
            cfg_file = _write_toml(
                tmp_path / ".bash2gitlab.toml",
                f'[autogit]\nmode = "{mode}"\n',
            )
            cfg = Config(config_path_override=cfg_file)
            assert cfg.autogit_mode == mode

    def test_autogit_mode_invalid_falls_back_to_off(self, tmp_path):
        cfg_file = _write_toml(
            tmp_path / ".bash2gitlab.toml",
            '[autogit]\nmode = "invalid_mode"\n',
        )
        cfg = Config(config_path_override=cfg_file)
        assert cfg.autogit_mode == "off"


# ---------------------------------------------------------------------------
# Environment variable override
# ---------------------------------------------------------------------------


class TestEnvVarOverride:
    def test_env_var_overrides_file(self, tmp_path, monkeypatch):
        cfg_file = _write_toml(tmp_path / ".bash2gitlab.toml", 'input_dir = "from-file"\n')
        monkeypatch.setenv("BASH2GITLAB_INPUT_DIR", "from-env")
        cfg = Config(config_path_override=cfg_file)
        assert cfg.input_dir == "from-env"

    def test_env_var_prefix_stripped(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_OUTPUT_DIR", "env-out")
        cfg = Config(config_path_override=None)
        assert cfg.output_dir == "env-out"

    def test_env_var_bool_string_true(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_DRY_RUN", "true")
        cfg = Config(config_path_override=None)
        assert cfg.dry_run is True

    def test_env_var_bool_string_false(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_DRY_RUN", "false")
        cfg = Config(config_path_override=None)
        assert cfg.dry_run is False

    def test_env_var_bool_1(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_DRY_RUN", "1")
        cfg = Config(config_path_override=None)
        assert cfg.dry_run is True

    def test_unknown_env_vars_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_NONEXISTENT_SETTING", "whatever")
        cfg = Config(config_path_override=None)
        # Should not raise; unknown keys are just loaded into env_config
        assert isinstance(cfg.env_config, dict)


# ---------------------------------------------------------------------------
# Type coercion edge cases
# ---------------------------------------------------------------------------


class TestTypeCoercion:
    def test_parallelism_as_string_in_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_PARALLELISM", "8")
        cfg = Config(config_path_override=None)
        # get_int coerces: should return 8
        result = cfg.get_int("parallelism")
        assert result == 8

    def test_bool_coerce_yes(self, tmp_path):
        cfg = Config(config_path_override=None)
        result = cfg._coerce_type("yes", bool, "test_key")
        assert result is True

    def test_bool_coerce_no(self, tmp_path):
        cfg = Config(config_path_override=None)
        result = cfg._coerce_type("no", bool, "test_key")
        assert result is False

    def test_int_coerce_invalid_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_PARALLELISM", "not-a-number")
        cfg = Config(config_path_override=None)
        with pytest.raises((ConfigInvalid, Exception)):
            cfg.get_int("parallelism")

    def test_get_dict_returns_empty_for_missing(self, tmp_path):
        cfg = Config(config_path_override=None)
        result = cfg.get_dict("nonexistent_key")
        assert result == {}


# ---------------------------------------------------------------------------
# pyproject.toml support
# ---------------------------------------------------------------------------


class TestPyprojectToml:
    def test_reads_tool_bash2gitlab_section(self, tmp_path):
        cfg_file = _write_toml(
            tmp_path / "pyproject.toml",
            '[tool.bash2gitlab]\ninput_dir = "ci"\n',
        )
        cfg = Config(config_path_override=cfg_file)
        assert cfg.input_dir == "ci"

    def test_ignores_other_tool_sections(self, tmp_path):
        cfg_file = _write_toml(
            tmp_path / "pyproject.toml",
            '[tool.pytest]\naddopts = "-v"\n[tool.bash2gitlab]\noutput_dir = "out"\n',
        )
        cfg = Config(config_path_override=cfg_file)
        assert cfg.output_dir == "out"


# ---------------------------------------------------------------------------
# reset_for_testing isolation
# ---------------------------------------------------------------------------


class TestResetForTesting:
    def test_reset_clears_previous_state(self, tmp_path):
        cfg1_file = _write_toml(tmp_path / "cfg1.toml", 'input_dir = "first"\n')
        cfg2_file = _write_toml(tmp_path / "cfg2.toml", 'input_dir = "second"\n')

        cfg1 = reset_for_testing(cfg1_file)
        assert cfg1.input_dir == "first"

        cfg2 = reset_for_testing(cfg2_file)
        assert cfg2.input_dir == "second"

    def test_reset_with_none_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)  # no config files here
        cfg = reset_for_testing(None)
        assert cfg.input_dir is None


# ---------------------------------------------------------------------------
# Target config key readiness
# ---------------------------------------------------------------------------


class TestTargetConfigReadiness:
    """These tests document the expected behavior once `target` is added.

    They test the existing infrastructure that the new `target` key will use,
    so they pass today and will also pass after the rewrite adds `target`.
    """

    def test_get_str_returns_none_for_missing_target_key(self, tmp_path):
        cfg_file = _write_toml(tmp_path / ".bash2gitlab.toml", "")
        cfg = Config(config_path_override=cfg_file)
        # The key doesn't exist yet — get_str must return None, not raise
        assert cfg.get_str("target") is None

    def test_get_str_reads_arbitrary_string_key(self, tmp_path):
        """Any new string key (like `target`) should be readable via get_str."""
        cfg_file = _write_toml(tmp_path / ".bash2gitlab.toml", 'target = "gitlab"\n')
        cfg = Config(config_path_override=cfg_file)
        assert cfg.get_str("target") == "gitlab"

    def test_env_var_provides_target_value(self, tmp_path, monkeypatch):
        """BASH2GITLAB_TARGET env var should work once the property exists."""
        monkeypatch.setenv("BASH2GITLAB_TARGET", "github-actions")
        cfg = Config(config_path_override=None)
        # env_config["target"] is populated by load_env_config
        assert cfg.env_config.get("target") == "github-actions"

    def test_section_target_override(self, tmp_path):
        """Section-level target should override top-level target."""
        cfg_file = _write_toml(
            tmp_path / ".bash2gitlab.toml",
            'target = "gitlab"\n[compile]\ntarget = "github-actions"\n',
        )
        cfg = Config(config_path_override=cfg_file)
        # Section-specific lookup should find the compile section's value
        assert cfg.get_str("target", section="compile") == "github-actions"
        # Top-level fallback remains
        assert cfg.get_str("target") == "gitlab"

    def test_target_string_values_pass_through_unmodified(self, tmp_path):
        """Platform names must not be coerced/mutated."""
        for target in ["gitlab", "github-actions", "azure-devops", "bitbucket"]:
            cfg_file = _write_toml(tmp_path / ".bash2gitlab.toml", f'target = "{target}"\n')
            cfg = Config(config_path_override=cfg_file)
            assert cfg.get_str("target") == target
