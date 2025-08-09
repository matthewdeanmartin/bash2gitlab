# test_commit_map_command.py
from pathlib import Path
import hashlib

import pytest

from bash2gitlab.commit_map_command import commit_map


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


@pytest.fixture
def prepare_environment(tmp_path: Path):
    """Create source and target directories with an initial file and hash."""
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()

    source_file = source_dir / "file.txt"
    target_file = target_dir / "file.txt"
    content = "original"
    source_file.write_text(content)
    target_file.write_text(content)
    hash_path = target_file.with_suffix(target_file.suffix + ".hash")
    hash_path.write_text(_hash(content))

    return {
        "source_dir": source_dir,
        "target_dir": target_dir,
        "source_file": source_file,
        "target_file": target_file,
        "hash_path": hash_path,
    }


def test_commit_map_copies_changes(prepare_environment):
    """Changed target files are copied back to source and hash updated."""
    env = prepare_environment
    env["target_file"].write_text("modified")
    commit_map({str(env["source_dir"]): str(env["target_dir"])})

    assert env["source_file"].read_text() == "modified"
    assert env["hash_path"].read_text() == _hash("modified")


def test_commit_map_dry_run_no_changes(prepare_environment):
    """Dry run leaves files and hashes untouched."""
    env = prepare_environment
    original_hash = env["hash_path"].read_text()
    env["target_file"].write_text("modified")
    commit_map({str(env["source_dir"]): str(env["target_dir"])}, dry_run=True)

    assert env["source_file"].read_text() == "original"
    assert env["hash_path"].read_text() == original_hash


def test_commit_map_skips_local_changes_without_force(prepare_environment, capsys):
    """Local source changes prevent overwrite unless force is used."""
    env = prepare_environment
    env["source_file"].write_text("local")
    env["target_file"].write_text("modified")
    original_hash = env["hash_path"].read_text()

    commit_map({str(env["source_dir"]): str(env["target_dir"])})

    assert env["source_file"].read_text() == "local"
    assert env["hash_path"].read_text() == original_hash
    captured = capsys.readouterr()
    assert "was modified in source since last deployment" in captured.out


def test_commit_map_force_overwrites_local_changes(prepare_environment):
    """Force option overwrites local changes and updates hash."""
    env = prepare_environment
    env["source_file"].write_text("local")
    env["target_file"].write_text("modified")

    commit_map({str(env["source_dir"]): str(env["target_dir"])}, force=True)

    assert env["source_file"].read_text() == "modified"
    assert env["hash_path"].read_text() == _hash("modified")
