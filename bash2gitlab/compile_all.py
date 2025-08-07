from __future__ import annotations

import base64
import difflib
import io
import logging
import multiprocessing
import shlex
import sys
from pathlib import Path
from typing import Any, Union

from ruamel.yaml import YAML, CommentedMap
from ruamel.yaml.comments import TaggedScalar
from ruamel.yaml.error import YAMLError
from ruamel.yaml.scalarstring import LiteralScalarString

from bash2gitlab.bash_reader import read_bash_script
from bash2gitlab.utils.dotenv import parse_env_file
from bash2gitlab.utils.utils import remove_leading_blank_lines, short_path

logger = logging.getLogger(__name__)

BANNER = f"""# DO NOT EDIT
# This is a compiled file, compiled with bash2gitlab
# Recompile instead of editing this file.
#
# Compiled with the command: 
#     {' '.join(sys.argv)}

"""


def extract_script_path(command_line: str) -> str | None:
    """
    Extracts the first shell script path from a shell command line.

    Args:
        command_line (str): A shell command line.

    Returns:
        str | None: The script path if the line is a script invocation; otherwise, None.
    """
    try:
        tokens: list[str] = shlex.split(command_line)
    except ValueError:
        # Malformed shell syntax
        return None

    executors = {"bash", "sh", "source", ".", "pwsh"}

    parts = 0
    path_found = None
    for i, token in enumerate(tokens):
        path = Path(token)
        if path.suffix == ".sh" or path.suffix == ".ps1":
            # Handle `bash script.sh`, `sh script.sh`, `source script.sh`
            if i > 0 and tokens[i - 1] in executors:
                path_found = str(path).replace("\\", "/")
            else:
                path_found = str(path).replace("\\", "/")
            parts += 1
        elif not token.isspace() and token not in executors:
            parts += 1

    if path_found and parts == 1:
        return path_found
    return None


def process_script_list(
    script_list: Union[list[Any], str],
    scripts_root: Path,
) -> Union[list[Any], LiteralScalarString]:
    """
    Processes a list of script lines, inlining any shell script references
    while preserving other lines like YAML references. It will convert the
    entire block to a literal scalar string `|` for long scripts, but only
    if no YAML tags (like !reference) are present.
    """
    if isinstance(script_list, str):
        script_list = [script_list]

    processed_items: list[Any] = []
    contains_tagged_scalar = False

    for item in script_list:
        # Check for non-string YAML objects first (like !reference).
        if not isinstance(item, str):
            if isinstance(item, TaggedScalar):
                contains_tagged_scalar = True
            processed_items.append(item)
            continue  # Go to next item

        # It's a string, see if it's a script path.
        script_path_str = extract_script_path(item)
        if script_path_str:
            rel_path = script_path_str.strip().lstrip("./")
            script_path = scripts_root / rel_path
            try:
                bash_code = read_bash_script(script_path)
                bash_lines = bash_code.splitlines()

                logger.info(f"Inlining script '{script_path}' ({len(bash_lines)} lines).")
                processed_items.extend(bash_lines)
            except (FileNotFoundError, ValueError) as e:
                logger.warning(f"Could not inline script '{script_path_str}': {e}. Preserving original line.")
                processed_items.append(item)
        else:
            # It's a regular command string, preserve it.
            processed_items.append(item)

    # --- Decide on the return format ---
    # Condition to use a literal block `|`:
    # 1. It must NOT contain any special YAML tags.
    # 2. Either one of the inlined scripts was long, or the resulting total is long (e.g., > 5 lines).
    _ = list(type(_) for _ in processed_items)
    if not contains_tagged_scalar and len(processed_items) > 5 and all(isinstance(_, str) for _ in processed_items):
        # We can safely convert to a single string block.
        final_script_block = "\n".join(map(str, processed_items))
        logger.info("Formatting script block as a single literal block for clarity.")
        return LiteralScalarString(final_script_block)
    else:
        # We must return a list to preserve YAML tags or because it's short.
        if contains_tagged_scalar:
            logger.debug("Preserving script block as a list to support YAML tags (!reference).")
        return processed_items


def process_job(job_data: dict, scripts_root: Path) -> int:
    """Processes a single job definition to inline scripts."""
    found = 0
    for script_key in ["script", "before_script", "after_script", "pre_get_sources_script"]:
        if script_key in job_data:
            result = process_script_list(job_data[script_key], scripts_root)
            if result != job_data[script_key]:
                job_data[script_key] = result
                found += 1
    return found


