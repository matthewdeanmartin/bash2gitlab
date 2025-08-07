from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

import toml


def get_deployment_map(pyproject_path: Path) -> dict[str, str]:
    """Parses the pyproject.toml file to get the deployment map.

    Args:
        pyproject_path: The path to the pyproject.toml file.

    Returns:
        A dictionary mapping source directories to target directories.

    Raises:
        FileNotFoundError: If the pyproject.toml file is not found.
        KeyError: If the [tool.bash2gitlab.map] section is missing.
    """
    if not pyproject_path.is_file():
        raise FileNotFoundError(f"pyproject.toml not found at '{pyproject_path}'")

    data = toml.load(pyproject_path)
    try:
        return data["tool"]["bash2gitlab"]["map"]
    except KeyError as ke:
        raise KeyError("'[tool.bash2gitlab.map]' section not found in pyproject.toml") from ke


def map_deploy(
    source_to_target_map: dict[str, str],
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Copies files from source to target directories based on a map.

    This function iterates through a dictionary mapping source directories to
    target directories. It copies each file from the source to the corresponding
    target, creating a .hash file to track changes.

    - If a destination file has been modified since the last deployment (hash
      mismatch), it will be skipped unless 'force' is True.
    - A .gitignore file with '*' is created in each target directory to
      prevent accidental check-ins.
    - All necessary directories are created.

    Args:
        source_to_target_map: A dictionary where keys are source paths and
                              values are target paths.
        dry_run: If True, simulates the deployment without making changes.
        force: If True, overwrites target files even if they have been modified.
    """
    for source_base, target_base in source_to_target_map.items():
        source_base_path = Path(source_base).resolve()
        target_base_path = Path(target_base).resolve()

        if not source_base_path.is_dir():
            print(f"Warning: Source directory '{source_base_path}' does not exist. Skipping.")
            continue

        print(f"\nProcessing map: '{source_base_path}' -> '{target_base_path}'")

        # Create target base directory and .gitignore if they don't exist
        if not target_base_path.exists():
            print(f"Target directory '{target_base_path}' does not exist.")
            if not dry_run:
                print(f"Creating directory: {target_base_path}")
                target_base_path.mkdir(parents=True, exist_ok=True)

        gitignore_path = target_base_path / ".gitignore"
        if not gitignore_path.exists():
            if not dry_run:
                print(f"Creating .gitignore in '{target_base_path}'")
                with open(gitignore_path, "w") as f:
                    f.write("*\n")
            else:
                print(f"DRY RUN: Would create .gitignore in '{target_base_path}'")

        for root, _, files in os.walk(source_base_path):
            source_root_path = Path(root)

            for filename in files:
                source_file_path = source_root_path / filename
                relative_path = source_file_path.relative_to(source_base_path)
                target_file_path = target_base_path / relative_path
                hash_file_path = target_file_path.with_suffix(target_file_path.suffix + ".hash")

                # Ensure parent directory of the target file exists
                if not target_file_path.parent.exists():
                    print(f"Target directory '{target_file_path.parent}' does not exist.")
                    if not dry_run:
                        print(f"Creating directory: {target_file_path.parent}")
                        target_file_path.parent.mkdir(parents=True, exist_ok=True)

                # Calculate source file hash
                with open(source_file_path, "rb") as f:
                    source_hash = hashlib.sha256(f.read()).hexdigest()

                # Check for modifications at the destination
                if target_file_path.exists():
                    with open(target_file_path, "rb") as f:
                        target_hash_actual = hashlib.sha256(f.read()).hexdigest()

                    stored_hash = ""
                    if hash_file_path.exists():
                        with open(hash_file_path) as f:
                            stored_hash = f.read().strip()

                    if stored_hash and target_hash_actual != stored_hash:
                        print(f"Warning: '{target_file_path}' was modified since last deployment.")
                        if not force:
                            print("Skipping copy. Use --force to overwrite.")
                            continue
                        else:
                            print("Forcing overwrite.")

                # Perform copy and write hash
                if not target_file_path.exists() or source_hash != target_hash_actual:
                    action = "Copied" if not target_file_path.exists() else "Updated"
                    print(f"{action}: '{source_file_path}' -> '{target_file_path}'")
                    if not dry_run:
                        shutil.copy2(source_file_path, target_file_path)
                        with open(hash_file_path, "w") as f:
                            f.write(source_hash)
                else:
                    print(f"Unchanged: '{target_file_path}'")
