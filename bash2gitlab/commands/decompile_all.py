"""
Take a gitlab template with inline yaml and split it up into yaml and shell
commands. Useful for project initialization.

Fixes:
 - Support decompiling a *file* or an entire *folder* tree
 - Force --out to be a *directory* (scripts live next to output YAML)
 - Script refs are made *relative to the YAML file* (e.g., "./script.sh")
 - Any YAML ``!reference [...]`` items in scripts are emitted as *bash comments*
 - Logging prints *paths relative to CWD* to reduce noise
 - Generate Makefile with proper dependency patterns for before_/after_ scripts
"""

from __future__ import annotations

import io
import logging
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import TaggedScalar
from ruamel.yaml.scalarstring import FoldedScalarString

from bash2gitlab.config import config
from bash2gitlab.errors.exceptions import ValidationFailed
from bash2gitlab.utils.mock_ci_vars import generate_mock_ci_variables_script
from bash2gitlab.utils.pathlib_polyfills import is_relative_to
from bash2gitlab.utils.utils import short_path
from bash2gitlab.utils.validate_pipeline import GitLabCIValidator
from bash2gitlab.utils.yaml_factory import get_yaml

logger = logging.getLogger(__name__)

SHEBANG = "#!/bin/bash"

__all__ = [
    "run_decompile_gitlab_file",
    "run_decompile_gitlab_tree",
]


# --- helpers -----------------------------------------------------------------


def dump_inline_no_doc_markers(yaml: YAML, node: Any) -> str:
    buf = io.StringIO()
    prev_start, prev_end = yaml.explicit_start, yaml.explicit_end
    try:
        yaml.explicit_start = False
        yaml.explicit_end = False
        yaml.dump(node, buf)
    finally:
        yaml.explicit_start, yaml.explicit_end = prev_start, prev_end
    return buf.getvalue().rstrip("\n")


def create_script_filename(job_name: str, script_key: str) -> str:
    """Create a standardized, safe filename for a script.

    For the main 'script' key, just use the job name. For others, append the key.
    """
    sanitized_job_name = re.sub(r"[^\w.-]", "-", job_name.lower())
    sanitized_job_name = re.sub(r"-+", "-", sanitized_job_name).strip("-")
    return f"{sanitized_job_name}.sh" if script_key == "script" else f"{sanitized_job_name}_{script_key}.sh"


def bashify_script_items(script_content: list[str | Any] | str, yaml: YAML) -> list[str]:
    """Convert YAML items from a script block into bash lines.

    - Strings are kept as-is.
    - Other YAML nodes are dumped to text with no doc markers.
    - ``!reference [...]`` turns into a bash comment line so the intent isn't lost.
    - Empty/whitespace lines are dropped.
    """
    raw_lines: list[str] = []

    if isinstance(script_content, str):
        raw_lines.extend(script_content.splitlines())
    else:
        for item in script_content:  # ruamel CommentedSeq-like or list
            if isinstance(item, str):
                raw_lines.append(item)
            elif isinstance(item, TaggedScalar) and str(item.tag).endswith("reference"):
                dumped = dump_inline_no_doc_markers(yaml, item)
                raw_lines.append(f"# {dumped}")
            elif item is not None:
                dumped = dump_inline_no_doc_markers(yaml, item)
                # If the dump still contains an explicit !reference tag, comment it out
                if dumped.lstrip().startswith("!reference"):
                    raw_lines.append(f"# {dumped}")
                else:
                    raw_lines.append(dumped)

    # Filter empties
    # return [ln for ln in (ln if isinstance(ln, str) else str(ln) for ln in raw_lines) if ln and ln.strip()]

    # Make sure line continuations (`\`) get their own newline
    normalized = []
    for ln in raw_lines:
        normalized.append(ln.rstrip())
    return [ln for ln in normalized if ln and ln.strip()]


