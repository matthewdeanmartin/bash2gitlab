"""
Pytest unit tests for the detect_drift module.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from bash2gitlab.commands import detect_drift
from bash2gitlab.commands.detect_drift import (
    Colors,
    _decode_hash_content,
    _generate_pretty_diff,
    _get_source_file_from_hash,
    find_hash_files,
    run_detect_drift,
)

# --- Fixtures and Helper Functions ---


def create_file(path: Path, content: str):
    """Helper to create a file with content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def create_hash_file(path: Path, content_to_hash: str):
    """Helper to create a .hash file from content."""
    encoded_content = base64.b64encode(content_to_hash.encode("utf-8")).decode("utf-8")
    create_file(path, encoded_content)


# --- Unit Tests for Helper Functions ---


def test_get_source_file_from_hash():
    """Tests that the source file path is correctly derived from the hash file path."""
    hash_path = Path("/tmp/test/some.file.yml.hash")
    expected_source_path = Path("/tmp/test/some.file.yml")
    assert _get_source_file_from_hash(hash_path) == expected_source_path


def test_decode_hash_content(tmp_path: Path):
    """Tests decoding of valid, invalid, and empty hash files."""
    original_content = "hello world"
    hash_file = tmp_path / "test.yml.hash"
    corrupted_file = tmp_path / "corrupted.yml.hash"
    empty_file = tmp_path / "empty.yml.hash"

    # Valid case
    create_hash_file(hash_file, original_content)
    assert _decode_hash_content(hash_file) == original_content

    # Corrupted case (not valid base64)
    create_file(corrupted_file, "not base64!")
    assert _decode_hash_content(corrupted_file) is None

    # Empty file case
    create_file(empty_file, "")
    assert _decode_hash_content(empty_file) is None

    # Non-existent file case
    assert _decode_hash_content(tmp_path / "nonexistent.hash") is None


def test_generate_pretty_diff_with_color(monkeypatch):
    """Tests that the diff output contains color codes when enabled."""
    # Ensure colors are enabled for this test
    monkeypatch.setattr(detect_drift.Colors, "_enabled", True)
    # Re-initialize colors based on the patched value
    monkeypatch.setattr(detect_drift, "Colors", detect_drift.Colors())

    content_before = "line 1\nline 2\nline 3"
    content_after = "line 1\nline two\nline 3"
    diff = _generate_pretty_diff(content_after, content_before, Path("test.txt"))

    assert Colors.FAIL in diff  # Should contain red for deletion
    assert Colors.OKGREEN in diff  # Should contain green for addition
    assert "-line 2" in diff
    assert "+line two" in diff


def test_find_hash_files(tmp_path: Path):
    """Tests the discovery of .hash files in various directory structures."""
    root_hash = tmp_path / "root.yml.hash"
    templates_dir = tmp_path / "templates"
    template_hash = templates_dir / "template1.yml.hash"
    nested_dir = templates_dir / "nested"
    nested_hash = nested_dir / "nested.yaml.hash"

    create_file(root_hash, "hash_content")
    create_file(template_hash, "hash_content")
    create_file(nested_hash, "hash_content")
    create_file(tmp_path / "not-a-hash.txt", "some content")

    # Test finding all files
    found_files = set(find_hash_files([tmp_path]))
    assert found_files == {root_hash, template_hash, nested_hash}

    # Test finding files only in a sub-directory
    found_files_in_templates = set(find_hash_files([templates_dir]))
    assert found_files_in_templates == {template_hash, nested_hash}

    # Test with a path that is not a directory
    assert list(find_hash_files([root_hash])) == []


# --- Integration Tests for check_for_drift ---


def test_check_for_drift_no_drift(tmp_path: Path, capsys):
    """Tests the scenario where files are unchanged."""
    output_dir = tmp_path / "output"
    source_file = output_dir / "config.yml"
    hash_file = output_dir / "config.yml.hash"
    content = "version: 1"

    create_file(source_file, content)
    create_hash_file(hash_file, content)

    result = run_detect_drift(output_dir)
    captured = capsys.readouterr()

    assert result == 0
    assert "No drift detected" in captured.out


def test_check_for_drift_detected(tmp_path: Path, capsys):
    """Tests the scenario where a file has been modified."""
    output_dir = tmp_path / "output"
    source_file = output_dir / "config.yml"
    hash_file = output_dir / "config.yml.hash"
    original_content = "version: 1"
    modified_content = "version: 2 # modified"

    create_file(source_file, modified_content)
    create_hash_file(hash_file, original_content)

    result = run_detect_drift(output_dir)
    captured = capsys.readouterr()

    assert result == 1
    assert "DRIFT DETECTED" in captured.out
    assert "-version: 1" in captured.out
    assert "+version: 2 # modified" in captured.out


def test_check_for_drift_missing_source_file(tmp_path: Path, caplog):
    """Tests the case where the source file is missing but the hash exists."""
    caplog.set_level(logging.ERROR)
    output_dir = tmp_path / "output"
    hash_file = output_dir / "config.yml.hash"

    create_hash_file(hash_file, "some content")

    result = run_detect_drift(output_dir)

    assert result == 1
    assert "missing for hash file" in caplog.text


def test_check_for_drift_corrupted_hash_file(tmp_path: Path, caplog):
    """Tests the case where the hash file is corrupted."""
    caplog.set_level(logging.ERROR)
    output_dir = tmp_path / "output"
    source_file = output_dir / "config.yml"
    hash_file = output_dir / "config.yml.hash"

    create_file(source_file, "content")
    create_file(hash_file, "not-base64")

    result = run_detect_drift(output_dir)

    assert result == 1
    assert "Could not decode the .hash file" in caplog.text


def test_check_for_drift_no_hash_files_found(tmp_path: Path, caplog, capsys):
    """Tests that the function handles cases with no .hash files gracefully."""
    caplog.set_level(logging.WARNING)
    output_dir = tmp_path / "output"
    create_file(output_dir / "some_file.txt", "content")

    result = run_detect_drift(output_dir)
    captured = capsys.readouterr()

    assert result == 0
    assert "No .hash files found" in caplog.text
    assert "No drift detected" not in captured.out  # Should exit early


def test_check_for_drift_with_templates_dir(tmp_path: Path, capsys):
    """Tests drift checking across a main output and a templates directory."""
    output_dir = tmp_path / "output"

    # No drift file
    source1 = output_dir / "config.yml"
    hash1 = output_dir / "config.yml.hash"
    create_file(source1, "content1")
    create_hash_file(hash1, "content1")

    # Drift file
    source2 = output_dir / "template.yml"
    hash2 = output_dir / "template.yml.hash"
    create_file(source2, "modified content")
    create_hash_file(hash2, "original content")

    result = run_detect_drift(output_dir)
    captured = capsys.readouterr()

    assert result == 1
    assert f"DRIFT DETECTED IN: {source2}" in captured.out
    assert "-original content" in captured.out
    assert "+modified content" in captured.out
