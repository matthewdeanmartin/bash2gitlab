"""
Deploys scripts from a central source directory to multiple target directories.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from collections.abc import Collection
from pathlib import Path

from bash2gitlab.commands.compile_not_bash import _INTERPRETER_EXTS

__all__ = ["run_map_deploy"]

from bash2gitlab.utils.utils import short_path

_VALID_SUFFIXES = {".sh", ".ps1", ".yml", ".yaml", ".bash"}

for _key, value in _INTERPRETER_EXTS.items():
    _VALID_SUFFIXES.update(value)

_CHUNK_SIZE = 65536  # 64kb

logger = logging.getLogger(__name__)


def calculate_file_hash(file_path: Path) -> str | None:
    """Calculates the SHA256 hash of a file, returning None if it doesn't exist."""
    if not file_path.is_file():
        return None

    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in chunks to handle large files efficiently
        while chunk := f.read(_CHUNK_SIZE):
            sha256.update(chunk)
    return sha256.hexdigest()


def deploy_to_single_target(
    source_base_path: Path,
    target_base_path: Path,
    dry_run: bool,
    force: bool,
) -> None:
    """
    Helper function to handle the deployment logic for one source-to-target pair.
    """
    logger.info(f"\nProcessing deployment: '{short_path(source_base_path)}' -> '{short_path(target_base_path)}'")

    # Create target directory and .gitignore if they don't exist
    if not dry_run:
        target_base_path.mkdir(parents=True, exist_ok=True)
        gitignore_path = target_base_path / ".gitignore"
        if not gitignore_path.exists():
            logger.info(f"Creating .gitignore in '{short_path(target_base_path)}'")
            gitignore_path.write_text("*\n")
    else:
        if not target_base_path.exists():
            logger.info(f"DRY RUN: Would create directory '{short_path(target_base_path)}'")
        if not (target_base_path / ".gitignore").exists():
            logger.info(f"DRY RUN: Would create .gitignore in '{short_path(target_base_path)}'")

    # Use rglob for efficient recursive file searching
    for source_file_path in source_base_path.rglob("*"):
        if not source_file_path.is_file() or source_file_path.suffix.lower() not in _VALID_SUFFIXES:
            continue

        relative_path = source_file_path.relative_to(source_base_path)
        target_file_path = target_base_path / relative_path
        hash_file_path = target_file_path.with_suffix(target_file_path.suffix + ".hash")

        source_hash = calculate_file_hash(source_file_path)

        # Check for modifications at the destination if the file exists
        if target_file_path.exists():
            target_hash = calculate_file_hash(target_file_path)
            stored_hash = hash_file_path.read_text().strip() if hash_file_path.exists() else None

            # Case 1: Target file was modified locally since last deployment.
            if stored_hash and target_hash != stored_hash:
                logger.warning(f"Warning: Target '{short_path(target_file_path)}' was modified locally.")
                if not force:
                    logger.warning("         Skipping copy. Use --force to overwrite.")
                    continue
                logger.warning("         Forcing overwrite.")

            # Case 2: Target file is identical to the source file.
            if source_hash == target_hash:
                logger.debug(f"Unchanged: '{short_path(target_file_path)}'")
                continue

        # If we reach here, we need to copy/update the file.
        action = "Deploying" if not target_file_path.exists() else "Updating"
        logger.info(f"{action}: '{short_path(source_file_path)}' -> '{short_path(target_file_path)}'")

        if not dry_run:
            target_file_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file_path, target_file_path)
            hash_file_path.write_text(source_hash or "")


def run_map_deploy(
    deployment_map: dict[str, list[str] | Collection[str]],
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """
    Deploys files from source directories to their corresponding target directories.

    This function iterates through a map where each source directory is associated
    with a list of target directories. It copies valid files and creates a '.hash'
    file alongside each deployed file to track its state.

    Args:
        deployment_map: A dictionary where keys are source paths and values are
                        a list or collection of target paths.
        dry_run: If True, simulates the deployment without making changes.
        force: If True, overwrites target files even if they have been modified
               locally since the last deployment.
    """
    if len(deployment_map):
        logger.info(f"Preparing to deploy {len(deployment_map)} items")
    else:
        logger.warning(
            """No items in map config section. Map deploy requires pyproject.toml to have something like
        [tool.bash2gitlab.map.map]
        "out/python" =["my_microservice/gitlab-scripts", "my_other/gitlab-scripts"]"""
        )

    # bash2gitlab.toml
    for source_base, target_bases in deployment_map.items():
        logger.info(f"Deploying {short_path(Path(source_base))} to {len(target_bases)} destinations")
        source_base_path = Path(source_base).resolve()

        if not source_base_path.is_dir():
            logger.warning(f"Warning: Source directory '{short_path(source_base_path)}' does not exist. Skipping.")
            continue

        if not isinstance(target_bases, (list, tuple, set)):
            logger.error(f"Invalid format for '{source_base}'. Targets must be a list. Skipping.")
            continue
        if not len(target_bases):
            logger.warning("Source folder but no destinations!")

        for target_base in target_bases:
            target_base_path = Path(target_base).resolve()
            deploy_to_single_target(source_base_path, target_base_path, dry_run, force)
