from __future__ import annotations

import io
import logging
import re
import shlex
import shutil
from pathlib import Path
from typing import Union

from ruamel.yaml import YAML, CommentedMap
from ruamel.yaml.scalarstring import LiteralScalarString

logger = logging.getLogger(__name__)

BANNER = """# DO NOT EDIT
# This is a compiled file, compiled with bash2gitlab
# Recompile instead of editing this file.

"""


def parse_env_file(file_content: str) -> dict[str, str]:
    """
    Parses a .env-style file content into a dictionary.
    Handles lines like 'KEY=VALUE' and 'export KEY=VALUE'.

    Args:
        file_content (str): The content of the variables file.

    Returns:
        Dict[str, str]: A dictionary of the parsed variables.
    """
    variables = {}
    logger.debug("Parsing global variables file.")
    for line in file_content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Regex to handle 'export KEY=VALUE', 'KEY=VALUE', etc.
        match = re.match(r"^(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$", line)
        if match:
            key = match.group("key")
            value = match.group("value").strip()
            # Remove matching quotes from the value
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            variables[key] = value
            logger.debug(f"Found global variable: {key}")
    return variables


def extract_script_path(command_line: str) -> str | None:
    """
    Extracts the first shell script path from a shell command line.

    Args:
        command_line (str): A shell command line.

    Returns:
        Optional[str]: The script path if the line is a script invocation; otherwise, None.
    """
    try:
        tokens: list[str] = shlex.split(command_line)
    except ValueError:
        # Malformed shell syntax
        return None

    executors = {"bash", "sh", "source", "."}

    parts = 0
    path_found = None
    for i, token in enumerate(tokens):
        path = Path(token)
        if path.suffix == ".sh":
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


def read_bash_script(path: Path, script_sources: dict[str, str]) -> str:
    """Reads a bash script's content from the pre-collected source map and strips the shebang if present."""
    if str(path) not in script_sources:
        raise FileNotFoundError(f"Script not found in source map: {path}")
    logger.debug(f"Reading script from source map: {path}")
    content = script_sources[str(path)].strip()
    if not content:
        raise ValueError(f"Script is empty: {path}")

    lines = content.splitlines()
    if lines and lines[0].startswith("#!"):
        logger.debug(f"Stripping shebang from script: {lines[0]}")
        lines = lines[1:]
    return "\n".join(lines)


def process_script_list(
    script_list: Union[list[str], str], scripts_root: Path, script_sources: dict[str, str]
) -> Union[list[str], LiteralScalarString]:
    """
    Processes a list of script lines, inlining any shell script references.
    Returns a new list of lines or a single literal scalar string for long scripts.
    """
    if isinstance(script_list, str):
        script_list = [script_list]

    # First pass: check for any long scripts. If one is found, it takes over the whole block.
    for line in script_list:
        script_path_str = extract_script_path(line) if isinstance(line, str) else None
        if script_path_str:
            rel_path = script_path_str.strip().lstrip("./")
            script_path = scripts_root / rel_path
            bash_code = read_bash_script(script_path, script_sources)
            # If a script is long, we replace the entire block for clarity.
            if len(bash_code.splitlines()) > 3:
                logger.info(f"Inlining long script '{script_path}' as a single block.")
                return LiteralScalarString(bash_code)

    # Second pass: if no long scripts were found, inline all scripts line-by-line.
    inlined_lines: list[str] = []
    for line in script_list:
        script_path_str = extract_script_path(line) if isinstance(line, str) else None
        if script_path_str:
            rel_path = script_path_str.strip().lstrip("./")
            script_path = scripts_root / rel_path
            bash_code = read_bash_script(script_path, script_sources)
            bash_lines = bash_code.splitlines()
            logger.info(f"Inlining short script '{script_path}' ({len(bash_lines)} lines).")
            inlined_lines.extend(bash_lines)
        else:
            inlined_lines.append(line)

    return inlined_lines


def process_job(job_data: dict, scripts_root: Path, script_sources: dict[str, str]) -> int:
    """Processes a single job definition to inline scripts."""
    found = 0
    for script_key in ["script", "before_script", "after_script", "pre_get_sources_script"]:
        if script_key in job_data:
            result = process_script_list(job_data[script_key], scripts_root, script_sources)
            if result != job_data[script_key]:
                job_data[script_key] = result
                found += 1
    return found


def inline_gitlab_scripts(
    gitlab_ci_yaml: str,
    scripts_root: Path,
    script_sources: dict[str, str],
    global_vars: dict[str, str],
    uncompiled_path: Path,  # Path to look for job_name_variables.sh files
) -> tuple[int, str]:
    """
    Loads a GitLab CI YAML file, inlines scripts, merges global and job-specific variables,
    reorders top-level keys, and returns the result as a string.
    """
    inlined_count = 0
    yaml = YAML()
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
            result = process_script_list(data[name], scripts_root, script_sources)
            if result != data[name]:
                data[name] = result
                inlined_count += 1

    # Process all jobs
    for job_name, job_data in data.items():
        if isinstance(job_data, dict):
            # FIX: Look for and process job-specific variables file
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
            if "script" in job_data:
                logger.info(f"Processing job: {job_name}")
                inlined_count += process_job(job_data, scripts_root, script_sources)
            if "hooks" in job_data:
                if isinstance(job_data["hooks"], dict) and "pre_get_sources_script" in job_data["hooks"]:
                    logger.info(f"Processing pre_get_sources_script: {job_name}")
                    inlined_count += process_job(job_data["hooks"], scripts_root, script_sources)
            if "run" in job_data:
                if isinstance(job_data["run"], list):
                    for item in job_data["run"]:
                        if isinstance(item, dict) and "script" in item:
                            logger.info(f"Processing run/script: {job_name}")
                            inlined_count += process_job(item, scripts_root, script_sources)

    # --- Reorder top-level keys for consistent output ---
    logger.info("Reordering top-level keys in the final YAML.")
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


