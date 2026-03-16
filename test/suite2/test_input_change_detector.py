"""Tests for input_change_detector: hash-based incremental build detection."""

from bash2yaml.commands.input_change_detector import (
    InputChangeDetector,
    compute_content_hash,
    get_changed_files,
    mark_compilation_complete,
    needs_compilation,
    normalize_text_content,
    normalize_yaml_content,
)


class TestNormalizeTextContent:
    def test_strips_whitespace(self):
        result = normalize_text_content("  hello   world  \n")
        assert result == "helloworld"

    def test_same_content_same_hash(self):
        a = normalize_text_content("echo hello")
        b = normalize_text_content("  echo   hello  ")
        assert a == b


class TestNormalizeYamlContent:
    def test_returns_string(self):
        yaml = "key: value\n"
        result = normalize_yaml_content(yaml)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_semantically_equivalent_yaml_normalizes_same(self):
        yaml1 = "key: value\n"
        yaml2 = "key:  value\n"
        n1 = normalize_yaml_content(yaml1)
        n2 = normalize_yaml_content(yaml2)
        assert n1 == n2

    def test_invalid_yaml_returns_original(self):
        invalid = "not: valid: yaml: : :"
        # Should not raise, falls back to original
        result = normalize_yaml_content(invalid)
        assert isinstance(result, str)


class TestComputeContentHash:
    def test_returns_hex_string(self, tmp_path):
        f = tmp_path / "test.sh"
        f.write_text("echo hello\n")
        h = compute_content_hash(f)
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.sh"
        f2 = tmp_path / "b.sh"
        f1.write_text("echo hello\n")
        f2.write_text("echo world\n")
        assert compute_content_hash(f1) != compute_content_hash(f2)

    def test_yaml_files_normalized(self, tmp_path):
        f1 = tmp_path / "a.yml"
        f2 = tmp_path / "b.yml"
        f1.write_text("key: value\n")
        f2.write_text("key:  value\n")
        # Semantically same YAML should have same hash
        assert compute_content_hash(f1) == compute_content_hash(f2)


class TestInputChangeDetector:
    def test_new_file_considered_changed(self, tmp_path):
        f = tmp_path / "script.sh"
        f.write_text("echo hello\n")
        detector = InputChangeDetector(tmp_path)
        assert detector.has_file_changed(f) is True

    def test_after_mark_compiled_not_changed(self, tmp_path):
        f = tmp_path / "script.sh"
        f.write_text("echo hello\n")
        detector = InputChangeDetector(tmp_path)
        # First check: changed (no previous hash)
        assert detector.has_file_changed(f) is True
        # Mark compiled
        detector.mark_compiled(tmp_path)
        # Now check again
        assert detector.has_file_changed(f) is False

    def test_modified_file_considered_changed(self, tmp_path):
        f = tmp_path / "script.sh"
        f.write_text("echo hello\n")
        detector = InputChangeDetector(tmp_path)
        detector.mark_compiled(tmp_path)
        # Modify the file
        f.write_text("echo changed\n")
        assert detector.has_file_changed(f) is True

    def test_missing_file_considered_changed(self, tmp_path):
        detector = InputChangeDetector(tmp_path)
        assert detector.has_file_changed(tmp_path / "nonexistent.sh") is True

    def test_needs_compilation_no_files(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        detector = InputChangeDetector(tmp_path)
        # Empty dir: no files means no compilation needed
        result = detector.needs_compilation(input_dir)
        assert result is False

    def test_needs_compilation_with_new_files(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "script.sh").write_text("echo hi\n")
        detector = InputChangeDetector(tmp_path)
        assert detector.needs_compilation(input_dir) is True

    def test_needs_compilation_false_after_mark(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "script.sh").write_text("echo hi\n")
        detector = InputChangeDetector(tmp_path)
        detector.mark_compiled(input_dir)
        assert detector.needs_compilation(input_dir) is False

    def test_get_changed_files_returns_list(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        f = input_dir / "script.sh"
        f.write_text("echo hi\n")
        detector = InputChangeDetector(tmp_path)
        changed = detector.get_changed_files(input_dir)
        assert f in changed

    def test_get_changed_files_empty_after_mark(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "script.sh").write_text("echo hi\n")
        detector = InputChangeDetector(tmp_path)
        detector.mark_compiled(input_dir)
        changed = detector.get_changed_files(input_dir)
        assert changed == []

    def test_cleanup_stale_hashes(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        f = input_dir / "script.sh"
        f.write_text("echo hi\n")
        detector = InputChangeDetector(tmp_path)
        detector.mark_compiled(input_dir)
        # Delete the input file
        f.unlink()
        # Cleanup
        detector.cleanup_stale_hashes(input_dir)
        # Hash file should be gone
        hash_files = list(detector.hash_dir.rglob("*.hash"))
        assert hash_files == []


class TestConvenienceFunctions:
    def test_needs_compilation_function(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "script.sh").write_text("echo hi\n")
        assert needs_compilation(input_dir) is True

    def test_mark_compilation_complete_function(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "script.sh").write_text("echo hi\n")
        mark_compilation_complete(input_dir)
        assert needs_compilation(input_dir) is False

    def test_get_changed_files_function(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        f = input_dir / "script.sh"
        f.write_text("echo hi\n")
        changed = get_changed_files(input_dir)
        assert f in changed