def inline_gitlab_scripts(
    gitlab_ci_yaml: str,
    scripts_root: Path,
    global_vars: dict[str, str],
    uncompiled_path: Path,  # Path to look for job_name_variables.sh files
) -> tuple[int, str]:
    """
    Loads a GitLab CI YAML file, inlines scripts, merges global and job-specific variables,
    reorders top-level keys, and returns the result as a string.
    This version now supports inlining scripts in top-level lists used as YAML anchors.
    """
    inlined_count = 0
    yaml = YAML()
    yaml.width = 4096
    yaml.preserve_quotes = True
    data = yaml.load(io.StringIO(gitlab_ci_yaml))

    # Merge global variables if provided
    if global_vars:
        logger.info("Merging global variables into the YAML configuration.")
        existing_vars = data.get("variables", {})
        merged_vars = global_vars.copy()
        # Update with existing vars, so YAML-defined vars overwrite global ones on conflict.
        merged_vars.update(existing_vars)
        data["variables"] = merged_vars
        inlined_count += 1

    for name in ["after_script", "before_script"]:
        if name in data:
            logger.info(f"Processing top-level '{name}' section, even though gitlab has deprecated them.")
            result = process_script_list(data[name], scripts_root)
            if result != data[name]:
                data[name] = result
                inlined_count += 1

    # Process all jobs and top-level script lists (which are often used for anchors)
    for job_name, job_data in data.items():
        # Handle top-level keys that are lists of scripts. This pattern is commonly
        # used to create reusable script blocks with YAML anchors, e.g.:
        # .my-script-template: &my-script-anchor
        #   - ./scripts/my-script.sh
        if isinstance(job_data, list):
            logger.debug(f"Processing top-level list key '{job_name}', potentially a script anchor.")
            result = process_script_list(job_data, scripts_root)
            if result != job_data:
                data[job_name] = result
                inlined_count += 1
        elif isinstance(job_data, dict):
            # Look for and process job-specific variables file
            safe_job_name = job_name.replace(":", "_")
            job_vars_filename = f"{safe_job_name}_variables.sh"
            job_vars_path = uncompiled_path / job_vars_filename

            if job_vars_path.is_file():
                logger.info(f"Found and loading job-specific variables for '{job_name}' from {job_vars_path}")
                content = job_vars_path.read_text(encoding="utf-8")
                job_specific_vars = parse_env_file(content)

                if job_specific_vars:
                    existing_job_vars = job_data.get("variables", CommentedMap())
                    # Start with variables from the .sh file
                    merged_job_vars = CommentedMap(job_specific_vars.items())
                    # Update with variables from the YAML, so they take precedence
                    merged_job_vars.update(existing_job_vars)
                    job_data["variables"] = merged_job_vars
                    inlined_count += 1

            # A simple heuristic for a "job" is a dictionary with a 'script' key.
            if (
                "script" in job_data
                or "before_script" in job_data
                or "after_script" in job_data
                or "pre_get_sources_script" in job_data
            ):
                logger.info(f"Processing job: {job_name}")
                inlined_count += process_job(job_data, scripts_root)
            if "hooks" in job_data:
                if isinstance(job_data["hooks"], dict) and "pre_get_sources_script" in job_data["hooks"]:
                    logger.info(f"Processing pre_get_sources_script: {job_name}")
                    inlined_count += process_job(job_data["hooks"], scripts_root)
            if "run" in job_data:
                if isinstance(job_data["run"], list):
                    for item in job_data["run"]:
                        if isinstance(item, dict) and "script" in item:
                            logger.info(f"Processing run/script: {job_name}")
                            inlined_count += process_job(item, scripts_root)

    # --- Reorder top-level keys for consistent output ---
    logger.debug("Reordering top-level keys in the final YAML.")
    ordered_data = CommentedMap()
    key_order = ["include", "variables", "stages"]

    # Add specified keys first, in the desired order
    for key in key_order:
        if key in data:
            ordered_data[key] = data.pop(key)

    # Add the rest of the keys (jobs, etc.) in their original relative order
    for key, value in data.items():
        ordered_data[key] = value

    out_stream = io.StringIO()
    yaml.dump(ordered_data, out_stream)  # Dump the reordered data
    return inlined_count, out_stream.getvalue()


def write_yaml_and_hash(
    output_file: Path,
    new_content: str,
    hash_file: Path,
):
    """Writes the YAML content and a base64 encoded version to a .hash file."""
    logger.info(f"Writing new file: {short_path(output_file)}")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    new_content = remove_leading_blank_lines(new_content)

    output_file.write_text(new_content, encoding="utf-8")

    # Store a base64 encoded copy of the exact content we just wrote.
    encoded_content = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
    hash_file.write_text(encoded_content, encoding="utf-8")
    logger.debug(f"Updated hash file: {short_path(hash_file)}")


