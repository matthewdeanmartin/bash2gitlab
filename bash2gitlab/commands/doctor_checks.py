from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal

import urllib3

from bash2gitlab.commands.precommit import HOOK_CONTENT, hook_hash, hook_path
from bash2gitlab.config import Config, config
from bash2gitlab.plugins import get_pm
from bash2gitlab.utils.pathlib_polyfills import is_relative_to
from bash2gitlab.utils.urllib3_helper import _HTTP
from bash2gitlab.utils.utils import short_path

logger = logging.getLogger(__name__)

# A reasonably large size that might cause issues with inlining.
# Corresponds to MAX_INLINE_LEN in compile_not_bash.py
LARGE_SCRIPT_THRESHOLD_BYTES = 1000 * 1024

PrecommitStatus = Literal["Installed", "Not Installed", "Foreign Hook", "Error"]


def list_active_plugins() -> list[str]:
    """
    Lists the names of all registered pluggy plugins, excluding the built-in default.
    """
    pm = get_pm()
    plugins = []
    for plugin in pm.get_plugins():
        name = getattr(plugin, "__name__", str(plugin))
        # Exclude the built-in default plugin from the user-facing list
        if name != "bash2gitlab.builtin_plugins.Defaults":
            plugins.append(name)
    return plugins


def check_directory_overlap(input_dir: Path, output_dir: Path) -> list[str]:
    """
    Checks if the input and output directories overlap, which could cause issues.
    """
    warnings = []
    try:
        if is_relative_to(output_dir.resolve(), input_dir.resolve()):
            warnings.append(f"Output directory '{short_path(output_dir)}' is inside the input directory.")
        if is_relative_to(input_dir.resolve(), output_dir.resolve()):
            warnings.append(f"Input directory '{short_path(input_dir)}' is inside the output directory.")
    except Exception as e:
        # This can happen if one of the paths doesn't exist, which is handled by another check.
        logger.debug(f"Could not check directory overlap: {e}")
    return warnings


def check_precommit_hook_status(repo_root: Path) -> tuple[PrecommitStatus, list[str]]:
    """
    Checks the status of the bash2gitlab pre-commit hook.
    """
    try:
        h_path = hook_path(repo_root)
        if not h_path.exists():
            return "Not Installed", []

        content = h_path.read_text(encoding="utf-8")
        if hook_hash(content) == hook_hash(HOOK_CONTENT):
            return "Installed", [f"Hook found at: {short_path(h_path)}"]
        else:
            return "Foreign Hook", [
                f"A non-bash2gitlab hook exists at: {short_path(h_path)}",
                "Run `install-precommit --force` to overwrite it.",
            ]
    except Exception as e:
        return "Error", [f"Could not check git hooks directory: {e}"]


def check_map_source_paths_exist() -> list[str]:
    """
    Verifies that all source directories specified in the [tool.bash2gitlab.map]
    configuration exist.
    """
    warnings = []
    deployment_map = config.map_folders
    if not deployment_map:
        return []

    for source_base in deployment_map.keys():
        source_path = Path(source_base)
        if not source_path.is_dir():
            warnings.append(f"Source directory from 'map' config does not exist: {short_path(source_path)}")
    return warnings


