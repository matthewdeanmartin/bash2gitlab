"""Display current config"""

from __future__ import annotations

import logging
import os
from typing import Any

from bash2gitlab.config import Config, config
from bash2gitlab.utils.terminal_colors import Colors
from bash2gitlab.utils.utils import short_path

logger = logging.getLogger(__name__)

__all__ = ["run_show_config"]

# Defines the structure of the output.
# Maps section titles to a list of tuples: (display_key, config_property_name)
CONFIG_STRUCTURE = {
    "General Settings": [
        ("input_dir", "input_dir"),
        ("output_dir", "output_dir"),
        ("parallelism", "parallelism"),
        ("dry_run", "dry_run"),
        ("verbose", "verbose"),
        ("quiet", "quiet"),
        ("custom_header", "custom_header"),
    ],
    "Custom Shebangs (`[shebangs]`)": [("shebangs", "custom_shebangs")],
    "Compile Command (`[compile]`)": [
        ("input_dir", "compile_input_dir"),
        ("output_dir", "compile_output_dir"),
        ("parallelism", "compile_parallelism"),
        ("watch", "compile_watch"),
    ],
    "Decompile Command (`[decompile]`)": [
        ("input_file", "decompile_input_file"),
        ("input_folder", "decompile_input_folder"),
        ("output_dir", "decompile_output_dir"),
    ],
    "Lint Command (`[lint]`)": [
        ("output_dir", "lint_output_dir"),
        ("gitlab_url", "lint_gitlab_url"),
        ("token", "lint_token"),
        ("project_id", "lint_project_id"),
        ("ref", "lint_ref"),
        ("include_merged_yaml", "lint_include_merged_yaml"),
        ("parallelism", "lint_parallelism"),
        ("timeout", "lint_timeout"),
    ],
    "Copy2Local Command (`[copy2local]`)": [
        ("repo_url", "copy2local_repo_url"),
        ("branch", "copy2local_branch"),
        ("source_dir", "copy2local_source_dir"),
        ("copy_dir", "copy2local_copy_dir"),
    ],
    "Map Commands (`[map]`)": [
        ("pyproject_path", "map_pyproject_path"),
        ("force", "map_force"),
    ],
}

# Known sections used for parsing property names
_SECTIONS = {"compile", "decompile", "lint", "copy2local", "map"}


def _parse_prop_name(prop_name: str) -> tuple[str, str | None]:
    """Parses a config property name into its key and section."""
    parts = prop_name.split("_", 1)
    if parts[0] in _SECTIONS:
        # e.g., "lint_gitlab_url" -> ("gitlab_url", "lint")
        return (parts[1], parts[0])
    if prop_name == "custom_shebangs":
        # e.g. "custom_shebangs" -> ("shebangs", None) but it is a section-like table
        return ("shebangs", None)
    # e.g., "input_dir" -> ("input_dir", None)
    return (prop_name, None)


def get_value_and_source_details(prop_name: str, config_instance: Config) -> tuple[Any, str, str | None]:
    """
    Determines the final value and the specific source of a configuration property.

    Returns:
        A tuple of (value, source_type, source_detail).
    """
    # 1. Get the final, resolved value from the config property.
    #    This correctly handles fallbacks (e.g., `lint_output_dir` -> `output_dir`).
    value = getattr(config_instance, prop_name, None)

    # 2. Determine the original source of the value.
    key, section = _parse_prop_name(prop_name)
    key_for_file = "shebangs" if prop_name == "custom_shebangs" else key

    # Check Environment Variable
    env_key = f"{section}_{key}" if section else key
    env_var_name = config_instance._ENV_VAR_PREFIX + env_key.upper()
    if env_var_name in os.environ:
        return value, "Environment Variable", env_var_name

    # Check Configuration File ([section])
    if section:
        config_section = config_instance.file_config.get(section, {})
        if isinstance(config_section, dict) and key in config_section:
            config_path = config_instance.config_path_override or config_instance.find_config_file()
            detail = f"[{section}] in {short_path(config_path)}" if config_path else f"in section [{section}]"
            return value, "Configuration File", detail

    # Check Configuration File (top-level)
    if key_for_file in config_instance.file_config:
        config_path = config_instance.config_path_override or config_instance.find_config_file()
        detail = f"in {short_path(config_path)}" if config_path else "in config file"
        return value, "Configuration File", detail

    # Check if the value came from a fallback to a general property
    if section and value is not None:
        # Check if the fallback general property has a source
        general_value, general_source, general_detail = get_value_and_source_details(key, config_instance)
        if general_value == value and general_source != "Default":
            return value, general_source, f"{general_detail} (fallback)"

    return value, "Default", None


def run_show_config() -> int:
    """
    Displays the resolved configuration values, grouped by section, and their sources.
    """
    print(f"{Colors.BOLD}bash2gitlab Configuration:{Colors.ENDC}")

    config_file_path = config.config_path_override or config.find_config_file()
    if config_file_path:
        print(f"Loaded from: {Colors.OKCYAN}{short_path(config_file_path)}{Colors.ENDC}")
    else:
        print(f"{Colors.WARNING}Note: No 'bash2gitlab.toml' or 'pyproject.toml' config file found.{Colors.ENDC}")

    max_key_len = max(len(k) for section in CONFIG_STRUCTURE.values() for k, _ in section)

    for section_title, keys in CONFIG_STRUCTURE.items():
        # Check if any value in the section is set to avoid printing empty sections
        has_values = any(getattr(config, prop_name, None) is not None for _, prop_name in keys)
        if not has_values:
            continue

        print(f"\n{Colors.BOLD}{section_title}{Colors.ENDC}")
        for display_key, prop_name in keys:
            value, source_type, source_detail = get_value_and_source_details(prop_name, config)

            if source_type == "Environment Variable":
                source_color = Colors.OKCYAN
            elif source_type == "Configuration File":
                source_color = Colors.OKGREEN
            else:
                source_color = Colors.WARNING

            key_padded = display_key.ljust(max_key_len)

            if isinstance(value, dict):
                value_str = (
                    f"\n{Colors.BOLD}"
                    + "\n".join(f"{' ' * (max_key_len + 5)}- {k}: {v}" for k, v in value.items())
                    + f"{Colors.ENDC}"
                )
            elif value is not None:
                value_str = f"{Colors.BOLD}{value}{Colors.ENDC}"
            else:
                value_str = f"{Colors.FAIL}Not Set{Colors.ENDC}"

            source_str = f"{source_color}({source_type}{Colors.ENDC}"
            if source_detail:
                source_str += f": {source_detail}"
            source_str += ")"

            # Don't show source for unset defaults
            if source_type == "Default" and value is None:
                source_str = ""

            print(f"  {key_padded} = {value_str} {source_str}")

    return 0
