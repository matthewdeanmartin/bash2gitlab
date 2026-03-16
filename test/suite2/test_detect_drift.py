"""Tests for detect_drift: hash-based drift detection."""

import base64

from bash2yaml.commands.detect_drift import decode_hash_content, find_hash_files, run_detect_drift
from bash2yaml.commands.hash_path_helpers import get_output_hash_path


def _make_hash_file(content: str, hash_file_path):
    """Write a base64-encoded hash file for given content."""
    hash_file_path.parent.mkdir(parents=True, exist_ok=True)
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    hash_file_path.write_text(encoded)


class TestDecodeHashContent:
    def test_decodes_valid_hash(self, tmp_path):
        content = "hello world\n"
        h = tmp_path / "test.hash"
        _make_hash_file(content, h)
        result = decode_hash_content(h)
        assert result == content

    def test_returns_none_for_empty_file(self, tmp_path):
        h = tmp_path / "empty.hash"
        h.write_text("")
        result = decode_hash_content(h)
        assert result is None

    def test_returns_none_for_corrupted_file(self, tmp_path):
        h = tmp_path / "bad.hash"
        h.write_text("not valid base64!!!")
        result = decode_hash_content(h)
        assert result is None

    def test_returns_none_for_missing_file(self, tmp_path):
        result = decode_hash_content(tmp_path / "nonexistent.hash")
        assert result is None


class TestFindHashFiles:
    def test_finds_hash_files_in_new_location(self, tmp_path):
        out_base = tmp_path / "out"
        hash_dir = out_base / ".bash2yaml" / "output_hashes"
        hash_dir.mkdir(parents=True)
        h = hash_dir / "ci.yml.hash"
        h.write_text("abc")
        found = list(find_hash_files([out_base]))
        assert h in found

    def test_skips_nonexistent_dirs(self, tmp_path):
        # Should not raise, just warn
        found = list(find_hash_files([tmp_path / "nonexistent"]))
        assert found == []

    def test_finds_hash_files_in_multiple_dirs(self, tmp_path):
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        h1 = dir1 / ".bash2yaml" / "output_hashes" / "a.yml.hash"
        h2 = dir2 / ".bash2yaml" / "output_hashes" / "b.yml.hash"
        for h in [h1, h2]:
            h.parent.mkdir(parents=True)
            h.write_text("abc")
        found = list(find_hash_files([dir1, dir2]))
        assert h1 in found
        assert h2 in found


class TestRunDetectDrift:
    def test_no_drift_returns_zero(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        content = "hello world\n"
        out_file = out_base / "ci.yml"
        out_file.write_text(content)
        hash_file = get_output_hash_path(out_file, out_base)
        _make_hash_file(content, hash_file)
        result = run_detect_drift(out_base)
        assert result == 0

    def test_drift_returns_one(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        original = "original content\n"
        modified = "modified content\n"
        out_file = out_base / "ci.yml"
        out_file.write_text(modified)
        hash_file = get_output_hash_path(out_file, out_base)
        _make_hash_file(original, hash_file)
        result = run_detect_drift(out_base)
        assert result == 1

    def test_no_hash_files_returns_zero(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        result = run_detect_drift(out_base)
        assert result == 0

    def test_missing_source_file_returns_one(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        # Create a hash file but no corresponding output file
        out_file = out_base / "ci.yml"
        hash_file = get_output_hash_path(out_file, out_base)
        _make_hash_file("some content\n", hash_file)
        result = run_detect_drift(out_base)
        assert result == 1

    def test_multiple_files_all_clean(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        for name in ["a.yml", "b.yml", "c.yml"]:
            content = f"content of {name}\n"
            out_file = out_base / name
            out_file.write_text(content)
            _make_hash_file(content, get_output_hash_path(out_file, out_base))
        result = run_detect_drift(out_base)
        assert result == 0

    def test_one_drifted_among_many(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        # Two clean files
        for name in ["a.yml", "b.yml"]:
            content = f"content of {name}\n"
            out_file = out_base / name
            out_file.write_text(content)
            _make_hash_file(content, get_output_hash_path(out_file, out_base))
        # One drifted file
        drifted = out_base / "c.yml"
        drifted.write_text("modified\n")
        _make_hash_file("original\n", get_output_hash_path(drifted, out_base))
        result = run_detect_drift(out_base)
        assert result == 1
