# test_utils_misc.py
from __future__ import annotations

from pathlib import Path

import pytest

from bash2gitlab.utils.utils import remove_leading_blank_lines, short_path

# ----------------------
# remove_leading_blank_lines
# ----------------------


def test_remove_leading_blank_lines_empty_string():
    assert remove_leading_blank_lines("") == ""


def test_remove_leading_blank_lines_all_blank():
    s = "\n \t \n\r\n"
    assert remove_leading_blank_lines(s) == ""


def test_remove_leading_blank_lines_strips_only_prefix():
    s = "\n\n   \t\nhello\nworld\n"
    # Note: function normalizes to '\n' because it rejoins with '\n'
    assert remove_leading_blank_lines(s) == "hello\nworld"


def test_remove_leading_blank_lines_preserves_internal_blanks():
    s = "alpha\n\nbeta\n"
    assert remove_leading_blank_lines(s) == "alpha\n\nbeta"


def test_remove_leading_blank_lines_handles_crlf_newlines():
    s = "\r\n\r\nA\r\nB\r\n"
    # splitlines() drops line endings; function rejoins with '\n'
    assert remove_leading_blank_lines(s) == "A\nB"


# ----------------------
# short_path
# ----------------------


def test_short_path_returns_relative_when_under_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    proj = tmp_path / "proj"
    sub = proj / "sub"
    sub.mkdir(parents=True)
    f = sub / "file.txt"
    f.write_text("x", encoding="utf-8")

    # Change CWD to proj
    monkeypatch.chdir(proj)

    # Pass absolute path under CWD
    result = short_path(f.resolve())
    # Should be relative to cwd
    assert result in {"sub/file.txt", str(Path("sub") / "file.txt")}


def test_short_path_returns_absolute_when_outside_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    proj = tmp_path / "proj"
    other = tmp_path / "other"
    (proj).mkdir()
    (other).mkdir()

    f_outside = other / "data.yml"
    f_outside.write_text("a: 1\n", encoding="utf-8")

    monkeypatch.chdir(proj)

    result = short_path(f_outside.resolve())
    # Should be an absolute path (resolved)
    assert Path(result).is_absolute()
    assert Path(result) == f_outside.resolve()


def test_short_path_with_relative_input_returns_absolute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    When given a *relative* Path, short_path() cannot make it relative_to(Path.cwd()),
    so it falls back to resolve() and returns an absolute path.
    """
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.chdir(proj)

    rel = Path("subdir") / "note.md"
    (proj / rel).parent.mkdir(parents=True)
    (proj / rel).write_text("hello", encoding="utf-8")

    result = short_path(rel)  # note: passing a relative Path
    assert Path(result).is_absolute()
    assert Path(result) == (proj / rel).resolve()
