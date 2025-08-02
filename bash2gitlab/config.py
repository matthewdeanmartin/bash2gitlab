from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

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
        self._config_path_override = config_path_override
        self._file_config: dict[str, Any] = self._load_file_config()
        self._env_config: dict[str, str] = self._load_env_config()

    def _find_config_file(self) -> Path | None:
        """Searches for a configuration file in the current directory and its parents."""
        current_dir = Path.cwd()
        for directory in [current_dir, *current_dir.parents]:
            for filename in self._CONFIG_FILES:
                config_path = directory / filename
                if config_path.is_file():
                    logger.debug(f"Found configuration file: {config_path}")
                    return config_path
        return None

    def _load_file_config(self) -> dict[str, Any]:
        """Loads configuration from the first TOML file found or a test override."""
        config_path = self._config_path_override or self._find_config_file()
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
                config = data.get("tool", {}).get("bash2gitlab", {})
            else:
                config = data

            logger.info(f"Loaded configuration from {config_path}")
            return config

        except tomllib.TOMLDecodeError as e:
            logger.error(f"Error decoding TOML file {config_path}: {e}")
            return {}
        except OSError as e:
            logger.error(f"Error reading file {config_path}: {e}")
            return {}

    def _load_env_config(self) -> dict[str, str]:
        """Loads configuration from environment variables."""
        config = {}
        for key, value in os.environ.items():
            if key.startswith(self._ENV_VAR_PREFIX):
                config_key = key[len(self._ENV_VAR_PREFIX) :].lower()
                config[config_key] = value
                logger.debug(f"Loaded from environment: {config_key}")
        return config

    def _get_str(self, key: str) -> str | None:
        """Gets a string value, respecting precedence."""
        value = self._env_config.get(key)
        if value is not None:
            return value

        value = self._file_config.get(key)
        return str(value) if value is not None else None

    def _get_bool(self, key: str) -> bool | None:
        """Gets a boolean value, respecting precedence."""
        value = self._env_config.get(key)
        if value is not None:
            return value.lower() in ("true", "1", "t", "y", "yes")

        value = self._file_config.get(key)
        if value is not None:
            if not isinstance(value, bool):
                logger.warning(f"Config value for '{key}' is not a boolean. Coercing to bool.")
            return bool(value)

        return None

    def _get_int(self, key: str) -> int | None:
        """Gets an integer value, respecting precedence."""
        value = self._env_config.get(key)
        if value is not None:
            try:
                return int(value)
            except ValueError:
                logger.warning(f"Config value for '{key}' is not an int. Ignoring.")
                return None

        value = self._file_config.get(key)
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
        return self._get_str("input_dir")

    @property
    def output_dir(self) -> str | None:
        return self._get_str("output_dir")

    @property
    def scripts_dir(self) -> str | None:
        return self._get_str("scripts_dir")

    @property
    def templates_in(self) -> str | None:
        return self._get_str("templates_in")

    @property
    def templates_out(self) -> str | None:
        return self._get_str("templates_out")

    @property
    def parallelism(self) -> int | None:
        return self._get_int("parallelism")

    # --- Shred Command Properties ---
    @property
    def input_file(self) -> str | None:
        return self._get_str("input_file")

    @property
    def output_file(self) -> str | None:
        return self._get_str("output_file")

    @property
    def scripts_out(self) -> str | None:
        return self._get_str("scripts_out")

    # --- Shared Properties ---
    @property
    def dry_run(self) -> bool | None:
        return self._get_bool("dry_run")

    @property
    def verbose(self) -> bool | None:
        return self._get_bool("verbose")

    @property
    def quiet(self) -> bool | None:
        return self._get_bool("quiet")


# Singleton instance for the rest of the application to use.
config = _Config()


def _reset_for_testing(config_path_override: Path | None = None):
    """
    Resets the singleton config instance. For testing purposes only.
    Allows specifying a direct path to a config file.
    """
    global config
    config = _Config(config_path_override=config_path_override)