def generate_makefile(jobs_info: dict[str, dict[str, str]], output_dir: Path, dry_run: bool = False) -> None:
    """Generate a Makefile with proper dependency patterns for GitLab CI jobs.

    Args:
        jobs_info: Dict mapping job names to their script info
        output_dir: Directory where Makefile should be created
        dry_run: Whether to actually write the file
    """
    makefile_lines: list[str] = [
        "# Auto-generated Makefile for GitLab CI jobs",
        "# Use 'make <job_name>' to run a job with proper before/after script handling",
        "",
        ".PHONY: help",
        "",
    ]

    # Collect all job names for help target
    job_names = list(jobs_info.keys())

    # Help target
    makefile_lines.extend(
        [
            "help:",
            "\t@echo 'Available jobs:'",
        ]
    )
    for job_name in sorted(job_names):
        makefile_lines.append(f"\t@echo '  {job_name}'")
    makefile_lines.extend(
        [
            "\t@echo ''",
            "\t@echo 'Use: make <job_name> to run a job'",
            "",
        ]
    )

    # Generate rules for each job
    for job_name, scripts in jobs_info.items():
        sanitized_name = re.sub(r"[^\w.-]", "-", job_name.lower())
        sanitized_name = re.sub(r"-+", "-", sanitized_name).strip("-")

        # Determine dependencies and targets
        dependencies: list[str] = []
        targets_after_main: list[str] = []

        # Before script dependency
        if "before_script" in scripts:
            before_target = f"{sanitized_name}_before_script"
            dependencies.append(before_target)

        # After script runs after main job
        if "after_script" in scripts:
            after_target = f"{sanitized_name}_after_script"
            targets_after_main.append(after_target)

        # Main job rule
        makefile_lines.append(f".PHONY: {sanitized_name}")
        if dependencies:
            makefile_lines.append(f"{sanitized_name}: {' '.join(dependencies)}")
        else:
            makefile_lines.append(f"{sanitized_name}:")

        # Execute the main script
        if "script" in scripts:
            makefile_lines.append(f"\t@echo 'Running {job_name} main script...'")
            makefile_lines.append(f"\t@./{scripts['script']}")
        else:
            makefile_lines.append(f"\t@echo 'No main script for {job_name}'")

        # Execute after scripts if they exist
        for after_target in targets_after_main:
            makefile_lines.append(f"\t@$(MAKE) {after_target}")

        makefile_lines.append("")

        # Before script rule
        if "before_script" in scripts:
            before_target = f"{sanitized_name}_before_script"
            makefile_lines.extend(
                [
                    f".PHONY: {before_target}",
                    f"{before_target}:",
                    f"\t@echo 'Running {job_name} before script...'",
                    f"\t@./{scripts['before_script']}",
                    "",
                ]
            )

        # After script rule
        if "after_script" in scripts:
            after_target = f"{sanitized_name}_after_script"
            makefile_lines.extend(
                [
                    f".PHONY: {after_target}",
                    f"{after_target}:",
                    f"\t@echo 'Running {job_name} after script...'",
                    f"\t@./{scripts['after_script']}",
                    "",
                ]
            )

        # Pre-get-sources script rule (standalone)
        if "pre_get_sources_script" in scripts:
            pre_target = f"{sanitized_name}_pre_get_sources_script"
            makefile_lines.extend(
                [
                    f".PHONY: {pre_target}",
                    f"{pre_target}:",
                    f"\t@echo 'Running {job_name} pre-get-sources script...'",
                    f"\t@./{scripts['pre_get_sources_script']}",
                    "",
                ]
            )

    # Add a rule to run all jobs
    if job_names:
        makefile_lines.extend(
            [
                ".PHONY: all",
                f"all: {' '.join(sorted(job_names))}",
                "",
            ]
        )

    makefile_content = "\n".join(makefile_lines)
    makefile_path = output_dir / "Makefile"

    logger.info("Generating Makefile at: %s", short_path(makefile_path))

    if not dry_run:
        makefile_path.write_text(makefile_content, encoding="utf-8")


# --- decompilers ---------------------------------------------------------------


def decompile_variables_block(
    variables_data: dict,
    base_name: str,
    scripts_output_path: Path,
    *,
    dry_run: bool = False,
) -> str | None:
    """Extract variables dict into a ``.sh`` file of ``export`` statements.

    Returns the filename (not full path) of the created variables script, or ``None``.
    """
    if not variables_data or not isinstance(variables_data, dict):
        return None

    variable_lines: list[str] = []
    for key, value in variables_data.items():
        value_str = str(value).replace('"', '\\"')
        variable_lines.append(f'export {key}="{value_str}"')

    if not variable_lines:
        return None

    script_filename = f"{base_name}_variables.sh"
    script_filepath = scripts_output_path / script_filename
    full_script_content = "\n".join(variable_lines) + "\n"

    logger.info("Decompileding variables for '%s' to '%s'", base_name, short_path(script_filepath))

    if not dry_run:
        script_filepath.parent.mkdir(parents=True, exist_ok=True)
        script_filepath.write_text(full_script_content, encoding="utf-8")
        script_filepath.chmod(0o755)

    return script_filename


