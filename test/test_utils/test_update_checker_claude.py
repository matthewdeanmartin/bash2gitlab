"""Comprehensive unit tests for the update checker module.

These tests aim to minimize mocking and test against real PyPI data where possible.
Uses temporary directories for cache testing.
"""

import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock

import orjson
import pytest
from packaging import version as _version

# Import the module under test - adjust import path as needed
from bash2gitlab.utils.update_checker import (
    NetworkError,
    PackageNotFoundError,
    VersionInfo,
    _background_update_worker,
    _Color,
    _exit_handler,
    cache_paths,
    can_use_color,
    check_for_updates,
    fetch_pypi_json,
    format_update_message,
    get_logger,
    get_version_info_from_pypi,
    is_dev_version,
    is_fresh,
    is_version_yanked,
    load_cache,
    reset_cache,
    save_cache,
    start_background_update_check,
)


class TestGetLogger:
    """Test logger creation and handling."""

    def test_returns_provided_logger(self):
        """Should return the provided logger instance."""
        test_logger = logging.getLogger("test")
        result = get_logger(test_logger)
        assert result is test_logger

    def test_creates_default_logger_when_none_provided(self):
        """Should create a default logger when None is provided."""
        result = get_logger(None)
        assert isinstance(result, logging.Logger)
        assert result.name == "update_checker"

    def test_default_logger_has_handler(self):
        """Default logger should have a handler configured."""
        result = get_logger(None)
        assert len(result.handlers) >= 1
        assert isinstance(result.handlers[0], logging.StreamHandler)

    def test_default_logger_level(self):
        """Default logger should be set to WARNING level."""
        result = get_logger(None)
        assert result.level == logging.WARNING


class TestCanUseColor:
    """Test color detection logic."""

    def test_no_color_environment_variable(self):
        """Should return False when NO_COLOR is set."""
        with mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
            assert can_use_color() is False

    def test_ci_environment_variable(self):
        """Should return False when CI is set."""
        with mock.patch.dict(os.environ, {"CI": "true"}, clear=True):
            assert can_use_color() is False

    def test_dumb_terminal(self):
        """Should return False when TERM is dumb."""
        with mock.patch.dict(os.environ, {"TERM": "dumb"}, clear=True):
            assert can_use_color() is False

    def test_tty_detection(self):
        """Should check if stdout is a TTY."""
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("sys.stdout.isatty", return_value=True):
                assert can_use_color() is True
            with mock.patch("sys.stdout.isatty", return_value=False):
                assert can_use_color() is False


class TestCachePaths:
    """Test cache path generation."""

    def test_cache_paths_structure(self):
        """Should return proper cache directory and file paths."""
        cache_dir, cache_file = cache_paths("test-package")

        expected_dir = Path(tempfile.gettempdir()) / "python_update_checker"
        expected_file = expected_dir / "test-package_cache.json"

        assert cache_dir == expected_dir
        assert cache_file == expected_file

    def test_different_packages_different_files(self):
        """Different packages should have different cache files."""
        _, file1 = cache_paths("package1")
        _, file2 = cache_paths("package2")

        assert file1 != file2
        assert "package1" in str(file1)
        assert "package2" in str(file2)


