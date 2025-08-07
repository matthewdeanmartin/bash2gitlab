from __future__ import annotations

import io
import logging
import re
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import FoldedScalarString

from bash2gitlab.utils.mock_ci_vars import generate_mock_ci_variables_script

logger = logging.getLogger(__name__)

SHEBANG = "#!/bin/bash"


def create_script_filename(job_name: str, script_key: str) -> str:
    """
    Creates a standardized, safe filename for a script.

    Args:
        job_name (str): The name of the GitLab CI job.
        script_key (str): The key of the script block (e.g., 'script', 'before_script').

    Returns:
        str: A safe, descriptive filename like 'job-name_script.sh'.
    """
    # Sanitize job_name: replace spaces and invalid characters with hyphens
    sanitized_job_name = re.sub(r"[^\w.-]", "-", job_name.lower())
    # Clean up multiple hyphens
    sanitized_job_name = re.sub(r"-+", "-", sanitized_job_name).strip("-")

    # For the main 'script' key, just use the job name. For others, append the key.
    if script_key == "script":
        return f"{sanitized_job_name}.sh"
    return f"{sanitized_job_name}_{script_key}.sh"


def shred_variables_block(
    variables_data: dict,
    base_name: str,
    scripts_output_path: Path,
    dry_run: bool = False,
) -> str | None:
    """
    Extracts a variables block into a .sh file containing export statements.

    Args:
        variables_data (dict): The dictionary of variables.
        base_name (str): The base for the filename (e.g., 'global' or a sanitized job name).
        scripts_output_path (Path): The directory to save the new .sh file.
        dry_run (bool): If True, don't write any files.

    Returns:
        str | None: The filename of the created variables script for sourcing, or None.
    """
    if not variables_data or not isinstance(variables_data, dict):
        return None

    variable_lines = []
    for key, value in variables_data.items():
        # Simple stringification for the value.
        # Shell-safe escaping is complex; this handles basic cases by quoting.
        value_str = str(value).replace('"', '\\"')
        variable_lines.append(f'export {key}="{value_str}"')

    if not variable_lines:
        return None

    # For global, filename is global_variables.sh. For jobs, it's job-name_variables.sh
    script_filename = f"{base_name}_variables.sh"
    script_filepath = scripts_output_path / script_filename
    full_script_content = "\n".join(variable_lines) + "\n"

    logger.info(f"Shredding variables for '{base_name}' to '{script_filepath}'")

    if not dry_run:
        script_filepath.parent.mkdir(parents=True, exist_ok=True)
        script_filepath.write_text(full_script_content, encoding="utf-8")
        # Make the script executable for consistency, though not strictly required for sourcing
        script_filepath.chmod(0o755)

    return script_filename