def decompile_script_block(
    *,
    script_content: list[str | Any] | str,
    job_name: str,
    script_key: str,
    scripts_output_path: Path,
    yaml_dir: Path,
    dry_run: bool = False,
    global_vars_filename: str | None = None,
    job_vars_filename: str | None = None,
    minimum_lines: int = 1,
) -> tuple[str | None, str | None]:
    """Extract a script block into a ``.sh`` file and return (script_path, bash_command).

    The generated bash command will reference the script *relative to the YAML file*.
    """
    if not script_content:
        return None, None

    yaml = get_yaml()

    script_lines = bashify_script_items(script_content, yaml)
    if not script_lines:
        logger.debug("Skipping empty script block in job '%s' for key '%s'.", job_name, script_key)
        return None, None

    # Check if the script meets the minimum lines requirement
    if len(script_lines) < minimum_lines:
        logger.debug(
            "Skipping script block in job '%s' for key '%s' - only %d lines (minimum: %d)",
            job_name,
            script_key,
            len(script_lines),
            minimum_lines,
        )
        return None, None

    script_filename = create_script_filename(job_name, script_key)
    script_filepath = scripts_output_path / script_filename

    # Build header with conditional sourcing for local execution
    script_filename_path = Path(create_script_filename(job_name, script_key))
    file_ext = script_filename_path.suffix.lstrip(".")

    custom_shebangs = config.custom_shebangs or {"sh": "#!/bin/bash"}
    shebang = custom_shebangs.get(file_ext, SHEBANG)  # SHEBANG is the '#!/bin/bash' default

    header_parts: list[str] = [shebang]
    sourcing_block: list[str] = []
    if global_vars_filename:
        sourcing_block.append(f"  . ./{global_vars_filename}")
    if job_vars_filename:
        sourcing_block.append(f"  . ./{job_vars_filename}")

    if sourcing_block:
        header_parts.append('\nif [[ "${CI:-}" == "" ]]; then')
        header_parts.extend(sourcing_block)
        header_parts.append("fi")

    script_header = "\n".join(header_parts)
    full_script_content = f"{script_header}\n\n" + "\n".join(script_lines) + "\n"

    logger.info("Decompileded script from '%s:%s' to '%s'", job_name, script_key, short_path(script_filepath))

    if not dry_run:
        script_filepath.parent.mkdir(parents=True, exist_ok=True)
        script_filepath.write_text(full_script_content, encoding="utf-8")
        script_filepath.chmod(0o755)

    # Compute bash command relative to YAML
    base = yaml_dir.resolve()
    target = script_filepath.resolve()
    relative_path = target.relative_to(base) if is_relative_to(target, base) else Path(script_filename)

    # Normalize to posix for YAML
    rel_str = str(relative_path).replace("\\", "/")
    if not rel_str.startswith(".") and "/" not in rel_str:
        rel_str = f"./{rel_str}"
    elif not rel_str.startswith("."):
        rel_str = "./" + rel_str

    return str(script_filepath), rel_str


def process_decompile_job(
    *,
    job_name: str,
    job_data: dict,
    scripts_output_path: Path,
    yaml_dir: Path,
    dry_run: bool = False,
    global_vars_filename: str | None = None,
    minimum_lines: int = 1,
) -> tuple[int, dict[str, str]]:
    """Process a single job definition to decompile its script and variables blocks.

    Returns (decompiled_count, scripts_info) where scripts_info maps script_key to filename.
    """
    decompiled_count = 0
    scripts_info: dict[str, str] = {}

    # Job-specific variables first
    job_vars_filename: str | None = None
    if isinstance(job_data.get("variables"), dict):
        sanitized_job_name = re.sub(r"[^\w.-]", "-", job_name.lower())
        sanitized_job_name = re.sub(r"-+", "-", sanitized_job_name).strip("-")
        job_vars_filename = decompile_variables_block(
            job_data["variables"], sanitized_job_name, scripts_output_path, dry_run=dry_run
        )
        if job_vars_filename:
            decompiled_count += 1

    # Script-like keys to decompile
    for key in ("script", "before_script", "after_script", "pre_get_sources_script"):
        if key in job_data and job_data[key]:
            _, command = decompile_script_block(
                script_content=job_data[key],
                job_name=job_name,
                script_key=key,
                scripts_output_path=scripts_output_path,
                yaml_dir=yaml_dir,
                dry_run=dry_run,
                global_vars_filename=global_vars_filename,
                job_vars_filename=job_vars_filename,
                minimum_lines=minimum_lines,
            )
            if command:
                job_data[key] = FoldedScalarString(command.replace("\\", "/"))
                decompiled_count += 1
                # Store just the filename for Makefile generation
                scripts_info[key] = command.lstrip("./")

    return decompiled_count, scripts_info


