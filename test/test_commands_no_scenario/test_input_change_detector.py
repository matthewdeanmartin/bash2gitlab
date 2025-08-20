from pathlib import Path

import pytest

import bash2gitlab.commands.input_change_detector as cd

# --- Tests for Helper Functions ---


def test_normalize_text_content():
    """Tests normalization of text content by removing all whitespace."""
    content = "hello \n world\t from a test"
    expected = "helloworldfromatest"
    assert cd.normalize_text_content(content) == expected


def test_normalize_text_content_empty():
    """Tests normalization of an empty string."""
    assert cd.normalize_text_content("") == ""


def test_compute_content_hash(tmp_path: Path):
    """Tests that content hashing is consistent across format changes."""
    # Test YAML files
    yaml_file1 = tmp_path / "test1.yml"
    yaml_file1.write_text("key: value\nlist:\n- a\n- b\n")

    yaml_file2_same_data = tmp_path / "test2.yml"
    yaml_file2_same_data.write_text("{key: value, list: [a, b]}")

    yaml_file3_diff_data = tmp_path / "test3.yml"
    yaml_file3_diff_data.write_text("key: other_value")

    hash1 = cd.compute_content_hash(yaml_file1)
    hash2 = cd.compute_content_hash(yaml_file2_same_data)
    hash3 = cd.compute_content_hash(yaml_file3_diff_data)

    assert hash1 != hash2
    assert hash1 != hash3

    # Test text files (e.g., shell scripts)
    sh_file1 = tmp_path / "script1.sh"
    sh_file1.write_text("echo 'hello'\n ls -l\n")

    sh_file2_same_data = tmp_path / "script2.sh"
    sh_file2_same_data.write_text("echo 'hello'    \n\nls -l")

    sh_file3_diff_data = tmp_path / "script3.sh"
    sh_file3_diff_data.write_text("echo 'goodbye'\n ls -l\n")

    hash4 = cd.compute_content_hash(sh_file1)
    hash5 = cd.compute_content_hash(sh_file2_same_data)
    hash6 = cd.compute_content_hash(sh_file3_diff_data)

    assert hash4 == hash5
    assert hash4 != hash6


def test_read_write_hash(tmp_path: Path):
    """Tests the private _read_stored_hash and _write_hash functions."""
    hash_file = tmp_path / "hashes" / "some.hash"
    test_hash = "12345abcdef"

    # Reading non-existent file should return None
    assert cd._read_stored_hash(hash_file) is None

    # Write the hash
    cd._write_hash(hash_file, test_hash)

    # Reading existing file should return the hash content
    assert hash_file.exists()
    assert cd._read_stored_hash(hash_file) == test_hash


# --- Tests for InputChangeDetector Class ---


@pytest.fixture
def detector(tmp_path: Path) -> cd.InputChangeDetector:
    """Provides an InputChangeDetector instance with a base path."""
    base_path = tmp_path / "project"
    base_path.mkdir()
    return cd.InputChangeDetector(base_path)


class TestInputChangeDetector:
    """Test suite for the InputChangeDetector class."""

    def test_get_hash_file_path_relative(self, detector: cd.InputChangeDetector):
        """Tests hash file path generation for a file relative to the base path."""
        input_file = detector.base_path / "src" / "main.py"
        expected_hash_path = detector.hash_dir / "src" / "main.py.hash"
        assert detector._get_hash_file_path(input_file) == expected_hash_path

    def test_get_hash_file_path_absolute(self, detector: cd.InputChangeDetector):
        """Tests hash file path generation for a file outside the base path."""
        # Use a path that is not relative to base_path
        input_file = Path("/var/tmp/other.sh")
        expected_hash_path = detector.hash_dir / "var" / "tmp" / "other.sh.hash"
        assert detector._get_hash_file_path(input_file) == expected_hash_path

    def test_has_file_changed_workflow(self, detector: cd.InputChangeDetector):
        """Tests the full change detection workflow for a single file."""
        input_dir = detector.base_path / "input"
        input_dir.mkdir()
        file_path = input_dir / "script.sh"
        file_path.write_text("initial content")

        # 1. New file should be considered changed
        assert detector.has_file_changed(file_path) is True

        # 2. After marking compiled, it should be unchanged
        detector.mark_compiled(input_dir)
        assert detector.has_file_changed(file_path) is False

        # 3. Changing only formatting/whitespace should NOT be a change
        file_path.write_text("  initial \n content   ")
        assert detector.has_file_changed(file_path) is False

        # 4. Changing content should be a change
        file_path.write_text("new content")
        assert detector.has_file_changed(file_path) is True

    def test_needs_compilation_workflow(self, detector: cd.InputChangeDetector):
        """Tests the directory-level compilation check."""
        input_dir = detector.base_path / "scripts"
        input_dir.mkdir()
        (input_dir / "script1.sh").write_text("echo 1")
        (input_dir / "script2.yml").write_text("key: val")

        # 1. With new files, compilation is needed
        assert detector.needs_compilation(input_dir) is True

        # 2. After marking, compilation is not needed
        detector.mark_compiled(input_dir)
        assert detector.needs_compilation(input_dir) is False

        # 3. Modify one file, compilation is needed again
        (input_dir / "script1.sh").write_text("echo 2")
        assert detector.needs_compilation(input_dir) is True

        # 4. Mark again, then add a new file
        detector.mark_compiled(input_dir)
        assert detector.needs_compilation(input_dir) is False
        (input_dir / "new_file.py").write_text("print()")
        assert detector.needs_compilation(input_dir) is True

    def test_get_changed_files(self, detector: cd.InputChangeDetector):
        """Tests getting a list of changed files."""
        input_dir = detector.base_path / "src"
        input_dir.mkdir()
        file1 = input_dir / "file1.py"
        file2 = input_dir / "file2.yml"
        file1.write_text("a=1")
        file2.write_text("k: v")

        # Initially, all files are new/changed
        changed = detector.get_changed_files(input_dir)
        assert set(changed) == {file1, file2}

        # After marking, no files have changed
        detector.mark_compiled(input_dir)
        assert detector.get_changed_files(input_dir) == []

        # Modify one file, only it should be in the list
        file2.write_text("k: v2")
        changed = detector.get_changed_files(input_dir)
        assert changed == [file2]


# --- Test Convenience Functions ---


def test_convenience_functions_workflow(tmp_path: Path):
    """Tests the standalone convenience functions."""
    input_dir = tmp_path / "my_project"
    input_dir.mkdir()
    file_path = input_dir / "run.sh"
    file_path.write_text("echo 'hello'")

    # 1. Check if compilation is needed (it should be)
    assert cd.needs_compilation(input_dir) is True
    changed_files = cd.get_changed_files(input_dir)
    assert changed_files == [file_path]

    # 2. Mark compilation as complete
    cd.mark_compilation_complete(input_dir)

    # 3. Now, compilation should not be needed
    assert cd.needs_compilation(input_dir) is False
    assert cd.get_changed_files(input_dir) == []

    # 4. Modify the file and check again
    file_path.write_text("echo 'world'")
    assert cd.needs_compilation(input_dir) is True
    assert cd.get_changed_files(input_dir) == [file_path]
