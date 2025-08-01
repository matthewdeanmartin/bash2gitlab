"""

❯ bash2gitlab compile --help
usage: bash2gitlab compile [-h] --in INPUT_DIR --out OUTPUT_DIR [--scripts SCRIPTS_DIR] [--templates-in TEMPLATES_IN]
                           [--templates-out TEMPLATES_OUT] [--format] [-v]

options:
  -h, --help            show this help message and exit
  --in INPUT_DIR        Input directory containing the uncompiled `.gitlab-ci.yml` and other sources.
  --out OUTPUT_DIR      Output directory for the compiled GitLab CI files.
  --scripts SCRIPTS_DIR
                        Directory containing bash scripts to inline. (Default: <in>)
  --templates-in TEMPLATES_IN
                        Input directory for CI templates. (Default: <in>)
  --templates-out TEMPLATES_OUT
                        Output directory for compiled CI templates. (Default: <out>)
  --format              Format all output YAML files using 'yamlfix'. Requires yamlfix to be installed.
  -v, --verbose         Enable verbose (DEBUG) logging output.

"""

from __future__ import annotations

import argparse
import logging
import logging.config
import sys
from pathlib import Path

from bash2gitlab import __about__
from bash2gitlab import __doc__ as root_doc
from bash2gitlab.clone2local import clone2local_handler
from bash2gitlab.compile_all import process_uncompiled_directory
from bash2gitlab.config import config
from bash2gitlab.init_project import init_handler
from bash2gitlab.logging_config import generate_config
from bash2gitlab.shred_all import shred_gitlab_ci
from bash2gitlab.tool_yamlfix import run_formatter
from bash2gitlab.watch_files import start_watch

logger = logging.getLogger(__name__)


def compile_handler(args: argparse.Namespace):
    """Handler for the 'compile' command."""
    logger.info("Starting bash2gitlab compiler...")

    # Resolve paths, using sensible defaults if optional paths are not provided
    in_dir = Path(args.input_dir).resolve()
    out_dir = Path(args.output_dir).resolve()
    scripts_dir = Path(args.scripts_dir).resolve() if args.scripts_dir else in_dir
    templates_in_dir = Path(args.templates_in).resolve() if args.templates_in else in_dir
    templates_out_dir = Path(args.templates_out).resolve() if args.templates_out else out_dir
    dry_run = bool(args.dry_run)

    if args.watch:
        start_watch(
            uncompiled_path=in_dir,
            output_path=out_dir,
            scripts_path=scripts_dir,
            templates_dir=templates_in_dir,
            output_templates_dir=templates_out_dir,
            dry_run=dry_run,
            format_output=args.format,
        )
        return

    try:
        process_uncompiled_directory(
            uncompiled_path=in_dir,
            output_path=out_dir,
            scripts_path=scripts_dir,
            templates_dir=templates_in_dir,
            output_templates_dir=templates_out_dir,
            dry_run=dry_run,
        )

        if args.format:
            run_formatter(out_dir, templates_out_dir)

        logger.info("✅ GitLab CI processing complete.")

    except (FileNotFoundError, RuntimeError, ValueError) as e:
        logger.error(f"❌ An error occurred: {e}")
        sys.exit(1)


def shred_handler(args: argparse.Namespace):
    """Handler for the 'shred' command."""
    logger.info("Starting bash2gitlab shredder...")

    # Resolve the file and directory paths
    in_file = Path(args.input_file).resolve()
    out_file = Path(args.output_file).resolve()
    if args.scripts_out:
        scripts_out_dir = Path(args.scripts_out).resolve()
    else:
        if out_file.is_file():
            scripts_out_dir = out_file.parent
        else:
            scripts_out_dir = out_file
    dry_run = bool(args.dry_run)

    try:
        jobs, scripts = shred_gitlab_ci(
            input_yaml_path=in_file,
            output_yaml_path=out_file,
            scripts_output_path=scripts_out_dir,
            dry_run=dry_run,
        )

        if dry_run:
            logger.info(f"DRY RUN: Would have processed {jobs} jobs and created {scripts} script(s).")
        else:
            logger.info(f"✅ Successfully processed {jobs} jobs and created {scripts} script(s).")
            logger.info(f"Modified YAML written to: {out_file}")
            logger.info(f"Scripts shredded to: {scripts_out_dir}")

    except FileNotFoundError as e:
        logger.error(f"❌ An error occurred: {e}")
        sys.exit(1)


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
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
        "--scripts",
        dest="scripts_dir",
        help="Directory containing bash scripts to inline. (Default: <in>)",
    )
    compile_parser.add_argument(
        "--templates-in",
        help="Input directory for CI templates. (Default: <in>)",
    )
    compile_parser.add_argument(
        "--templates-out",
        help="Output directory for compiled CI templates. (Default: <out>)",
    )
    compile_parser.add_argument(
        "--format",
        action="store_true",
        help="Format all output YAML files using 'yamlfix'. Requires yamlfix to be installed.",
    )
    compile_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the compilation process without writing any files.",
    )
    compile_parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose (DEBUG) logging output.")
    compile_parser.add_argument("-q", "--quiet", action="store_true", help="Disable output.")
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
    shred_parser.add_argument(
        "--scripts-out",
        help="Output directory to save the shredded .sh script files.",
    )
    shred_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the shredding process without writing any files.",
    )
    compile_parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch source directories and auto-recompile on changes.",
    )
    shred_parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose (DEBUG) logging output.")
    shred_parser.add_argument("-q", "--quiet", action="store_true", help="Disable output.")
    shred_parser.set_defaults(func=shred_handler)

    # --- clone2local Command ---
    clone_parser = subparsers.add_parser(
        "clone2local", help="Clone a repository using sparse checkout.",
    )
    clone_parser.add_argument(
        "--repo-url", required=True, help="Repository URL to clone.",
    )
    clone_parser.add_argument(
        "--clone-dir", required=True, help="Destination directory for the clone.",
    )
    clone_parser.add_argument(
        "--sparse-dirs",
        nargs="+",
        required=True,
        help="Directories to include in the sparse checkout.",
    )
    clone_parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose (DEBUG) logging output.")
    clone_parser.add_argument("-q", "--quiet", action="store_true", help="Disable output.")
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
    init_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the initialization process without creating the config file.",
    )
    init_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging output.",
    )
    init_parser.add_argument("-q", "--quiet", action="store_true", help="Disable output.")
    init_parser.set_defaults(func=init_handler)

    args = parser.parse_args()

    # --- Configuration Precedence: CLI > ENV > TOML ---
    # Merge string/path arguments
    if args.command == "compile":
        args.input_dir = args.input_dir or config.input_dir
        args.output_dir = args.output_dir or config.output_dir
        args.scripts_dir = args.scripts_dir or config.scripts_dir
        args.templates_in = args.templates_in or config.templates_in
        args.templates_out = args.templates_out or config.templates_out
        # Validate required arguments after merging
        if not args.input_dir:
            compile_parser.error("argument --in is required")
        if not args.output_dir:
            compile_parser.error("argument --out is required")
    elif args.command == "shred":
        args.input_file = args.input_file or config.input_file
        args.output_file = args.output_file or config.output_file
        args.scripts_out = args.scripts_out or config.scripts_out
        # Validate required arguments after merging
        if not args.input_file:
            shred_parser.error("argument --in is required")
        if not args.output_file:
            shred_parser.error("argument --out is required")

    # Merge boolean flags
    args.verbose = args.verbose or config.verbose or False
    args.quiet = args.quiet or config.quiet or False
    if hasattr(args, "format"):
        args.format = args.format or config.format or False
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
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
