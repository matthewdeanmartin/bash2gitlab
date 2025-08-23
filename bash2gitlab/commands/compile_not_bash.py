"""Support for inlining many types of scripts.

Turns invocations like `python -m pkg.tool`, `node scripts/foo.js`, `awk -f prog.awk data.txt`
into a single interpreter call that evaluates the file contents inline, e.g.:

    # >>> BEGIN inline: python -m pkg.tool
    python -c '...file contents...'
    # <<< END inline

If a line doesn't match a supported pattern, returns None.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

__all__ = ["maybe_inline_interpreter_command"]

from bash2gitlab.errors.exceptions import Bash2GitlabError

logger = logging.getLogger(__name__)

# Maximum *quoted* payload length to inline. Large payloads risk hitting ARG_MAX
# limits on various platforms/runners. Choose a conservative default.
MAX_INLINE_LEN = int(os.getenv("BASH2GITLAB_MAX_INLINE_LEN", "16000"))

# Env toggles
ALLOW_ANY_EXT = os.getenv("BASH2GITLAB_ALLOW_ANY_EXT") == "1"

# Interpreters → flag that accepts a *single* string of code.
# Empty string means the code is the first positional argument (awk/jq).
_INTERPRETER_FLAGS: dict[str, str | None] = {
    # existing
    "python": "-c",
    "node": "-e",
    "ruby": "-e",
    "php": "-r",
    "fish": "-c",
    # shells
    "bash": "-c",
    "sh": "-c",
    "zsh": "-c",
    "ksh": "-c",
    "pwsh": "-Command",
    "powershell": "-Command",
    # scripting languages
    "perl": "-e",
    "lua": "-e",
    "elixir": "-e",
    "raku": "-e",
    "julia": "-e",
    "groovy": "-e",
    "scala": "-e",  # may depend on launcher availability
    "clojure": "-e",
    "bb": "-e",  # babashka
    "erl": "-eval",  # special-cased with -noshell -s init stop
    "R": "-e",
    "Rscript": "-e",
    # JS runtimes
    "deno": "eval",  # map `deno run` to `deno eval`
    "bun": "eval",  # map `bun run` to `bun eval` (verify version)
    # mini-languages / filters
    "awk": "",  # program as first arg
    "sed": "-e",
    "jq": "",  # filter as first arg
}

# Interpreter → expected extensions for sanity checking. Permissive by default.
_INTERPRETER_EXTS: dict[str, tuple[str, ...]] = {
    "python": (".py",),
    "node": (".js", ".mjs", ".cjs"),
    "ruby": (".rb",),
    "php": (".php",),
    "fish": (".fish", ".sh"),
    # shells
    "bash": (".sh",),
    "sh": (".sh",),
    "zsh": (".zsh", ".sh"),
    "ksh": (".ksh", ".sh"),
    "pwsh": (".ps1",),
    "powershell": (".ps1",),
    # scripting languages
    "perl": (".pl", ".pm"),
    "lua": (".lua",),
    "elixir": (".exs",),
    "raku": (".raku", ".p6"),
    "julia": (".jl",),
    "groovy": (".groovy",),
    "scala": (".scala",),
    "clojure": (".clj",),
    "bb": (".clj",),
    "erl": (".erl",),
    "R": (".R", ".r"),
    "Rscript": (".R", ".r"),
    # JS runtimes
    "deno": (".ts", ".tsx", ".js", ".mjs"),
    "bun": (".ts", ".tsx", ".js"),
    # mini-languages
    "awk": (".awk", ".txt"),
    "sed": (".sed", ".txt"),
    "jq": (".jq", ".txt"),
}

# Match common interpreter invocations. Supports python -m, deno/bun run, and tail args.
# BUG: might not handle script files with spaces in the name. Maybe use shlex.split().
_INTERP_LINE = re.compile(
    r"""
    ^\s*
    (?P<interp>
        python(?:\d+(?:\.\d+)?)? | node | deno | bun |
        ruby | php | fish |
        bash | sh | zsh | ksh |
        pwsh | powershell |
        perl | lua | elixir | raku | julia | groovy | scala | clojure | bb | erl | Rscript | R |
        awk | sed | jq
    )
    (?:\s+run)?              # handle `deno run`, `bun run`
    \s+
    (?:
        -m\s+(?P<module>[A-Za-z0-9_\.]+)  # python -m package.module
        |
        (?P<path>\.?/?[^\s]+)             # or a script path
    )
    (?P<rest>\s+.*)?              # preserve trailing args/files
    \s*$
    """,
    re.VERBOSE,
)


def shell_single_quote(s: str) -> str:
    """Safely single-quote *s* for POSIX shell.
    Turns: abc'def  ->  'abc'"'"'def'
    """
    return "'" + s.replace("'", "'\"'\"'") + "'"


def normalize_interp(interp: str) -> str:
    """Map interpreter aliases to their base key for look-ups.
    e.g., python3.12 → python.
    """
    if interp.startswith("python"):
        return "python"
    return interp


def resolve_interpreter_target(
    interp: str, module: str | None, path_str: str | None, scripts_root: Path
) -> tuple[Path, str]:
    """Resolve the target file and a display label from either a module or a path.
    For python -m, map "a.b.c" -> a/b/c.py
    """
    if module:
        if normalize_interp(interp) != "python":
            raise Bash2GitlabError(f"-m is only supported for python, got: {interp}")
        rel = Path(module.replace(".", "/") + ".py")
        return scripts_root / rel, f"python -m {module}"
    if path_str:
        rel_str = Path(path_str.strip()).as_posix().lstrip("./")
        shown = f"{interp} {Path(rel_str).as_posix()}"
        return scripts_root / rel_str, shown
    raise Bash2GitlabError("Neither module nor path provided.")


def is_reasonable_ext(interp: str, file: Path) -> bool:
    if ALLOW_ANY_EXT:
        return True
    base = normalize_interp(interp)
    exts = _INTERPRETER_EXTS.get(base)
    if not exts:
        return True
    return file.suffix.lower() in exts


def read_script_bytes(p: Path) -> str | None:
    try:
        text = p.read_text(encoding="utf-8")
    # reading local workspace file
    except Exception as e:  # nosec
        logger.warning("Could not read %s: %s; preserving original.", p, e)
        return None
    # Strip UTF-8 BOM if present
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    # Strip shebang
    if text.startswith("#!"):
        lines = text.splitlines()
        text = "\n".join(lines[1:])
    return text


def build_eval_command(interp: str, flag: str | None, quoted: str, rest: str | None) -> str | None:
    if flag is None:
        return None
    r = rest or ""
    # erl needs some boilerplate to run and exit non-interactively
    if interp == "erl":
        return f"erl -noshell -eval {quoted} -s init stop{r}"
    if flag == "":  # awk / jq (no flag; program/filter is first positional)
        return f"{interp} {quoted}{r}"
    return f"{interp} {flag} {quoted}{r}"


def maybe_inline_interpreter_command(line: str, scripts_root: Path) -> tuple[list[str], Path] | tuple[None, None]:
    """If *line* looks like an interpreter execution we can inline, return:
    [BEGIN_MARK, <interpreter -flag 'code'>, END_MARK]. Otherwise, return None.
    """
    m = _INTERP_LINE.match(line)
    if not m:
        return None, None

    interp_raw = m.group("interp")
    interp = normalize_interp(interp_raw)
    module = m.group("module")
    path_str = m.group("path")
    rest = m.group("rest") or ""

    try:
        target_file, shown = resolve_interpreter_target(interp_raw, module, path_str, scripts_root)
    except ValueError as e:
        logger.debug("Interpreter inline skip: %s", e)
        return None, None

    if not target_file.is_file():
        logger.warning("Could not inline %s: file not found at %s; preserving original.", shown, target_file)
        return None, None

    if not is_reasonable_ext(interp, target_file):
        logger.debug("Interpreter inline skip: extension %s not expected for %s", target_file.suffix, interp)
        return None, None

    code = read_script_bytes(target_file)
    if code is None:
        return None, None

    quoted = shell_single_quote(code)

    # size guard
    if len(quoted) > MAX_INLINE_LEN:
        logger.warning(
            "Skipping inline for %s: payload %d chars exceeds MAX_INLINE_LEN=%d.",
            shown,
            len(quoted),
            MAX_INLINE_LEN,
        )
        return None, None

    flag = _INTERPRETER_FLAGS.get(interp)
    if flag is None:
        logger.debug("Interpreter inline skip: no eval flag known for %s", interp)
        return None, None

    inlined_cmd = build_eval_command(interp, flag, quoted, rest)
    if inlined_cmd is None:
        return None, None

    begin_marker = f"# >>> BEGIN inline: {shown}"
    end_marker = "# <<< END inline"
    logger.debug("Inlining interpreter command '%s' (%d chars).", shown, len(code))
    return [begin_marker, inlined_cmd, end_marker], target_file
