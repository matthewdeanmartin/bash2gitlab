"""Support for inlining many types of scripts"""

from __future__ import annotations

import logging
import re
from pathlib import Path

__all__ = ["_maybe_inline_interpreter_command"]


logger = logging.getLogger(__name__)

_INTERPRETER_FLAGS = {
    "python": "-c",
    "node": "-e",
    "ruby": "-e",
    "php": "-r",
    "fish": "-c",
}

# Simple extension mapping to help sanity-check paths by interpreter
_INTERPRETER_EXTS = {
    "python": (".py",),
    "node": (".js", ".mjs", ".cjs"),
    "ruby": (".rb",),
    "php": (".php",),
    "fish": (".fish", ".sh"),  # a lot of folks keep fish scripts as .fish; allow .sh too
}

_INTERP_LINE = re.compile(
    r"""
    ^\s*
    (?P<interp>python|node|ruby|php|fish)      # interpreter
    \s+
    (?:
        -m\s+(?P<module>[A-Za-z0-9_\.]+)       # python -m package.module
        |
        (?P<path>\.?/?[^\s]+)                  # or a path like scripts/foo.py
    )
    (?:\s+.*)?                                 # allow trailing args (ignored for now)
    \s*$
    """,
    re.VERBOSE,
)


def _shell_single_quote(s: str) -> str:
    """
    Safely single-quote *s* for POSIX shell.
    Turns: abc'def  ->  'abc'"'"'def'
    """
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _resolve_interpreter_target(
    interp: str, module: str | None, path_str: str | None, scripts_root: Path
) -> tuple[Path, str]:
    """
    Resolve the target file and a display label from either a module or a path.
    For python -m, we map "a.b.c" -> a/b/c.py.
    """
    if module:
        if interp != "python":
            raise ValueError(f"-m is only supported for python, got: {interp}")
        rel = Path(module.replace(".", "/") + ".py")
        return scripts_root / rel, f"{interp} -m {module}"
    if path_str:
        # normalize ./ and leading slashes relative to scripts_root
        rel_str = Path(path_str.strip()).as_posix().lstrip("./")
        return scripts_root / rel_str, f"{interp} {Path(rel_str).as_posix()}"
    raise ValueError("Neither module nor path provided.")


def _is_reasonable_ext(interp: str, file: Path) -> bool:
    exts = _INTERPRETER_EXTS.get(interp)
    if not exts:
        return True
    return file.suffix.lower() in exts


def _maybe_inline_interpreter_command(line: str, scripts_root: Path) -> list[str] | None:
    """
    If *line* looks like an interpreter execution (python/node/ruby/php/fish),
    return [BEGIN, <interp -flag 'code'>, END]; else return None.
    """
    m = _INTERP_LINE.match(line)
    if not m:
        return None

    interp = m.group("interp")
    module = m.group("module")
    path_str = m.group("path")

    try:
        target_file, shown = _resolve_interpreter_target(interp, module, path_str, scripts_root)
    except ValueError as e:
        logger.debug("Interpreter inline skip: %s", e)
        return None

    if not target_file.is_file():
        logger.warning("Could not inline %s: file not found at %s; preserving original.", shown, target_file)
        return None

    if not _is_reasonable_ext(interp, target_file):
        logger.debug("Interpreter inline skip: extension %s not expected for %s", target_file.suffix, interp)
        return None

    try:
        code = target_file.read_text(encoding="utf-8")
    except Exception as e:  # nosec
        logger.warning("Could not read %s: %s; preserving original.", target_file, e)
        return None

    # Strip shebang if present
    if code.startswith("#!"):
        code = "\n".join(code.splitlines()[1:])

    flag = _INTERPRETER_FLAGS.get(interp)
    if not flag:
        return None

    quoted = _shell_single_quote(code)
    begin_marker = f"# >>> BEGIN inline: {shown}"
    end_marker = "# <<< END inline"
    inlined_cmd = f"{interp} {flag} {quoted}"
    logger.debug("Inlining interpreter command '%s' (%d chars).", shown, len(code))
    return [begin_marker, inlined_cmd, end_marker]
