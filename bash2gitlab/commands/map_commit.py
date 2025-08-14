"""Copy from many repos relevant shell scripts changes back to the central repo."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
from pathlib import Path

__all__ = ["run_commit_map"]


_VALID_SUFFIXES = {".sh", ".ps1", ".yml", ".yaml", ".bash"}

logger = logging.getLogger(__name__)


def run_commit_map(
    source_to_target_map: dict[str, str],
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Copy modified deployed files back to their source directories.

    This function performs the inverse of :func:`bash2gitlab.map_deploy_command.map_deploy`.
    For every mapping of ``source`` to ``target`` directories it traverses the
    deployed ``target`` directory and copies changed files back to the
    corresponding ``source`` directory. Change detection relies on ``.hash``
    files created during deployment. A file is copied back when the content of
    the deployed file differs from the stored hash. After a successful copy the
    ``.hash`` file is updated to reflect the new content hash.

    Args:
        source_to_target_map: Mapping of source directories to deployed target
            directories.
        dry_run: If ``True`` the operation is only simulated and no files are
            written.
        force: If ``True`` a source file is overwritten even if it was modified
            locally since the last deployment.
    """
    for source_base, target_base in source_to_target_map.items():
        source_base_path = Path(source_base).resolve()
        target_base_path = Path(target_base).resolve()

        if not target_base_path.is_dir():
            print(f"Warning: Target directory '{target_base_path}' does not exist. Skipping.")
            continue

        print(f"\nProcessing map: '{target_base_path}' -> '{source_base_path}'")

        for root, _, files in os.walk(target_base_path):
            target_root_path = Path(root)

            for filename in files:
                if filename == ".gitignore" or filename.endswith(".hash"):
                    continue

                target_file_path = target_root_path / filename
                if target_file_path.suffix.lower() not in _VALID_SUFFIXES:
                    continue

                relative_path = target_file_path.relative_to(target_base_path)
                source_file_path = source_base_path / relative_path
                hash_file_path = target_file_path.with_suffix(target_file_path.suffix + ".hash")

                # Calculate hash of the deployed file
                with open(target_file_path, "rb") as f:
                    target_hash = hashlib.sha256(f.read()).hexdigest()

                stored_hash = ""
                if hash_file_path.exists():
                    with open(hash_file_path, encoding="utf-8") as f:
                        stored_hash = f.read().strip()

                source_hash_actual = ""
                if source_file_path.exists():
                    with open(source_file_path, "rb") as f:
                        source_hash_actual = hashlib.sha256(f.read()).hexdigest()

                if stored_hash and target_hash == stored_hash:
                    print(f"Unchanged: '{target_file_path}'")
                    continue

                if stored_hash and source_hash_actual and source_hash_actual != stored_hash and not force:
                    print(f"Warning: '{source_file_path}' was modified in source since last deployment.")
                    print("Skipping copy. Use --force to overwrite.")
                    continue

                action = "Copied" if not source_file_path.exists() else "Updated"
                print(f"{action}: '{target_file_path}' -> '{source_file_path}'")

                if dry_run:
                    continue

                if not source_file_path.parent.exists():
                    print(f"Creating directory: {source_file_path.parent}")
                    source_file_path.parent.mkdir(parents=True, exist_ok=True)

                shutil.copy2(target_file_path, source_file_path)
                with open(hash_file_path, "w", encoding="utf-8") as f:
                    f.write(target_hash)