class TestCacheOperations:
    """Test cache loading, saving, and freshness checking."""

    def test_load_cache_nonexistent_file(self, tmp_path):
        """Should return None for non-existent cache file."""
        logger = get_logger(None)
        cache_file = tmp_path / "nonexistent.json"

        result = load_cache(cache_file, logger)
        assert result is None

    def test_load_cache_valid_json(self, tmp_path):
        """Should load valid JSON cache files."""
        logger = get_logger(None)
        cache_file = tmp_path / "valid.json"

        test_data = {"key": "value", "number": 42}
        cache_file.write_text(orjson.dumps(test_data).decode(), encoding="utf-8")

        result = load_cache(cache_file, logger)
        assert result == test_data

    def test_load_cache_invalid_json(self, tmp_path):
        """Should raise JSONDecodeError for invalid JSON."""
        logger = get_logger(None)
        cache_file = tmp_path / "invalid.json"
        cache_file.write_text("invalid json content", encoding="utf-8")

        with pytest.raises(orjson.JSONDecodeError):
            load_cache(cache_file, logger)

    def test_load_cache_non_dict(self, tmp_path):
        """Should return None when JSON is not a dictionary."""
        logger = get_logger(None)
        cache_file = tmp_path / "list.json"
        cache_file.write_text(orjson.dumps([1, 2, 3]).decode(), encoding="utf-8")

        result = load_cache(cache_file, logger)
        assert result is None

    def test_save_cache_creates_directory(self, tmp_path):
        """Should create cache directory if it doesn't exist."""
        logger = get_logger(None)
        cache_dir = tmp_path / "new_cache_dir"
        cache_file = cache_dir / "test.json"

        assert not cache_dir.exists()

        save_cache(cache_dir, cache_file, {"test": "data"}, logger)

        assert cache_dir.exists()
        assert cache_file.exists()

    def test_save_cache_content(self, tmp_path):
        """Should save data with last_check timestamp."""
        logger = get_logger(None)
        cache_file = tmp_path / "test.json"

        test_data = {"key": "value"}
        save_cache(tmp_path, cache_file, test_data, logger)

        loaded_data = orjson.loads(cache_file.read_text(encoding="utf-8"))
        assert loaded_data["key"] == "value"
        assert "last_check" in loaded_data
        assert isinstance(loaded_data["last_check"], (int, float))

    def test_is_fresh_with_embedded_timestamp(self, tmp_path):
        """Should check freshness using embedded last_check timestamp."""
        logger = get_logger(None)
        cache_file = tmp_path / "test.json"

        # Create cache with recent timestamp
        current_time = time.time()
        cache_data = {"last_check": current_time - 100, "data": "test"}
        cache_file.write_text(orjson.dumps(cache_data).decode(), encoding="utf-8")

        # Should be fresh with 200s TTL
        assert is_fresh(cache_file, 200, logger) is True

        # Should be stale with 50s TTL
        assert is_fresh(cache_file, 50, logger) is False

    def test_is_fresh_fallback_to_mtime(self, tmp_path):
        """Should fall back to file mtime when no embedded timestamp."""
        logger = get_logger(None)
        cache_file = tmp_path / "test.json"

        # Create cache without last_check
        cache_data = {"data": "test"}
        cache_file.write_text(orjson.dumps(cache_data).decode(), encoding="utf-8")

        # Should use file mtime - file is fresh since just created
        assert is_fresh(cache_file, 60, logger) is True

    def test_is_fresh_nonexistent_file(self, tmp_path):
        """Should return False for non-existent files."""
        logger = get_logger(None)
        cache_file = tmp_path / "nonexistent.json"

        assert is_fresh(cache_file, 60, logger) is False

    def test_reset_cache_removes_file(self, tmp_path):
        """Should remove cache file if it exists."""
        cache_file = tmp_path / "test_cache.json"
        cache_file.write_text("test data")

        # Mock cache_paths to return our test path
        with mock.patch("bash2gitlab.utils.update_checker.cache_paths", return_value=(tmp_path, cache_file)):
            reset_cache("test")

        assert not cache_file.exists()

    def test_reset_cache_nonexistent_file(self, tmp_path):
        """Should not raise error for non-existent cache file."""
        cache_file = tmp_path / "nonexistent.json"

        with mock.patch("bash2gitlab.utils.update_checker.cache_paths", return_value=(tmp_path, cache_file)):
            # Should not raise an exception
            reset_cache("test")


