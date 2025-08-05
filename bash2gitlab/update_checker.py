"""
A reusable Python submodule to check for package updates on PyPI using only stdlib.

This module provides a function to check if a newer version of a specified
package is available on PyPI. It is designed to be fault-tolerant, efficient,
and dependency-light with the following features:

- Uses only the Python standard library for networking (urllib).
- Caches results to limit network requests. Cache lifetime is configurable.
- Provides a function to manually reset the cache.
- Stores the cache in an OS-appropriate temporary directory.
- Logs a warning if the package is not found on PyPI (404).
- Provides optional colorized output for terminals that support it.
- Uses the `packaging` library for robust version parsing and comparison.
- Includes an option to check for pre-releases (e.g., alpha, beta, rc).

Requirements:
- packaging: `pip install packaging`

To use, simply import and call the `check_for_updates` function.

"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from urllib import error, request

# The 'packaging' library is highly recommended for robust version handling.
from packaging import version

# --- ANSI Color Codes ---
YELLOW = "\033[93m"
GREEN = "\033[92m"
ENDC = "\033[0m"


# --- Custom Exception ---
class PackageNotFoundError(Exception):
    """Custom exception for when a package is not found on PyPI."""


def check_for_updates(
    package_name: str,
    current_version: str,
    logger: logging.Logger | None = None,
    cache_ttl_seconds: int = 86400,
    include_prereleases: bool = False,
) -> str | None:
    """
    Checks for a new version of a package on PyPI.

    If an update is available, it returns a formatted message string.
    Otherwise, it returns None. It fails fast and silently on errors.

    Args:
        package_name: The name of the package as it appears on PyPI.
        current_version: The current version string of the running application.
        logger: An optional logging.Logger instance. Used ONLY to log a
                warning if the package is not found on PyPI.
        cache_ttl_seconds: The number of seconds to cache the result.
        include_prereleases: If True, include alpha/beta/rc versions.

    Returns:
        A formatted message string if an update is available, else None.
    """
    try:
        cache_dir = os.path.join(tempfile.gettempdir(), "python_update_checker")
        cache_file = os.path.join(cache_dir, f"{package_name}_cache.json")

        if _is_check_recently_done(cache_file, cache_ttl_seconds):
            return None

        latest_version_str = _get_latest_version_from_pypi(package_name, include_prereleases)
        if not latest_version_str:
            return None

        current = version.parse(current_version)
        latest = version.parse(latest_version_str)

        if latest > current:
            pypi_url = f"https://pypi.org/project/{package_name}/"
            use_color = _can_use_color()

            if use_color:
                message = (
                    f"{YELLOW}A new version of {package_name} is available: {GREEN}{latest}{YELLOW} "
                    f"(you are using {current}).\n"
                    f"Please upgrade using your preferred package manager.\n"
                    f"More info: {pypi_url}{ENDC}"
                )
            else:
                message = (
                    f"A new version of {package_name} is available: {latest} "
                    f"(you are using {current}).\n"
                    f"Please upgrade using your preferred package manager.\n"
                    f"More info: {pypi_url}"
                )
            _update_cache(cache_dir, cache_file)
            return message

        _update_cache(cache_dir, cache_file)
        return None

    except PackageNotFoundError:
        _log = _get_logger(logger)
        _log(f"WARNING: Package '{package_name}' not found on PyPI.")
        return None
    except Exception:
        return None


def reset_cache(package_name: str) -> None:
    """
    Deletes the cache file for a specific package, forcing a fresh check
    on the next run. Fails silently if the file cannot be removed.

    Args:
        package_name: The name of the package whose cache should be reset.
    """
    try:
        cache_dir = os.path.join(tempfile.gettempdir(), "python_update_checker")
        cache_file = os.path.join(cache_dir, f"{package_name}_cache.json")
        if os.path.exists(cache_file):
            os.remove(cache_file)
    except (OSError, PermissionError):
        # Fail silently if cache cannot be removed
        pass


def _get_logger(logger: logging.Logger | None):
    """Returns a callable for logging or printing."""
    if logger:
        return logger.warning  # Use warning level for 404s
    return print


def _can_use_color() -> bool:
    """
    Checks if the terminal supports color. Returns False if in a CI environment,
    if NO_COLOR is set, or if the terminal is 'dumb'.
    """
    if "NO_COLOR" in os.environ:
        return False
    if "CI" in os.environ and os.environ["CI"]:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return sys.stdout.isatty()


def _is_check_recently_done(cache_file: str, ttl_seconds: int) -> bool:
    """Checks if an update check was performed within the TTL."""
    try:
        if os.path.exists(cache_file):
            last_check_time = os.path.getmtime(cache_file)
            if (time.time() - last_check_time) < ttl_seconds:
                return True
    except (OSError, PermissionError):
        return False
    return False


def _get_latest_version_from_pypi(package_name: str, include_prereleases: bool) -> str | None:
    """
    Fetches the latest version string of a package from PyPI's JSON API.
    Raises PackageNotFoundError for 404 errors.
    """
    url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        req = request.Request(url, headers={"User-Agent": "python-update-checker/1.1"})
        with request.urlopen(req, timeout=10) as response:  # nosec
            data = json.loads(response.read().decode("utf-8"))

        releases = data.get("releases", {})
        if not releases:
            return data.get("info", {}).get("version")

        all_versions: list[version.Version] = []
        for v_str in releases.keys():
            try:
                parsed_v = version.parse(v_str)
                if not parsed_v.is_prerelease or include_prereleases:
                    all_versions.append(parsed_v)
            except version.InvalidVersion:
                continue

        if not all_versions:
            return None

        return str(max(all_versions))

    except error.HTTPError as e:
        if e.code == 404:
            raise PackageNotFoundError from e
        return None
    except (error.URLError, json.JSONDecodeError, TimeoutError, OSError):
        return None


def _update_cache(cache_dir: str, cache_file: str) -> None:
    """Creates or updates the cache file with the current timestamp."""
    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache_file, "w") as f:
            f.write(json.dumps({"last_check": time.time()}))
    except (OSError, PermissionError):
        pass
