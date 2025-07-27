from __future__ import annotations

import logging
import subprocess  # nosec
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# TODO: possibly switch to yamlfixer-opt-nc or prettier as yamlfix somewhat unsupported.


def run_formatter(output_dir: Path, templates_output_dir: Path):
    """
    Runs yamlfix on the output directories.

    Args:
        output_dir (Path): The main output directory.
        templates_output_dir (Path): The templates output directory.
    """
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
