"""
Handles CLI interactions for bash2gitlab

usage: bash2gitlab [-h] [--version] {compile,shred,detect-drift,copy2local,init,map-deploy,commit-map} ...

A tool for making development of centralized yaml gitlab templates more pleasant.

positional arguments:
  {compile,shred,detect-drift,copy2local,init,map-deploy,commit-map}
    compile             Compile an uncompiled directory into a standard GitLab CI structure.
    shred               Shred a GitLab CI file, extracting inline scripts into separate .sh files.
    detect-drift        Detect if generated files have been edited and display what the edits are.
    copy2local          Copy folder(s) from a repo to local, for testing bash in the dependent repo
    init                Initialize a new bash2gitlab project and config file.
    map-deploy          Deploy files from source to target directories based on a mapping in pyproject.toml.
    commit-map          Copy changed files from deployed directories back to their source locations based on a mapping in pyproject.toml.

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
"""

from __future__ import annotations

import argparse
import logging
import logging.config
import sys
from pathlib import Path

import argcomplete

from bash2gitlab import __about__
from bash2gitlab import __doc__ as root_doc
from bash2gitlab.commands.clone2local import clone_repository_ssh, fetch_repository_archive
from bash2gitlab.commands.commit_map import run_commit_map
from bash2gitlab.commands.compile_all import run_compile_all
from bash2gitlab.commands.detect_drift import run_detect_drift
from bash2gitlab.commands.init_project import create_config_file, prompt_for_config
from bash2gitlab.commands.map_deploy import get_deployment_map, run_map_deploy
from bash2gitlab.commands.shred_all import run_shred_gitlab
from bash2gitlab.config import config
from bash2gitlab.utils.cli_suggestions import SmartParser
from bash2gitlab.utils.logging_config import generate_config
from bash2gitlab.utils.update_checker import check_for_updates
from bash2gitlab.watch_files import start_watch

logger = logging.getLogger(__name__)


def init_handler(args: argparse.Namespace) -> int:
    """Handles the `init` command logic."""
    logger.info("Starting interactive project initializer...")
    base_path = Path(args.directory).resolve()

    if not base_path.exists():
        base_path.mkdir(parents=True)
        logger.info(f"Created project directory: {base_path}")
    elif (base_path / "bash2gitlab.toml").exists():
        logger.error(f"A 'bash2gitlab.toml' file already exists in '{base_path}'. Aborting.")
        return 1

    try:
        user_config = prompt_for_config()
        create_config_file(base_path, user_config, args.dry_run)
    except (KeyboardInterrupt, EOFError):
        logger.warning("\nInitialization cancelled by user.")
        return 1
    return 0


def clone2local_handler(args: argparse.Namespace) -> int:
    """
    Argparse handler for the clone2local command.

    This handler remains compatible with the new archive-based fetch function.
    """
    # This function now calls the new implementation, preserving the call stack.
    dry_run = bool(args.dry_run)

    if str(args.repo_url).startswith("ssh"):
        clone_repository_ssh(args.repo_url, args.branch, args.source_dir, args.copy_dir, dry_run)
    else:
        fetch_repository_archive(args.repo_url, args.branch, args.source_dir, args.copy_dir, dry_run)
    return 0


def compile_handler(args: argparse.Namespace) -> int:
    """Handler for the 'compile' command."""
    logger.info("Starting bash2gitlab compiler...")

    # Resolve paths, using sensible defaults if optional paths are not provided
    in_dir = Path(args.input_dir).resolve()
    out_dir = Path(args.output_dir).resolve()
    dry_run = bool(args.dry_run)
    parallelism = args.parallelism

    if args.watch:
        start_watch(
            uncompiled_path=in_dir,
            output_path=out_dir,
            dry_run=dry_run,
            parallelism=parallelism,
        )
        return 0

    try:
        run_compile_all(
            uncompiled_path=in_dir,
            output_path=out_dir,
            dry_run=dry_run,
            parallelism=parallelism,
        )

        logger.info("✅ GitLab CI processing complete.")

    except FileNotFoundError as e:
        logger.error(f"❌ An error occurred: {e}")
        return 10
    except (RuntimeError, ValueError) as e:
        logger.error(f"❌ An error occurred: {e}")
        return 1
    return 0


