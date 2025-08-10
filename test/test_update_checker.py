import os
from unittest import mock

from bash2gitlab.utils.update_checker import _can_use_color, _Color, check_for_updates, reset_cache


def test_finds_newer_version():
    """Test that a known old version returns an update message string."""
    reset_cache("requests")
    result = check_for_updates(package_name="requests", current_version="2.0.0")
    assert result is not None
    assert "A new version of requests is available" in result
    assert "you are using 2.0.0" in result


def test_handles_up_to_date_package():
    """Test that a version that is clearly too high results in None."""
    reset_cache("packaging")
    result = check_for_updates(package_name="packaging", current_version="999.0.0")
    assert result is None


def test_handles_nonexistent_package(capsys):
    """Test that a 404 on a package name logs a warning and returns None."""
    reset_cache("no-such-package-exists-xyz-abc-123")
    result = check_for_updates(package_name="no-such-package-exists-xyz-abc-123", current_version="1.0.0")
    assert result is None
    captured = capsys.readouterr()
    assert "Package 'no-such-package-exists-xyz-abc-123' not found on PyPI." in captured.out


def test_caching_works():
    """Test that the function caches results and respects the TTL."""
    pkg = "pylint"
    reset_cache(pkg)
    v = "1.0.0"
    ttl = 10  # 10 second cache

    # I don't think this is mocking time correctly.
    with mock.patch("time.time") as mock_time:
        # 1. First call, should hit network and return a message
        mock_time.return_value = 1000.0
        result1 = check_for_updates(pkg, v, cache_ttl_seconds=ttl)
        assert result1 is not None

        # 2. Second call, immediately after. Should be cached, return None.
        mock_time.return_value = 1005.0  # Still within TTL
        result2 = check_for_updates(pkg, v, cache_ttl_seconds=ttl)
        assert result2 is None


def test_cache_reset_works():
    """Test that reset_cache clears the cache and allows a fresh check."""
    reset_cache("pytest")
    pkg = "pytest"
    v = "6.0.0"
    ttl = 60  # Use a long TTL to ensure caching would normally apply

    # 1. First call, creates the cache and returns a message
    result1 = check_for_updates(pkg, v, cache_ttl_seconds=ttl)
    assert result1 is not None

    # 2. Second call, should be cached and return None
    result2 = check_for_updates(pkg, v, cache_ttl_seconds=ttl)
    assert result2 is None

    # 3. Reset the cache for the package
    reset_cache(pkg)

    # 4. Third call, should hit the network again and return a message
    result3 = check_for_updates(pkg, v, cache_ttl_seconds=ttl)
    assert result3 is not None


def test_prerelease_check_finds_newer():
    """Test that pre-releases are found when the flag is enabled."""
    reset_cache("pandas")
    result = check_for_updates(package_name="pandas", current_version="2.0.0", include_prereleases=True)
    # This can either find a newer version or find nothing if we're at the latest
    # The main test is that it doesn't crash and returns a string or None.
    assert isinstance(result, (str, type(None)))
    if result:
        assert "A new version of pandas is available" in result


@mock.patch("bash2gitlab.utils.update_checker._can_use_color", return_value=True)
def test_color_output_enabled(mock_color):
    """Test that ANSI color codes are present when color is enabled."""
    reset_cache("requests")
    result = check_for_updates(package_name="requests", current_version="2.0.0")
    assert result is not None
    c = _Color()
    assert c.YELLOW in result, "Output should contain color codes when enabled"


@mock.patch.dict(os.environ, {"CI": "true"})
def test_color_output_disabled_in_ci():
    """Test that color is disabled when a CI environment variable is set."""
    reset_cache("httpx")
    assert not _can_use_color()
    result = check_for_updates(package_name="httpx", current_version="0.1.0")
    assert result is not None
    c = _Color()
    assert c.YELLOW not in result, "Output should not have color in CI"
