from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def parse_env_file(file_content: str) -> dict[str, str]:
    """
    Parses a .env-style file content into a dictionary.
    Handles lines like 'KEY=VALUE' and 'export KEY=VALUE'.

    Args:
        file_content (str): The content of the variables file.

    Returns:
        dict[str, str]: A dictionary of the parsed variables.
    """
    variables = {}
    logger.debug("Parsing global variables file.")
    for line in file_content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Regex to handle 'export KEY=VALUE', 'KEY=VALUE', etc.
        match = re.match(r"^(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$", line)
        if match:
            key = match.group("key")
            value = match.group("value").strip()
            # Remove matching quotes from the value
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            variables[key] = value
            logger.debug(f"Found global variable: {key}")
    return variables
