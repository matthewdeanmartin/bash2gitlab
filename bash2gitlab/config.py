"""TOML based configuration. A way to communicate command arguments without using CLI switches."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from bash2gitlab.utils.utils import short_path

# Use tomllib if available (Python 3.11+), otherwise fall back to tomli
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

logger = logging.getLogger(__name__)


class _Config:
    """
    Handles loading and accessing configuration settings with a clear precedence:
    1. Environment Variables (BASH2GITLAB_*)
    2. Configuration File ('bash2gitlab.toml' or 'pyproject.toml')
    3. Default values (handled by the consumer, e.g., argparse)
    """

    _ENV_VAR_PREFIX = "BASH2GITLAB_"
    _CONFIG_FILES = ["bash2gitlab.toml", "pyproject.toml"]

    def __init__(self, config_path_override: Path | None = None):
        """
        Initializes the configuration object.

        Args:
            config_path_override (Path | None): If provided, this specific config file
                will be loaded, bypassing the normal search. For testing.
        """
        self.config_path_override = config_path_override
        self.file_config: dict[str, Any] = self.load_file_config()
        self.env_config: dict[str, str] = self.load_env_config()

    def find_config_file(self) -> Path | None:
        """Searches for a configuration file in the current directory and its parents."""
        current_dir = Path.cwd()
        for directory in [current_dir, *current_dir.parents]:
            for filename in self._CONFIG_FILES:
                config_path = directory / filename
                if config_path.is_file():
                    logger.debug(f"Found configuration file: {config_path}")
                    return config_path
        return None

    def load_file_config(self) -> dict[str, Any]:
        """Loads configuration from the first TOML file found or a test override."""
        config_path = self.config_path_override or self.find_config_file()
        if not config_path:
            return {}

        if not tomllib:
            logger.warning(
                "TOML library not found. Cannot load config from file. Please `pip install tomli` on Python < 3.11."
            )
            return {}

        try:
            with config_path.open("rb") as f:
                data = tomllib.load(f)

            if config_path.name == "pyproject.toml":
                file_config = data.get("tool", {}).get("bash2gitlab", {})
            else:
                file_config = data

            logger.info(f"Loaded configuration from {short_path(config_path)}")
            return file_config

        except tomllib.TOMLDecodeError as e:
            logger.error(f"Error decoding TOML file {short_path(config_path)}: {e}")
            return {}
        except OSError as e:
            logger.error(f"Error reading file {short_path(config_path)}: {e}")
            return {}

    def load_env_config(self) -> dict[str, str]:
        """Loads configuration from environment variables."""
        file_config = {}
        for key, value in os.environ.items():
            if key.startswith(self._ENV_VAR_PREFIX):
                config_key = key[len(self._ENV_VAR_PREFIX) :].lower()
                file_config[config_key] = value
                logger.debug(f"Loaded from environment: {config_key}")
        return file_config

    def get_str(self, key: str) -> str | None:
        """Gets a string value, respecting precedence."""
        value = self.env_config.get(key)
        if value is not None:
            return value

        value = self.file_config.get(key)
        return str(value) if value is not None else None

    def get_bool(self, key: str) -> bool | None:
        """Gets a boolean value, respecting precedence."""
        value = self.env_config.get(key)
        if value is not None:
            return value.lower() in ("true", "1", "t", "y", "yes")

        value = self.file_config.get(key)
        if value is not None:
            if not isinstance(value, bool):
                logger.warning(f"Config value for '{key}' is not a boolean. Coercing to bool.")
            return bool(value)

        return None

    def get_int(self, key: str) -> int | None:
        """Gets an integer value, respecting precedence."""
        value = self.env_config.get(key)
        if value is not None:
            try:
                return int(value)
            except ValueError:
                logger.warning(f"Config value for '{key}' is not an int. Ignoring.")
                return None

        value = self.file_config.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                logger.warning(f"Config value for '{key}' is not an int. Ignoring.")
                return None

        return None

    # --- Compile Command Properties ---
    @property
    def input_dir(self) -> str | None:
        return self.get_str("input_dir")

    @property
    def output_dir(self) -> str | None:
        return self.get_str("output_dir")

    @property
    def parallelism(self) -> int | None:
        return self.get_int("parallelism")

    # --- Shred Command Properties ---
    @property
    def input_file(self) -> str | None:
        return self.get_str("input_file")

    @property
    def output_file(self) -> str | None:
        return self.get_str("output_file")

    # --- Shared Properties ---
    @property
    def dry_run(self) -> bool | None:
        return self.get_bool("dry_run")

    @property
    def verbose(self) -> bool | None:
        return self.get_bool("verbose")

    @property
    def quiet(self) -> bool | None:
        return self.get_bool("quiet")


# Singleton instance for the rest of the application to use.
config = _Config()


def reset_for_testing(config_path_override: Path | None = None):
    """
    Resets the singleton config instance. For testing purposes only.
    Allows specifying a direct path to a config file.
    """
    # pylint: disable=global-statement
    global config
    config = _Config(config_path_override=config_path_override)
