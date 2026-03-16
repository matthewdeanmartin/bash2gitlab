"""Tests for hash_path_helpers: path computation, migration, iteration."""

from bash2yaml.commands.hash_path_helpers import (
    find_hash_file,
    get_old_hash_path,
    get_output_hash_path,
    get_source_file_from_hash,
    iter_hash_files_in_directory,
    migrate_hash_file,
)


class TestGetOutputHashPath:
    def test_simple_file(self, tmp_path):
        out_base = tmp_path / "out"
        out_file = out_base / "ci.yml"
        result = get_output_hash_path(out_file, out_base)
        assert result == out_base / ".bash2yaml" / "output_hashes" / "ci.yml.hash"

    def test_nested_file(self, tmp_path):
        out_base = tmp_path / "out"
        out_file = out_base / "sub" / "deploy.yml"
        result = get_output_hash_path(out_file, out_base)
        assert result == out_base / ".bash2yaml" / "output_hashes" / "sub" / "deploy.yml.hash"

    def test_suffix_preserved(self, tmp_path):
        out_base = tmp_path / "out"
        out_file = out_base / "file.yaml"
        result = get_output_hash_path(out_file, out_base)
        assert result.name == "file.yaml.hash"


class TestGetOldHashPath:
    def test_appends_hash_suffix(self, tmp_path):
        f = tmp_path / "ci.yml"
        result = get_old_hash_path(f)
        assert result == tmp_path / "ci.yml.hash"


class TestFindHashFile:
    def test_finds_new_location(self, tmp_path):
        out_base = tmp_path / "out"
        out_file = out_base / "ci.yml"
        new_hash = get_output_hash_path(out_file, out_base)
        new_hash.parent.mkdir(parents=True)
        new_hash.write_text("abc")
        result = find_hash_file(out_file, out_base)
        assert result == new_hash

    def test_finds_old_location_as_fallback(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        out_file = out_base / "ci.yml"
        old_hash = get_old_hash_path(out_file)
        old_hash.write_text("abc")
        result = find_hash_file(out_file, out_base)
        assert result == old_hash

    def test_prefers_new_over_old(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        out_file = out_base / "ci.yml"
        new_hash = get_output_hash_path(out_file, out_base)
        new_hash.parent.mkdir(parents=True)
        new_hash.write_text("new")
        old_hash = get_old_hash_path(out_file)
        old_hash.write_text("old")
        result = find_hash_file(out_file, out_base)
        assert result == new_hash

    def test_returns_none_when_missing(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        out_file = out_base / "ci.yml"
        result = find_hash_file(out_file, out_base)
        assert result is None


class TestMigrateHashFile:
    def test_migrates_old_to_new(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        out_file = out_base / "ci.yml"
        old_hash = get_old_hash_path(out_file)
        old_hash.write_text("myhash")
        migrated = migrate_hash_file(out_file, out_base)
        assert migrated is True
        new_hash = get_output_hash_path(out_file, out_base)
        assert new_hash.exists()
        assert new_hash.read_text() == "myhash"
        assert not old_hash.exists()

    def test_no_migrate_if_no_old(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        out_file = out_base / "ci.yml"
        migrated = migrate_hash_file(out_file, out_base)
        assert migrated is False

    def test_no_migrate_if_new_already_exists(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        out_file = out_base / "ci.yml"
        old_hash = get_old_hash_path(out_file)
        old_hash.write_text("old")
        new_hash = get_output_hash_path(out_file, out_base)
        new_hash.parent.mkdir(parents=True)
        new_hash.write_text("new")
        migrated = migrate_hash_file(out_file, out_base)
        assert migrated is False
        assert new_hash.read_text() == "new"


class TestGetSourceFileFromHash:
    def test_new_location(self, tmp_path):
        out_base = tmp_path / "out"
        hash_file = out_base / ".bash2yaml" / "output_hashes" / "ci" / "deploy.yml.hash"
        result = get_source_file_from_hash(hash_file, out_base)
        assert result == out_base / "ci" / "deploy.yml"

    def test_old_sibling_location(self, tmp_path):
        out_base = tmp_path / "out"
        hash_file = out_base / "ci.yml.hash"
        result = get_source_file_from_hash(hash_file, out_base)
        assert result == out_base / "ci.yml"


class TestIterHashFilesInDirectory:
    def test_finds_new_hash_files(self, tmp_path):
        out_base = tmp_path / "out"
        hash_dir = out_base / ".bash2yaml" / "output_hashes"
        hash_dir.mkdir(parents=True)
        h = hash_dir / "ci.yml.hash"
        h.write_text("abc")
        result = iter_hash_files_in_directory(out_base)
        assert h in result

    def test_finds_old_hash_files(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        h = out_base / "ci.yml.hash"
        h.write_text("abc")
        result = iter_hash_files_in_directory(out_base)
        assert h in result

    def test_empty_dir_returns_empty(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        result = iter_hash_files_in_directory(out_base)
        assert result == []

    def test_no_duplicate_for_migrated_file(self, tmp_path):
        """A file with both old and new hash should not appear twice."""
        out_base = tmp_path / "out"
        out_base.mkdir()
        out_file = out_base / "ci.yml"
        # Create both old and new hash files
        old = get_old_hash_path(out_file)
        old.write_text("old")
        new = get_output_hash_path(out_file, out_base)
        new.parent.mkdir(parents=True)
        new.write_text("new")
        result = iter_hash_files_in_directory(out_base)
        # Only the new location should appear (old is for a file that has new hash)
        assert new in result
        assert old not in result
