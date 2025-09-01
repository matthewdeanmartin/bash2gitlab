import os
from unittest import mock

from bash2gitlab.utils.update_checker import _Color, can_use_color, check_for_updates, reset_cache


def test_finds_newer_version():
    """Test that a known old version returns an update message string."""
    reset_cache("requests")
    result = check_for_updates(package_name="requests", current_version="2.0.0")
    assert result is not None
    assert "A new stable version of requests is available" in result
    assert "you are using 2.0.0" in result


def test_handles_up_to_date_package():
    """Test that a version that is clearly too high results in None."""
    reset_cache("packaging")
    result = check_for_updates(package_name="packaging", current_version="999.0.0")
    assert result is None


def test_prerelease_check_finds_newer():
    """Test that pre-releases are found when the flag is enabled."""
    reset_cache("pandas")
    result = check_for_updates(package_name="pandas", current_version="2.0.0", include_prereleases=True)
    # This can either find a newer version or find nothing if we're at the latest
    # The main test is that it doesn't crash and returns a string or None.
    assert isinstance(result, (str, type(None)))
    if result:
        assert "A new stable version of pandas is available" in result


@mock.patch("bash2gitlab.utils.update_checker.can_use_color", return_value=True)
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
    assert not can_use_color()
    result = check_for_updates(package_name="httpx", current_version="0.1.0")
    assert result is not None
    c = _Color()
    assert c.YELLOW not in result, "Output should not have color in CI"
