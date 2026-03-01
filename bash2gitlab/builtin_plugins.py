"""Default implementation of pluggy hooks"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from pluggy import HookimplMarker

from bash2gitlab.commands.autogit import run_autogit
from bash2gitlab.commands.compile_not_bash import maybe_inline_interpreter_command
from bash2gitlab.config import config
from bash2gitlab.errors.exit_codes import ExitCode
from bash2gitlab.utils.parse_bash import extract_script_path as _extract

hookimpl = HookimplMarker("bash2gitlab")
logger = logging.getLogger(__name__)


class Defaults:
    """Default plugin implementations for bash2gitlab hooks."""

    @hookimpl(tryfirst=True)  # firstresult=True
    def extract_script_path(self, line: str) -> str | None:
        """Extract script path from a command line."""
        return _extract(line)

    @hookimpl(tryfirst=True)  # firstresult=True
    def inline_command(self, line: str, scripts_root: Path) -> tuple[list[str], Path] | tuple[None, None]:
        """Inline non-bash scripts (Python, PHP, etc.) into YAML."""
        return maybe_inline_interpreter_command(line, scripts_root)

    @hookimpl
    def after_command(self, result: int, args: argparse.Namespace) -> None:
        """If a command was successful and --autogit was passed, run autogit."""
        if result != ExitCode.OK:
            return

        if not getattr(args, "autogit", False):
            return

        logger.info("Command successful, triggering autogit...")
        try:
            # The message for --autogit will always come from config.
            autogit_result = run_autogit(config=config, commit_message=None)
            if autogit_result != 0:
                logger.error("Autogit process failed.")

        except Exception as e:
            logger.error("An unexpected error occurred during autogit: %s", e, exc_info=False)
            logger.debug("Traceback for autogit failure:", exc_info=True)
