"""Input change detection for bash2gitlab compilation.

This module provides functionality to detect if input files have changed since
the last compilation, allowing for efficient incremental builds.
"""

from __future__ import annotations

import hashlib
import logging
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML

from bash2gitlab.utils.yaml_factory import get_yaml

logger = logging.getLogger(__name__)


def normalize_yaml_content(content: str) -> str:
    """Normalize YAML content by loading and dumping to remove formatting differences."""
    try:
        yaml = get_yaml()
        data = yaml.load(content)
        # Use a clean YAML dumper for normalization

        norm_yaml = YAML()
        norm_yaml.preserve_quotes = False
        norm_yaml.default_flow_style = False

        output = StringIO()
        norm_yaml.dump(data, output)
        return output.getvalue()
    except Exception as e:
        logger.warning(f"Failed to normalize YAML content: {e}. Using original content.")
        return content


def normalize_text_content(content: str) -> str:
    """Normalize text content by removing all whitespace."""
    return "".join(content.split())


def compute_content_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of file content, normalized appropriately."""
    content = file_path.read_text(encoding="utf-8")

    # Normalize based on file type
    if file_path.suffix.lower() in {".yml", ".yaml"}:
        normalized_content = normalize_yaml_content(content)
    else:
        normalized_content = normalize_text_content(content)

    return hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()


def _read_stored_hash(hash_file: Path) -> str | None:
    """Read stored hash from hash file."""
    try:
        if hash_file.exists():
            return hash_file.read_text(encoding="utf-8").strip()
    except Exception as e:
        logger.warning(f"Failed to read hash file {hash_file}: {e}")
    return None


def _write_hash(hash_file: Path, content_hash: str) -> None:
    """Write hash to hash file."""
    try:
        hash_file.parent.mkdir(parents=True, exist_ok=True)
        hash_file.write_text(content_hash, encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to write hash file {hash_file}: {e}")


class InputChangeDetector:
    """Detects changes in input files since last compilation."""

    def __init__(self, base_path: Path, hash_dir_name: str = ".bash2gitlab"):
        """Initialize change detector.

        Args:
            base_path: Base directory for the project
            hash_dir_name: Name of directory to store hash files
        """
        self.base_path = base_path
        self.hash_dir = base_path / hash_dir_name / "input_hashes"

    def _get_hash_file_path(self, input_file: Path) -> Path:
        """Get the hash file path for an input file."""
        # Create a mirror directory structure in the hash directory
        try:
            rel_path = input_file.relative_to(self.base_path)
        except ValueError:
            # If input_file is not relative to base_path, use absolute path conversion
            rel_path = Path(str(input_file).lstrip("/\\").replace(":", "_"))

        hash_file = self.hash_dir / rel_path.with_suffix(rel_path.suffix + ".hash")
        return hash_file

    def has_file_changed(self, file_path: Path) -> bool:
        """Check if a single file has changed since last compilation.

        Args:
            file_path: Path to the input file to check

        Returns:
            True if file has changed or no previous hash exists, False otherwise
        """
        if not file_path.exists():
            logger.warning(f"Input file does not exist: {file_path}")
            return True

        hash_file = self._get_hash_file_path(file_path)
        stored_hash = _read_stored_hash(hash_file)

        if stored_hash is None:
            logger.debug(f"No previous hash for {file_path}, considering changed")
            return True

        current_hash = compute_content_hash(file_path)
        changed = current_hash != stored_hash

        if changed:
            logger.debug(f"File changed: {file_path}")
        else:
            logger.debug(f"File unchanged: {file_path}")

        return changed

    def needs_compilation(self, input_dir: Path) -> bool:
        """Check if any input file in the directory has changed.

        Args:
            input_dir: Directory containing input files

        Returns:
            True if any file has changed, False if all files are unchanged
        """
        if not input_dir.exists():
            logger.warning(f"Input directory does not exist: {input_dir}")
            return True

        # Get all relevant input files
        input_files: list[Path] = []
        for pattern in ["*.yml", "*.yaml", "*.sh", "*.py", "*.js", "*.rb", "*.php", "*.fish"]:
            input_files.extend(input_dir.rglob(pattern))

        if not input_files:
            logger.info(f"No input files found in {input_dir}")
            return False

        # Check if any file has changed
        for file_path in input_files:
            if self.has_file_changed(file_path):
                logger.info(f"Compilation needed: {file_path} has changed")
                return True

        logger.info("No input files have changed, compilation not needed")
        return False

    def get_changed_files(self, input_dir: Path) -> list[Path]:
        """Get list of files that have changed since last compilation.

        Args:
            input_dir: Directory containing input files

        Returns:
            List of paths to files that have changed
        """
        if not input_dir.exists():
            return []

        changed_files = []

        # Get all relevant input files
        input_files: list[Path] = []
        for pattern in ["*.yml", "*.yaml", "*.sh", "*.py", "*.js", "*.rb", "*.php", "*.fish"]:
            input_files.extend(input_dir.rglob(pattern))

        for file_path in input_files:
            if self.has_file_changed(file_path):
                changed_files.append(file_path)

        return changed_files

    def mark_compiled(self, input_dir: Path) -> None:
        """Mark all input files as compiled by updating their hashes.

        Args:
            input_dir: Directory containing input files that were compiled
        """
        if not input_dir.exists():
            logger.warning(f"Input directory does not exist: {input_dir}")
            return

        # Get all relevant input files
        input_files: list[Path] = []
        for pattern in ["*.yml", "*.yaml", "*.sh", "*.py", "*.js", "*.rb", "*.php", "*.fish"]:
            input_files.extend(input_dir.rglob(pattern))

        for file_path in input_files:
            try:
                current_hash = compute_content_hash(file_path)
                hash_file = self._get_hash_file_path(file_path)
                _write_hash(hash_file, current_hash)
                logger.debug(f"Updated hash for {file_path}")
            except Exception as e:
                logger.warning(f"Failed to update hash for {file_path}: {e}")

    def cleanup_stale_hashes(self, input_dir: Path) -> None:
        """Remove hash files for input files that no longer exist.

        Args:
            input_dir: Directory containing current input files
        """
        if not self.hash_dir.exists():
            return

        # Get current input files
        current_files: set[Path] = set()
        if input_dir.exists():
            for pattern in ["*.yml", "*.yaml", "*.sh", "*.py", "*.js", "*.rb", "*.php", "*.fish"]:
                current_files.update(input_dir.rglob(pattern))

        # Find and remove stale hash files
        removed_count = 0
        for hash_file in self.hash_dir.rglob("*.hash"):
            # Reconstruct the original file path
            try:
                rel_path = hash_file.relative_to(self.hash_dir)
                original_path = self.base_path / rel_path.with_suffix(rel_path.suffixes[0])  # Remove .hash

                if original_path not in current_files:
                    hash_file.unlink()
                    removed_count += 1
                    logger.debug(f"Removed stale hash file: {hash_file}")
            except Exception as e:
                logger.warning(f"Error processing hash file {hash_file}: {e}")

        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} stale hash files")


# Convenience functions for drop-in replacement
def needs_compilation(input_dir: Path, base_path: Path | None = None) -> bool:
    """Check if compilation is needed for input directory.

    Args:
        input_dir: Directory containing input files
        base_path: Base path for hash storage (defaults to input_dir)

    Returns:
        True if compilation is needed, False otherwise
    """
    if base_path is None:
        base_path = input_dir

    detector = InputChangeDetector(base_path)
    return detector.needs_compilation(input_dir)


def mark_compilation_complete(input_dir: Path, base_path: Path | None = None) -> None:
    """Mark compilation as complete for input directory.

    Args:
        input_dir: Directory containing input files that were compiled
        base_path: Base path for hash storage (defaults to input_dir)
    """
    if base_path is None:
        base_path = input_dir

    detector = InputChangeDetector(base_path)
    detector.mark_compiled(input_dir)


def get_changed_files(input_dir: Path, base_path: Path | None = None) -> list[Path]:
    """Get list of changed files in input directory.

    Args:
        input_dir: Directory containing input files
        base_path: Base path for hash storage (defaults to input_dir)

    Returns:
        List of paths to files that have changed
    """
    if base_path is None:
        base_path = input_dir

    detector = InputChangeDetector(base_path)
    return detector.get_changed_files(input_dir)
