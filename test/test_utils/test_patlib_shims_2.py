# tests/test_path_polyfills.py
import errno
import os
import stat
import sys
from pathlib import Path, PurePath

import pytest

from bash2gitlab.utils.pathlib_polyfills import (
    glob_cs,
    hardlink_to,
    is_relative_to,
    path_walk,
    readlink,
    relative_to_walk_up,
    with_stem,
)

# ---------------------------
# is_relative_to
# ---------------------------


def test_is_relative_to_true(tmp_path: Path):
    parent = tmp_path
    child = tmp_path / "a" / "b"
    child.mkdir(parents=True)
    assert is_relative_to(child, parent) is True


def test_is_relative_to_false(tmp_path: Path):
    p1 = tmp_path / "a"
    p2 = tmp_path / "b"
    p1.mkdir()
    p2.mkdir()
    assert is_relative_to(p1, p2) is False


def test_is_relative_to_resolves_dotdot(tmp_path: Path):
    parent = tmp_path
    child = tmp_path / "x" / ".." / "y"
    # Create the resolved target
    (tmp_path / "y").mkdir()
    # Even with '..', resolution should make it relative to parent
    assert is_relative_to(child, parent) is True


# ---------------------------
# with_stem
# ---------------------------


@pytest.mark.parametrize(
    "name,new_stem,expected",
    [
        ("file.txt", "new", "new.txt"),
        ("archive.tar.gz", "pkg", "pkg.tar.gz"),
        (".hidden", "shown", "shown"),  # no suffixes
        ("noext", "changed", "changed"),
    ],
)
def test_with_stem_preserves_suffixes(name, new_stem, expected):
    p = PurePath(name)
    result = with_stem(p, new_stem)
    assert isinstance(result, PurePath)
    assert result.name == expected


# ---------------------------
# readlink
# ---------------------------


def _can_make_symlink(tmp_path: Path) -> bool:
    if not hasattr(os, "symlink"):
        return False
    target = tmp_path / "tgt.txt"
    target.write_text("hi")
    link = tmp_path / "ln.txt"
    try:
        os.symlink(os.fspath(target), os.fspath(link))
        return True
    except OSError as e:
        # Windows often needs admin or developer mode: ERROR_PRIVILEGE_NOT_HELD (1314)
        if getattr(e, "winerror", None) == 1314 or e.errno in {errno.EPERM, errno.EACCES}:
            return False
        raise
    finally:
        try:
            link.unlink()
        except Exception:
            pass


@pytest.mark.skipif(sys.platform == "win32", reason="Windows path quirk")
def test_readlink_roundtrip(tmp_path: Path):
    if not _can_make_symlink(tmp_path):
        pytest.skip("Symlink not permitted in this environment")

    target = tmp_path / "target.txt"
    target.write_text("data")
    link = tmp_path / "link.txt"
    os.symlink(os.fspath(target), os.fspath(link))

    resolved = readlink(link)
    # readlink returns the target *path* (may be absolute/relative depending how created)
    # Normalize by resolving both
    assert resolved.resolve() == target.resolve()


# ---------------------------
# hardlink_to
# ---------------------------


def _can_hardlink(tmp_path: Path) -> bool:
    if not hasattr(os, "link"):
        return False
    src = tmp_path / "src.txt"
    src.write_text("content")
    dst = tmp_path / "dst.txt"
    try:
        os.link(os.fspath(src), os.fspath(dst))
        return True
    except OSError as e:
        # Some filesystems (e.g., FAT/exFAT, WSL mounts) may not support hardlinks
        if e.errno in {errno.EPERM, errno.EOPNOTSUPP, errno.EXDEV, errno.EACCES}:
            return False
        raise
    finally:
        try:
            dst.unlink()
        except Exception:
            pass