class TestVersionHelpers:
    """Test version-related helper functions."""

    def test_is_dev_version_true_cases(self):
        """Should detect development versions."""
        assert is_dev_version("1.0.dev0") is True
        assert is_dev_version("2.1.3.dev1") is True

    def test_is_dev_version_false_cases(self):
        """Should not detect stable/prerelease versions as dev."""
        assert is_dev_version("1.0.0") is False
        assert is_dev_version("1.0.0a1") is False
        assert is_dev_version("1.0.0rc1") is False

    def test_is_dev_version_invalid_version(self):
        """Should raise InvalidVersion for invalid version strings."""
        with pytest.raises(_version.InvalidVersion):
            is_dev_version("not.a.version")

    def test_is_version_yanked_true(self):
        """Should detect yanked versions."""
        releases = {
            "1.0.0": [
                {"yanked": True, "filename": "package-1.0.0.tar.gz"},
                {"yanked": False, "filename": "package-1.0.0-py3-none-any.whl"},
            ]
        }
        assert is_version_yanked(releases, "1.0.0") is True

    def test_is_version_yanked_false(self):
        """Should not detect non-yanked versions."""
        releases = {"1.0.0": [{"yanked": False, "filename": "package-1.0.0.tar.gz"}]}
        assert is_version_yanked(releases, "1.0.0") is False

    def test_is_version_yanked_missing_version(self):
        """Should return False for missing versions."""
        releases = {"1.0.0": []}
        assert is_version_yanked(releases, "2.0.0") is False

    def test_is_version_yanked_empty_releases(self):
        """Should return False when version has no releases."""
        releases = {"1.0.0": []}
        assert is_version_yanked(releases, "1.0.0") is False


class TestVersionInfo:
    """Test VersionInfo dataclass."""

    def test_version_info_creation(self):
        """Should create VersionInfo with provided values."""
        vi = VersionInfo(latest_stable="1.2.3", latest_dev="1.3.0.dev1", current_yanked=True)
        assert vi.latest_stable == "1.2.3"
        assert vi.latest_dev == "1.3.0.dev1"
        assert vi.current_yanked is True


class TestFormatUpdateMessage:
    """Test update message formatting."""

    def test_no_updates_available(self):
        """Should return empty string when no updates available."""
        logger = get_logger(None)
        vi = VersionInfo("1.0.0", None, False)

        result = format_update_message("test-pkg", "1.0.0", vi, logger)
        assert result == ""

    def test_stable_update_available(self):
        """Should format message for stable update."""
        logger = get_logger(None)
        vi = VersionInfo("2.0.0", None, False)

        result = format_update_message("test-pkg", "1.0.0", vi, logger)

        assert "new stable version" in result
        assert "2.0.0" in result
        assert "1.0.0" in result
        assert "test-pkg" in result
        assert "Please upgrade" in result
        assert "pypi.org/project/test-pkg" in result

    def test_dev_version_available(self):
        """Should format message for dev version."""
        logger = get_logger(None)
        vi = VersionInfo("1.0.0", "1.1.0.dev1", False)

        result = format_update_message("test-pkg", "1.0.0", vi, logger)

        assert "Development version" in result
        assert "1.1.0.dev1" in result
        assert "use at your own risk" in result

    def test_yanked_version_warning(self):
        """Should show warning for yanked current version."""
        logger = get_logger(None)
        vi = VersionInfo("1.0.0", None, True)

        result = format_update_message("test-pkg", "1.0.0", vi, logger)

        assert "WARNING" in result
        assert "yanked" in result
        assert "1.0.0" in result

    def test_color_formatting_enabled(self):
        """Should use colors when available."""
        logger = get_logger(None)
        vi = VersionInfo("2.0.0", None, False)

        with mock.patch("bash2gitlab.utils.update_checker.can_use_color", return_value=True):
            result = format_update_message("test-pkg", "1.0.0", vi, logger)

        # Should contain ANSI color codes
        assert "\033[" in result

    def test_color_formatting_disabled(self):
        """Should not use colors when disabled."""
        logger = get_logger(None)
        vi = VersionInfo("2.0.0", None, False)

        with mock.patch("bash2gitlab.utils.update_checker.can_use_color", return_value=False):
            result = format_update_message("test-pkg", "1.0.0", vi, logger)

        # Should not contain ANSI color codes
        assert "\033[" not in result

    def test_invalid_current_version(self):
        """Should handle invalid current version strings."""
        logger = get_logger(None)
        vi = VersionInfo("2.0.0", None, False)

        # Should not crash with invalid version
        result = format_update_message("test-pkg", "invalid.version", vi, logger)
        assert isinstance(result, str)

    def test_invalid_latest_versions(self):
        """Should handle invalid latest version strings."""
        logger = get_logger(None)
        vi = VersionInfo("invalid.stable", "invalid.dev", False)

        # Should not crash with invalid versions
        result = format_update_message("test-pkg", "1.0.0", vi, logger)
        assert isinstance(result, str)


