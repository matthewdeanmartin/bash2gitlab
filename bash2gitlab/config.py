from __future__ import annotations

import logging
import os
import sys
from collections.abc import Collection
from pathlib import Path
from typing import Any, TypeVar

from bash2gitlab.errors.exceptions import ConfigInvalid
from bash2gitlab.utils.utils import short_path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Config:
    """
    Manages configuration for bash2gitlab, loading from files and environment variables.

    Configuration is loaded with the following priority:
    1. Environment variables (e.g., BASH2GITLAB_LINT_GITLAB_URL)
    2. Command-specific sections in the config file (e.g., [lint])
    3. Top-level settings in the config file (e.g., output_dir)
    4. Hardcoded defaults (implicitly, where applicable)
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
        """Loads configuration from bash2gitlab.toml or pyproject.toml."""
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
            raise ConfigInvalid() from e
        except OSError as e:
            logger.error(f"Error reading file {short_path(config_path)}: {e}")
            raise ConfigInvalid() from e

    def load_env_config(self) -> dict[str, str]:
        """Loads configuration from environment variables."""
        env_config = {}
        for key, value in os.environ.items():
            if key.startswith(self._ENV_VAR_PREFIX):
                # Converts BASH2GITLAB_SECTION_KEY to section_key
                config_key = key[len(self._ENV_VAR_PREFIX) :].lower()
                env_config[config_key] = value
                logger.debug(f"Loaded from environment: {config_key}")
        return env_config

    def _get_value(self, key: str, section: str | None = None) -> tuple[Any, str]:
        """Internal helper to get a value and its source."""
        # Check environment variables first
        env_key = f"{section}_{key}" if section else key
        value = self.env_config.get(env_key)
        if value is not None:
            return value, "env"

        # Check config file (section-specific, then top-level)
        if section:
            config_section = self.file_config.get(section, {})
            if isinstance(config_section, dict):
                value = config_section.get(key)
                if value is not None:
                    return value, "file"

        value = self.file_config.get(key)
        if value is not None:
            return value, "file"

        return None, "none"

    def _coerce_type(self, value: Any, target_type: type[T], key: str) -> T | None:
        """Coerces a value to the target type, logging warnings on failure."""
        if value is None:
            return None
        try:
            if target_type is bool and isinstance(value, str):
                return value.lower() in ("true", "1", "t", "y", "yes")  # type: ignore[return-value]
            return target_type(value)  # type: ignore[return-value,call-arg]
        except (ValueError, TypeError) as e:
            logger.warning(f"Config value for '{key}' is not a valid {target_type.__name__}. Ignoring.")
            raise ConfigInvalid() from e

    def get_str(self, key: str, section: str | None = None) -> str | None:
        value, _ = self._get_value(key, section)
        return str(value) if value is not None else None

    def get_bool(self, key: str, section: str | None = None) -> bool | None:
        value, _ = self._get_value(key, section)
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        return self._coerce_type(value, bool, key)

    def get_int(self, key: str, section: str | None = None) -> int | None:
        value, _ = self._get_value(key, section)
        return self._coerce_type(value, int, key)

    def get_float(self, key: str, section: str | None = None) -> float | None:
        value, _ = self._get_value(key, section)
        return self._coerce_type(value, float, key)

    def get_dict(self, key: str, section: str | None = None) -> dict[str, str]:
        value, _ = self._get_value(key, section)
        if isinstance(value, dict):
            copy_dict = {}
            for the_key, the_value in value.items():
                copy_dict[str(the_key)] = str(the_value)
            return copy_dict
        return {}

    def get_dict_of_list(self, key: str, section: str | None = None) -> dict[str, list[str] | Collection[str]]:
        value, _ = self._get_value(key, section)
        if isinstance(value, dict):
            copy_dict = {}
            for the_key, the_value in value.items():
                copy_dict[str(the_key)] = the_value
            return copy_dict
        return {}

    # --- General Properties ---
    @property
    def input_dir(self) -> str | None:
        return self.get_str("input_dir")

    @property
    def output_dir(self) -> str | None:
        return self.get_str("output_dir")

    @property
    def parallelism(self) -> int | None:
        return self.get_int("parallelism")

    @property
    def dry_run(self) -> bool | None:
        return self.get_bool("dry_run")

    @property
    def verbose(self) -> bool | None:
        return self.get_bool("verbose")

    @property
    def quiet(self) -> bool | None:
        return self.get_bool("quiet")

    @property
    def custom_header(self) -> str | None:
        return self.get_str("custom_header")

    # --- Custom Shebangs ---
    @property
    def custom_shebangs(self) -> dict[str, str] | None:
        return self.get_dict("shebangs")

    # --- `compile` Command Properties ---
    @property
    def compile_input_dir(self) -> str | None:
        return self.get_str("input_dir", section="compile") or self.input_dir

    @property
    def compile_output_dir(self) -> str | None:
        return self.get_str("output_dir", section="compile") or self.output_dir

    @property
    def compile_parallelism(self) -> int | None:
        return self.get_int("parallelism", section="compile") or self.parallelism

    @property
    def compile_watch(self) -> bool | None:
        return self.get_bool("watch", section="compile")

    # --- `decompile` Command Properties ---
    @property
    def decompile_input_file(self) -> str | None:
        return self.get_str("input_file", section="decompile")

    @property
    def decompile_input_folder(self) -> str | None:
        return self.get_str("input_folder", section="decompile")

    @property
    def decompile_output_dir(self) -> str | None:
        return self.get_str("output_dir", section="decompile") or self.output_dir

    # --- `lint` Command Properties ---
    @property
    def lint_output_dir(self) -> str | None:
        return self.get_str("output_dir", section="lint") or self.output_dir

    @property
    def lint_gitlab_url(self) -> str | None:
        return self.get_str("gitlab_url", section="lint")

    @property
    def lint_project_id(self) -> int | None:
        return self.get_int("project_id", section="lint")

    @property
    def lint_ref(self) -> str | None:
        return self.get_str("ref", section="lint")

    @property
    def lint_include_merged_yaml(self) -> bool | None:
        return self.get_bool("include_merged_yaml", section="lint")

    @property
    def lint_parallelism(self) -> int | None:
        return self.get_int("parallelism", section="lint") or self.parallelism

    @property
    def lint_timeout(self) -> float | None:
        return self.get_float("timeout", section="lint")

    # --- `copy2local` Command Properties ---
    @property
    def copy2local_repo_url(self) -> str | None:
        return self.get_str("repo_url", section="copy2local")

    @property
    def copy2local_branch(self) -> str | None:
        return self.get_str("branch", section="copy2local")

    @property
    def copy2local_source_dir(self) -> str | None:
        return self.get_str("source_dir", section="copy2local")

    @property
    def copy2local_copy_dir(self) -> str | None:
        return self.get_str("copy_dir", section="copy2local")

    # --- `map-deploy` / `commit-map` Properties ---
    @property
    def map_folders(self) -> dict[str, list[str] | Collection[str]]:
        return self.get_dict_of_list("map", section="map")  # type: ignore[return=value]

    @property
    def map_force(self) -> bool | None:
        return self.get_bool("force", section="map")


config = Config()


def reset_for_testing(config_path_override: Path | None = None) -> Config:
    """
    Resets the singleton config instance. For testing purposes only.
    Allows specifying a direct path to a config file.
    """
    # pylint: disable=global-statement
    global config
    config = Config(config_path_override=config_path_override)
    return config