def write_compiled_file(output_file: Path, new_content: str, dry_run: bool = False) -> bool:
    """
    Writes a compiled file safely. If the destination file was manually edited in a meaningful way
    (i.e., the YAML data structure changed), it aborts with a descriptive error and a diff.

    Args:
        output_file: The path to the destination file.
        new_content: The full, new content to be written.
        dry_run: If True, simulate without writing.

    Returns:
        True if a file was written or would be written in a dry run, False otherwise.

    Raises:
        SystemExit: If the destination file has been manually modified.
    """
    if dry_run:
        logger.info(f"[DRY RUN] Would evaluate writing to {short_path(output_file)}")
        # In dry run, we report as if a change would happen if there is one.
        if not output_file.exists() or output_file.read_text(encoding="utf-8") != new_content:
            logger.info(f"[DRY RUN] Changes detected for {short_path(output_file)}.")
            return True
        logger.info(f"[DRY RUN] No changes for {short_path(output_file)}.")
        return False

    hash_file = output_file.with_suffix(output_file.suffix + ".hash")

    if not output_file.exists():
        logger.info(f"Output file {short_path(output_file)} does not exist. Creating.")
        write_yaml_and_hash(output_file, new_content, hash_file)
        return True

    # --- File and hash file exist, perform validation ---
    if not hash_file.exists():
        error_message = (
            f"ERROR: Destination file '{short_path(output_file)}' exists but its .hash file is missing. "
            "Aborting to prevent data loss. If you want to regenerate this file, "
            "please remove it and run the script again."
        )
        logger.error(error_message)
        raise SystemExit(1)

    # Decode the last known content from the hash file
    last_known_base64 = hash_file.read_text(encoding="utf-8").strip()
    try:
        last_known_content_bytes = base64.b64decode(last_known_base64)
        last_known_content = last_known_content_bytes.decode("utf-8")
    except (ValueError, TypeError) as e:
        error_message = (
            f"ERROR: Could not decode the .hash file for '{short_path(output_file)}'. It may be corrupted.\n"
            f"Error: {e}\n"
            "Aborting to prevent data loss. Please remove the file and its .hash file to regenerate."
        )
        logger.error(error_message)
        raise SystemExit(1) from e

    current_content = output_file.read_text(encoding="utf-8")

    # Load both YAML versions to compare their data structures
    yaml = YAML()
    try:
        current_doc = yaml.load(current_content)
        last_known_doc = yaml.load(last_known_content)
    except YAMLError as e:
        error_message = (
            f"ERROR: Could not parse YAML from '{short_path(output_file)}'. It may be corrupted.\n"
            f"Error: {e}\n"
            "Aborting. Please fix the file syntax or remove it to regenerate."
        )
        logger.error(error_message)
        raise SystemExit(1) from e

    # If the loaded documents are not identical, it means a meaningful change was made.
    if current_doc != last_known_doc:
        # Generate a diff between the *last known good version* and the *current modified version*
        diff = difflib.unified_diff(
            last_known_content.splitlines(keepends=True),
            current_content.splitlines(keepends=True),
            fromfile=f"{output_file} (last known good)",
            tofile=f"{output_file} (current, with manual edits)",
        )
        diff_text = "".join(diff)

        error_message = (
            f"\n--- MANUAL EDIT DETECTED ---\n"
            f"CANNOT OVERWRITE: The destination file below has been modified:\n"
            f"  {output_file}\n\n"
            f"The script detected that its data no longer matches the last generated version.\n"
            f"To prevent data loss, the process has been stopped.\n\n"
            f"--- DETECTED CHANGES ---\n"
            f"{diff_text if diff_text else 'No visual differences found, but YAML data structure has changed.'}\n"
            f"--- HOW TO RESOLVE ---\n"
            f"1. Revert the manual changes in '{output_file}' and run this script again.\n"
            f"OR\n"
            f"2. If the manual changes are desired, incorporate them into the source files\n"
            f"   (e.g., the .sh or uncompiled .yml files), then delete the generated file\n"
            f"   ('{output_file}') and its '.hash' file ('{hash_file}') to allow the script\n"
            f"   to regenerate it from the new base.\n"
        )
        # We use sys.exit to print the message directly and exit with an error code.
        sys.exit(error_message)

    # If we reach here, the current file is valid (or just reformatted).
    # Now, we check if the *newly generated* content is different from the current content.
    if new_content != current_content:
        logger.info(f"Content of {short_path(output_file)} has changed (reformatted or updated). Writing new version.")
        write_yaml_and_hash(output_file, new_content, hash_file)
        return True
    else:
        logger.info(f"Content of {short_path(output_file)} is already up to date. Skipping.")
        return False


