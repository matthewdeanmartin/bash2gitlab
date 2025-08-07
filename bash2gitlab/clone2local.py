from __future__ import annotations

import logging
import shutil
import subprocess  # nosec: B404
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


def fetch_repository_archive(repo_url: str, branch: str, source_dir: str, clone_dir: str | Path) -> None:
    """Fetches and extracts a specific directory from a repository archive.

    This function avoids using Git by downloading the repository as a ZIP archive.
    It unpacks the archive to a temporary location, copies the requested
    source directory to the final destination, and cleans up all temporary
    files upon completion or in case of an error.

    Args:
        repo_url: The base URL of the repository (e.g., 'https://github.com/user/repo').
        branch: The name of the branch to download (e.g., 'main', 'develop').
        source_dir: A single directory path (relative to the repo root) to
            extract and copy to the clone_dir.
        clone_dir: The destination directory. This directory must be empty.

    Raises:
        FileExistsError: If the clone_dir exists and is not empty.
        ConnectionError: If the specified branch archive cannot be found, accessed,
            or if a network error occurs.
        IOError: If the downloaded archive is empty or has an unexpected
            file structure.
        TypeError: If the repository URL does not use an http/https protocol.
        Exception: Propagates other exceptions from network, file, or
            archive operations after attempting to clean up.
    """
    clone_path = Path(clone_dir)
    logger.debug(
        "Fetching archive for repo %s (branch: %s) into %s with dir %s",
        repo_url,
        branch,
        clone_path,
        source_dir,
    )

    # 1. Validate that the destination directory is empty.
    if clone_path.exists() and any(clone_path.iterdir()):
        raise FileExistsError(f"Destination directory '{clone_path}' exists and is not empty.")
    # Ensure the directory exists, but don't error if it's already there (as long as it's empty)
    clone_path.mkdir(parents=True, exist_ok=True)

    try:
        # Use a temporary directory that cleans itself up automatically.
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            archive_path = temp_path / "repo.zip"
            unzip_root = temp_path / "unzipped"
            unzip_root.mkdir()

            # 2. Construct the archive URL and check for its existence.
            archive_url = f"{repo_url.rstrip('/')}/archive/refs/heads/{branch}.zip"
            if not archive_url.startswith("http"):
                raise TypeError(f"Expected http or https protocol, got {archive_url}")

            try:
                # Use a simple open to verify existence without a full download.
                # nosec: B310 - URL is constructed from trusted inputs in this context.
                with urllib.request.urlopen(archive_url, timeout=10) as _response:  # nosec: B310
                    # The 'with' block itself confirms a 2xx status.
                    logger.info("Confirmed repository archive exists at: %s", archive_url)
            except urllib.error.HTTPError as e:
                # Re-raise with a more specific message for clarity.
                raise ConnectionError(
                    f"Could not find archive for branch '{branch}' at '{archive_url}'. "
                    f"Please check the repository URL and branch name. (HTTP Status: {e.code})"
                ) from e
            except urllib.error.URLError as e:
                raise ConnectionError(f"A network error occurred while verifying the URL: {e.reason}") from e

            logger.info("Downloading archive to %s", archive_path)
            # nosec: B310 - URL is validated above.
            urllib.request.urlretrieve(archive_url, archive_path)  # nosec: B310

            # 3. Unzip the downloaded archive.
            logger.info("Extracting archive to %s", unzip_root)
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(unzip_root)

            # The archive usually extracts into a single sub-directory (e.g., 'repo-name-main').
            # We need to find this directory to locate the source files.
            extracted_items = list(unzip_root.iterdir())
            if not extracted_items:
                raise OSError("Archive is empty.")

            # Find the single root directory within the extracted files.
            source_repo_root = None
            if len(extracted_items) == 1 and extracted_items[0].is_dir():
                source_repo_root = extracted_items[0]
            else:
                # Fallback for archives that might not have a single root folder.
                logger.warning("Archive does not contain a single root directory. Using extraction root.")
                source_repo_root = unzip_root

            # 4. Copy the specified directory to the final destination.
            logger.info("Copying specified directories to final destination.")

            repo_source_dir = source_repo_root / source_dir
            dest_dir = clone_path

            if repo_source_dir.is_dir():
                logger.debug("Copying '%s' to '%s'", repo_source_dir, dest_dir)
                # FIX: Use the correct source path `repo_source_dir` for the copy operation.
                shutil.copytree(repo_source_dir, dest_dir, dirs_exist_ok=True)
            else:
                logger.warning("Directory '%s' not found in repository archive, skipping.", repo_source_dir)

    except Exception as e:
        logger.error("Operation failed: %s. Cleaning up destination directory.", e)
        # 5. Clean up the destination on any failure.
        shutil.rmtree(clone_path, ignore_errors=True)
        # Re-raise the exception to notify the caller of the failure.
        raise

    logger.info("Successfully fetched directories into %s", clone_path)


