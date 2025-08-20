"""Utility functions with no strong link to the domain of the overall application."""

from __future__ import annotations

from pathlib import Path


def remove_leading_blank_lines(text: str) -> str:
    """
    Removes leading blank lines (including lines with only whitespace) from a string.
    """
    lines = text.splitlines()
    # Find the first non-blank line
    for i, line in enumerate(lines):
        if line.strip() != "":
            return "\n".join(lines[i:])
    return ""  # All lines were blank


def short_path(path: Path) -> str:
    """
    Return the path relative to the current working directory if possible.
    Otherwise, return the absolute path.

    Args:
        path (Path): The path to format for debugging.

    Returns:
        str: Relative path or absolute path as a fallback.
    """
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path.resolve())