def collect_script_sources(scripts_dir: Path) -> dict[str, str]:
    """Recursively finds all .sh files and reads them into a dictionary."""
    if not scripts_dir.is_dir():
        raise FileNotFoundError(f"Scripts directory not found: {scripts_dir}")

    script_sources = {}
    for script_file in scripts_dir.glob("**/*.sh"):
        content = script_file.read_text(encoding="utf-8").strip()
        if not content:
            logger.warning(f"Script is empty and will be ignored: {script_file}")
            continue
        script_sources[str(script_file)] = content

    if not script_sources:
        raise RuntimeError(f"No non-empty scripts found in '{scripts_dir}'.")

    return script_sources


def process_uncompiled_directory(
    uncompiled_path: Path,
    output_path: Path,
    scripts_path: Path,
    templates_dir: Path,
    output_templates_dir: Path,
    dry_run: bool = False,
) -> int:
    """
    Main function to process a directory of uncompiled GitLab CI files.

    Args:
        uncompiled_path (Path): Path to the input .gitlab-ci.yml, other yaml and bash files.
        output_path (Path): Path to write the .gitlab-ci.yml file and other yaml.
        scripts_path (Path): Optionally put all bash files into a script folder.
        templates_dir (Path): Optionally put all yaml files into a template folder.
        output_templates_dir (Path): Optionally put all compiled template files into an output template folder.
        dry_run (bool): If True, simulate the process without writing any files.

    Returns:
        - The total number of jobs processed.
    """
    inlined_count = 0
    # Safely clean up previous outputs
    logger.info(f"Cleaning previous output in '{output_path}' and '{output_templates_dir}'")
    for extension in ["yml", "yaml"]:
        if (output_path / f".gitlab-ci.{extension}").exists():
            (output_path / f".gitlab-ci.{extension}").unlink()
    if output_templates_dir != uncompiled_path and output_templates_dir.exists() and not dry_run:
        shutil.rmtree(output_templates_dir)

    if not dry_run:
        output_templates_dir.mkdir(parents=True, exist_ok=True)

    script_sources = collect_script_sources(scripts_path)
    written_files = 0

    # Load global variables from the special file, if it exists
    global_vars = {}
    global_vars_path = uncompiled_path / "global_variables.sh"
    if global_vars_path.is_file():
        logger.info(f"Found and loading variables from {global_vars_path}")
        content = global_vars_path.read_text(encoding="utf-8")
        global_vars = parse_env_file(content)
        inlined_count += 1

    # Process root .gitlab-ci.yml
    root_yaml_extension = "yml"
    root_yaml = uncompiled_path / f".gitlab-ci.{root_yaml_extension}"
    if not root_yaml.exists():
        root_yaml_extension = "yaml"
        root_yaml = uncompiled_path / ".gitlab-ci.yaml"

    output_root_yaml: Path | None = None
    if root_yaml.is_file():
        logger.info(f"Processing root file: {root_yaml}")
        raw_text = root_yaml.read_text(encoding="utf-8")
        inlined_for_file, compiled = inline_gitlab_scripts(
            raw_text,
            scripts_path,
            script_sources,
            global_vars,
            uncompiled_path,  # Pass the path for finding job-specific vars
        )
        inlined_count += inlined_for_file
        output_root_yaml = output_path / f".gitlab-ci.{root_yaml_extension}"
        if not dry_run:
            if inlined_for_file:
                output_root_yaml.write_text(BANNER + compiled, encoding="utf-8")
            else:
                output_root_yaml.write_text(raw_text, encoding="utf-8")

        written_files += 1

    # Process templates/*.yml and *.yaml
    if templates_dir.is_dir():
        template_files = list(templates_dir.glob("*.yml")) + list(templates_dir.glob("*.yaml"))
        if not template_files:
            logger.warning(f"No template YAML files found in {templates_dir}")

        for template_path in template_files:
            output_to_write = output_templates_dir / template_path.name
            if output_root_yaml != output_to_write:
                logger.info(f"Processing template file: {template_path}")
                raw_text = template_path.read_text(encoding="utf-8")
                inlined_for_file, compiled = inline_gitlab_scripts(
                    raw_text,
                    scripts_path,
                    script_sources,
                    {},  # Do not pass global variables to templates
                    uncompiled_path,  # Pass the path for finding job-specific vars
                )
                inlined_count += inlined_for_file

                if not dry_run:
                    if inlined_for_file > 0:
                        # inlines happened
                        output_to_write.write_text(BANNER + compiled, encoding="utf-8")
                    else:
                        # no change
                        output_to_write.write_text(raw_text, encoding="utf-8")
                written_files += 1

    if written_files == 0:
        raise RuntimeError("No output files were written. Check input paths and file names.")
    else:
        logger.info(f"Successfully processed and wrote {written_files} file(s).")

    return inlined_count