# --- public entry points -----------------------------------------------------


def iterate_yaml_files(root: Path) -> Iterable[Path]:
    yield from root.rglob("*.yml")
    yield from root.rglob("*.yaml")


def run_decompile_gitlab_file(
    *, input_yaml_path: Path, output_dir: Path, dry_run: bool = False, minimum_lines: int = 1
) -> tuple[int, int, Path]:
    """Decompile a *single* GitLab CI YAML file into scripts + modified YAML in *output_dir*.

    Returns (jobs_processed, total_files_created, output_yaml_path).
    """
    if not input_yaml_path.is_file():
        raise FileNotFoundError(f"Input YAML file not found: {input_yaml_path}")

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)  # force directory

    yaml = get_yaml()
    yaml.indent(mapping=2, sequence=4, offset=2)

    logger.info("Loading GitLab CI configuration from: %s", short_path(input_yaml_path))
    data = yaml.load(input_yaml_path)

    # Layout: write YAML and scripts side-by-side under output_dir[/subdirs]
    output_yaml_path = output_dir / input_yaml_path.name
    scripts_dir = output_yaml_path.parent
    yaml_dir = output_yaml_path.parent

    jobs_processed = 0
    total_files_created = 0
    jobs_info: dict[str, dict[str, str]] = {}

    # Top-level variables -> global_variables.sh next to YAML
    global_vars_filename: str | None = None
    if isinstance(data.get("variables"), dict):
        logger.info("Processing global variables block.")
        global_vars_filename = decompile_variables_block(data["variables"], "global", scripts_dir, dry_run=dry_run)
        if global_vars_filename:
            total_files_created += 1

    # Jobs
    for key, value in data.items():
        if isinstance(value, dict) and "script" in value:
            logger.debug("Processing job: %s", key)
            jobs_processed += 1
            decompiled_count, scripts_info = process_decompile_job(
                job_name=key,
                job_data=value,
                scripts_output_path=scripts_dir,
                yaml_dir=yaml_dir,
                dry_run=dry_run,
                global_vars_filename=global_vars_filename,
                minimum_lines=minimum_lines,
            )
            total_files_created += decompiled_count
            if scripts_info:
                jobs_info[key] = scripts_info

    if total_files_created > 0:
        logger.info("Decompileded %s file(s) from %s job(s).", total_files_created, jobs_processed)
        if not dry_run:
            logger.info("Writing modified YAML to: %s", short_path(output_yaml_path))
            output_yaml_path.parent.mkdir(parents=True, exist_ok=True)
            with output_yaml_path.open("w", encoding="utf-8") as f:
                yaml.dump(data, f)
            with output_yaml_path.open() as f:
                new_content = f.read()
                validator = GitLabCIValidator()
                ok, problems = validator.validate_ci_config(new_content)
                if not ok:
                    raise ValidationFailed(problems)
    else:
        logger.info("No script or variable blocks found to decompile.")

    # Generate Makefile if we have jobs
    if jobs_info:
        generate_makefile(jobs_info, output_dir, dry_run=dry_run)
        if not dry_run:
            total_files_created += 1  # Count the Makefile

    if not dry_run:
        output_yaml_path.parent.mkdir(exist_ok=True)
        generate_mock_ci_variables_script(str(output_yaml_path.parent / "mock_ci_variables.sh"))

    return jobs_processed, total_files_created, output_yaml_path


def run_decompile_gitlab_tree(
    *, input_root: Path, output_dir: Path, dry_run: bool = False, minimum_lines: int = 1
) -> tuple[int, int, int]:
    """Decompile *all* ``*.yml`` / ``*.yaml`` under ``input_root`` into ``output_dir``.

    The relative directory structure under ``input_root`` is preserved in ``output_dir``.

    Returns (yaml_files_processed, total_jobs_processed, total_files_created).
    """
    if not input_root.is_dir():
        raise FileNotFoundError(f"Input folder not found: {input_root}")

    yaml_files_processed = 0
    total_jobs = 0
    total_created = 0

    for in_file in iterate_yaml_files(input_root):
        rel_dir = in_file.parent.relative_to(input_root)
        out_subdir = (output_dir / rel_dir).resolve()
        jobs, created, _ = run_decompile_gitlab_file(
            input_yaml_path=in_file, output_dir=out_subdir, dry_run=dry_run, minimum_lines=minimum_lines
        )
        yaml_files_processed += 1
        total_jobs += jobs
        total_created += created

    return yaml_files_processed, total_jobs, total_created