def drift_handler(args: argparse.Namespace) -> int:
    run_detect_drift(Path(args.out))
    return 0


def shred_handler(args: argparse.Namespace) -> int:
    """Handler for the 'shred' command."""
    logger.info("Starting bash2gitlab shredder...")

    # Resolve the file and directory paths
    in_file = Path(args.input_file).resolve()
    out_file = Path(args.output_file).resolve()

    dry_run = bool(args.dry_run)

    try:
        jobs, scripts = run_shred_gitlab(input_yaml_path=in_file, output_yaml_path=out_file, dry_run=dry_run)

        if dry_run:
            logger.info(f"DRY RUN: Would have processed {jobs} jobs and created {scripts} script(s).")
        else:
            logger.info(f"✅ Successfully processed {jobs} jobs and created {scripts} script(s).")
            logger.info(f"Modified YAML written to: {out_file}")
        return 0
    except FileNotFoundError as e:
        logger.error(f"❌ An error occurred: {e}")
        return 10


def commit_map_handler(args: argparse.Namespace) -> int:
    pyproject_path = Path(args.pyproject_path)
    try:
        mapping = get_deployment_map(pyproject_path)
    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        return 10
    except KeyError as ke:
        logger.error(f"❌ {ke}")
        return 11

    run_commit_map(mapping, dry_run=args.dry_run, force=args.force)
    return 0


def map_deploy_handler(args: argparse.Namespace) -> int:

    pyproject_path = Path(args.pyproject_path)
    try:
        mapping = get_deployment_map(pyproject_path)
    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        return 10
    except KeyError as ke:
        logger.error(f"❌ {ke}")
        return 11

    run_map_deploy(mapping, dry_run=args.dry_run, force=args.force)
    return 0


def add_common_arguments(parser):
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the command without filesystem changes.",
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose (DEBUG) logging output.")
    parser.add_argument("-q", "--quiet", action="store_true", help="Disable output.")


