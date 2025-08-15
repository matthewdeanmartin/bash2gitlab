"""Improved update checker utility for bash2gitlab (standalone module).

Key improvements over prior version:
- Clear public API with docstrings and type hints
- Robust networking with timeouts, retries, and explicit User-Agent
- Safe, simple JSON cache with TTL to avoid frequent network calls
- Correct prerelease handling using packaging.version
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
    ENDC: str = "\033[0m"


def get_logger(user_logger: logging.Logger | None) -> Callable[[str], None]:
    """Get a warning logging function.

    Args:
        user_logger (logging.Logger | None): Logger instance or None.

    Returns:
        Callable[[str], None]: Logger warning method or built-in print.
    """
    if isinstance(user_logger, logging.Logger):
        return user_logger.warning
    return print


def can_use_color() -> bool:
    """Determine if color output is allowed.

    Returns:
        bool: True if output can be colorized.
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
        package_name (str): Name of the package.

    Returns:
        tuple[Path, Path]: Cache directory and file path.
    """
    cache_dir = Path(tempfile.gettempdir()) / "python_update_checker"
    cache_file = cache_dir / f"{package_name}_cache.json"
    return cache_dir, cache_file


def is_fresh(cache_file: Path, ttl_seconds: int) -> bool:
    """Check if cache file is fresh.

    Args:
        cache_file (Path): Path to cache file.
        ttl_seconds (int): TTL in seconds.

    Returns:
        bool: True if cache is within TTL.
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
        cache_dir (Path): Cache directory.
        cache_file (Path): Cache file path.
        payload (dict): Data to store.
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
        package_name (str): Package name to clear from cache.
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
        url (str): URL to fetch.
        timeout (float): Timeout in seconds.

    Returns:
        dict: Parsed JSON data.
    """
    req = request.Request(url, headers={"User-Agent": "bash2gitlab-update-checker/2"})
    with request.urlopen(req, timeout=timeout) as resp:  # nosec
        return json.loads(resp.read().decode("utf-8"))


def get_latest_version_from_pypi(
    package_name: str,
    *,
    include_prereleases: bool,
    timeout: float = 5.0,
    retries: int = 2,
    backoff: float = 0.5,
) -> str | None:
    """Get latest version from PyPI.

    Args:
        package_name (str): Package name.
        include_prereleases (bool): Whether to include prereleases.
        timeout (float): Request timeout.
        retries (int): Number of retries.
        backoff (float): Backoff factor between retries.

    Returns:
        str | None: Latest version string, None if unavailable.

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
                return str(info_ver) if info_ver else None
            parsed: list[_version.Version] = []
            for v_str in releases.keys():
                try:
                    v = _version.parse(v_str)
                except _version.InvalidVersion:
                    continue
                if v.is_prerelease and not include_prereleases:
                    continue
                parsed.append(v)
            if not parsed:
                return None
            return str(max(parsed))
        except error.HTTPError as e:
            if e.code == 404:
                raise PackageNotFoundError from e
            last_err = e
        except (error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            last_err = e
        time.sleep(backoff * (attempt + 1))
    raise NetworkError(str(last_err))


def format_update_message(
    package_name: str,
    current: _version.Version,
    latest: _version.Version,
) -> str:
    """Format the update notification message.

    Args:
        package_name (str): Package name.
        current (_version.Version): Current version.
        latest (_version.Version): Latest version.

    Returns:
        str: Formatted update message.
    """
    pypi_url = f"https://pypi.org/project/{package_name}/"
    if can_use_color():
        c = _Color()
        return (
            f"{c.YELLOW}A new version of {package_name} is available: {c.GREEN}{latest}{c.YELLOW} "
            f"(you are using {current}).\n"
            f"Please upgrade using your preferred package manager.\n"
            f"More info: {pypi_url}{c.ENDC}"
        )
    return (
        f"A new version of {package_name} is available: {latest} (you are using {current}).\n"
        f"Please upgrade using your preferred package manager.\n"
        f"More info: {pypi_url}"
    )


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
        package_name (str): The PyPI package name to check.
        current_version (str): The currently installed version string.
        logger (logging.Logger | None): Optional logger for warnings.
        cache_ttl_seconds (int): Cache time-to-live in seconds.
        include_prereleases (bool): Whether to consider prereleases newer.

    Returns:
        str | None: Formatted update message if update available, else None.
    """
    warn = get_logger(logger)
    cache_dir, cache_file = cache_paths(package_name)
    if is_fresh(cache_file, cache_ttl_seconds):
        return None
    try:
        latest_str = get_latest_version_from_pypi(package_name, include_prereleases=include_prereleases)
        if not latest_str:
            save_cache(cache_dir, cache_file, {"latest": None})
            return None
        current = _version.parse(current_version)
        latest = _version.parse(latest_str)
        if latest > current:
            save_cache(cache_dir, cache_file, {"latest": latest_str})
            return format_update_message(package_name, current, latest)
        save_cache(cache_dir, cache_file, {"latest": latest_str})
        return None
    except PackageNotFoundError:
        warn(f"Package '{package_name}' not found on PyPI.")
        save_cache(cache_dir, cache_file, {"latest": None})
        return None
    except NetworkError:
        save_cache(cache_dir, cache_file, {"latest": None})
        return None
    except Exception:
        save_cache(cache_dir, cache_file, {"latest": None})
        return None


# if __name__ == "__main__":
#     msg = check_for_updates("bash2gitlab", "0.0.0")
#     if msg:
#         print(msg)
#     else:
#         print("No update message (cached or up-to-date).")