def shred_script_block(
    script_content: list[str] | str,
    job_name: str,
    script_key: str,
    scripts_output_path: Path,
    dry_run: bool = False,
    global_vars_filename: str | None = None,
    job_vars_filename: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Extracts a script block into a .sh file and returns the command to run it.
    The generated script will source global and job-specific variable files if they exist.

    Args:
        script_content (Union[list[str], str]): The script content from the YAML.
        job_name (str): The name of the job.
        script_key (str): The key of the script ('script', 'before_script', etc.).
        scripts_output_path (Path): The directory to save the new .sh file.
        dry_run (bool): If True, don't write any files.
        global_vars_filename (str, optional): Filename of the global variables script.
        job_vars_filename (str, optional): Filename of the job-specific variables script.

    Returns:
        A tuple containing:
        - The path to the new script file (or None if no script was created).
        - The command to execute the new script (e.g., './scripts/my-job.sh').
    """
    if not script_content:
        return None, None

    yaml = YAML()
    yaml.width = 4096

    # This block will handle converting CommentedSeq and its contents (which may include
    # CommentedMap objects) into a simple list of strings.
    processed_lines = []
    if isinstance(script_content, str):
        processed_lines.extend(script_content.splitlines())
    elif script_content:  # It's a list-like object (e.g., ruamel.yaml.CommentedSeq)

        for item in script_content:
            if isinstance(item, str):
                processed_lines.append(item)
            elif item is not None:
                # Any non-string item (like a CommentedMap that ruamel parsed from "key: value")
                # should be dumped back into a string representation.
                with io.StringIO() as string_stream:
                    yaml.dump(item, string_stream)
                    # The dump might include '...' at the end, remove it and any trailing newline.
                    item_as_string = string_stream.getvalue().replace("...", "").strip()
                    if item_as_string:
                        processed_lines.append(item_as_string)

    # Filter out empty or whitespace-only lines from the final list
    script_lines = [line for line in processed_lines if line and line.strip()]

    if not script_lines:
        logger.debug(f"Skipping empty script block in job '{job_name}' for key '{script_key}'.")
        return None, None

    script_filename = create_script_filename(job_name, script_key)
    script_filepath = scripts_output_path / script_filename
    execution_command = f"./{script_filepath.relative_to(scripts_output_path.parent)}"

    # Build the header with conditional sourcing for local execution
    header_parts = [SHEBANG]
    sourcing_block = []
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

    logger.info(f"Shredding script from '{job_name}:{script_key}' to '{script_filepath}'")

    if not dry_run:
        script_filepath.parent.mkdir(parents=True, exist_ok=True)
        script_filepath.write_text(full_script_content, encoding="utf-8")
        script_filepath.chmod(0o755)

    return str(script_filepath), execution_command


def process_shred_job(
    job_name: str,
    job_data: dict,
    scripts_output_path: Path,
    dry_run: bool = False,
    global_vars_filename: str | None = None,
) -> int:
    """
    Processes a single job definition to shred its script and variables blocks.

    Args:
        job_name (str): The name of the job.
        job_data (dict): The dictionary representing the job's configuration.
        scripts_output_path (Path): The directory to save shredded scripts.
        dry_run (bool): If True, simulate without writing files.
        global_vars_filename (str, optional): Filename of the global variables script.

    Returns:
        int: The number of files (scripts and variables) shredded from this job.
    """
    shredded_count = 0

    # Shred job-specific variables first
    job_vars_filename = None
    if "variables" in job_data and isinstance(job_data.get("variables"), dict):
        sanitized_job_name = re.sub(r"[^\w.-]", "-", job_name.lower())
        sanitized_job_name = re.sub(r"-+", "-", sanitized_job_name).strip("-")
        job_vars_filename = shred_variables_block(
            job_data["variables"], sanitized_job_name, scripts_output_path, dry_run
        )
        if job_vars_filename:
            shredded_count += 1

    # Shred script blocks
    script_keys = ["script", "before_script", "after_script", "pre_get_sources_script"]
    for key in script_keys:
        if key in job_data and job_data[key]:
            _, command = shred_script_block(
                script_content=job_data[key],
                job_name=job_name,
                script_key=key,
                scripts_output_path=scripts_output_path,
                dry_run=dry_run,
                global_vars_filename=global_vars_filename,
                job_vars_filename=job_vars_filename,
            )
            if command:
                # Replace the script block with a single command to execute the new file
                job_data[key] = FoldedScalarString(command.replace("\\", "/"))
                shredded_count += 1
    return shredded_count


def shred_gitlab_ci(
    input_yaml_path: Path,
    output_yaml_path: Path,
    scripts_output_path: Path,
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Loads a GitLab CI YAML file, shreds all script and variable blocks into
    separate .sh files, and saves the modified YAML.

    Args:
        input_yaml_path (Path): Path to the input .gitlab-ci.yml file.
        output_yaml_path (Path): Path to write the modified .gitlab-ci.yml file.
        scripts_output_path (Path): Directory to store the generated .sh files.
        dry_run (bool): If True, simulate the process without writing any files.

    Returns:
        A tuple containing:
        - The total number of jobs processed.
        - The total number of .sh files created (scripts and variables).
    """
    if not input_yaml_path.is_file():
        raise FileNotFoundError(f"Input YAML file not found: {input_yaml_path}")

    if output_yaml_path.is_dir():
        output_yaml_path = output_yaml_path / input_yaml_path.name

    logger.info(f"Loading GitLab CI configuration from: {input_yaml_path}")
    yaml = YAML()
    yaml.width = 4096
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    data = yaml.load(input_yaml_path)

    jobs_processed = 0
    total_files_created = 0

    # First, process the top-level 'variables' block, if it exists.
    global_vars_filename = None
    if "variables" in data and isinstance(data.get("variables"), dict):
        logger.info("Processing global variables block.")
        global_vars_filename = shred_variables_block(data["variables"], "global", scripts_output_path, dry_run)
        if global_vars_filename:
            total_files_created += 1

    # Process all top-level keys that look like jobs
    for key, value in data.items():
        # Heuristic: A job is a dictionary that contains a 'script' key.
        if isinstance(value, dict) and "script" in value:
            logger.debug(f"Processing job: {key}")
            jobs_processed += 1
            total_files_created += process_shred_job(key, value, scripts_output_path, dry_run, global_vars_filename)

    if total_files_created > 0:
        logger.info(f"Shredded {total_files_created} file(s) from {jobs_processed} job(s).")
        if not dry_run:
            logger.info(f"Writing modified YAML to: {output_yaml_path}")
            output_yaml_path.parent.mkdir(parents=True, exist_ok=True)
            with output_yaml_path.open("w", encoding="utf-8") as f:
                yaml.dump(data, f)
    else:
        logger.info("No script or variable blocks found to shred.")

    if not dry_run:
        scripts_output_path.mkdir(exist_ok=True)
        generate_mock_ci_variables_script(str(scripts_output_path / "mock_ci_variables.sh"))

    return jobs_processed, total_files_created
