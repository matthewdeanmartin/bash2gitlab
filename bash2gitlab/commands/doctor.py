from __future__ import annotations

import logging
import re
import shutil
import subprocess  # nosec
from pathlib import Path

from bash2gitlab.commands.clean_all import list_stray_files as list_stray_output_files
from bash2gitlab.commands.graph_all import find_script_references_in_node
from bash2gitlab.config import config
from bash2gitlab.utils.terminal_colors import Colors
from bash2gitlab.utils.yaml_factory import get_yaml

logger = logging.getLogger(__name__)

__all__ = ["run_doctor"]


def check(message: str, success: bool) -> bool:
    """Prints a formatted check message and returns the success status."""
    status = f"{Colors.OKGREEN}✔ OK{Colors.ENDC}" if success else f"{Colors.FAIL}✖ FAILED{Colors.ENDC}"
    print(f"  [{status}] {message}")
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
        # Get the first line of output and strip whitespace
        return result.stdout.splitlines()[0].strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.debug(f"Could not get version for {cmd}: {e}")
        return f"{Colors.FAIL}Error checking version{Colors.ENDC}"


def find_unreferenced_source_files(uncompiled_path: Path) -> set[Path]:
    """Finds script files in the source directory that are not referenced by any YAML."""
    root_path = uncompiled_path.resolve()
    all_scripts = set(root_path.rglob("*.sh")) | set(root_path.rglob("*.py"))
    referenced_scripts: set[Path] = set()
    # processed_scripts: set[Path] = set()  # To avoid cycles in script parsing

    yaml_parser = get_yaml()
    template_files = list(root_path.rglob("*.yml")) + list(root_path.rglob("*.yaml"))

    # Build a set of all referenced scripts by adapting graph logic
    for yaml_path in template_files:
        try:
            content = yaml_path.read_text("utf-8")
            yaml_data = yaml_parser.load(content)
            if yaml_data:
                # Dummy graph, we only care about the side effect on referenced_scripts
                dummy_graph: dict[Path, set[Path]] = {}
                find_script_references_in_node(
                    yaml_data, yaml_path, root_path, dummy_graph, processed_scripts=referenced_scripts
                )

        except Exception:  # nosec
            # Ignore parsing errors, focus is on finding valid references
            pass

    # The above only adds the top-level scripts. Now, find sourced scripts.
    scripts_to_scan = list(referenced_scripts)
    scanned_for_source: set[Path] = set()

    while scripts_to_scan:
        script = scripts_to_scan.pop(0)
        if script in scanned_for_source or not script.is_file():
            continue
        scanned_for_source.add(script)
        try:
            content = script.read_text("utf-8")
            for line in content.splitlines():
                match = re.search(r"^\s*(?:source|\.)\s+([\w./\\-]+)", line)
                if match:
                    sourced_path = (script.parent / match.group(1)).resolve()
                    if sourced_path.is_file() and sourced_path not in referenced_scripts:
                        referenced_scripts.add(sourced_path)
                        scripts_to_scan.append(sourced_path)

        except Exception:  # nosec
            pass

    return all_scripts - referenced_scripts


def run_doctor() -> int:
    """Runs a series of health checks on the project and environment."""
    print(f"{Colors.BOLD}🩺 Running bash2gitlab doctor...{Colors.ENDC}\n")
    issues_found = 0

    # --- Configuration Checks ---
    print(f"{Colors.BOLD}Configuration:{Colors.ENDC}")
    input_dir_str = config.input_dir
    output_dir_str = config.output_dir

    if check("Input directory is configured", bool(input_dir_str)):
        input_dir = Path(input_dir_str or "")
        if not check(f"Input directory exists: '{input_dir}'", input_dir.is_dir()):
            issues_found += 1
    else:
        issues_found += 1

    if check("Output directory is configured", bool(output_dir_str)):
        output_dir = Path(output_dir_str or "")
        if not check(f"Output directory exists: '{output_dir}'", output_dir.is_dir()):
            print(f"  {Colors.WARNING}  -> Note: This is not an error if you haven't compiled yet.{Colors.ENDC}")
    else:
        issues_found += 1

    # --- External Dependencies ---
    print(f"\n{Colors.BOLD}External Dependencies:{Colors.ENDC}")
    print(f"  - Bash version: {get_command_version('bash')}")
    print(f"  - Git version:  {get_command_version('git')}")
    print(f"  - PowerShell:   {get_command_version('pwsh')}")

    # --- Project Health ---
    print(f"\n{Colors.BOLD}Project Health:{Colors.ENDC}")
    if input_dir_str and Path(input_dir_str).is_dir():
        unreferenced_files = find_unreferenced_source_files(Path(input_dir_str))
        if unreferenced_files:
            issues_found += 1
            check("No unreferenced script files in source directory", False)
            for f in sorted(unreferenced_files):
                print(f"    {Colors.WARNING}  -> Stray source file: {f.relative_to(input_dir_str)}{Colors.ENDC}")
        else:
            check("No unreferenced script files in source directory", True)

    if output_dir_str and Path(output_dir_str).is_dir():
        stray_files = list_stray_output_files(Path(output_dir_str))
        if stray_files:
            issues_found += 1
            check("No unhashed/stray files in output directory", False)
            for f in sorted(stray_files):
                print(f"    {Colors.WARNING}  -> Stray output file: {f.relative_to(output_dir_str)}{Colors.ENDC}")
        else:
            check("No unhashed/stray files in output directory", True)

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
