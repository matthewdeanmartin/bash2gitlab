"""Helper functions for managing hash file paths in centralized directories.

This module provides utilities to manage hash files for output files in a centralized
.bash2gitlab/output_hashes/ directory structure, while maintaining backward compatibility
with the old sibling hash file approach.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

HASH_DIR_NAME = ".bash2gitlab"
OUTPUT_HASH_SUBDIR = "output_hashes"


def get_output_hash_path(output_file: Path, output_base: Path) -> Path:
    """Get the centralized hash file path for an output file.

    Args:
        output_file: Path to the output file (e.g., out/nested/file.yml)
        output_base: Base output directory (e.g., out/)

    Returns:
        Path to hash file in centralized location
        (e.g., out/.bash2gitlab/output_hashes/nested/file.yml.hash)

    Example:
        >>> get_output_hash_path(Path("out/ci/deploy.yml"), Path("out"))
        Path("out/.bash2gitlab/output_hashes/ci/deploy.yml.hash")
    """
    try:
        rel_path = output_file.relative_to(output_base)
    except ValueError:
        # If output_file is not relative to output_base, use absolute conversion
        logger.warning(f"Output file {output_file} is not relative to {output_base}, using absolute path conversion")
        rel_path = Path(str(output_file).lstrip("/\\").replace(":", "_"))

    hash_dir = output_base / HASH_DIR_NAME / OUTPUT_HASH_SUBDIR
    hash_file = hash_dir / rel_path.with_suffix(rel_path.suffix + ".hash")
    return hash_file


def get_old_hash_path(output_file: Path) -> Path:
    """Get the old-style sibling hash file path.

    Args:
        output_file: Path to the output file

    Returns:
        Path to sibling hash file (e.g., file.yml.hash)
    """
    return output_file.with_suffix(output_file.suffix + ".hash")


def find_hash_file(output_file: Path, output_base: Path) -> Path | None:
    """Find hash file, checking new location first, then old location.

    Args:
        output_file: Path to the output file
        output_base: Base output directory

    Returns:
        Path to existing hash file, or None if neither exists
    """
    # Check new centralized location first
    new_path = get_output_hash_path(output_file, output_base)
    if new_path.exists():
        return new_path

    # Fall back to old sibling location
    old_path = get_old_hash_path(output_file)
    if old_path.exists():
        return old_path

    return None


def migrate_hash_file(output_file: Path, output_base: Path) -> bool:
    """Migrate old sibling hash file to new centralized location.

    Args:
        output_file: Path to the output file
        output_base: Base output directory

    Returns:
        True if migration occurred, False otherwise
    """
    old_path = get_old_hash_path(output_file)
    if not old_path.exists():
        return False

    new_path = get_output_hash_path(output_file, output_base)

    # Don't migrate if new location already exists (new takes precedence)
    if new_path.exists():
        logger.debug(f"New hash file already exists at {new_path}, removing old {old_path}")
        try:
            old_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to remove old hash file {old_path}: {e}")
        return False

    # Create parent directory for new location
    try:
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_path), str(new_path))
        logger.info(f"Migrated hash file: {old_path} -> {new_path}")
        return True
    except Exception as e:
        logger.warning(f"Failed to migrate hash file from {old_path} to {new_path}: {e}")
        return False


def get_source_file_from_hash(hash_file: Path, output_base: Path) -> Path:
    """Derive the original output file path from a hash file path.

    Handles both old (sibling) and new (centralized) hash file locations.

    Args:
        hash_file: Path to the hash file
        output_base: Base output directory

    Returns:
        Path to the corresponding output file

    Example:
        >>> get_source_file_from_hash(
        ...     Path("out/.bash2gitlab/output_hashes/ci/deploy.yml.hash"),
        ...     Path("out")
        ... )
        Path("out/ci/deploy.yml")
    """
    hash_str = str(hash_file)

    # Remove .hash suffix
    if hash_str.endswith(".hash"):
        base_str = hash_str[: -len(".hash")]
    else:
        base_str = hash_str

    base_path = Path(base_str)

    # Check if this is in the new centralized location
    hash_dir = output_base / HASH_DIR_NAME / OUTPUT_HASH_SUBDIR
    try:
        rel_path = base_path.relative_to(hash_dir)
        # It's in the centralized location, reconstruct output file path
        return output_base / rel_path
    except ValueError:
        # Not in centralized location, must be old sibling style
        return base_path


def iter_hash_files_in_directory(output_base: Path) -> list[Path]:
    """Find all hash files in both old and new locations.

    Args:
        output_base: Base output directory

    Returns:
        List of all hash file paths (new location preferred over old)
    """
    hash_files: set[Path] = set()

    # Collect hash files from new centralized location
    hash_dir = output_base / HASH_DIR_NAME / OUTPUT_HASH_SUBDIR
    if hash_dir.exists():
        for hash_file in hash_dir.rglob("*.hash"):
            if hash_file.is_file():
                hash_files.add(hash_file)

    # Collect hash files from old sibling locations
    # Track output files that already have hash in new location
    files_with_new_hash: set[Path] = set()
    for hash_file in hash_files:
        output_file = get_source_file_from_hash(hash_file, output_base)
        files_with_new_hash.add(output_file)

    # Find old-style hash files, excluding those already in new location
    for old_hash in output_base.rglob("*.hash"):
        if old_hash.is_file():
            # Skip if it's in the centralized directory
            if hash_dir in old_hash.parents:
                continue

            # Get corresponding output file
            output_file = get_source_file_from_hash(old_hash, output_base)

            # Only include if there's no new-style hash for this file
            if output_file not in files_with_new_hash:
                hash_files.add(old_hash)

    return sorted(hash_files)
