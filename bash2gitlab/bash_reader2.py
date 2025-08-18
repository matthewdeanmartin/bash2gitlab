"""Read a bash script and inline any `source script.sh` patterns."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from bash2gitlab.utils.pathlib_polyfills import is_relative_to
from bash2gitlab.utils.utils import short_path

# NOTE: No changes to imports, constants, or helper functions are needed.
# The following are included for completeness.


__all__ = ["read_bash_script"]

# Set up a logger for this module
logger = logging.getLogger(__name__)

# Regex to match 'source file.sh' or '. file.sh'
# It ensures the line contains nothing else but the sourcing command, except a comment.
# - ^\s* - Start of the line with optional whitespace.
# - (?:source|\.) - Non-capturing group for 'source' or '.'.
# - \s+         - At least one whitespace character.
# - (?P<path>[\w./\\-]+) - Captures the file path.
# - \s*$        - Optional whitespace until the end of the line.
# SOURCE_COMMAND_REGEX = re.compile(r"^\s*(?:source|\.)\s+(?P<path>[\w./\\-]+)\s*$")
# Handle optional comment.
SOURCE_COMMAND_REGEX = re.compile(r"^\s*(?:source|\.)\s+(?P<path>[\w./\\-]+)\s*(?:#.*)?$")

# Regex to match pragmas like '# Pragma: do-not-inline'
# It is case-insensitive to 'Pragma' and captures the command.
PRAGMA_REGEX = re.compile(
    r"#\s*Pragma:\s*(?P<command>do-not-inline(?:-next-line)?|start-do-not-inline|end-do-not-inline|allow-outside-root)",
    re.IGNORECASE,
)


class SourceSecurityError(RuntimeError):
    pass


class PragmaError(ValueError):
    pass


def secure_join(base_dir: Path, user_path: str, allowed_root: Path, *, bypass_security_check: bool = False) -> Path:
    user_path = user_path.strip().strip('"').strip("'").replace("\\", "/")
    candidate = (base_dir / user_path).resolve(strict=True)
    allowed_root = allowed_root.resolve(strict=True)
    if not os.environ.get("BASH2GITLAB_SKIP_ROOT_CHECKS") and not bypass_security_check:
        if not is_relative_to(candidate, allowed_root):
            raise SourceSecurityError(f"Refusing to source '{candidate}': escapes allowed root '{allowed_root}'.")
    elif bypass_security_check:
        logger.warning(
            "Security check explicitly bypassed for path '%s' due to 'allow-outside-root' pragma.", candidate
        )
    return candidate


def read_bash_script(path: Path) -> str:
    """
    Reads a bash script and inlines any sourced files.
    This is the main entry point.
    """
    logger.debug(f"Reading and inlining script from: {path}")

    # Use the recursive inliner to do all the work, including shebang handling.
    content = inline_bash_source(path)

    if not content.strip():
        raise ValueError(f"Script is empty or only contains whitespace: {path}")

    # The returned content is now final.
    return content


# --- FUNCTION WITH THE FIX ---
def inline_bash_source(
    main_script_path: Path,
    processed_files: set[Path] | None = None,
    *,
    allowed_root: Path | None = None,
    max_depth: int = 64,
    _depth: int = 0,
) -> str:
    """
    Reads a bash script and recursively inlines content from sourced files,
    honoring pragmas to prevent inlining or bypass security.
    """
    if processed_files is None:
        processed_files = set()
    if allowed_root is None:
        allowed_root = Path.cwd()

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
    if not main_script_path.is_file():
        raise FileNotFoundError(f"Script not found: {main_script_path}")

    logger.debug(f"Processing script: {main_script_path}")
    processed_files.add(main_script_path)

    final_content_lines: list[str] = []
    in_do_not_inline_block = False
    skip_next_line = False

    try:
        with main_script_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()

            # --- (FIX) SHEBANG HANDLING MOVED HERE ---
            # Only strip the shebang if this is the top-level script (_depth == 0).
            # This respects pragmas because the logic now happens *before* line-by-line processing.
            if _depth == 0 and lines and lines[0].startswith("#!"):
                logger.debug(f"Stripping shebang from main script: {lines[0].strip()}")
                lines = lines[1:]

            for line_num, line in enumerate(lines, 1):
                source_match = SOURCE_COMMAND_REGEX.match(line)
                pragma_match = PRAGMA_REGEX.search(line)
                pragma_command = pragma_match.group("command").lower() if pragma_match else None

                # --- (FIX) Phase 1: State Management & Strippable Pragmas ---
                # These pragmas are control directives and should be stripped from the output.
                if pragma_command == "start-do-not-inline":
                    if in_do_not_inline_block:
                        raise PragmaError(f"Cannot nest 'start-do-not-inline' at {main_script_path}:{line_num}")
                    in_do_not_inline_block = True
                    continue  # Strip the pragma line itself

                if pragma_command == "end-do-not-inline":
                    if not in_do_not_inline_block:
                        raise PragmaError(f"Found 'end-do-not-inline' without 'start' at {main_script_path}:{line_num}")
                    in_do_not_inline_block = False
                    continue  # Strip the pragma line itself

                if pragma_command == "do-not-inline-next-line":
                    skip_next_line = True
                    continue  # Strip the pragma line itself

                # --- (FIX) Phase 2: Content Filtering ---
                # If we are inside a do-not-inline block, strip this line of content.
                if in_do_not_inline_block:
                    continue

                # --- Phase 3: Line-by-line Processing (for lines we intend to keep) ---
                should_inline = source_match is not None
                reason_to_skip = ""

                if skip_next_line:
                    reason_to_skip = "previous line had 'do-not-inline-next-line' pragma"
                    should_inline = False
                    skip_next_line = False  # Consume the flag
                elif pragma_command == "do-not-inline":
                    reason_to_skip = "line contains 'do-not-inline' pragma"
                    should_inline = False
                    # Line is kept, just not inlined. Warning for non-sourcing lines.
                    if not source_match:
                        logger.warning(
                            "Pragma 'do-not-inline' on non-sourcing line at %s:%d has no effect.",
                            main_script_path,
                            line_num,
                        )

                if pragma_command == "allow-outside-root" and not source_match:
                    logger.warning(
                        "Pragma 'allow-outside-root' on non-sourcing line at %s:%d has no effect.",
                        main_script_path,
                        line_num,
                    )

                # --- Perform Action: Inline or Append ---
                if should_inline and source_match:
                    sourced_script_name = source_match.group("path")
                    bypass_security = pragma_command == "allow-outside-root"
                    try:
                        sourced_script_path = secure_join(
                            base_dir=main_script_path.parent,
                            user_path=sourced_script_name,
                            allowed_root=allowed_root,
                            bypass_security_check=bypass_security,
                        )
                    except (FileNotFoundError, SourceSecurityError) as e:
                        logger.error(
                            "Blocked/missing source '%s' from '%s': %s", sourced_script_name, main_script_path, e
                        )
                        raise
                    logger.info("Inlining sourced file: %s -> %s", sourced_script_name, short_path(sourced_script_path))
                    inlined = inline_bash_source(
                        sourced_script_path,
                        processed_files,
                        allowed_root=allowed_root,
                        max_depth=max_depth,
                        _depth=_depth + 1,
                    )
                    final_content_lines.append(inlined)
                else:
                    if source_match and reason_to_skip:
                        logger.info(
                            "Skipping inline of '%s' at %s:%d because %s.",
                            source_match.group("path"),
                            main_script_path,
                            line_num,
                            reason_to_skip,
                        )
                    final_content_lines.append(line)

        if in_do_not_inline_block:
            raise PragmaError(f"Unclosed 'start-do-not-inline' pragma in file: {main_script_path}")

    except Exception:
        # Propagate after logging context
        logger.exception("Failed to read or process %s", main_script_path)
        raise

    final = "".join(final_content_lines)
    if not final.endswith("\n") and final:
        return final + "\n"
    return final
