"""Parser for detecting scripts that are safe to inline without changing semantics"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

_EXECUTORS = {"bash", "sh", "pwsh"}
_DOT_SOURCE = {"source", "."}
_VALID_SUFFIXES = {".sh", ".ps1", ".bash"}
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def split_cmd(cmd_line: str) -> list[str] | None:
    """
    Split *cmd_line* into tokens while preserving backslashes (e.g. '.\\foo.sh').
    Uses POSIX-like rules for quoting/whitespace but disables backslash escaping.
    """
    try:
        lex = shlex.shlex(cmd_line, posix=True)
        lex.whitespace_split = True  # split on whitespace
        # lex.commenters = ""               # don't treat '#' as a comment
        lex.escape = ""  # *** preserve backslashes ***
        return list(lex)
    except ValueError:
        # Unbalanced quotes or similar
        return None


def extract_script_path(cmd_line: str) -> str | None:
    """
    Return a *safe-to-inline* script path or ``None``.
    A path is safe when:

        • there are **no interpreter flags**
        • there are **no extra positional arguments**
        • there are **no leading ENV=val assignments**
    """
    if not isinstance(cmd_line, str):
        raise Exception("Expected string for cmd_line")

    tokens = split_cmd(cmd_line)
    if not tokens:
        return None

    # Disallow leading VAR=val assignments
    if _ENV_ASSIGN_RE.match(tokens[0]):
        return None

    # Case A ─ plain script call
    if len(tokens) == 1 and is_script(tokens[0]):
        return to_posix(tokens[0])

    # Case B ─ executor + script
    if len(tokens) == 2 and is_executor(tokens[0]) and is_script(tokens[1]):
        return to_posix(tokens[1])

    # Case C ─ dot-source
    if len(tokens) == 2 and tokens[0] in _DOT_SOURCE and is_script(tokens[1]):
        return to_posix(tokens[1])

    return None


# ───────────────────────── helper predicates ────────────────────────────────
def is_executor(tok: str) -> bool:
    """True if token is bash/sh/pwsh *without leading dash*."""
    return tok in _EXECUTORS


def is_script(tok: str) -> bool:
    """
    True if token ends with a known script suffix and is not an option flag.

    Handles both POSIX-style (./foo.sh) and Windows-style (.\\foo.sh, C:\\path\\bar.ps1).
    """
    if tok.startswith("-"):
        return False
    normalized = tok.replace("\\", "/")
    return Path(normalized).suffix.lower() in _VALID_SUFFIXES


def to_posix(tok: str) -> str:
    """Return a normalized POSIX-style path for consistent downstream handling."""
    return Path(tok.replace("\\", "/")).as_posix()
