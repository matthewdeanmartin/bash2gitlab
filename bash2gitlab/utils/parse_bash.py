from __future__ import annotations

import re
import shlex
from pathlib import Path

_EXECUTORS = {"bash", "sh", "pwsh"}
_DOT_SOURCE = {"source", "."}
_VALID_SUFFIXES = {".sh", ".ps1"}
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def extract_script_path(cmd_line: str) -> str | None:
    """
    Return a *safe-to-inline* script path or ``None``.
    A path is safe when:

        • there are **no interpreter flags**
        • there are **no extra positional arguments**
        • there are **no leading ENV=val assignments**

    Examples that return a path
    ---------------------------
    ./build.sh
    bash build.sh
    source utils/helpers.sh
    . scripts/deploy.ps1          # pwsh default

    Examples that return ``None``
    ------------------------------
    bash -e build.sh
    FOO=bar ./build.sh
    ./build.sh arg1 arg2
    pwsh -NoProfile run.ps1
    """
    try:
        tokens = shlex.split(cmd_line, posix=True)
    except ValueError:
        return None  # malformed quoting

    if not tokens:
        return None

    # ── Disallow leading VAR=val assignments ────────────────────────────────
    if _ENV_ASSIGN_RE.match(tokens[0]):
        return None

    # Case A ─ plain script call ------------------------------------------------
    if len(tokens) == 1 and _is_script(tokens[0]):
        return Path(tokens[0]).as_posix()

    # Case B ─ executor + script ------------------------------------------------
    if len(tokens) == 2 and _is_executor(tokens[0]) and _is_script(tokens[1]):
        return Path(tokens[1]).as_posix()

    # Case C ─ dot-source -------------------------------------------------------
    if len(tokens) == 2 and tokens[0] in _DOT_SOURCE and _is_script(tokens[1]):
        return Path(tokens[1]).as_posix()

    # Anything else is unsafe to inline
    return None


# ───────────────────────── helper predicates ────────────────────────────────
def _is_executor(tok: str) -> bool:
    """True if token is bash/sh/pwsh *without leading dash*."""
    return tok in _EXECUTORS


def _is_script(tok: str) -> bool:
    """True if token ends with .sh or .ps1 and is not an option flag."""
    return not tok.startswith("-") and Path(tok).suffix.lower() in _VALID_SUFFIXES