class TestFetchPypiJson:
    """Test PyPI JSON fetching with mocked network."""

    def test_fetch_package_info_success(self, monkeypatch):
        """Test successful package info fetch with mocked network."""
        logger = get_logger(None)

        mock_response = {
            "info": {"name": "requests", "version": "2.28.0"},
            "releases": {"2.28.0": []},
        }

        def mock_urlopen(request, timeout):
            import json

            class MockResponse:
                def read(self):
                    return json.dumps(mock_response).encode("utf-8")

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

            return MockResponse()

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

        result = fetch_pypi_json("https://pypi.org/pypi/requests/json", 10.0, logger)
        assert isinstance(result, dict)
        assert "info" in result
        assert "releases" in result
        assert result["info"]["name"] == "requests"

    def test_fetch_nonexistent_package(self, monkeypatch):
        """Should raise PackageNotFoundError for non-existent packages."""
        from urllib.error import HTTPError

        logger = get_logger(None)

        def mock_urlopen(request, timeout):
            raise HTTPError(request.full_url, 404, "Not Found", {}, None)

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

        with pytest.raises(PackageNotFoundError):
            fetch_pypi_json("https://pypi.org/pypi/this-package-should-never-exist-12345/json", 5.0, logger)


class TestGetVersionInfoFromPypi:
    """Test version info extraction from PyPI data."""

    @pytest.fixture
    def mock_pypi_data(self):
        """Sample PyPI response data for testing."""
        return {
            "info": {"name": "test-package", "version": "2.0.0"},
            "releases": {
                "1.0.0": [{"yanked": False}],
                "1.1.0": [{"yanked": True}],  # yanked version
                "2.0.0": [{"yanked": False}],
                "2.1.0a1": [{"yanked": False}],  # prerelease
                "3.0.0.dev1": [{"yanked": False}],  # dev version
            },
        }

    def test_version_info_extraction_basic(self, mock_pypi_data):
        """Should extract version info correctly."""
        logger = get_logger(None)

        with mock.patch("bash2gitlab.utils.update_checker.fetch_pypi_json", return_value=mock_pypi_data):
            result = get_version_info_from_pypi("test-package", "1.0.0", logger, include_prereleases=False)

        assert result.latest_stable == "2.0.0"  # Skips prerelease
        assert result.latest_dev == "3.0.0.dev1"
        assert result.current_yanked is False

    def test_version_info_with_prereleases(self, mock_pypi_data):
        """Should include prereleases when requested."""
        logger = get_logger(None)

        with mock.patch("bash2gitlab.utils.update_checker.fetch_pypi_json", return_value=mock_pypi_data):
            result = get_version_info_from_pypi("test-package", "1.0.0", logger, include_prereleases=True)

        assert result.latest_stable == "2.1.0a1"  # Includes prerelease
        assert result.latest_dev == "3.0.0.dev1"

    def test_version_info_yanked_current(self, mock_pypi_data):
        """Should detect when current version is yanked."""
        logger = get_logger(None)

        with mock.patch("bash2gitlab.utils.update_checker.fetch_pypi_json", return_value=mock_pypi_data):
            result = get_version_info_from_pypi("test-package", "1.1.0", logger, include_prereleases=False)

        assert result.current_yanked is True

    def test_version_info_no_releases(self):
        """Should handle packages with no releases."""
        logger = get_logger(None)
        mock_data = {"info": {"version": "1.0.0"}, "releases": {}}

        with mock.patch("bash2gitlab.utils.update_checker.fetch_pypi_json", return_value=mock_data):
            result = get_version_info_from_pypi("test-package", "1.0.0", logger, include_prereleases=False)

        assert result.latest_stable == "1.0.0"
        assert result.latest_dev is None
        assert result.current_yanked is False


