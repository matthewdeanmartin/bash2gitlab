from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

from bash2gitlab.utils.terminal_colors import Colors


def unified_diff(old: str, new: str, path: Path, from_label: str = "current", to_label: str = "new") -> str:
    """Return a unified diff between *old* and *new* content with filenames."""
    # keepends=True preserves newline structure for line-accurate diffs in logs.
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"{path} ({from_label})",
            tofile=f"{path} ({to_label})",
        )
    )


@dataclass(frozen=True)
class DiffStats:
    changed: int
    insertions: int
    deletions: int


def diff_stats(diff_text: str) -> DiffStats:
    """Compute (changed_lines, insertions, deletions) from unified diff text.

    We ignore headers (---, +++, @@). A changed line is any insertion or deletion.
    """
    ins = del_ = 0
    for line in diff_text.splitlines():
        if not line:
            continue
        # Skip headers/hunks
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        # Pure additions/deletions in unified diff start with '+' or '-'
        if line.startswith("+"):
            ins += 1
        elif line.startswith("-"):
            del_ += 1
    return DiffStats(changed=ins + del_, insertions=ins, deletions=del_)


def generate_pretty_diff(source_content: str, decoded_content: str, source_file_path: Path) -> str:
    """
    Generates a colorized (if enabled), unified diff string between two content strings.

    Args:
        source_content: The current content of the file.
        decoded_content: The original content from the hash.
        source_file_path: The path to the source file (for labeling the diff).

    Returns:
        A formatted and colorized diff string.
    """
    diff_lines = difflib.unified_diff(
        decoded_content.splitlines(),
        source_content.splitlines(),
        fromfile=f"{source_file_path} (from hash)",
        tofile=f"{source_file_path} (current, with manual edits)",
        lineterm="",
    )

    colored_diff = []
    for line in diff_lines:
        if line.startswith("+"):
            colored_diff.append(f"{Colors.OKGREEN}{line}{Colors.ENDC}")
        elif line.startswith("-"):
            colored_diff.append(f"{Colors.FAIL}{line}{Colors.ENDC}")
        elif line.startswith("@@"):
            colored_diff.append(f"{Colors.OKCYAN}{line}{Colors.ENDC}")
        else:
            colored_diff.append(line)
    return "\n".join(colored_diff)
