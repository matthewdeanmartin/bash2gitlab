from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from bash2gitlab import config as config_module


@pytest.fixture(autouse=True)
def reset_singleton_and_env():
    """
    A fixture that runs for every test. It resets the config singleton
    and ensures environment variables are cleaned up.
    """
    # Store original environment variables that might be changed
    original_env = os.environ.copy()

    # Reset the singleton before the test runs
    config_module.reset_for_testing()

    yield  # Test runs here

    # Restore environment variables
    os.environ.clear()
    os.environ.update(original_env)

    # Reset the singleton again after the test
    config_module.reset_for_testing()


def test_load_from_bash2gitlab_toml(tmp_path: Path):
    """Verify that config is loaded correctly from a bash2gitlab.toml file."""
    config_file = tmp_path / "bash2gitlab.toml"
    config_file.write_text(
        """
        input_dir = "/path/from/toml"
        output_dir = "output/toml"
        """
    )

    # Reset the config to load from the specified path
    config_module.reset_for_testing(config_path_override=config_file)
    config = config_module.config

    assert config.input_dir == "/path/from/toml"
    assert config.output_dir == "output/toml"
    assert config.verbose is None  # Not defined in file


def test_load_from_pyproject_toml(tmp_path: Path):
    """Verify that config is loaded correctly from a [tool.bash2gitlab] section."""
    config_file = tmp_path / "pyproject.toml"
    config_file.write_text(
        """
        [tool.other_tool]
        setting = "ignore"

        [tool.bash2gitlab]
        input_dir = "my_ci.yml"
        scripts_out = "decompileded_scripts/"
        dry_run = false
        """
    )

    config_module.reset_for_testing(config_path_override=config_file)
    config = config_module.config

    assert config.dry_run is False


def test_env_var_overrides_file_config(tmp_path: Path):
    """Ensure environment variables take precedence over file settings."""
    config_file = tmp_path / "bash2gitlab.toml"
    config_file.write_text(
        """
        input_dir = "/path/from/toml"
        output_dir = "output/toml"
        verbose = false
        """
    )

    # Set environment variables that should override the file
    with patch.dict(
        os.environ,
        {
            "BASH2GITLAB_INPUT_DIR": "/path/from/env",
            "BASH2GITLAB_VERBOSE": "true",
        },
    ):
        config_module.reset_for_testing(config_path_override=config_file)
        config = config_module.config

        # This value should come from the environment variable
        assert config.input_dir == "/path/from/env"
        # This value should come from the file, as it's not in the env
        assert config.output_dir == "output/toml"
        # This boolean should be overridden by the env var
        assert config.verbose is True


@pytest.mark.parametrize(
    "env_value, expected",
    [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("t", True),
        ("y", True),
        ("yes", True),
        ("false", False),
        ("FALSE", False),
        ("0", False),
        ("f", False),
        ("n", False),
        ("no", False),
        ("random_string", False),
        ("", False),
    ],
)
def test_boolean_env_var_parsing(env_value: str, expected: bool):
    """Test various string representations for boolean environment variables."""
    with patch.dict(os.environ, {"BASH2GITLAB_DRY_RUN": env_value}):
        config_module.reset_for_testing()
        config = config_module.config
        assert config.dry_run is expected


def test_no_config_file_found(tmp_path: Path):
    """Test behavior when no config file exists."""
    # Change CWD to a temporary directory where no config file exists
    os.chdir(tmp_path)
    config_module.reset_for_testing()
    config = config_module.config

    assert config.input_dir is None
    assert config.output_dir is None


def test_config_file_finding_logic(tmp_path: Path):
    """Test that the config file is found in a parent directory."""
    # Create config in the root of tmp_path
    root_config = tmp_path / "bash2gitlab.toml"
    root_config.write_text('input_dir = "found_in_root"')

    # Create a subdirectory and change CWD to it
    sub_dir = tmp_path / "sub"
    sub_dir.mkdir()
    os.chdir(sub_dir)

    # Reset should now find the file in the parent directory
    config_module.reset_for_testing()
    config = config_module.config

    assert config.input_dir == "found_in_root"
