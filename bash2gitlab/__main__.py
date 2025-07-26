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
import subprocess  # nosec
import sys
from pathlib import Path

# --- Project Imports ---
# Make sure the project is installed or the path is correctly set for these imports to work
from bash2gitlab import __about__
from bash2gitlab import __doc__ as root_doc
from bash2gitlab.compile_all import process_uncompiled_directory
from bash2gitlab.logging_config import generate_config


def run_formatter(output_dir: Path, templates_output_dir: Path):
    """
    Runs yamlfix on the output directories.

    Args:
        output_dir (Path): The main output directory.
        templates_output_dir (Path): The templates output directory.
    """
    logger = logging.getLogger(__name__)
    try:
        # Check if yamlfix is installed
        subprocess.run(["yamlfix", "--version"], check=True, capture_output=True)  # nosec
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error(
            "❌ 'yamlfix' is not installed or not in PATH. Please install it to use the --format option (`pip install yamlfix`)."
        )
        sys.exit(1)

    targets = []
    if output_dir.is_dir():
        targets.append(str(output_dir))
    if templates_output_dir.is_dir():
        targets.append(str(templates_output_dir))

    if not targets:
        logger.warning("No output directories found to format.")
        return

    logger.info(f"Running yamlfix on: {', '.join(targets)}")
    try:
        subprocess.run(["yamlfix", *targets], check=True, capture_output=True)  # nosec
        logger.info("✅ Formatting complete.")
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Error running yamlfix: {e.stderr.decode()}")
        sys.exit(1)


def compile_handler(args: argparse.Namespace):
    """Handler for the 'compile' command."""
    logger = logging.getLogger(__name__)
    logger.info("Starting bash2gitlab compiler...")

    # Resolve paths, using sensible defaults if optional paths are not provided
    in_dir = Path(args.input_dir).resolve()
    out_dir = Path(args.output_dir).resolve()
    scripts_dir = Path(args.scripts_dir).resolve() if args.scripts_dir else in_dir
    templates_in_dir = Path(args.templates_in).resolve() if args.templates_in else in_dir
    templates_out_dir = Path(args.templates_out).resolve() if args.templates_out else out_dir
    dry_run = bool(args.dry_run)

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
        "compile", help="Compile an 'uncompiled' directory into a standard GitLab CI structure."
    )
    compile_parser.add_argument(
        "--in",
        dest="input_dir",
        required=True,
        help="Input directory containing the uncompiled `.gitlab-ci.yml` and other sources.",
    )
    compile_parser.add_argument(
        "--out",
        dest="output_dir",
        required=True,
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

    args = parser.parse_args()

    # --- Setup Logging ---
    if args.verbose:
        log_level = "DEBUG"
    elif args.quiet:
        log_level = "CRITICAL"
    else:
        log_level = "INFO"
    logging.config.dictConfig(generate_config(level=log_level))

    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