def clone_repository_ssh(repo_url: str, branch: str, source_dir: str, clone_dir: str | Path) -> None:
    """Clones a repo via Git and copies a specific directory.

    This function is designed for SSH or authenticated HTTPS URLs that require
    local Git and credential management (e.g., SSH keys). It performs an
    efficient, shallow clone of a specific branch into a temporary directory,
    then copies the requested source directory to the final destination.

    Args:
        repo_url: The repository URL (e.g., 'git@github.com:user/repo.git').
        branch: The name of the branch to check out (e.g., 'main', 'develop').
        source_dir: A single directory path (relative to the repo root) to copy.
        clone_dir: The destination directory. This directory must be empty.

    Raises:
        FileExistsError: If the clone_dir exists and is not empty.
        subprocess.CalledProcessError: If any Git command fails.
        Exception: Propagates other exceptions from file operations after
            attempting to clean up.
    """
    clone_path = Path(clone_dir)
    logger.debug(
        "Cloning repo %s (branch: %s) into %s with source dir %s",
        repo_url,
        branch,
        clone_path,
        source_dir,
    )

    # 1. Validate that the destination directory is empty.
    if clone_path.exists() and any(clone_path.iterdir()):
        raise FileExistsError(f"Destination directory '{clone_path}' exists and is not empty.")
    clone_path.mkdir(parents=True, exist_ok=True)

    try:
        # Use a temporary directory for the full clone, which will be auto-cleaned.
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_clone_path = Path(temp_dir)
            logger.info("Cloning '%s' to temporary location: %s", repo_url, temp_clone_path)

            # 2. Clone the repository.
            # We clone the specific branch directly to be more efficient.
            # nosec: B603, B607 - repo_url is a variable, but is intended to be a trusted source.
            subprocess.run(  # nosec: B603, B607
                ["git", "clone", "--depth", "1", "--branch", branch, repo_url, str(temp_clone_path)],
                check=True,
                capture_output=True,  # Capture stdout/stderr to hide git's noisy output
            )

            logger.info("Clone successful. Copying specified directories.")
            # 3. Copy the specified directory to the final destination.
            repo_source_dir = temp_clone_path / source_dir
            dest_dir = clone_path

            if repo_source_dir.is_dir():
                logger.debug("Copying '%s' to '%s'", repo_source_dir, dest_dir)
                shutil.copytree(repo_source_dir, dest_dir, dirs_exist_ok=True)
            else:
                logger.warning("Directory '%s' not found in repository, skipping.", source_dir)

    except Exception as e:
        logger.error("Operation failed: %s. Cleaning up destination directory.", e)
        # 4. Clean up the destination on any failure.
        shutil.rmtree(clone_path, ignore_errors=True)
        # Re-raise the exception to notify the caller of the failure.
        raise

    logger.info("Successfully cloned directories into %s", clone_path)
