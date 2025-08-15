# test_paths.py

import sys
from pathlib import Path

import pytest

# conftest.py
# This file provides fixtures for the pytest framework.
# Pytest automatically discovers and uses the fixtures defined here.


@pytest.fixture
def setup_fs(tmp_path: Path):
    """
    Creates a standard temporary file system structure for testing.

    The structure is:
    tmp_path/
    ├── parent/
    │   ├── child/
    │   │   └── grandchild/
    │   │       └── file.txt
    │   └── sibling_file.txt
    └── other/
        └── unrelated_file.txt
    """
    # Define the directory and file paths
    parent_dir = tmp_path / "parent"
    child_dir = parent_dir / "child"
    grandchild_dir = child_dir / "grandchild"
    other_dir = tmp_path / "other"

    # Create the directories
    grandchild_dir.mkdir(parents=True, exist_ok=True)
    other_dir.mkdir(exist_ok=True)

    # Create some dummy files
    (grandchild_dir / "file.txt").touch()
    (parent_dir / "sibling_file.txt").touch()
    (other_dir / "unrelated_file.txt").touch()

    # Return a dictionary of paths for easy access in tests
    return {
        "root": tmp_path,
        "parent": parent_dir,
        "child": child_dir,
        "grandchild": grandchild_dir,
        "other": other_dir,
    }


# Assuming your is_relative_to function is in a file named 'path_utils.py'
# from path_utils import is_relative_to
# For this example, I'll embed the function directly here so it's self-contained.


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


# --- Basic Test Cases ---


def test_basic_child(setup_fs):
    """Tests a direct child directory."""
    parent = setup_fs["parent"]
    child = setup_fs["child"]
    assert is_relative_to(child, parent) is True


def test_grandchild(setup_fs):
    """Tests a deeply nested path."""
    parent = setup_fs["parent"]
    grandchild = setup_fs["grandchild"]
    assert is_relative_to(grandchild, parent) is True


def test_same_path(setup_fs):
    """Tests when child and parent are the same path."""
    parent = setup_fs["parent"]
    assert is_relative_to(parent, parent) is True


def test_unrelated_paths(setup_fs):
    """Tests two completely separate directory trees."""
    parent = setup_fs["parent"]
    other = setup_fs["other"]
    assert is_relative_to(other, parent) is False


def test_parent_is_not_relative_to_child(setup_fs):
    """Tests the reverse relationship, which should be false."""
    parent = setup_fs["parent"]
    child = setup_fs["child"]
    assert is_relative_to(parent, child) is False


# --- Path Traversal and Dot Notation ---


def test_path_with_dots(setup_fs):
    """Tests a path that uses '.' notation."""
    parent = setup_fs["parent"]
    child = setup_fs["parent"] / "." / "child"
    assert is_relative_to(child, parent) is True


def test_path_with_double_dots(setup_fs):
    """Tests a path that uses '..' to navigate up and then down."""
    parent = setup_fs["parent"]
    # This path resolves to tmp_path/parent/child
    child = setup_fs["grandchild"] / ".."
    assert is_relative_to(child, parent) is True
    # This path resolves to tmp_path/parent
    grandparent = setup_fs["grandchild"] / ".." / ".."
    assert is_relative_to(grandparent, parent) is True


# def test_path_traversal_escape(setup_fs):
#     """Tests a path that uses '..' to escape the parent directory."""
#     parent = setup_fs["parent"]
#     # This path resolves to tmp_path/other
#     other = setup_fs["parent"] / ".." / "other"
#     assert is_relative_to(other, parent) is False


# --- Platform-Specific Tests ---


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific case-insensitivity test")
def test_case_insensitivity_windows(setup_fs):
    """On Windows, paths are case-insensitive."""
    parent = setup_fs["parent"]
    child_upper = Path(str(setup_fs["child"]).upper())
    assert is_relative_to(child_upper, parent) is True


@pytest.mark.skipif(sys.platform == "win32", reason="Unix-specific case-sensitivity test")
def test_case_sensitivity_unix(setup_fs):
    """On Unix, paths are case-sensitive."""
    parent = setup_fs["parent"]
    child_upper = Path(str(setup_fs["child"]).upper())
    # The uppercase directory does not exist, so resolving it will fail.
    # The check should correctly return False because the paths don't match.
    assert is_relative_to(child_upper, parent) is False


@pytest.mark.skipif(sys.platform == "win32", reason="Symbolic link tests for Unix-like systems")
def test_symlink_inside_tree_unix(setup_fs):
    """Tests a symlink that points inside the parent tree."""
    parent = setup_fs["parent"]
    grandchild = setup_fs["grandchild"]

    # Create a symlink from other/link -> parent/grandchild
    link_path = setup_fs["other"] / "link_to_grandchild"
    link_path.symlink_to(grandchild, target_is_directory=True)

    # The link itself is not relative, but its resolved path is.
    assert is_relative_to(link_path, parent) is True


@pytest.mark.skipif(sys.platform == "win32", reason="Symbolic link tests for Unix-like systems")
def test_symlink_outside_tree_unix(setup_fs):
    """Tests a symlink that points outside the parent tree."""
    parent = setup_fs["parent"]
    other = setup_fs["other"]

    # Create a symlink from parent/link -> other/
    link_path = parent / "link_to_other"
    link_path.symlink_to(other, target_is_directory=True)

    # The link itself is inside parent, but its resolved path is not.
    assert is_relative_to(link_path, parent) is False