class TestCheckForUpdates:
    """Test the main check_for_updates function."""

    def test_check_updates_with_cache(self, tmp_path):
        """Should use cache when fresh."""
        logger = get_logger(None)

        # Create fresh cache
        cache_dir = tmp_path
        cache_file = tmp_path / "test-package_cache.json"
        cache_data = {"last_check": time.time(), "latest_stable": "2.0.0", "latest_dev": None, "current_yanked": False}
        cache_file.write_text(orjson.dumps(cache_data).decode())

        with mock.patch("bash2gitlab.utils.update_checker.cache_paths", return_value=(cache_dir, cache_file)):
            result = check_for_updates("test-package", "1.0.0", logger)

        # Should have found an update from cache without hitting PyPI
        assert result is not None
        assert "2.0.0" in result

    def test_full_update_check_flow_with_update(self, tmp_path):
        """Test complete flow when update is available."""
        logger = get_logger(None)
        cache_dir = tmp_path
        cache_file = tmp_path / "test_cache.json"

        mock_version_info = VersionInfo("2.0.0", "2.1.0.dev1", False)  # Updates available

        with mock.patch("bash2gitlab.utils.update_checker.cache_paths", return_value=(cache_dir, cache_file)):
            with mock.patch(
                "bash2gitlab.utils.update_checker.get_version_info_from_pypi", return_value=mock_version_info
            ):
                result = check_for_updates("test-pkg", "1.0.0", logger)

        assert result is not None
        assert "2.0.0" in result  # Stable update
        assert "Development version" in result  # Dev version
        assert "2.1.0.dev1" in result

        # Cache should be populated
        cache_data = orjson.loads(cache_file.read_text())
        assert cache_data["latest_stable"] == "2.0.0"
        assert cache_data["latest_dev"] == "2.1.0.dev1"

    def test_cache_reuse_across_calls(self, tmp_path):
        """Test that cache is properly reused across multiple calls."""
        logger = get_logger(None)
        cache_dir = tmp_path
        cache_file = tmp_path / "test_cache.json"

        mock_version_info = VersionInfo("2.0.0", None, False)

        with mock.patch("bash2gitlab.utils.update_checker.cache_paths", return_value=(cache_dir, cache_file)):
            with mock.patch(
                "bash2gitlab.utils.update_checker.get_version_info_from_pypi", return_value=mock_version_info
            ) as mock_pypi:
                # First call should hit PyPI
                result1 = check_for_updates("test-pkg", "1.0.0", logger, cache_ttl_seconds=3600)

                # Second call should use cache
                result2 = check_for_updates("test-pkg", "1.0.0", logger, cache_ttl_seconds=3600)

        # PyPI should only be called once
        assert mock_pypi.call_count == 1

        # Both results should be identical
        assert result1 == result2
        assert "2.0.0" in result1

    def test_yanked_version_handling_end_to_end(self, tmp_path):
        """Test end-to-end handling of yanked versions."""
        logger = get_logger(None)
        cache_dir = tmp_path
        cache_file = tmp_path / "test_cache.json"

        # Current version is yanked, but newer stable available
        mock_version_info = VersionInfo("2.0.0", None, True)

        with mock.patch("bash2gitlab.utils.update_checker.cache_paths", return_value=(cache_dir, cache_file)):
            with mock.patch(
                "bash2gitlab.utils.update_checker.get_version_info_from_pypi", return_value=mock_version_info
            ):
                result = check_for_updates("test-pkg", "1.5.0", logger)  # Yanked version

        assert result is not None
        assert "WARNING" in result
        assert "yanked" in result
        assert "1.5.0" in result  # Current yanked version
        assert "2.0.0" in result  # New stable version


