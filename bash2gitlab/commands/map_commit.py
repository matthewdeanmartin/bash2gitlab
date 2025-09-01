"""
Syncs changes from multiple target folders back to a single source folder.
This is intended to be fed by a TOML configuration file where users can easily
map one source directory to a list of target/deployed directories.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from collections.abc import Collection
from pathlib import Path

from bash2gitlab.commands.compile_not_bash import _INTERPRETER_EXTS

__all__ = ["run_commit_map"]


_VALID_SUFFIXES = {".sh", ".ps1", ".yml", ".yaml", ".bash"}

for _key, value in _INTERPRETER_EXTS.items():
    _VALID_SUFFIXES.update(value)

_CHUNK_SIZE = 65536  # 64kb

logger = logging.getLogger(__name__)


def _calculate_file_hash(file_path: Path) -> str | None:
    """Calculates the SHA256 hash of a file, returning None if it doesn't exist."""
    if not file_path.is_file():
        return None

    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(_CHUNK_SIZE):
            sha256.update(chunk)
    return sha256.hexdigest()


def _sync_single_target_to_source(
    source_base_path: Path,
    target_base_path: Path,
    dry_run: bool,
    force: bool,
) -> None:
    """Helper to sync one target directory back to the source."""
    if not target_base_path.is_dir():
        print(f"Warning: Target directory '{target_base_path}' does not exist. Skipping.")
        return

    print(f"\nProcessing sync: '{target_base_path}' -> '{source_base_path}'")

    for target_file_path in target_base_path.rglob("*"):
        # Skip directories and non-file types
        if not target_file_path.is_file():
            continue

        # Skip ignored files
        if (
            target_file_path.name == ".gitignore"
            or target_file_path.suffix == ".hash"
            or target_file_path.suffix.lower() not in _VALID_SUFFIXES
        ):
            continue

        relative_path = target_file_path.relative_to(target_base_path)
        source_file_path = source_base_path / relative_path
        hash_file_path = target_file_path.with_suffix(target_file_path.suffix + ".hash")

        target_hash = _calculate_file_hash(target_file_path)
        stored_hash = hash_file_path.read_text().strip() if hash_file_path.exists() else None

        # Case 1: File is unchanged since last deployment/sync.
        if stored_hash and target_hash == stored_hash:
            # Using logger.debug for unchanged files to reduce noise
            logger.debug(f"Unchanged: '{target_file_path}'")
            continue

        # Case 2: Source file was modified locally since deployment.
        source_hash = _calculate_file_hash(source_file_path)
        if stored_hash and source_hash and source_hash != stored_hash and not force:
            print(f"Warning: Source file '{source_file_path}' was modified locally.")
            print("         Skipping sync. Use --force to overwrite.")
            continue

        # Case 3: File in target has changed, proceed with sync.
        action = "Creating" if not source_file_path.exists() else "Updating"
        print(f"{action}: '{source_file_path}' (from '{target_file_path}')")

        if not dry_run:
            # Ensure the destination directory exists
            source_file_path.parent.mkdir(parents=True, exist_ok=True)
            # Copy file and its metadata
            shutil.copy2(target_file_path, source_file_path)
            # Update the hash file in the target directory to reflect the new state
            hash_file_path.write_text(target_hash or "")


def run_commit_map(
    deployment_map: dict[str, list[str] | Collection[str]],
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """
    Syncs modified files from target directories back to their source directory.

    For each source directory, this function iterates through its corresponding
    list of target (deployed) directories. It detects changes in the target
    files by comparing their current content hash against a stored hash in a
    parallel '.hash' file.

    If a file has changed in the target, it is copied back to the source,
    overwriting the original.

    Args:
        deployment_map: A mapping where each key is a source directory and the
            value is a list of target directories where the source content
            was deployed.
        dry_run: If ``True``, simulates the sync and prints actions without
            modifying any files.
        force: If ``True``, a source file will be overwritten even if it was
            modified locally since the last deployment.
    """
    for source_base, target_bases in deployment_map.items():
        source_base_path = Path(source_base).resolve()

        if not isinstance(target_bases, (list, tuple, set)):
            logger.error(f"Invalid format for '{source_base}'. Targets must be a list. Skipping.")
            continue

        for target_base in target_bases:
            target_base_path = Path(target_base).resolve()
            _sync_single_target_to_source(source_base_path, target_base_path, dry_run, force)
