"""A command to copy just some of a centralized repo's bash commands to a local repo for debugging."""

from __future__ import annotations

import logging
import shutil
import subprocess  # nosec: B404
import tempfile
import zipfile
from pathlib import Path

import urllib3

from bash2gitlab.utils.urllib3_helper import _HTTP
from bash2gitlab.utils.utils import short_path

logger = logging.getLogger(__name__)

__all__ = ["fetch_repository_archive", "clone_repository_ssh"]


def fetch_repository_archive(
    repo_url: str, branch: str, source_dir: Path, clone_path: Path, dry_run: bool = False
) -> None:
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
        clone_path: The destination directory. This directory must be empty.
        dry_run: Simulate action

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
    if not dry_run:
        clone_path.mkdir(parents=True, exist_ok=True)

    # Build the archive URL
    archive_url = f"{repo_url.rstrip('/')}/archive/refs/heads/{branch}.zip"
    if not archive_url.startswith(("http://", "https://")):
        # Keep your project-specific error type if you have one; otherwise ValueError/TypeError is fine.
        raise TypeError(f"Expected http or https protocol, got {archive_url}")

    http = _HTTP  # _get_http_pool()

    try:
        # Use a temporary directory that cleans itself up automatically.
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            archive_path = temp_path / "repo.zip"
            unzip_root = temp_path / "unzipped"
            if not dry_run:
                unzip_root.mkdir()

            if dry_run:
                logger.info("[dry-run] Would download %s to %s", archive_url, archive_path)
                logger.info("[dry-run] Would extract %s to %s", archive_path, unzip_root)
                return

            # 2. Download the archive with streaming; will follow redirects via pool defaults.
            logger.info("Downloading archive from %s", archive_url)
            try:
                # Use a conservative timeout; rely on pool's retries if configured.
                timeout = urllib3.Timeout(connect=5.0, read=60.0)
                # Stream the body to disk (no preload).
                with (
                    http.request(
                        "GET",
                        archive_url,
                        headers={"Accept": "application/zip"},
                        preload_content=False,
                        timeout=timeout,
                        redirect=True,
                    ) as resp,
                    open(archive_path, "wb") as out,
                ):
                    if resp.status >= 400:
                        raise ConnectionError(f"Failed to fetch archive (HTTP {resp.status}) from {archive_url}")
                    # Efficiently stream to file
                    shutil.copyfileobj(resp, out)

            except urllib3.exceptions.HTTPError as e:
                # Network/connection-level errors (DNS, TLS, max retries, etc.)
                raise ConnectionError(f"A network error occurred while fetching the URL: {e}") from e

            if not archive_path.exists() or archive_path.stat().st_size == 0:
                raise OSError("Downloaded archive is empty or missing.")

            # 3. Unzip the downloaded archive.
            logger.info("Extracting archive to %s", unzip_root)
            if dry_run:
                # Nothing left meaningful to dry run
                return

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


def clone_repository_ssh(repo_url: str, branch: str, source_dir: Path, clone_path: Path, dry_run: bool = False) -> None:
    """Clones a repo via Git and copies a specific directory.

    This function is designed for SSH or authenticated HTTPS URLs that require
    local Git and credential management (e.g., SSH keys). It performs an
    efficient, shallow clone of a specific branch into a temporary directory,
    then copies the requested source directory to the final destination.

    Args:
        repo_url: The repository URL (e.g., 'git@github.com:user/repo.git').
        branch: The name of the branch to check out (e.g., 'main', 'develop').
        source_dir: A single directory path (relative to the repo root) to copy.
        clone_path: The destination directory. This directory must be empty.
        dry_run: Simulate action

    Raises:
        FileExistsError: If the clone_dir exists and is not empty.
        subprocess.CalledProcessError: If any Git command fails.
        Exception: Propagates other exceptions from file operations after
            attempting to clean up.
    """
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
    if not dry_run:
        clone_path.mkdir(parents=True, exist_ok=True)

    try:
        # Use a temporary directory for the full clone, which will be auto-cleaned.
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_clone_path = Path(temp_dir)
            logger.info("Cloning '%s' to temporary location: %s", repo_url, short_path(temp_clone_path))

            # 2. Clone the repository.
            # We clone the specific branch directly to be more efficient.
            # repo_url is a variable, but is intended to be a trusted source.
            command = ["git", "clone", "--depth", "1", "--branch", branch, repo_url, str(temp_clone_path)]
            if dry_run:
                logger.info(f"Would have run {' '.join(command)}")
            else:
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
                logger.debug("Copying '%s' to '%s'", short_path(repo_source_dir), short_path(dest_dir))
                shutil.copytree(repo_source_dir, dest_dir, dirs_exist_ok=True)
            elif not dry_run:
                logger.warning("Directory '%s' not found in repository, skipping.", short_path(source_dir))

    except Exception as e:
        logger.error("Operation failed: %s. Cleaning up destination directory.", e)
        # 4. Clean up the destination on any failure.
        shutil.rmtree(clone_path, ignore_errors=True)
        # Re-raise the exception to notify the caller of the failure.
        raise

    logger.info("Successfully cloned directories into %s", short_path(clone_path))
