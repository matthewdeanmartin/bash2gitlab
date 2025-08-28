from __future__ import annotations

import contextlib
import io
import logging
import re
import shutil
import subprocess  # nosec
from pathlib import Path

from bash2gitlab.commands.detect_drift import run_detect_drift
from bash2gitlab.commands.doctor_checks import (
    check_directory_overlap,
    check_for_large_scripts,
    check_lint_config_validity,
    check_map_source_paths_exist,
    check_precommit_hook_status,
    list_active_plugins,
)
from bash2gitlab.commands.input_change_detector import needs_compilation
from bash2gitlab.commands.map_commit import run_commit_map
from bash2gitlab.config import config
from bash2gitlab.utils.terminal_colors import Colors
from bash2gitlab.utils.utils import short_path
from bash2gitlab.utils.validate_pipeline import GitLabCIValidator

logger = logging.getLogger(__name__)

__all__ = ["run_doctor"]


def check(message: str, success: bool, details: list[str] | None = None) -> bool:
    """Prints a check message with a status and optional details."""
    status = f"{Colors.OKGREEN}✔ OK{Colors.ENDC}" if success else f"{Colors.FAIL}✖ FAILED{Colors.ENDC}"
    print(f"  [{status}] {message}")
    if details:
        for detail in details:
            print(f"    {Colors.WARNING}  -> {detail}{Colors.ENDC}")
    return success


