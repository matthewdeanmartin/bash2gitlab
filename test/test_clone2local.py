from __future__ import annotations

import logging
import zipfile
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest
from pytest_mock import MockerFixture

from bash2gitlab.clone2local import fetch_repository_archive


@pytest.fixture
def temp_test_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for test artifacts."""
    # tmp_path is a built-in pytest fixture that provides a temporary directory
    return tmp_path


def create_fake_zip_archive(branch: str, sparse_dirs: list[str]) -> BytesIO:
    """
    Creates an in-memory zip file that simulates a GitHub repository archive.
    The archive will contain a root folder like 'my-repo-main/'
    """
    zip_buffer = BytesIO()
    repo_root_name = f"test-repo-{branch}"

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Create a dummy file in the root to ensure it's not empty
        zf.writestr(f"{repo_root_name}/README.md", "# Test Repo")

        # Create the specified sparse directories and a file within each
        for i, dir_path in enumerate(sparse_dirs):
            full_path = Path(repo_root_name) / dir_path
            zf.writestr(str(full_path / f"file{i}.txt"), f"content of file {i}")

        # Add an extra directory that we do NOT want to be copied
        zf.writestr(f"{repo_root_name}/unwanted_dir/dont_copy.txt", "should not exist")

    zip_buffer.seek(0)
    return zip_buffer


class TestFetchRepositoryArchive:
    """Test suite for the fetch_repository_archive function."""

    def test_fetch_successful(self, mocker: MockerFixture, temp_test_dir: Path):
        """
        Tests the successful download, extraction, and sparse copy of directories.
        """
        # --- Arrange ---
        repo_url = "https://github.com/test/repo"
        branch = "main"
        sparse_dirs = ["app/src", "docs"]
        clone_dir = temp_test_dir / "my-clone"

        # Mock urlopen to simulate a successful connection (HTTP 200)
        mock_urlopen = mocker.patch("urllib.request.urlopen")
        mock_urlopen.return_value.__enter__.return_value.status = 200

        # Mock urlretrieve to "download" our fake zip file
        def fake_urlretrieve(url, dest_path):
            with open(dest_path, "wb") as f:
                f.write(create_fake_zip_archive(branch, sparse_dirs).read())

        mocker.patch("urllib.request.urlretrieve", side_effect=fake_urlretrieve)

        # --- Act ---
        fetch_repository_archive(repo_url, branch, sparse_dirs, clone_dir)

        # --- Assert ---
        assert clone_dir.exists()
        # Check that the requested sparse directories were copied
        assert (clone_dir / "src").is_dir()
        assert (clone_dir / "src" / "file0.txt").exists()
        assert (clone_dir / "docs").is_dir()
        assert (clone_dir / "docs" / "file1.txt").exists()

        # Check that the unwanted directory was NOT copied
        assert not (clone_dir / "unwanted_dir").exists()
        assert not (clone_dir / "README.md").exists()  # File in root shouldn't be copied

    def test_clone_dir_not_empty_raises_error(self, temp_test_dir: Path):
        """
        Tests that FileExistsError is raised if the destination directory is not empty.
        """
        # --- Arrange ---
        clone_dir = temp_test_dir / "not-empty"
        clone_dir.mkdir()
        (clone_dir / "some-file.txt").touch()

        # --- Act & Assert ---
        with pytest.raises(FileExistsError, match="exists and is not empty"):
            fetch_repository_archive("any_url", "main", [], clone_dir)

    def test_branch_not_found_raises_connection_error(self, mocker: MockerFixture, temp_test_dir: Path):
        """
        Tests that a ConnectionError is raised for a 404 HTTP error.
        """
        # --- Arrange ---
        clone_dir = temp_test_dir / "my-clone"
        mock_urlopen = mocker.patch("urllib.request.urlopen")
        mock_urlopen.side_effect = HTTPError("url", 404, "Not Found", {}, None)

        # --- Act & Assert ---
        with pytest.raises(ConnectionError, match="Could not find archive for branch"):
            fetch_repository_archive("https://any_url", "nonexistent-branch", [], clone_dir)

        # Assert that the clone directory was cleaned up
        assert not clone_dir.exists()

    def test_network_url_error_raises_connection_error(self, mocker: MockerFixture, temp_test_dir: Path):
        """
        Tests that a ConnectionError is raised for a generic URLError.
        """
        # --- Arrange ---
        clone_dir = temp_test_dir / "my-clone"
        mock_urlopen = mocker.patch("urllib.request.urlopen")
        mock_urlopen.side_effect = URLError("some network error")

        # --- Act & Assert ---
        with pytest.raises(ConnectionError, match="A network error occurred"):
            fetch_repository_archive("https://any_url", "main", [], clone_dir)

        # Assert that the clone directory was cleaned up
        assert not clone_dir.exists()

    def test_cleanup_on_copy_failure(self, mocker: MockerFixture, temp_test_dir: Path):
        """
        Tests that the destination directory is cleaned up if an error occurs during copying.
        """
        # --- Arrange ---
        repo_url = "https://github.com/test/repo"
        branch = "main"
        sparse_dirs = ["app/src"]
        clone_dir = temp_test_dir / "my-clone"

        # Mock network calls to succeed
        mocker.patch("urllib.request.urlopen").return_value.__enter__.return_value.status = 200
        mocker.patch(
            "urllib.request.urlretrieve",
            side_effect=lambda url, dest: open(dest, "wb").write(create_fake_zip_archive(branch, sparse_dirs).read()),
        )

        # Mock shutil.copytree to fail
        mocker.patch("shutil.copytree", side_effect=OSError("Disk full!"))

        # --- Act & Assert ---
        with pytest.raises(IOError):
            fetch_repository_archive(repo_url, branch, sparse_dirs, clone_dir)

        # The most important assertion: the clone directory should not exist after failure.
        assert not clone_dir.exists()

    def test_missing_sparse_dir_is_skipped(self, mocker: MockerFixture, temp_test_dir: Path, caplog):
        """
        Tests that a missing sparse directory is skipped with a warning, and doesn't fail.
        """
        # --- Arrange ---
        repo_url = "https://github.com/test/repo"
        branch = "main"
        # 'existing_dir' will be in our fake zip, 'missing_dir' will not.
        sparse_dirs_in_zip = ["existing_dir"]
        sparse_dirs_to_request = ["existing_dir", "missing_dir"]
        clone_dir = temp_test_dir / "my-clone"

        mocker.patch("urllib.request.urlopen").return_value.__enter__.return_value.status = 200
        mocker.patch(
            "urllib.request.urlretrieve",
            side_effect=lambda url, dest: open(dest, "wb").write(
                create_fake_zip_archive(branch, sparse_dirs_in_zip).read()
            ),
        )

        # --- Act ---
        with caplog.at_level(logging.WARNING):
            fetch_repository_archive(repo_url, branch, sparse_dirs_to_request, clone_dir)

        # --- Assert ---
        # Check that the existing directory was copied
        assert (clone_dir / "existing_dir").is_dir()
        # Check that the missing directory was not created
        assert not (clone_dir / "missing_dir").exists()
        # Check that a warning was logged
        assert "Directory 'missing_dir' not found in repository archive, skipping." in caplog.text
