from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from bash2gitlab.config import _Config, config
from bash2gitlab.utils.terminal_colors import Colors

logger = logging.getLogger(__name__)

__all__ = ["run_show_config"]


def get_value_and_source(key: str, config_instance: _Config) -> tuple[Any, str, str | None]:
    """
    Determines the value and source of a configuration key.

    Returns:
        A tuple of (value, source_type, source_detail).
    """
    env_var_name = config_instance._ENV_VAR_PREFIX + key.upper()
    env_value = os.environ.get(env_var_name)

    if env_value is not None:
        # Re-evaluate the value using the config's type-aware methods
        value = getattr(config_instance, key)
        return value, "Environment Variable", env_var_name

    # Check file config
    file_config_value = config_instance.file_config.get(key)
    if file_config_value is not None:
        value = getattr(config_instance, key)
        config_path = config_instance.config_path_override or config_instance.find_config_file()
        source_detail = str(config_path.relative_to(Path.cwd())) if config_path else "Unknown file"
        return value, "Configuration File", source_detail

    # If neither, it's a default from the argparse layer or None
    value = getattr(config_instance, key)
    return value, "Default", None


def run_show_config() -> int:
    """
    Displays the resolved configuration values and their sources.
    """
    print(f"{Colors.BOLD}bash2gitlab Configuration:{Colors.ENDC}")

    config_keys = [
        "input_dir",
        "output_dir",
        "parallelism",
        "input_file",
        "output_file",
        "dry_run",
        "verbose",
        "quiet",
    ]

    # Find the longest key for alignment
    max_key_len = max(len(key) for key in config_keys)

    for key in config_keys:
        value, source_type, source_detail = get_value_and_source(key, config)

        # Colorize the source type for better readability
        if source_type == "Environment Variable":
            source_color = Colors.OKCYAN
        elif source_type == "Configuration File":
            source_color = Colors.OKGREEN
        else:
            source_color = Colors.WARNING

        # Format the output line
        key_padded = key.ljust(max_key_len)
        value_str = f"{Colors.BOLD}{value}{Colors.ENDC}" if value is not None else f"{Colors.FAIL}Not Set{Colors.ENDC}"
        source_str = f"{source_color}({source_type}{Colors.ENDC}"
        if source_detail:
            source_str += f": {source_detail}"
        source_str += ")"

        print(f"  {key_padded} = {value_str} {source_str}")

    config_file_path = config.config_path_override or config.find_config_file()
    if not config_file_path:
        print(f"\n{Colors.WARNING}Note: No 'bash2gitlab.toml' or 'pyproject.toml' config file found.{Colors.ENDC}")

    return 0