# --- Refactor: GitLab lint config validity using the same PoolManager --------
def check_lint_config_validity(config: Config) -> list[str]:
    """
    Validates the GitLab URL, project ID, and token for the lint command.

    Returns a list of human-readable problems (empty list = OK).
    """
    # BUG: This is not how to reference properties on config.

    gitlab_url = config.lint_gitlab_url
    project_id = config.lint_project_id
    token = os.environ.get("GITLAB_PRIVATE_TOKEN")  # Tokens are often in env

    if not project_id or not gitlab_url:
        return ["Linting with `project_id` is recommended for better accuracy but is not configured."]

    if not gitlab_url.lower().startswith("http"):
        return [f"Invalid GitLab URL: {gitlab_url!r}"]

    api_url = f"{gitlab_url.rstrip('/')}/api/v4/projects/{project_id}"

    # Per-call headers merge with client defaults
    headers = {
        "User-Agent": "bash2gitlab-doctor/1.0",
        "Accept": "application/json",
    }
    if token:
        headers["PRIVATE-TOKEN"] = token

    try:
        # Short, explicit timeouts; tune for your environment
        with _HTTP.request(
            "GET",
            api_url,
            headers=headers,
            timeout=urllib3.Timeout(connect=2.0, read=3.0),
            preload_content=False,
            decode_content=True,
        ) as r:
            status = r.status
            # Drain body for connection reuse even if we don't need it
            _ = r.read(0)

        if status == 200:
            return []
        if status == 401:
            return ["Authentication failed (401 Unauthorized). Check your token."]
        if status == 404:
            return [f"Project with ID '{project_id}' not found at {gitlab_url}."]
        return [f"GitLab API returned status {status} for project {project_id}."]

    except urllib3.exceptions.SSLError as e:
        return [f"TLS/SSL error while connecting to '{gitlab_url}': {e}"]
    except (urllib3.exceptions.ReadTimeoutError, urllib3.exceptions.ConnectTimeoutError) as e:
        return [f"Connection to GitLab timed out: {e}"]
    except urllib3.exceptions.MaxRetryError as e:
        return [f"Could not connect to GitLab instance at '{gitlab_url}': {e}"]
    except urllib3.exceptions.HTTPError as e:
        return [f"HTTP error while contacting GitLab: {e}"]
    except Exception as e:  # keep a catch-all to mirror original behavior
        return [f"An unexpected error occurred while checking GitLab connectivity: {e}"]


# def check_lint_config_validity() -> list[str]:
#     """
#     Validates the GitLab URL, project ID, and token for the lint command.
#     """
#     gitlab_url = config.lint_gitlab_url
#     project_id = config.lint_project_id
#     token = os.environ.get("GITLAB_PRIVATE_TOKEN")  # Tokens are often in env
#
#     if not project_id or not gitlab_url:
#         return ["Linting with `project_id` is recommended for better accuracy but is not configured."]
#
#     api_url = f"{gitlab_url.rstrip('/')}/api/v4/projects/{project_id}"
#     headers = {"User-Agent": "bash2gitlab-doctor/1.0"}
#     if token:
#         headers["PRIVATE-TOKEN"] = token
#
#     req = urllib.request.Request(api_url, headers=headers)
#     try:
#         with urllib.request.urlopen(req, timeout=5) as response:  # nosec
#             if response.status == 200:
#                 return []  # Success
#             else:
#                 return [f"GitLab API returned status {response.status} for project {project_id}."]
#     except urllib.error.HTTPError as e:
#         if e.code == 404:
#             return [f"Project with ID '{project_id}' not found at {gitlab_url}."]
#         if e.code == 401:
#             return ["Authentication failed (401 Unauthorized). Check your token."]
#         return [f"GitLab API request failed with HTTP status {e.code}."]
#     except (urllib.error.URLError, TimeoutError) as e:
#         return [f"Could not connect to GitLab instance at '{gitlab_url}': {e}"]
#     except Exception as e:
#         return [f"An unexpected error occurred while checking GitLab connectivity: {e}"]


def check_for_large_scripts(input_dir: Path) -> list[str]:
    """
    Scans for script files that are unusually large, which might cause performance
    issues or hit YAML size limits when inlined.
    """
    warnings = []
    if not input_dir.is_dir():
        return []

    script_patterns = ["*.sh", "*.bash", "*.py", "*.rb", "*.js", "*.ps1"]
    for pattern in script_patterns:
        for script_file in input_dir.rglob(pattern):
            try:
                size = script_file.stat().st_size
                if size > LARGE_SCRIPT_THRESHOLD_BYTES:
                    warnings.append(
                        f"Large script file found: {short_path(script_file)} ({size / 1024:.1f} KB). "
                        f"This may impact performance or YAML readability when inlined."
                    )
            except FileNotFoundError:
                # File might be a broken symlink, ignore.
                continue
    return warnings
