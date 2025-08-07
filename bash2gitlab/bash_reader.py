from __future__ import annotations

import logging
import re
from pathlib import Path

# Set up a logger for this module
logger = logging.getLogger(__name__)

# Regex to match 'source file.sh' or '. file.sh'
# It ensures the line contains nothing else but the sourcing command.
# - ^\s* - Start of the line with optional whitespace.
# - (?:source|\.) - Non-capturing group for 'source' or '.'.
# - \s+         - At least one whitespace character.
# - (?P<path>[\w./\\-]+) - Captures the file path.
# - \s*$        - Optional whitespace until the end of the line.
SOURCE_COMMAND_REGEX = re.compile(r"^\s*(?:source|\.)\s+(?P<path>[\w./\\-]+)\s*$")


def read_bash_script(path: Path) -> str:
    """Reads a bash script and inlines any sourced files."""
    logger.debug(f"Reading and inlining script from: {path}")

    # Use the new bash_reader to recursively inline all `source` commands
    content = inline_bash_source(path)

    if not content.strip():
        raise ValueError(f"Script is empty or only contains whitespace: {path}")

    lines = content.splitlines()
    if lines and lines[0].startswith("#!"):
        logger.debug(f"Stripping shebang from script: {lines[0]}")
        lines = lines[1:]

    return "\n".join(lines)


def inline_bash_source(main_script_path: Path, processed_files: set[Path] | None = None) -> str:
    """
    Reads a bash script and recursively inlines content from sourced files.

    This function processes a bash script, identifies any 'source' or '.' commands,
    and replaces them with the content of the specified script. It handles
    nested sourcing and prevents infinite loops from circular dependencies.

    Args:
        main_script_path: The absolute path to the main bash script to process.
        processed_files: A set used internally to track already processed files
                         to prevent circular sourcing. Should not be set manually.

    Returns:
        A string containing the script content with all sourced files inlined.

    Raises:
        FileNotFoundError: If the main_script_path or any sourced script does not exist.
    """
    # Initialize the set to track processed files on the first call
    if processed_files is None:
        processed_files = set()

    # Resolve the absolute path to handle relative paths correctly
    main_script_path = main_script_path.resolve()

    # Prevent circular sourcing by checking if the file has been processed
    if main_script_path in processed_files:
        logger.warning(f"Circular source detected and skipped: {main_script_path}")
        return ""

    # Check if the script exists before trying to read it
    if not main_script_path.is_file():
        raise FileNotFoundError(f"Script not found: {main_script_path}")

    logger.debug(f"Processing script: {main_script_path}")
    processed_files.add(main_script_path)

    final_content_lines = []
    try:
        with main_script_path.open("r", encoding="utf-8") as f:
            for line in f:
                match = SOURCE_COMMAND_REGEX.match(line)
                if match:
                    # A source command was found, process the sourced file
                    sourced_script_name = match.group("path")
                    # Resolve the path relative to the current script's directory
                    sourced_script_path = (main_script_path.parent / sourced_script_name).resolve()

                    logger.info(f"Inlining sourced file: {sourced_script_name} -> {sourced_script_path}")

                    # Recursively call the function to inline the nested script
                    inlined_content = inline_bash_source(sourced_script_path, processed_files)
                    final_content_lines.append(inlined_content)
                else:
                    # This line is not a source command, so keep it as is
                    final_content_lines.append(line)
    except Exception as e:
        logger.error(f"Failed to read or process {main_script_path}: {e}")
        # Re-raise the exception to notify the caller of the failure
        raise

    return "".join(final_content_lines)
