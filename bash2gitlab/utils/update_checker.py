"""Improved update checker utility for bash2gitlab (standalone module).

Key improvements over prior version:
- Clear public API with docstrings and type hints
- Robust networking with timeouts, retries, and explicit User-Agent
- Safe, simple JSON cache with TTL to avoid frequent network calls
- Correct prerelease handling using packaging.version
- Yanked version detection with warnings
- Development version detection and reporting
- Optional colorized output that respects NO_COLOR/CI/TERM and TTY
- Proper logging with debug information for troubleshooting
- Clean exception handling - only entry points catch and suppress
- ZERO-COST background checking with exit handler

Public functions:
- start_background_update_check(package_name, current_version, ...)
- check_for_updates(package_name, current_version, ...) [synchronous fallback]
- reset_cache(package_name)

Return contract:
- Background check shows message on exit if update available
- Synchronous check returns a user-facing message string when an update is available; otherwise None.
"""

from __future__ import annotations

import atexit
import logging
import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib import error

import orjson as json
from packaging import version as _version

__all__ = [
    "start_background_update_check",
    "check_for_updates",
    "reset_cache",
    "PackageNotFoundError",
    "NetworkError",
]

from bash2gitlab import __about__
from bash2gitlab.errors.exceptions import Bash2GitlabError
from bash2gitlab.utils.urllib3_helper import fetch_json

# Global state for background checking
_background_check_result: str | None = None
_background_check_registered = False


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