class TestRealWorldScenarios:
    """Test realistic scenarios with mocked PyPI responses."""

    def test_nonexistent_package(self, monkeypatch):
        """Test behavior with a non-existent package - should return None gracefully."""
        from urllib.error import HTTPError

        logger = get_logger(None)

        def mock_urlopen(request, timeout):
            raise HTTPError(request.full_url, 404, "Not Found", {}, None)

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

        # Behavior: check_for_updates catches PackageNotFoundError and returns None
        result = check_for_updates("this-package-absolutely-should-not-exist-12345", "1.0.0", logger)
        assert result is None

    def test_background_check_with_mocked_network(self, monkeypatch):
        """Test background checking with mocked network (deterministic)."""
        import bash2gitlab.utils.update_checker as update_checker

        logger = get_logger(None)

        mock_response = {
            "info": {"name": "requests", "version": "2.28.0"},
            "releases": {"2.28.0": [], "1.0.0": []},
        }

        def mock_urlopen(request, timeout):
            import json

            class MockResponse:
                def read(self):
                    return json.dumps(mock_response).encode("utf-8")

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

            return MockResponse()

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

        # Reset global state
        update_checker._background_check_result = None
        update_checker._background_check_thread = None

        start_background_update_check("requests", "1.0.0", logger)

        # Wait for thread to complete deterministically
        if update_checker._background_check_thread:
            update_checker._background_check_thread.join(timeout=5.0)

        # Behavior: background check should complete and set result
        result = update_checker._background_check_result
        assert result is not None
        assert "requests" in result


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_malformed_version_strings(self):
        """Test handling of malformed version strings."""
        logger = get_logger(None)

        # These should not crash the formatter
        vi = VersionInfo("valid.1.0.0", "also.valid.1.0.0", False)
        result = format_update_message("test-pkg", "not.a.version", vi, logger)
        assert isinstance(result, str)

    def test_corrupted_cache_file(self, tmp_path):
        """Test handling of corrupted cache files."""
        logger = get_logger(None)
        cache_file = tmp_path / "corrupted.json"

        # Create file with corrupted JSON
        cache_file.write_text("{ incomplete json")

        with pytest.raises(orjson.JSONDecodeError):
            load_cache(cache_file, logger)

    def test_extremely_large_cache_ttl(self, tmp_path):
        """Test with very large cache TTL."""
        logger = get_logger(None)
        cache_file = tmp_path / "test.json"

        # Create old cache
        old_time = time.time() - 1000
        cache_data = {"last_check": old_time}
        cache_file.write_text(orjson.dumps(cache_data).decode())

        # Very large TTL should make it fresh
        assert is_fresh(cache_file, 999999, logger) is True

    def test_negative_cache_ttl(self, tmp_path):
        """Test with negative cache TTL."""
        logger = get_logger(None)
        cache_file = tmp_path / "test.json"

        # Create fresh cache
        cache_data = {"last_check": time.time()}
        cache_file.write_text(orjson.dumps(cache_data).decode())

        # Negative TTL should always be stale
        assert is_fresh(cache_file, -1, logger) is False

    def test_unicode_in_package_names(self):
        """Test handling of unicode characters in package names."""
        _logger = get_logger(None)

        # Should not crash with unicode package names
        cache_dir, cache_file = cache_paths("test-pkg-πύθων")
        assert "test-pkg-πύθων" in str(cache_file)

    def test_very_long_package_names(self):
        """Test handling of very long package names."""
        _logger = get_logger(None)

        long_name = "a" * 1000
        cache_dir, cache_file = cache_paths(long_name)

        # Should handle long names without crashing
        assert isinstance(cache_file, Path)
        assert len(str(cache_file)) > len(long_name)


