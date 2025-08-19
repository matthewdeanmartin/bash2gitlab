""".env file support with descriptions"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)


class EnvVar(TypedDict):
    """Type definition for environment variable with optional description."""

    value: str
    description: str | None


def parse_env_content_with_descriptions(content: str) -> dict[str, EnvVar]:
    """
    Parses .env-style content string into a dictionary with descriptions.
    Handles lines like 'KEY=VALUE' and 'export KEY=VALUE'.
    Associates comments immediately preceding variable definitions as descriptions.

    Args:
        content: The .env file content as a string.

    Returns:
        dict[str, EnvVar]: A dictionary mapping variable names to EnvVar objects
                          containing value and optional description.
    """
    variables: dict[str, EnvVar] = {}
    current_description: str | None = None

    logger.debug("Parsing environment content")

    for line in content.splitlines():
        stripped_line = line.strip()

        # Skip empty lines
        if not stripped_line:
            current_description = None
            continue

        # Handle comments
        if stripped_line.startswith("#"):
            # Extract comment text (remove # and leading/trailing whitespace)
            comment_text = stripped_line[1:].strip()
            if comment_text:  # Only use non-empty comments as descriptions
                current_description = comment_text
            continue

        # Try to match variable assignment
        match = re.match(r"^(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$", stripped_line)
        if match:
            key = match.group("key")
            value = match.group("value").strip()

            # Remove matching quotes from the value
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]

            variables[key] = EnvVar(value=value, description=current_description)
            logger.debug(
                f"Found variable: {key} = {value}"
                + (f" (description: {current_description})" if current_description else "")
            )

            # Reset description after using it
            current_description = None
        else:
            # If line doesn't match variable pattern, reset description
            current_description = None

    return variables


def parse_env_file_with_descriptions(file_path: Path | str) -> dict[str, EnvVar]:
    """
    Parses a .env-style file into a dictionary with descriptions.
    Handles lines like 'KEY=VALUE' and 'export KEY=VALUE'.
    Associates comments immediately preceding variable definitions as descriptions.

    Args:
        file_path: Path to the .env file to parse.

    Returns:
        dict[str, EnvVar]: A dictionary mapping variable names to EnvVar objects
                          containing value and optional description.
    """
    file_path = Path(file_path)

    if not file_path.exists():
        logger.warning(f"Environment file {file_path} does not exist")
        return {}

    content = file_path.read_text(encoding="utf-8")
    logger.debug(f"Parsing environment file: {file_path}")

    return parse_env_content_with_descriptions(content)


def set_environment_variables(env_vars: dict[str, EnvVar]) -> None:
    """
    Sets environment variables from the parsed structure.

    Args:
        env_vars: Dictionary of environment variables with descriptions.
    """
    logger.debug("Setting environment variables")

    for key, env_var in env_vars.items():
        os.environ[key] = env_var["value"]
        logger.debug(f"Set environment variable: {key} = {env_var['value']}")


def write_env_file(env_vars: dict[str, EnvVar], file_path: Path | str, include_export: bool = False) -> None:
    """
    Writes environment variables with descriptions to a .env file.

    Args:
        env_vars: Dictionary of environment variables with descriptions.
        file_path: Path where to write the .env file.
        include_export: Whether to prefix variables with 'export'.
    """
    file_path = Path(file_path)
    logger.debug(f"Writing environment file: {file_path}")

    lines: list[str] = []

    for key, env_var in env_vars.items():
        # Add description as comment if present
        if env_var["description"]:
            lines.append(f"# {env_var['description']}")

        # Format the variable assignment
        prefix = "export " if include_export else ""
        value = env_var["value"]

        # Quote the value if it contains spaces or special characters
        if " " in value or any(char in value for char in "\"'$`\\"):
            value = f'"{value}"'

        lines.append(f"{prefix}{key}={value}")
        lines.append("")  # Add empty line for readability

    # Remove trailing empty line
    if lines and lines[-1] == "":
        lines.pop()

    file_path.write_text("\n".join(lines), encoding="utf-8")
    logger.debug(f"Successfully wrote {len(env_vars)} variables to {file_path}")


def env_vars_to_simple_dict(env_vars: dict[str, EnvVar]) -> dict[str, str]:
    """
    Converts the environment variables structure to a simple key-value dictionary.

    Args:
        env_vars: Dictionary of environment variables with descriptions.

    Returns:
        dict[str, str]: Simple dictionary mapping variable names to values.
    """
    return {key: env_var["value"] for key, env_var in env_vars.items()}


# Legacy function for backwards compatibility
def parse_env_file(file_content: str) -> dict[str, str]:
    """
    Legacy function: Parses a .env-style file content into a simple dictionary.
    This maintains compatibility with existing code by delegating to the new implementation.

    Args:
        file_content: The content of the variables file.

    Returns:
        dict[str, str]: A dictionary of the parsed variables.
    """
    env_vars = parse_env_content_with_descriptions(file_content)
    return env_vars_to_simple_dict(env_vars)
