from __future__ import annotations

import os
from pathlib import Path, PurePath


def is_relative_to(child: Path, parent: Path) -> bool:
    """
    Check if a path is relative to another.

    Uses the native Path.is_relative_to() on Python 3.9+ and falls back
    to a polyfill for older versions.
    """
    try:
        # First, try to use the native implementation (available in Python 3.9+)
        return child.is_relative_to(parent)
    except AttributeError:
        # If the native method doesn't exist, fall back to the shim.
        try:
            # Resolving paths is important to handle symlinks and '..'
            child.resolve().relative_to(parent.resolve())
            return True
        except ValueError:
            # This error is raised by relative_to() if the path is not a subpath
            return False


#


# 3.9+ -> 3.8
def with_stem(p: PurePath, new_stem: str) -> PurePath:
    # Keep all suffixes (e.g., .tar.gz)
    return p.with_name(new_stem + "".join(p.suffixes))


# 3.9+ -> 3.8
def readlink(p: Path) -> Path:
    return Path(os.readlink(p))


# 3.10+ -> 3.8  (mirrors symlink_to API)
def hardlink_to(dst: Path, target: Path) -> None:
    os.link(os.fspath(target), os.fspath(dst))


# 3.12+ -> 3.8  (PurePath.relative_to(..., walk_up=True))
def relative_to_walk_up(path: PurePath, other: PurePath) -> PurePath:
    return Path(os.path.relpath(os.fspath(path), start=os.fspath(other)))


# 3.12+ -> 3.8  (Path.walk)
def path_walk(root: Path, top_down=True, on_error=None, follow_symlinks=False):
    for dirpath, dirnames, filenames in os.walk(root, topdown=top_down, onerror=on_error, followlinks=follow_symlinks):
        base = Path(dirpath)
        yield base, [base / d for d in dirnames], [base / f for f in filenames]


# 3.12+ -> 3.8  (case_sensitive kwarg for glob/rglob/match)
def glob_cs(p: Path, pattern: str, case_sensitive=None):
    # Py3.8: just ignore the flag (you can post-filter if you truly need case control)
    return p.glob(pattern)