#
# class TestConcurrency:
#     """Test thread safety and concurrent access."""
#
#     def test_concurrent_cache_access(self, tmp_path):
#         """Test concurrent access to cache files."""
#         logger = get_logger(None)
#         cache_dir = tmp_path
#         cache_file = tmp_path / "concurrent_test.json"
#
#         results = []
#
#         def worker():
#             try:
#                 with mock.patch("bash2gitlab.utils.update_checker.cache_paths", return_value=(cache_dir, cache_file)):
#                     # Simulate some work
#                     save_cache(cache_dir, cache_file, {"worker": threading.current_thread().name}, logger)
#                     time.sleep(0.01)  # Small delay
#                     data = load_cache(cache_file, logger)
#                     results.append(data)
#             except Exception as e:
#                 results.append(f"Error: {e}")
#
#         # Start multiple threads
#         threads = [threading.Thread(target=worker) for _ in range(5)]
#         for t in threads:
#             t.start()
#         for t in threads:
#             t.join()
#
#         # All threads should have completed without major errors
#         assert len(results) == 5
#         # At least some should have succeeded
#         successful_results = [r for r in results if isinstance(r, dict)]
#         assert len(successful_results) > 0
#


# Pytest configuration and fixtures
@pytest.fixture
def temp_cache_dir(tmp_path):
    """Provide a temporary directory for cache operations."""
    return tmp_path / "test_cache"


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset global state before each test."""
    import bash2gitlab.utils.update_checker as update_checker

    update_checker._background_check_result = None
    update_checker._background_check_registered = False
    update_checker._background_check_thread = None
    yield
    # Cleanup after test
    update_checker._background_check_result = None
    update_checker._background_check_registered = False
    update_checker._background_check_thread = None


@pytest.fixture
def mock_logger():
    """Provide a mock logger for testing."""
    logger = MagicMock(spec=logging.Logger)
    logger.debug = MagicMock()
    logger.warning = MagicMock()
    logger.name = "test_logger"
    return logger


# Markers for different test types
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (may hit network)")
    config.addinivalue_line("markers", "network: marks tests that require network access")


def test_check_updates_package_not_found(tmp_path):
    """Should handle package not found gracefully."""
    logger = get_logger(None)
    cache_dir = tmp_path
    cache_file = tmp_path / "nonexistent_cache.json"

    with mock.patch("bash2gitlab.utils.update_checker.cache_paths", return_value=(cache_dir, cache_file)):
        with mock.patch(
            "bash2gitlab.utils.update_checker.get_version_info_from_pypi", side_effect=PackageNotFoundError()
        ):
            result = check_for_updates("nonexistent-package", "1.0.0", logger)

    assert result is None

    # Should cache the error
    error_cache = orjson.loads(cache_file.read_text())
    assert error_cache["error"] == "not_found"


def test_check_updates_network_error(tmp_path):
    """Should handle network errors gracefully."""
    logger = get_logger(None)
    cache_dir = tmp_path
    cache_file = tmp_path / "test_cache.json"

    with mock.patch("bash2gitlab.utils.update_checker.cache_paths", return_value=(cache_dir, cache_file)):
        with mock.patch(
            "bash2gitlab.utils.update_checker.get_version_info_from_pypi", side_effect=NetworkError("Connection failed")
        ):
            result = check_for_updates("test-package", "1.0.0", logger)

    assert result is None

    # Should cache the error
    error_cache = orjson.loads(cache_file.read_text())
    assert error_cache["error"] == "network"


class TestBackgroundUpdates:
    """Test background update checking."""

    def test_background_worker_success(self):
        """Background worker should store result on success."""
        logger = get_logger(None)

        # Reset global state
        import bash2gitlab.utils.update_checker as update_checker

        update_checker._background_check_result = None

        with mock.patch("bash2gitlab.utils.update_checker.check_for_updates", return_value="Update available"):
            _background_update_worker("test-pkg", "1.0.0", logger, 3600, False)

        assert update_checker._background_check_result == "Update available"

    def test_background_worker_exception(self):
        """Background worker should handle exceptions gracefully."""
        logger = get_logger(None)

        # Reset global state
        import bash2gitlab.utils.update_checker as update_checker

        update_checker._background_check_result = None

        with mock.patch("bash2gitlab.utils.update_checker.check_for_updates", side_effect=Exception("Test error")):
            _background_update_worker("test-pkg", "1.0.0", logger, 3600, False)

        # Should not crash and result should be None
        assert update_checker._background_check_result is None

    def test_exit_handler_with_result(self, capsys):
        """Exit handler should print result when available."""
        import bash2gitlab.utils.update_checker as update_checker

        update_checker._background_check_result = "Test update message"

        _exit_handler()

        captured = capsys.readouterr()
        assert "Test update message" in captured.err

    def test_exit_handler_no_result(self, capsys):
        """Exit handler should not print when no result available."""
        import bash2gitlab.utils.update_checker as update_checker

        update_checker._background_check_result = None

        _exit_handler()

        captured = capsys.readouterr()
        assert captured.err == ""

    def test_start_background_check_fresh_cache(self, tmp_path):
        """Should use fresh cache without starting thread."""
        logger = get_logger(None)
        cache_dir = tmp_path
        cache_file = tmp_path / "test_cache.json"

        # Create fresh cache
        cache_data = {"last_check": time.time(), "latest_stable": "2.0.0", "latest_dev": None, "current_yanked": False}
        cache_file.write_text(orjson.dumps(cache_data).decode())

        import bash2gitlab.utils.update_checker as update_checker

        update_checker._background_check_result = None

        with mock.patch("bash2gitlab.utils.update_checker.cache_paths", return_value=(cache_dir, cache_file)):
            start_background_update_check("test-pkg", "1.0.0", logger)

        # Should have set result from cache
        assert update_checker._background_check_result is not None
        assert "2.0.0" in update_checker._background_check_result

    def test_start_background_check_stale_cache(self, tmp_path):
        """Should start thread for stale cache."""
        logger = get_logger(None)
        cache_dir = tmp_path
        cache_file = tmp_path / "test_cache.json"

        # Create stale cache
        cache_data = {
            "last_check": time.time() - 90000,  # Very old
            "latest_stable": "1.0.0",
            "latest_dev": None,
            "current_yanked": False,
        }
        cache_file.write_text(orjson.dumps(cache_data).decode())

        thread_started = False
        _original_thread = threading.Thread

        def mock_thread(*args, **kwargs):
            nonlocal thread_started
            thread_started = True
            # Return a mock thread that we can control
            mock_thread_obj = MagicMock()
            mock_thread_obj.start = MagicMock()
            return mock_thread_obj

        with mock.patch("bash2gitlab.utils.update_checker.cache_paths", return_value=(cache_dir, cache_file)):
            with mock.patch("threading.Thread", side_effect=mock_thread):
                start_background_update_check("test-pkg", "1.0.0", logger)

        assert thread_started

    def test_start_background_check_exception_handling(self):
        """Should handle exceptions gracefully in entry point."""
        logger = get_logger(None)

        # Force an exception in cache path calculation
        with mock.patch("bash2gitlab.utils.update_checker.cache_paths", side_effect=Exception("Test error")):
            # Should not raise an exception
            start_background_update_check("test-pkg", "1.0.0", logger)


class TestColorClass:
    """Test the _Color dataclass."""

    def test_color_constants(self):
        """Should have proper ANSI color codes."""
        c = _Color()
        assert c.YELLOW == "\033[93m"
        assert c.GREEN == "\033[92m"
        assert c.RED == "\033[91m"
        assert c.BLUE == "\033[94m"
        assert c.ENDC == "\033[0m"
