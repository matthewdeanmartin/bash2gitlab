"""Read a bash script and inline any `source script.sh` patterns."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from bash2gitlab.utils.pathlib_polyfills import is_relative_to
from bash2gitlab.utils.utils import short_path

# Set up a logger for this module
logger = logging.getLogger(__name__)

# Regex to match 'source file.sh' or '. file.sh'
# It ensures the line contains nothing else but the sourcing command.
# - ^\s* - Start of the line with optional whitespace.
# - (?:source|\.) - Non-capturing group for 'source' or '.'.
# - \s+         - At least one whitespace character.
# - (?P<path>[\w./\\-]+) - Captures the file path.
# - \s*$        - Optional whitespace until the end of the line.
# SOURCE_COMMAND_REGEX = re.compile(r"^\s*(?:source|\.)\s+(?P<path>[\w./\\-]+)\s*$")
# Handle optional comment.
SOURCE_COMMAND_REGEX = re.compile(r"^\s*(?:source|\.)\s+(?P<path>[\w./\\-]+)\s*(?:#.*)?$")


class SourceSecurityError(RuntimeError):
    pass


def secure_join(base_dir: Path, user_path: str, allowed_root: Path) -> Path:
    """
    Resolve 'user_path' (which may contain ../ and symlinks) against base_dir,
    then ensure the final real path is inside allowed_root.
    """
    # Normalize separators and strip quotes/whitespace
    user_path = user_path.strip().strip('"').strip("'").replace("\\", "/")

    # Resolve relative to the including script's directory
    candidate = (base_dir / user_path).resolve(strict=True)

    # Ensure the real path (after following symlinks) is within allowed_root
    allowed_root = allowed_root.resolve(strict=True)
    if not os.environ.get("BASH2GITLAB_SKIP_ROOT_CHECKS"):
        if not is_relative_to(candidate, allowed_root):
            raise SourceSecurityError(f"Refusing to source '{candidate}': escapes allowed root '{allowed_root}'.")
    return candidate


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

    final = "\n".join(lines)
    if not final.endswith("\n"):
        return final + "\n"
    return final


def inline_bash_source(
    main_script_path: Path,
    processed_files: set[Path] | None = None,
    *,
    allowed_root: Path | None = None,
    max_depth: int = 64,
    _depth: int = 0,
) -> str:
    """
    Reads a bash script and recursively inlines content from sourced files.

    This function processes a bash script, identifies any 'source' or '.' commands,
    and replaces them with the content of the specified script. It handles
    nested sourcing and prevents infinite loops from circular dependencies.

    Safely inline bash sources by confining resolution to 'allowed_root' (default: CWD).
    Blocks directory traversal and symlink escapes. Detects cycles and runaway depth.

    Args:
        main_script_path: The absolute path to the main bash script to process.
        processed_files: A set used internally to track already processed files
                         to prevent circular sourcing. Should not be set manually.
        allowed_root: Root to prevent parent traversal
        max_depth: Depth
        _depth: For recursion


    Returns:
        A string containing the script content with all sourced files inlined.

    Raises:
        FileNotFoundError: If the main_script_path or any sourced script does not exist.
    """
    if processed_files is None:
        processed_files = set()

    if allowed_root is None:
        allowed_root = Path.cwd()

    # Normalize and security-check the entry script itself
    try:
        main_script_path = secure_join(
            base_dir=main_script_path.parent if main_script_path.is_absolute() else Path.cwd(),
            user_path=str(main_script_path),
            allowed_root=allowed_root,
        )
    except FileNotFoundError:
        raise FileNotFoundError(f"Script not found: {main_script_path}") from None

    if _depth > max_depth:
        raise RecursionError(f"Max include depth ({max_depth}) exceeded at {main_script_path}")

    if main_script_path in processed_files:
        logger.warning("Circular source detected and skipped: %s", main_script_path)
        return ""

    # Check if the script exists before trying to read it
    if not main_script_path.is_file():
        raise FileNotFoundError(f"Script not found: {main_script_path}")

    logger.debug(f"Processing script: {main_script_path}")
    processed_files.add(main_script_path)

    final_content_lines: list[str] = []
    try:
        with main_script_path.open("r", encoding="utf-8") as f:
            for line in f:
                match = SOURCE_COMMAND_REGEX.match(line)
                if match:
                    # A source command was found, process the sourced file
                    sourced_script_name = match.group("path")
                    try:
                        sourced_script_path = secure_join(
                            base_dir=main_script_path.parent,
                            user_path=sourced_script_name,
                            allowed_root=allowed_root,
                        )
                    except (FileNotFoundError, SourceSecurityError) as e:
                        logger.error(
                            "Blocked or missing source '%s' included from '%s': %s",
                            sourced_script_name,
                            main_script_path,
                            e,
                        )
                        raise

                    logger.info(
                        "Inlining sourced file: %s -> %s",
                        sourced_script_name,
                        short_path(sourced_script_path),
                    )
                    inlined = inline_bash_source(
                        sourced_script_path,
                        processed_files,
                        allowed_root=allowed_root,
                        max_depth=max_depth,
                        _depth=_depth + 1,
                    )
                    final_content_lines.append(inlined)
                else:
                    # This line is not a source command, so keep it as is
                    final_content_lines.append(line)
    except Exception:
        # Propagate after logging context
        logger.exception("Failed to read or process %s", main_script_path)
        raise

    final = "".join(final_content_lines)
    if not final.endswith("\n"):
        return final + "\n"
    return final
