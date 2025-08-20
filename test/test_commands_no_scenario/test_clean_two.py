# test_file_hasher.py

import base64
from pathlib import Path

import pytest

# Assuming the code is in a file named 'file_hasher.py'
# If your file has a different name, adjust the import
from bash2gitlab.commands.clean_all import (
    base_from_hash,
    clean_targets,
    is_target_unchanged,
    iter_target_pairs,
    list_stray_files,
    partner_hash_file,
    read_current_text,
    read_hash_text,
)

# --- Test Data and Helpers ---------------------------------------------------

CONTENT_OK = "This is the original content."
CONTENT_CHANGED = "This content has been modified."
CONTENT_B64 = base64.b64encode(CONTENT_OK.encode("utf-8")).decode("utf-8")
CONTENT_INVALID_B64 = "this is not base64 content!"


@pytest.fixture
def complex_dir(tmp_path: Path) -> Path:
    """Creates a directory with a mix of valid pairs, stray files, and edge cases."""
    # 1. A valid, matching pair
    (tmp_path / "good.txt").write_text(CONTENT_OK, encoding="utf-8")
    (tmp_path / "good.txt.hash").write_text(CONTENT_B64, encoding="utf-8")

    # 2. A pair where the base file has changed
    (tmp_path / "changed.txt").write_text(CONTENT_CHANGED, encoding="utf-8")
    (tmp_path / "changed.txt.hash").write_text(CONTENT_B64, encoding="utf-8")

    # 3. A pair where the hash file is corrupt/invalid
    (tmp_path / "invalid.yml").write_text(CONTENT_OK, encoding="utf-8")
    (tmp_path / "invalid.yml.hash").write_text(CONTENT_INVALID_B64, encoding="utf-8")

    # 4. A stray base file
    (tmp_path / "stray.txt").write_text("I have no hash.", encoding="utf-8")

    # 5. A stray hash file
    (tmp_path / "stray.txt.hash").write_text(CONTENT_B64, encoding="utf-8")

    # 6. Subdirectory with a valid pair
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "sub_good.txt").write_text(CONTENT_OK, encoding="utf-8")
    (sub / "sub_good.txt.hash").write_text(CONTENT_B64, encoding="utf-8")

    # 7. Subdirectory with a stray hash
    (sub / "sub_stray.txt.hash").write_text(CONTENT_B64, encoding="utf-8")

    return tmp_path


# --- Tests for Helper Functions ----------------------------------------------


@pytest.mark.parametrize(
    "base_name, expected_hash_name",
    [
        ("foo.txt", "foo.txt.hash"),
        ("bar.tar.gz", "bar.tar.gz.hash"),
        ("baz", "baz.hash"),
        ("dir/file.ext", "dir/file.ext.hash"),
    ],
)
def test_partner_hash_file(base_name, expected_hash_name):
    """Tests that the correct hash file path is generated."""
    assert partner_hash_file(Path(base_name)) == Path(expected_hash_name)


@pytest.mark.parametrize(
    "hash_name, expected_base_name",
    [
        ("foo.txt.hash", "foo.txt"),
        ("bar.tar.gz.hash", "bar.tar.gz"),
        ("baz.hash", "baz"),
        ("dir/file.ext.hash", "dir/file.ext"),
        ("not_a_hash.txt", "not_a_hash.txt"),  # Should not change
    ],
)
def test_base_from_hash(hash_name, expected_base_name):
    """Tests that the correct base file path is derived from a hash file path."""
    assert base_from_hash(Path(hash_name)) == Path(expected_base_name)


# --- Tests for Inspection Utilities ------------------------------------------


def test_iter_target_pairs_empty(tmp_path: Path):
    """Tests that an empty directory yields no pairs."""
    assert list(iter_target_pairs(tmp_path)) == []


def test_list_stray_files_no_strays(tmp_path: Path):
    """Tests that a directory with only valid pairs has no strays."""
    (tmp_path / "a.txt").touch()
    (tmp_path / "a.txt.hash").touch()
    assert list_stray_files(tmp_path) == []


# --- Tests for Hash Verification ---------------------------------------------


def test_read_current_text(tmp_path: Path):
    """Tests reading UTF-8 text from a file."""
    path = tmp_path / "file.txt"
    content = "Hello, world! 👋"
    path.write_text(content, encoding="utf-8")
    assert read_current_text(path) == content


def test_read_hash_text(tmp_path: Path):
    """Tests decoding of a valid base64 hash file."""
    hash_file = tmp_path / "file.hash"
    hash_file.write_text(f"  {CONTENT_B64}  \n", encoding="utf-8")  # Test stripping
    assert read_hash_text(hash_file) == CONTENT_OK


def test_read_hash_text_invalid(tmp_path: Path):
    """Tests that invalid base64 content returns None."""
    hash_file = tmp_path / "file.hash"
    hash_file.write_text(CONTENT_INVALID_B64, encoding="utf-8")
    assert read_hash_text(hash_file) is None


def test_is_target_unchanged_true(tmp_path: Path):
    """Tests when base file content matches the hash."""
    base_file = tmp_path / "a.txt"
    hash_file = tmp_path / "a.txt.hash"
    base_file.write_text(CONTENT_OK, encoding="utf-8")
    hash_file.write_text(CONTENT_B64, encoding="utf-8")

    assert is_target_unchanged(base_file, hash_file) is True


def test_is_target_unchanged_false(tmp_path: Path):
    """Tests when base file content does not match the hash."""
    base_file = tmp_path / "a.txt"
    hash_file = tmp_path / "a.txt.hash"
    base_file.write_text(CONTENT_CHANGED, encoding="utf-8")
    hash_file.write_text(CONTENT_B64, encoding="utf-8")

    assert is_target_unchanged(base_file, hash_file) is False


def test_is_target_unchanged_invalid_hash(tmp_path: Path):
    """Tests when the hash file is unreadable."""
    base_file = tmp_path / "a.txt"
    hash_file = tmp_path / "a.txt.hash"
    base_file.write_text(CONTENT_OK, encoding="utf-8")
    hash_file.write_text(CONTENT_INVALID_B64, encoding="utf-8")

    assert is_target_unchanged(base_file, hash_file) is None


# --- Tests for Cleaning ------------------------------------------------------


def test_clean_targets_no_pairs(tmp_path: Path):
    """Tests that cleaning an empty or stray-only directory does nothing."""
    (tmp_path / "stray.txt").touch()
    assert clean_targets(tmp_path) == (0, 0, 0)
    assert (tmp_path / "stray.txt").exists()
