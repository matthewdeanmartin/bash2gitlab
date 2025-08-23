"""Default implementation of pluggy hooks"""

from __future__ import annotations

from pathlib import Path

from pluggy import HookimplMarker

from bash2gitlab.commands.compile_not_bash import maybe_inline_interpreter_command
from bash2gitlab.utils.parse_bash import extract_script_path as _extract

hookimpl = HookimplMarker("bash2gitlab")


class Defaults:
    @hookimpl(tryfirst=True)  # firstresult=True
    def extract_script_path(self, line: str) -> str | None:
        return _extract(line)

    @hookimpl(tryfirst=True)  # firstresult=True
    def inline_command(self, line: str, scripts_root: Path) -> tuple[list[str], Path] | tuple[None, None]:
        return maybe_inline_interpreter_command(line, scripts_root)