def main() -> int:
    """Main CLI entry point."""
    check_for_updates(__about__.__title__, __about__.__version__)

    parser = SmartParser(
        prog=__about__.__title__,
        description=root_doc,
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {__about__.__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- Compile Command ---
    compile_parser = subparsers.add_parser(
        "compile", help="Compile an uncompiled directory into a standard GitLab CI structure."
    )
    compile_parser.add_argument(
        "--in",
        dest="input_dir",
        required=not bool(config.input_dir),
        help="Input directory containing the uncompiled `.gitlab-ci.yml` and other sources.",
    )
    compile_parser.add_argument(
        "--out",
        dest="output_dir",
        required=not bool(config.output_dir),
        help="Output directory for the compiled GitLab CI files.",
    )
    compile_parser.add_argument(
        "--parallelism",
        type=int,
        default=config.parallelism,
        help="Number of files to compile in parallel (default: CPU count).",
    )

    compile_parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch source directories and auto-recompile on changes.",
    )
    add_common_arguments(compile_parser)
    compile_parser.set_defaults(func=compile_handler)

    # --- Shred Command ---
    shred_parser = subparsers.add_parser(
        "shred", help="Shred a GitLab CI file, extracting inline scripts into separate .sh files."
    )
    shred_parser.add_argument(
        "--in",
        dest="input_file",
        help="Input GitLab CI file to shred (e.g., .gitlab-ci.yml).",
    )
    shred_parser.add_argument(
        "--out",
        dest="output_file",
        help="Output path for the modified GitLab CI file.",
    )
    add_common_arguments(shred_parser)
    shred_parser.set_defaults(func=shred_handler)

    # detect drift command
    # --- Shred Command ---
    detect_drift_parser = subparsers.add_parser(
        "detect-drift", help="Detect if generated files have been edited and display what the edits are."
    )
    detect_drift_parser.add_argument(
        "--out",
        dest="out",
        help="Output path where generated files are.",
    )
    add_common_arguments(detect_drift_parser)
    detect_drift_parser.set_defaults(func=drift_handler)

    # --- copy2local Command ---
    clone_parser = subparsers.add_parser(
        "copy2local",
        help="Copy folder(s) from a repo to local, for testing bash in the dependent repo",
    )
    clone_parser.add_argument(
        "--repo-url",
        required=True,
        help="Repository URL to copy.",
    )
    clone_parser.add_argument(
        "--branch",
        required=True,
        help="Branch to copy.",
    )
    clone_parser.add_argument(
        "--copy-dir",
        required=True,
        help="Destination directory for the copy.",
    )
    clone_parser.add_argument(
        "--source-dir",
        required=True,
        help="Directory to include in the copy.",
    )
    add_common_arguments(clone_parser)
    clone_parser.set_defaults(func=clone2local_handler)

    # Init Parser
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a new bash2gitlab project and config file.",
    )
    init_parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="The directory to initialize the project in. Defaults to the current directory.",
    )
    add_common_arguments(init_parser)
    init_parser.set_defaults(func=init_handler)

    # --- map-deploy Command ---
    map_deploy_parser = subparsers.add_parser(
        "map-deploy",
        help="Deploy files from source to target directories based on a mapping in pyproject.toml.",
    )
    map_deploy_parser.add_argument(
        "--pyproject",
        dest="pyproject_path",
        default="pyproject.toml",
        help="Path to the pyproject.toml file containing the [tool.bash2gitlab.map] section.",
    )
    map_deploy_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite target files even if they have been modified since the last deployment.",
    )
    add_common_arguments(map_deploy_parser)
    map_deploy_parser.set_defaults(func=map_deploy_handler)

    # --- commit-map Command ---
    commit_map_parser = subparsers.add_parser(
        "commit-map",
        help=(
            "Copy changed files from deployed directories back to their source"
            " locations based on a mapping in pyproject.toml."
        ),
    )
    commit_map_parser.add_argument(
        "--pyproject",
        dest="pyproject_path",
        default="pyproject.toml",
        help="Path to the pyproject.toml file containing the [tool.bash2gitlab.map] section.",
    )
    commit_map_parser.add_argument(
        "--force",
        action="store_true",
        help=("Overwrite source files even if they have been modified since the last " "deployment."),
    )
    add_common_arguments(commit_map_parser)

    commit_map_parser.set_defaults(func=commit_map_handler)

    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    # --- Configuration Precedence: CLI > ENV > TOML ---
    # Merge string/path arguments
    if args.command == "compile":
        args.input_dir = args.input_dir or config.input_dir
        args.output_dir = args.output_dir or config.output_dir
        # Validate required arguments after merging
        if not args.input_dir:
            compile_parser.error("argument --in is required")
        if not args.output_dir:
            compile_parser.error("argument --out is required")
    elif args.command == "shred":
        args.input_file = args.input_file or config.input_file
        args.output_file = args.output_file or config.output_file
        # Validate required arguments after merging
        if not args.input_file:
            shred_parser.error("argument --in is required")
        if not args.output_file:
            shred_parser.error("argument --out is required")

    # Merge boolean flags
    args.verbose = args.verbose or config.verbose or False
    args.quiet = args.quiet or config.quiet or False
    if hasattr(args, "dry_run"):
        args.dry_run = args.dry_run or config.dry_run or False

    # --- Setup Logging ---
    if args.verbose:
        log_level = "DEBUG"
    elif args.quiet:
        log_level = "CRITICAL"
    else:
        log_level = "INFO"
    logging.config.dictConfig(generate_config(level=log_level))

    # Execute the appropriate handler
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
