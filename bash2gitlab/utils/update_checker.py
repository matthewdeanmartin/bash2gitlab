"""Improved update checker utility for bash2gitlab (standalone module).

Key improvements over prior version:
- Clear public API with docstrings and type hints
- Robust networking with timeouts, retries, and explicit User-Agent
- Safe, simple JSON cache with TTL to avoid frequent network calls
- Correct prerelease handling using packaging.version
- Yanked version detection with warnings
- Development version detection and reporting
- Optional colorized output that respects NO_COLOR/CI/TERM and TTY
- Non-invasive logging: caller may pass a logger or rely on a safe default
- Narrow exception surface with custom error types

Public functions:
- check_for_updates(package_name, current_version, ...)
- reset_cache(package_name)

Return contract:
- Returns a user-facing message string when an update is available; otherwise None.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib import error, request

from packaging import version as _version

__all__ = [
    "check_for_updates",
    "reset_cache",
    "PackageNotFoundError",
    "NetworkError",
]


class PackageNotFoundError(Exception):
    """Raised when the package does not exist on PyPI (HTTP 404)."""


class NetworkError(Exception):
    """Raised when a network error occurs while contacting PyPI."""


@dataclass(frozen=True)
class _Color:
    YELLOW: str = "\033[93m"
    GREEN: str = "\033[92m"
    RED: str = "\033[91m"
    BLUE: str = "\033[94m"
    ENDC: str = "\033[0m"


@dataclass(frozen=True)
class VersionInfo:
    """Information about available versions."""

    latest_stable: str | None
    latest_dev: str | None
    current_yanked: bool


def get_logger(user_logger: logging.Logger | None) -> Callable[[str], None]:
    """Get a warning logging function.

    Args:
        user_logger: Logger instance or None.

    Returns:
        Logger warning method or built-in print.
    """
    if isinstance(user_logger, logging.Logger):
        return user_logger.warning
    return print


def can_use_color() -> bool:
    """Determine if color output is allowed.

    Returns:
        True if output can be colorized.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("CI"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def cache_paths(package_name: str) -> tuple[Path, Path]:
    """Compute cache directory and file path for a package.

    Args:
        package_name: Name of the package.

    Returns:
        Cache directory and file path.
    """
    cache_dir = Path(tempfile.gettempdir()) / "python_update_checker"
    cache_file = cache_dir / f"{package_name}_cache.json"
    return cache_dir, cache_file


def is_fresh(cache_file: Path, ttl_seconds: int) -> bool:
    """Check if cache file is fresh.

    Args:
        cache_file: Path to cache file.
        ttl_seconds: TTL in seconds.

    Returns:
        True if cache is within TTL.
    """
    try:
        if cache_file.exists():
            last_check_time = cache_file.stat().st_mtime
            return (time.time() - last_check_time) < ttl_seconds
    except (OSError, PermissionError):
        return False
    return False


def save_cache(cache_dir: Path, cache_file: Path, payload: dict) -> None:
    """Save data to cache.

    Args:
        cache_dir: Cache directory.
        cache_file: Cache file path.
        payload: Data to store.
    """
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with cache_file.open("w", encoding="utf-8") as f:
            json.dump({"last_check": time.time(), **payload}, f)
    except (OSError, PermissionError):
        pass


def reset_cache(package_name: str) -> None:
    """Remove cache entry for a given package.

    Args:
        package_name: Package name to clear from cache.
    """
    _, cache_file = cache_paths(package_name)
    try:
        if cache_file.exists():
            cache_file.unlink(missing_ok=True)
    except (OSError, PermissionError):
        pass


def fetch_pypi_json(url: str, timeout: float) -> dict:
    """Fetch JSON metadata from PyPI.

    Args:
        url: URL to fetch.
        timeout: Timeout in seconds.

    Returns:
        Parsed JSON data.
    """
    req = request.Request(url, headers={"User-Agent": "bash2gitlab-update-checker/2"})
    with request.urlopen(req, timeout=timeout) as resp:  # nosec
        return json.loads(resp.read().decode("utf-8"))


def is_dev_version(version_str: str) -> bool:
    """Check if a version string represents a development version.

    Args:
        version_str: Version string to check.

    Returns:
        True if this is a development version.
    """
    try:
        v = _version.parse(version_str)
        return v.is_devrelease
    except _version.InvalidVersion:
        return False


def is_version_yanked(releases: dict, version_str: str) -> bool:
    """Check if a specific version has been yanked.

    Args:
        releases: PyPI releases data.
        version_str: Version string to check.

    Returns:
        True if the version is yanked.
    """
    version_releases = releases.get(version_str, [])
    if not version_releases:
        return False

    # Check if any release file for this version is yanked
    for release in version_releases:
        if release.get("yanked", False):
            return True
    return False


def get_version_info_from_pypi(
    package_name: str,
    current_version: str,
    *,
    include_prereleases: bool,
    timeout: float = 5.0,
    retries: int = 2,
    backoff: float = 0.5,
) -> VersionInfo:
    """Get version information from PyPI.

    Args:
        package_name: Package name.
        current_version: Current version to check if yanked.
        include_prereleases: Whether to include prereleases.
        timeout: Request timeout.
        retries: Number of retries.
        backoff: Backoff factor between retries.

    Returns:
        Version information including latest stable, dev, and yank status.

    Raises:
        PackageNotFoundError: If the package does not exist.
        NetworkError: If network error occurs after retries.
    """
    url = f"https://pypi.org/pypi/{package_name}/json"
    last_err: Exception | None = None

    for attempt in range(retries + 1):
        try:
            data = fetch_pypi_json(url, timeout)
            releases = data.get("releases", {})

            if not releases:
                info_ver = data.get("info", {}).get("version")
                return VersionInfo(
                    latest_stable=str(info_ver) if info_ver else None, latest_dev=None, current_yanked=False
                )

            # Check if current version is yanked
            current_yanked = is_version_yanked(releases, current_version)

            # Parse all valid versions
            stable_versions: list[_version.Version] = []
            dev_versions: list[_version.Version] = []

            for v_str in releases.keys():
                try:
                    v = _version.parse(v_str)
                except _version.InvalidVersion:
                    continue

                # Skip yanked versions when looking for latest
                if is_version_yanked(releases, v_str):
                    continue

                if v.is_devrelease:
                    dev_versions.append(v)
                elif v.is_prerelease:
                    if include_prereleases:
                        stable_versions.append(v)
                else:
                    stable_versions.append(v)

            latest_stable = str(max(stable_versions)) if stable_versions else None
            latest_dev = str(max(dev_versions)) if dev_versions else None

            return VersionInfo(latest_stable=latest_stable, latest_dev=latest_dev, current_yanked=current_yanked)

        except error.HTTPError as e:
            if e.code == 404:
                raise PackageNotFoundError from e
            last_err = e
        except (error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            last_err = e

        if attempt < retries:
            time.sleep(backoff * (attempt + 1))

    raise NetworkError(str(last_err))


def format_update_message(
    package_name: str,
    current_version_str: str,
    version_info: VersionInfo,
) -> str:
    """Format the update notification message.

    Args:
        package_name: Package name.
        current_version_str: Current version string.
        version_info: Version information from PyPI.

    Returns:
        Formatted update message.
    """
    pypi_url = f"https://pypi.org/project/{package_name}/"
    messages: list[str] = []

    try:
        current = _version.parse(current_version_str)
    except _version.InvalidVersion:
        current = None

    c = _Color() if can_use_color() else None

    # Check if current version is yanked
    if version_info.current_yanked:
        if c:
            yank_msg = f"{c.RED}WARNING: Your current version {current_version_str} of {package_name} has been yanked from PyPI!{c.ENDC}"
        else:
            yank_msg = (
                f"WARNING: Your current version {current_version_str} of {package_name} has been yanked from PyPI!"
            )
        messages.append(yank_msg)

    # Check for stable updates
    if version_info.latest_stable and current:
        try:
            latest_stable = _version.parse(version_info.latest_stable)
            if latest_stable > current:
                if c:
                    stable_msg = f"{c.YELLOW}A new stable version of {package_name} is available: {c.GREEN}{latest_stable}{c.YELLOW} (you are using {current}).{c.ENDC}"
                else:
                    stable_msg = f"A new stable version of {package_name} is available: {latest_stable} (you are using {current})."
                messages.append(stable_msg)
        except _version.InvalidVersion:
            pass

    # Check for dev versions
    if version_info.latest_dev:
        try:
            latest_dev = _version.parse(version_info.latest_dev)
            if current is None or latest_dev > current:
                if c:
                    dev_msg = f"{c.BLUE}Development version available: {c.GREEN}{latest_dev}{c.BLUE} (use at your own risk).{c.ENDC}"
                else:
                    dev_msg = f"Development version available: {latest_dev} (use at your own risk)."
                messages.append(dev_msg)
        except _version.InvalidVersion:
            pass

    if messages:
        upgrade_msg = "Please upgrade using your preferred package manager."
        info_msg = f"More info: {pypi_url}"
        messages.extend([upgrade_msg, info_msg])
        return "\n".join(messages)

    return ""


def check_for_updates(
    package_name: str,
    current_version: str,
    logger: logging.Logger | None = None,
    *,
    cache_ttl_seconds: int = 86400,
    include_prereleases: bool = False,
) -> str | None:
    """Check PyPI for a newer version of a package.

    Args:
        package_name: The PyPI package name to check.
        current_version: The currently installed version string.
        logger: Optional logger for warnings.
        cache_ttl_seconds: Cache time-to-live in seconds.
        include_prereleases: Whether to consider prereleases newer.

    Returns:
        Formatted update message if update available, else None.
    """
    warn = get_logger(logger)
    cache_dir, cache_file = cache_paths(package_name)

    if is_fresh(cache_file, cache_ttl_seconds):
        return None

    try:
        version_info = get_version_info_from_pypi(
            package_name, current_version, include_prereleases=include_prereleases
        )

        message = format_update_message(package_name, current_version, version_info)

        # Cache the results
        cache_payload = {
            "latest_stable": version_info.latest_stable,
            "latest_dev": version_info.latest_dev,
            "current_yanked": version_info.current_yanked,
        }
        save_cache(cache_dir, cache_file, cache_payload)

        return message if message else None

    except PackageNotFoundError:
        warn(f"Package '{package_name}' not found on PyPI.")
        save_cache(cache_dir, cache_file, {"error": "not_found"})
        return None
    except NetworkError:
        save_cache(cache_dir, cache_file, {"error": "network"})
        return None
    except Exception:
        save_cache(cache_dir, cache_file, {"error": "unknown"})
        return None


# if __name__ == "__main__":
#     msg = check_for_updates("bash2gitlab", "0.0.0")
#     if msg:
#         print(msg)
#     else:
#         print("No update message (cached or up-to-date).")