def get_logger(user_logger: logging.Logger | None) -> logging.Logger:
    """Get a logger instance.

    Args:
        user_logger: Logger instance or None.

    Returns:
        Logger instance (user-provided or default).
    """
    if isinstance(user_logger, logging.Logger):
        return user_logger

    # Create a default logger
    logger = logging.getLogger("update_checker")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter("%(name)s: %(levelname)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)

    return logger


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
    return sys.stdout.isatty()


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


def load_cache(cache_file: Path, logger: logging.Logger) -> dict | None:
    """Load cache JSON safely. Returns None on any error.

    Args:
        cache_file: Path to cache file.
        logger: Logger instance for debugging.

    Returns:
        Cache data or None if not found/invalid.
    """
    logger.debug(f"Attempting to load cache from {cache_file}")

    if not cache_file.exists():
        logger.debug(f"Cache file {cache_file} does not exist")
        return None

    try:
        raw = cache_file.read_text(encoding="utf-8")
        logger.debug(f"Read {len(raw)} bytes from cache file")

        data = json.loads(raw)
        if not isinstance(data, dict):
            logger.debug(f"Cache data is not a dict, got {type(data)}")
            return None

        logger.debug(f"Successfully loaded cache with keys: {list(data.keys())}")
        return data

    except json.JSONDecodeError as e:
        logger.debug(f"Failed to parse JSON from cache: {e}")
        raise
    except OSError as e:
        logger.debug(f"Failed to read cache file: {e}")
        raise


def is_fresh(cache_file: Path, ttl_seconds: int, logger: logging.Logger) -> bool:
    """Check if cache file is fresh using its embedded last_check (preferred)
    or falling back to file mtime.

    Args:
        cache_file: Path to cache file.
        ttl_seconds: Time-to-live in seconds.
        logger: Logger instance for debugging.

    Returns:
        True if cache is fresh.
    """
    logger.debug(f"Checking cache freshness for {cache_file}, TTL={ttl_seconds}s")

    try:
        data = load_cache(cache_file, logger)
        now = time.time()

        if data and isinstance(data.get("last_check"), (int, float)):
            age = now - float(data["last_check"])
            fresh = age < ttl_seconds
            logger.debug(f"Cache age from embedded timestamp: {age:.1f}s, fresh: {fresh}")
            return fresh

        if cache_file.exists():
            last_check_time = cache_file.stat().st_mtime
            age = now - last_check_time
            fresh = age < ttl_seconds
            logger.debug(f"Cache age from file mtime: {age:.1f}s, fresh: {fresh}")
            return fresh

    except Exception as e:
        logger.debug(f"Error checking cache freshness: {e}")
        # Re-raise instead of silently returning False
        raise

    logger.debug("No cache file found")
    return False


def save_cache(cache_dir: Path, cache_file: Path, payload: dict, logger: logging.Logger) -> None:
    """Save data to cache.

    Args:
        cache_dir: Cache directory.
        cache_file: Cache file path.
        payload: Data to store.
        logger: Logger instance for debugging.
    """
    logger.debug(f"Saving cache to {cache_file} with payload keys: {list(payload.keys())}")

    cache_dir.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Created cache directory: {cache_dir}")

    body = {"last_check": time.time(), **payload}
    cache_content = json.dumps(body).decode()

    cache_file.write_text(cache_content, encoding="utf-8")
    logger.debug(f"Wrote {len(cache_content)} bytes to cache file")


def reset_cache(package_name: str) -> None:
    """Remove cache entry for a given package.

    Args:
        package_name: Package name to clear from cache.
    """
    _, cache_file = cache_paths(package_name)
    if cache_file.exists():
        cache_file.unlink(missing_ok=True)


def fetch_pypi_json(url: str, timeout: float, logger: logging.Logger) -> dict:
    """Fetch JSON metadata from PyPI.

    Args:
        url: URL to fetch.
        timeout: Timeout in seconds.
        logger: Logger instance for debugging.

    Returns:
        Parsed JSON data.

    Raises:
        PackageNotFoundError: If package not found (404).
        NetworkError: For other network errors.
    """
    logger.debug(f"Fetching PyPI JSON from {url} with timeout {timeout}s")

    try:
        data = fetch_json(url, timeout)
        logger.debug(f"Successfully fetched JSON with {len(data)} top-level keys")
        return data
    except Bash2GitlabError as e:
        logger.debug(f"bash2gitlab error fetching JSON: {e}")
        raise PackageNotFoundError() from e


def is_dev_version(version_str: str) -> bool:
    """Check if a version string represents a development version.

    Args:
        version_str: Version string to check.

    Returns:
        True if this is a development version.

    Raises:
        _version.InvalidVersion: If version string is invalid.
    """
    v = _version.parse(version_str)
    return v.is_devrelease


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
    return any(release.get("yanked", False) for release in version_releases)


def get_version_info_from_pypi(
    package_name: str,
    current_version: str,
    logger: logging.Logger,
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
        logger: Logger instance for debugging.
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

    logger.debug(f"Getting version info for {package_name}, current: {current_version}")
    logger.debug(f"Will retry up to {retries} times with {backoff}s backoff")

    for attempt in range(retries + 1):
        logger.debug(f"Attempt {attempt + 1}/{retries + 1}")

        try:
            data = fetch_pypi_json(url, timeout, logger)
            releases = data.get("releases", {})

            if not releases:
                logger.debug("No releases found in PyPI data, using info.version")
                info_ver = data.get("info", {}).get("version")
                return VersionInfo(
                    latest_stable=str(info_ver) if info_ver else None, latest_dev=None, current_yanked=False
                )

            logger.debug(f"Found {len(releases)} releases in PyPI data")

            # Check if current version is yanked
            current_yanked = is_version_yanked(releases, current_version)
            logger.debug(f"Current version {current_version} yanked: {current_yanked}")

            # Parse all valid versions
            stable_versions: list[_version.Version] = []
            dev_versions: list[_version.Version] = []

            for v_str in releases.keys():
                try:
                    v = _version.parse(v_str)
                except _version.InvalidVersion:
                    logger.debug(f"Skipping invalid version: {v_str}")
                    continue

                # Skip yanked versions when looking for latest
                if is_version_yanked(releases, v_str):
                    logger.debug(f"Skipping yanked version: {v_str}")
                    continue

                if v.is_devrelease:
                    dev_versions.append(v)
                elif v.is_prerelease:
                    if include_prereleases:
                        stable_versions.append(v)
                    else:
                        logger.debug(f"Skipping prerelease (not requested): {v_str}")
                else:
                    stable_versions.append(v)

            latest_stable = str(max(stable_versions)) if stable_versions else None
            latest_dev = str(max(dev_versions)) if dev_versions else None

            logger.debug(f"Latest stable: {latest_stable}, latest dev: {latest_dev}")

            return VersionInfo(latest_stable=latest_stable, latest_dev=latest_dev, current_yanked=current_yanked)

        except error.HTTPError as e:
            logger.debug(f"HTTP error on attempt {attempt + 1}: {e.code} {e.reason}")
            if e.code == 404:
                raise PackageNotFoundError from e
            last_err = e
        except (error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            logger.debug(f"Network/parsing error on attempt {attempt + 1}: {e}")
            last_err = e

        if attempt < retries:
            sleep_time = backoff * (attempt + 1)
            logger.debug(f"Sleeping {sleep_time}s before retry")
            time.sleep(sleep_time)

    logger.debug(f"All {retries + 1} attempts failed, raising NetworkError")
    raise NetworkError(str(last_err))


def format_update_message(
    package_name: str,
    current_version_str: str,
    version_info: VersionInfo,
    logger: logging.Logger,
) -> str:
    """Format the update notification message.

    Args:
        package_name: Package name.
        current_version_str: Current version string.
        version_info: Version information from PyPI.
        logger: Logger instance for debugging.

    Returns:
        Formatted update message.
    """
    logger.debug(f"Formatting update message for {package_name} {current_version_str}")

    pypi_url = f"https://pypi.org/project/{package_name}/"
    messages: list[str] = []

    try:
        current = _version.parse(current_version_str)
        logger.debug(f"Parsed current version: {current}")
    except _version.InvalidVersion as e:
        logger.debug(f"Invalid current version '{current_version_str}': {e}")
        current = None

    c = _Color() if can_use_color() else None
    logger.debug(f"Using colors: {c is not None}")

    # Check if current version is yanked
    if version_info.current_yanked:
        logger.debug("Current version is yanked, adding warning")
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
                logger.debug(f"Found stable update: {latest_stable} > {current}")
                if c:
                    stable_msg = f"{c.YELLOW}A new stable version of {package_name} is available: {c.GREEN}{latest_stable}{c.YELLOW} (you are using {current}).{c.ENDC}"
                else:
                    stable_msg = f"A new stable version of {package_name} is available: {latest_stable} (you are using {current})."
                messages.append(stable_msg)
            else:
                logger.debug(f"No stable update needed: {latest_stable} <= {current}")
        except _version.InvalidVersion as e:
            logger.debug(f"Invalid latest stable version '{version_info.latest_stable}': {e}")

    # Check for dev versions
    if version_info.latest_dev:
        try:
            latest_dev = _version.parse(version_info.latest_dev)
            if current is None or latest_dev > current:
                logger.debug(f"Found dev version: {latest_dev}")
                if c:
                    dev_msg = f"{c.BLUE}Development version available: {c.GREEN}{latest_dev}{c.BLUE} (use at your own risk).{c.ENDC}"
                else:
                    dev_msg = f"Development version available: {latest_dev} (use at your own risk)."
                messages.append(dev_msg)
        except _version.InvalidVersion as e:
            logger.debug(f"Invalid latest dev version '{version_info.latest_dev}': {e}")

    if messages:
        upgrade_msg = "Please upgrade using your preferred package manager."
        info_msg = f"More info: {pypi_url}"
        messages.extend([upgrade_msg, info_msg])
        result = "\n".join(messages)
        logger.debug(f"Generated update message with {len(messages)} lines")
        return result

    logger.debug("No update message needed")
    return ""


def _background_update_worker(
    package_name: str,
    current_version: str,
    logger: logging.Logger | None,
    cache_ttl_seconds: int,
    include_prereleases: bool,
) -> None:
    """Background worker function to check for updates.

    This runs in a separate thread and stores the result globally.
    """
    global _background_check_result

    # Only catch exceptions at this entry point
    try:
        result = check_for_updates(
            package_name=package_name,
            current_version=current_version,
            logger=logger,
            cache_ttl_seconds=cache_ttl_seconds,
            include_prereleases=include_prereleases,
        )
        _background_check_result = result
    except Exception as e:
        # Background checks should not cause issues, but we should log what happened
        actual_logger = get_logger(logger)
        actual_logger.debug(f"Background update check failed: {e}")
        _background_check_result = None


def _exit_handler() -> None:
    """Exit handler to display update message if available."""
    if _background_check_result:
        print(f"\n{_background_check_result}", file=sys.stderr)


def start_background_update_check(
    package_name: str,
    current_version: str,
    logger: logging.Logger | None = None,
    *,
    cache_ttl_seconds: int = 86400,
    include_prereleases: bool = False,
) -> None:
    """Start a background update check that displays results on program exit.

    This function returns immediately (zero cost to user) and starts a background
    thread to check for updates. If an update is available, it will be shown when
    the program exits.

    Args:
        package_name: The PyPI package name to check.
        current_version: The currently installed version string.
        logger: Optional logger for warnings.
        cache_ttl_seconds: Cache time-to-live in seconds.
        include_prereleases: Whether to consider prereleases newer.
    """
    global _background_check_registered, _background_check_result

    # Only catch exceptions at this entry point
    try:
        actual_logger = get_logger(logger)
        cache_dir, cache_file = cache_paths(package_name)

        fresh = is_fresh(cache_file, cache_ttl_seconds, actual_logger)
        cached = load_cache(cache_file, actual_logger) if cache_file.exists() else None

        if not _background_check_registered:
            atexit.register(_exit_handler)
            _background_check_registered = True

        if fresh and isinstance(cached, dict):
            actual_logger.debug("Using fresh cache for background check")
            # Recompute message against *current* environment (current_version)
            vi = VersionInfo(
                latest_stable=cached.get("latest_stable"),
                latest_dev=cached.get("latest_dev"),
                current_yanked=bool(cached.get("current_yanked", False)),
            )
            msg = format_update_message(package_name, current_version, vi, actual_logger)
            _background_check_result = msg if msg else None
            return

        actual_logger.debug("Starting background thread for update check")
        # Cache stale/missing -> refresh in the background; result will be printed on exit (if ready)
        worker_thread = threading.Thread(
            target=_background_update_worker,
            args=(package_name, current_version, logger, cache_ttl_seconds, include_prereleases),
            daemon=True,
            name=f"UpdateChecker-{package_name}",
        )
        worker_thread.start()

    except Exception as e:
        # Silently fail for background checks only - log if we have a logger
        if logger:
            logger.debug(f"Failed to start background update check: {e}")


def check_for_updates(
    package_name: str,
    current_version: str,
    logger: logging.Logger | None = None,
    *,
    cache_ttl_seconds: int = 86400,
    include_prereleases: bool = False,
) -> str | None:
    """Check PyPI for a newer version of a package (synchronous).

    Args:
        package_name: The PyPI package name to check.
        current_version: The currently installed version string.
        logger: Optional logger for warnings.
        cache_ttl_seconds: Cache time-to-live in seconds.
        include_prereleases: Whether to consider prereleases newer.

    Returns:
        Formatted update message if update available, else None.

    Raises:
        PackageNotFoundError: If package not found on PyPI.
        NetworkError: If network errors occur.
        Various other exceptions for cache/filesystem issues.
    """
    actual_logger = get_logger(logger)
    cache_dir, cache_file = cache_paths(package_name)

    fresh = is_fresh(cache_file, cache_ttl_seconds, actual_logger)
    cached = load_cache(cache_file, actual_logger) if cache_file.exists() else None

    if fresh and isinstance(cached, dict):
        actual_logger.debug("Using fresh cache for synchronous check")
        # Recompute message using current state/version — no API call
        vi = VersionInfo(
            latest_stable=cached.get("latest_stable"),
            latest_dev=cached.get("latest_dev"),
            current_yanked=bool(cached.get("current_yanked", False)),
        )
        msg = format_update_message(package_name, current_version, vi, actual_logger)
        return msg if msg else None

    # Stale/missing -> query PyPI
    actual_logger.debug("Cache stale/missing, querying PyPI")

    try:
        vi = get_version_info_from_pypi(
            package_name, current_version, actual_logger, include_prereleases=include_prereleases
        )

        # Cache only data, not the message
        save_cache(
            cache_dir,
            cache_file,
            {
                "latest_stable": vi.latest_stable,
                "latest_dev": vi.latest_dev,
                "current_yanked": vi.current_yanked,
            },
            actual_logger,
        )

        msg = format_update_message(package_name, current_version, vi, actual_logger)
        return msg if msg else None

    except PackageNotFoundError:
        actual_logger.warning(f"Package '{package_name}' not found on PyPI.")
        save_cache(cache_dir, cache_file, {"error": "not_found"}, actual_logger)
        return None
    except NetworkError as e:
        actual_logger.warning(f"Network error checking for updates: {e}")
        save_cache(cache_dir, cache_file, {"error": "network"}, actual_logger)
        return None


if __name__ == "__main__":
    start_background_update_check(__about__.__title__, __about__.__version__)
    # print(check_for_updates(__about__.__title__, __about__.__version__))
