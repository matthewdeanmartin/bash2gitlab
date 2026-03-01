"""Unit tests for artifact inlining functionality."""

from pathlib import Path

from bash2gitlab.commands.compile_artifacts import (
    create_zip_artifact,
    encode_artifact,
    format_size,
    maybe_inline_artifact,
)


def write_file(tmp_path: Path, name: str, content: str) -> Path:
    """Helper to create a file with UTF-8 encoding."""
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_pragma_regex_matches_basic(tmp_path: Path):
    """Test that basic pragma syntax is recognized."""
    write_file(tmp_path, "config.txt", "test content")
    line = "- # Pragma: inline-artifact config.txt"
    result, _found_path = maybe_inline_artifact(line, tmp_path)
    assert result is not None
    assert result[0].startswith("# >>> BEGIN inline-artifact:")
    assert "__B2G_ARTIFACT=" in result[1]
    assert "base64 -d" in result[3]
    assert result[4] == "unset __B2G_ARTIFACT"
    assert result[5] == "# <<< END inline-artifact"


def test_pragma_with_output_path(tmp_path: Path):
    """Test pragma with --output option."""
    write_file(tmp_path, "config.txt", "test content")
    line = "- # Pragma: inline-artifact config.txt --output=/tmp/extracted"
    result, _found_path = maybe_inline_artifact(line, tmp_path)
    assert result is not None
    assert "/tmp/extracted" in result[3]


def test_pragma_with_format_option(tmp_path: Path):
    """Test pragma with --format option."""
    write_file(tmp_path, "config.txt", "test content")
    line = "- # Pragma: inline-artifact config.txt --format=tar.gz"
    result, _found_path = maybe_inline_artifact(line, tmp_path)
    assert result is not None
    assert "(tar.gz," in result[0]


def test_pragma_without_dash_prefix(tmp_path: Path):
    """Test that pragma works without leading dash (though not recommended)."""
    write_file(tmp_path, "config.txt", "test content")
    line = "# Pragma: inline-artifact config.txt"
    result, _found_path = maybe_inline_artifact(line, tmp_path)
    assert result is not None


def test_directory_artifact(tmp_path: Path):
    """Test inlining a directory."""
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    write_file(config_dir, "file1.txt", "content1")
    write_file(config_dir, "file2.txt", "content2")

    line = "- # Pragma: inline-artifact configs"
    result, _found_path = maybe_inline_artifact(line, tmp_path)
    assert result is not None
    assert "configs" in result[0]
    assert "__B2G_ARTIFACT=" in result[1]


def test_single_file_artifact(tmp_path: Path):
    """Test inlining a single file."""
    write_file(tmp_path, "single.conf", "single file content")

    line = "- # Pragma: inline-artifact single.conf"
    result, _found_path = maybe_inline_artifact(line, tmp_path)
    assert result is not None
    assert "single.conf" in result[0]


def test_missing_source_returns_none(tmp_path: Path):
    """Test that missing source path returns None."""
    line = "- # Pragma: inline-artifact missing.txt"
    result, _found_path = maybe_inline_artifact(line, tmp_path)
    assert result is None


def test_non_pragma_line_returns_none(tmp_path: Path):
    """Test that non-pragma lines return None."""
    line = "echo hello"
    result, _found_path = maybe_inline_artifact(line, tmp_path)
    assert result is None


def test_artifact_too_large_returns_none(tmp_path: Path, monkeypatch):
    """Test that oversized artifacts return None."""
    # Create a large file - use random data since repeated chars compress well
    import random
    import string

    large_content = "".join(random.choices(string.ascii_letters + string.digits, k=100000))
    write_file(tmp_path, "large.txt", large_content)

    # Set a very small max size to ensure failure
    monkeypatch.setenv("BASH2GITLAB_MAX_ARTIFACT_SIZE", "100")

    line = "- # Pragma: inline-artifact large.txt"
    result, _found_path = maybe_inline_artifact(line, tmp_path)
    assert result is None


def test_create_zip_artifact_file(tmp_path: Path):
    """Test creating zip from a single file."""
    test_file = write_file(tmp_path, "test.txt", "test content")
    zip_bytes = create_zip_artifact(test_file)
    assert len(zip_bytes) > 0
    # Verify it's a zip file (starts with PK)
    assert zip_bytes[:2] == b"PK"


def test_create_zip_artifact_directory(tmp_path: Path):
    """Test creating zip from a directory."""
    test_dir = tmp_path / "testdir"
    test_dir.mkdir()
    write_file(test_dir, "file1.txt", "content1")
    write_file(test_dir, "file2.txt", "content2")

    zip_bytes = create_zip_artifact(test_dir)
    assert len(zip_bytes) > 0
    assert zip_bytes[:2] == b"PK"


def test_encode_artifact():
    """Test base64 encoding of artifact."""
    test_bytes = b"hello world"
    encoded = encode_artifact(test_bytes)
    assert isinstance(encoded, str)
    # Verify it's valid base64
    import base64

    decoded = base64.b64decode(encoded)
    assert decoded == test_bytes


def test_format_size():
    """Test size formatting."""
    assert "bytes" in format_size(500)
    assert "KB" in format_size(5000)
    assert "MB" in format_size(5000000)


def test_security_path_traversal_blocked(tmp_path: Path):
    """Test that path traversal attempts are blocked."""
    # Try to reference a file outside the input_dir
    line = "- # Pragma: inline-artifact ../outside.txt"
    result, _found_path = maybe_inline_artifact(line, tmp_path)
    # Should return None due to security check
    assert result is None


def test_nested_directory_structure(tmp_path: Path):
    """Test inlining nested directory structures."""
    nested = tmp_path / "level1" / "level2" / "level3"
    nested.mkdir(parents=True)
    write_file(nested, "deep.txt", "deep content")

    line = "- # Pragma: inline-artifact level1"
    result, _found_path = maybe_inline_artifact(line, tmp_path)
    assert result is not None
    assert "level1" in result[0]


def test_default_output_path(tmp_path: Path):
    """Test that default output path is set correctly."""
    write_file(tmp_path, "myfile.txt", "content")

    line = "- # Pragma: inline-artifact myfile.txt"
    result, _found_path = maybe_inline_artifact(line, tmp_path)
    assert result is not None
    # Default output should be ./myfile.txt
    assert "./myfile.txt" in result[2] or "./myfile.txt" in result[3]
