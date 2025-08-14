"""
Hooks, mainly with an eye to allowing supporting inlining other scripting languages.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pluggy

hookspec = pluggy.HookspecMarker("bash2gitlab")


@hookspec(firstresult=True)
def extract_script_path(line: str) -> str | None:
    """Return a path-like string if this line is a ‘run this script’ line."""


@hookspec(firstresult=True)
def inline_command(line: str, scripts_root: Path) -> list[str] | None:
    """Return a list of lines to inline in place of this command, or None."""


@hookspec
def yaml_before_dump(doc: Any, *, path: Path | None = None) -> Any:
    """Given a YAML doc right before dump, return replacement or None."""


@hookspec
def watch_file_extensions() -> Iterable[str]:
    return []


@hookspec
def register_cli(subparsers, config) -> None: ...


@hookspec
def before_command(args: argparse.Namespace) -> None:
    """
    Called right before dispatching a subcommand.
    May mutate `args` (e.g., add defaults), but must not return anything.
    """


@hookspec
def after_command(result: int, args: argparse.Namespace) -> None:
    """
    Called after the command handler returns. Read-only by convention.
    Use for logging/metrics/teardown. No return.
    """