def _compile_single_file(
    source_path: Path,
    output_file: Path,
    scripts_path: Path,
    variables: dict[str, str],
    uncompiled_path: Path,
    dry_run: bool,
    label: str,
) -> tuple[int, int]:
    """Compile a single YAML file and write the result.

    Returns a tuple of the number of inlined sections and whether a file was written (0 or 1).
    """
    logger.info(f"Processing {label}: {short_path(source_path)}")
    raw_text = source_path.read_text(encoding="utf-8")
    inlined_for_file, compiled_text = inline_gitlab_scripts(raw_text, scripts_path, variables, uncompiled_path)
    final_content = (BANNER + compiled_text) if inlined_for_file > 0 else raw_text
    written = write_compiled_file(output_file, final_content, dry_run)
    return inlined_for_file, int(written)


def process_uncompiled_directory(
    uncompiled_path: Path,
    output_path: Path,
    scripts_path: Path,
    templates_dir: Path,
    output_templates_dir: Path,
    dry_run: bool = False,
    parallelism: int | None = None,
) -> int:
    """
    Main function to process a directory of uncompiled GitLab CI files.
    This version safely writes files by checking hashes to avoid overwriting manual changes.

    Args:
        uncompiled_path (Path): Path to the input .gitlab-ci.yml, other yaml and bash files.
        output_path (Path): Path to write the .gitlab-ci.yml file and other yaml.
        scripts_path (Path): Optionally put all bash files into a script folder.
        templates_dir (Path): Optionally put all yaml files into a template folder.
        output_templates_dir (Path): Optionally put all compiled template files into an output template folder.
        dry_run (bool): If True, simulate the process without writing any files.
        parallelism (int | None): Maximum number of processes to use for parallel compilation.

    Returns:
        The total number of inlined sections across all files.
    """
    total_inlined_count = 0
    written_files_count = 0

    if not dry_run:
        output_path.mkdir(parents=True, exist_ok=True)
        if templates_dir.is_dir():
            output_templates_dir.mkdir(parents=True, exist_ok=True)

    global_vars = {}
    global_vars_path = uncompiled_path / "global_variables.sh"
    if global_vars_path.is_file():
        logger.info(f"Found and loading variables from {short_path(global_vars_path)}")
        content = global_vars_path.read_text(encoding="utf-8")
        global_vars = parse_env_file(content)
        total_inlined_count += 1

    files_to_process: list[tuple[Path, Path, dict[str, str], str]] = []

    root_yaml = uncompiled_path / ".gitlab-ci.yml"
    if not root_yaml.exists():
        root_yaml = uncompiled_path / ".gitlab-ci.yaml"

    if root_yaml.is_file():
        output_root_yaml = output_path / root_yaml.name
        files_to_process.append((root_yaml, output_root_yaml, global_vars, "root file"))

    if templates_dir.is_dir():
        template_files = list(templates_dir.rglob("*.yml")) + list(templates_dir.rglob("*.yaml"))
        if not template_files:
            logger.warning(f"No template YAML files found in {templates_dir}")

        for template_path in template_files:
            relative_path = template_path.relative_to(templates_dir)
            output_file = output_templates_dir / relative_path
            files_to_process.append((template_path, output_file, {}, "template file"))

    total_files = len(files_to_process)
    max_workers = multiprocessing.cpu_count()
    if parallelism and parallelism > 0:
        max_workers = min(parallelism, max_workers)

    if total_files >= 5 and max_workers > 1 and parallelism:
        args_list = [
            (src, out, scripts_path, variables, uncompiled_path, dry_run, label)
            for src, out, variables, label in files_to_process
        ]
        with multiprocessing.Pool(processes=max_workers) as pool:
            results = pool.starmap(_compile_single_file, args_list)
        total_inlined_count += sum(inlined for inlined, _ in results)
        written_files_count += sum(written for _, written in results)
    else:
        for src, out, variables, label in files_to_process:
            inlined_for_file, wrote = _compile_single_file(
                src, out, scripts_path, variables, uncompiled_path, dry_run, label
            )
            total_inlined_count += inlined_for_file
            written_files_count += wrote

    if written_files_count == 0 and not dry_run:
        logger.warning(
            "No output files were written. This could be because all files are up-to-date, or due to errors."
        )
    elif not dry_run:
        logger.info(f"Successfully processed files. {written_files_count} file(s) were created or updated.")
    elif dry_run:
        logger.info(f"[DRY RUN] Simulation complete. Would have processed {written_files_count} file(s).")

    return total_inlined_count