def get_command_version(cmd: str) -> str:
    """Gets the version of a command-line tool."""
    if not shutil.which(cmd):
        return f"{Colors.WARNING}not found{Colors.ENDC}"
    try:
        result = subprocess.run(  # nosec
            [cmd, "--version"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.splitlines()[0].strip()
    except Exception as e:
        logger.debug(f"Could not get version for {cmd}: {e}")
        return f"{Colors.FAIL}Error checking version{Colors.ENDC}"


def find_unreferenced_scripts(input_path: Path) -> list[Path]:
    """
    Finds script files in the input directory that do not appear to be referenced
    by any YAML files.
    """
    if not input_path.is_dir():
        return []

    all_yaml_content = ""
    yaml_files = list(input_path.rglob("*.yml")) + list(input_path.rglob("*.yaml"))
    for yaml_file in yaml_files:
        all_yaml_content += yaml_file.read_text(encoding="utf-8")

    unreferenced = []
    script_patterns = ["*.sh", "*.bash", "*.py", "*.rb", "*.js", "*.ps1"]
    for pattern in script_patterns:
        for script_file in input_path.rglob(pattern):
            if script_file.name not in all_yaml_content:
                unreferenced.append(script_file)

    return unreferenced


def check_yaml_validity(path: Path) -> list[str]:
    """Validates all YAML files in a directory against the GitLab CI schema."""
    if not path.is_dir():
        return [f"Directory not found: {short_path(path)}"]

    validator = GitLabCIValidator()
    failures = []
    yaml_files = list(path.rglob("*.yml")) + list(path.rglob("*.yaml"))

    if not yaml_files:
        return []

    for yaml_file in yaml_files:
        content = yaml_file.read_text("utf-8")
        is_valid, errors = validator.validate_ci_config(content)
        if not is_valid:
            failures.append(f"Invalid schema in {short_path(yaml_file)}: {errors[0]}")
    return failures


def check_map_commit_status() -> list[str]:
    """Performs a dry-run of 'commit-map' to find uncommitted changes."""
    if not config.map_folders:
        return []

    output_capture = io.StringIO()
    with contextlib.redirect_stdout(output_capture):
        run_commit_map(config.map_folders, dry_run=True, force=False)

    output = output_capture.getvalue()
    uncommitted_changes = []
    for line in output.splitlines():
        if "Creating:" in line or "Updating:" in line:
            match = re.search(r"(Creating|Updating): '([^']*)'", line)
            if match:
                uncommitted_changes.append(
                    f"Uncommitted change in deployed file corresponding to {short_path(Path(match.group(2)))}"
                )

    return uncommitted_changes


def run_doctor() -> int:
    """Runs a series of health checks on the project and environment."""
    print(f"{Colors.BOLD}🩺 Running bash2gitlab doctor...{Colors.ENDC}\n")
    issues_found = 0

    def flag_issue():
        nonlocal issues_found
        issues_found += 1

    # --- Configuration Checks ---
    print(f"{Colors.BOLD}Configuration:{Colors.ENDC}")
    input_dir_str = config.input_dir
    output_dir_str = config.output_dir

    if not check("Input directory is configured (`input_dir`)", bool(input_dir_str)):
        flag_issue()
    if not check("Output directory is configured (`output_dir`)", bool(output_dir_str)):
        flag_issue()

    if issues_found > 0:
        print(f"\n{Colors.FAIL}Core configuration missing. Halting further checks.{Colors.ENDC}")
        return 1

    input_dir = Path(input_dir_str or "")
    output_dir = Path(output_dir_str or "")

    if not check(f"Input directory exists: '{short_path(input_dir)}'", input_dir.is_dir()):
        flag_issue()
    if not check(f"Output directory exists: '{short_path(output_dir)}'", output_dir.is_dir()):
        print(f"  {Colors.WARNING}  -> Note: This is normal if you haven't compiled yet.{Colors.ENDC}")

    overlap_warnings = check_directory_overlap(input_dir, output_dir)
    if not check("Input and output directories do not overlap", not overlap_warnings, overlap_warnings):
        flag_issue()

    map_source_errors = check_map_source_paths_exist()
    if not check("All 'map' source directories exist", not map_source_errors, map_source_errors):
        flag_issue()

    # --- Integrity and State Checks ---
    print(f"\n{Colors.BOLD}Project State & Integrity:{Colors.ENDC}")

    if needs_compilation(input_dir):
        check(
            "Source files are in sync with compiled output",
            False,
            ["Uncompiled changes detected. Run `bash2gitlab compile`."],
        )
        flag_issue()
    else:
        check("Source files are in sync with compiled output", True)

    drift_code = run_detect_drift(output_dir)
    if not check("No manual edits (drift) detected in output folder", drift_code == 0):
        flag_issue()

    uncommitted_map_changes = check_map_commit_status()
    if not check("No uncommitted changes in mapped directories", not uncommitted_map_changes, uncommitted_map_changes):
        flag_issue()

    # --- Sanity Checks ---
    print(f"\n{Colors.BOLD}Sanity Checks:{Colors.ENDC}")

    unreferenced = find_unreferenced_scripts(input_dir)
    details = [f"Script not referenced in any YAML: {short_path(p)}" for p in unreferenced]
    if not check("All script files appear to be referenced", not unreferenced, details):
        flag_issue()

    large_script_warnings = check_for_large_scripts(input_dir)
    if not check("No excessively large script files found", not large_script_warnings, large_script_warnings):
        # This is a warning, not a failure
        pass

    input_yaml_errors = check_yaml_validity(input_dir)
    if not check(
        "Input directory YAML files are valid against GitLab schema", not input_yaml_errors, input_yaml_errors
    ):
        flag_issue()

    output_yaml_errors = check_yaml_validity(output_dir)
    if not check(
        "Output directory YAML files are valid against GitLab schema", not output_yaml_errors, output_yaml_errors
    ):
        flag_issue()

    # --- Environment Checks ---
    print(f"\n{Colors.BOLD}Environment & Tooling:{Colors.ENDC}")

    precommit_status, precommit_details = check_precommit_hook_status(Path.cwd())
    if not check(
        f"Pre-commit hook status: {precommit_status}",
        precommit_status in ["Installed", "Not Installed"],
        precommit_details,
    ):
        flag_issue()

    lint_warnings = check_lint_config_validity(config)
    if not check("Lint configuration is valid and reachable", not lint_warnings, lint_warnings):
        flag_issue()

    plugins = list_active_plugins()
    check("Checking for active plugins", True, plugins if plugins else ["No third-party plugins found."])

    print(f"  - Bash version: {get_command_version('bash')}")
    print(f"  - Git version:  {get_command_version('git')}")
    print(f"  - PowerShell:   {get_command_version('pwsh')}")

    # --- Summary ---
    print("-" * 40)
    if issues_found == 0:
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}✅ All checks passed. Your project looks healthy!{Colors.ENDC}")
        return 0
    else:
        print(
            f"\n{Colors.FAIL}{Colors.BOLD}✖ Doctor found {issues_found} issue(s). Please review the output above.{Colors.ENDC}"
        )
        return 1


if __name__ == "__main__":
    run_doctor()