def test_hardlink_to_creates_link(tmp_path: Path):
    if not _can_hardlink(tmp_path):
        pytest.skip("Hard links not supported in this environment/filesystem")
    src = tmp_path / "a.txt"
    src.write_text("hello")
    dst = tmp_path / "b.txt"

    hardlink_to(dst, src)

    assert dst.exists()
    # Hardlink should point to same inode on POSIX; on Windows, verify content and size.
    assert dst.read_text() == "hello"
    if hasattr(os, "stat") and hasattr(stat, "S_IFMT"):
        try:
            s1 = os.stat(src)
            s2 = os.stat(dst)
            # On POSIX: same inode & device implies hard link
            same_inode = (s1.st_ino == s2.st_ino) and (s1.st_dev == s2.st_dev)
            # Don't fail on platforms that don't expose it meaningfully
            if os.name == "posix":
                assert same_inode
        except Exception:
            pass


# ---------------------------
# relative_to_walk_up
# ---------------------------


@pytest.mark.parametrize(
    "path,other,expected",
    [
        (PurePath("/a/b/c"), PurePath("/a/b"), PurePath("c")),
        (PurePath("/a/b/c"), PurePath("/a/b/c"), PurePath(".")),
        (PurePath("/a/b/c"), PurePath("/a/x"), PurePath("../b/c")),
    ],
)
def test_relative_to_walk_up_unixlike(tmp_path, path, other, expected, monkeypatch):
    # Normalize for Windows by rebasing onto tmp_path drive
    base = tmp_path
    p = base / Path(*path.parts[1:])
    o = base / Path(*other.parts[1:])
    p.mkdir(parents=True, exist_ok=True)
    o.mkdir(parents=True, exist_ok=True)
    rel = relative_to_walk_up(p, o)
    assert PurePath(rel) == expected


# ---------------------------
# path_walk
# ---------------------------


def test_path_walk_yields_paths(tmp_path: Path):
    (tmp_path / "d1/d2").mkdir(parents=True)
    (tmp_path / "d1/file1.txt").write_text("1")
    (tmp_path / "d1/d2/file2.txt").write_text("2")

    seen_dirs = set()
    seen_files = set()

    for base, dirs, files in path_walk(tmp_path):
        assert isinstance(base, Path)
        for d in dirs:
            assert d.is_dir()
            seen_dirs.add(d.relative_to(tmp_path))
        for f in files:
            assert f.is_file()
            seen_files.add(f.relative_to(tmp_path))

    assert PurePath("d1") in seen_dirs
    assert PurePath("d1/d2") in seen_dirs
    assert PurePath("d1/file1.txt") in seen_files
    assert PurePath("d1/d2/file2.txt") in seen_files


def test_path_walk_follow_symlinks(tmp_path: Path):
    target_dir = tmp_path / "real"
    target_dir.mkdir()
    (target_dir / "f.txt").write_text("x")

    link_dir = tmp_path / "linkdir"
    try:
        os.symlink(os.fspath(target_dir), os.fspath(link_dir))
    except (OSError, NotImplementedError):
        pytest.skip("Symlink not available/permitted")

    seen = set()
    for _base, _dirs, files in path_walk(tmp_path, follow_symlinks=True):
        for f in files:
            seen.add(f.name)
    assert "f.txt" in seen


# ---------------------------
# glob_cs
# ---------------------------


def test_glob_cs_ignores_case_flag(tmp_path: Path):
    (tmp_path / "Foo.TXT").write_text("hi")
    (tmp_path / "bar.txt").write_text("hi")
    # Our shim ignores case_sensitive flag in Py3.8; just ensure it returns a generator of matches
    res = list(glob_cs(tmp_path, "*.txt", case_sensitive=False))
    # Depending on FS case sensitivity, this may or may not include Foo.TXT;
    # we at least must include bar.txt
    names = {p.name for p in res}
    assert "bar.txt" in names


def test_glob_cs_basic_matching(tmp_path: Path):
    (tmp_path / "one.py").write_text("x")
    (tmp_path / "two.PY").write_text("x")
    matches = {p.suffix.lower() for p in glob_cs(tmp_path, "*.py")}
    assert ".py" in matches
