## Tree for bash2gitlab
```
├── compile_all.py
├── logging_config.py
├── py.typed
├── shred_all.py
├── __about__.py
└── __main__.py
```

## File: compile_all.py
```python
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
) -> tuple[int, str]:
    """
    Loads a GitLab CI YAML file, inlines scripts, merges global variables,
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
        # A simple heuristic for a "job" is a dictionary with a 'script' key.
        if isinstance(job_data, dict) and "script" in job_data:
            logger.info(f"Processing job: {job_name}")
            inlined_count += process_job(job_data, scripts_root, script_sources)
        if isinstance(job_data, dict) and "hooks" in job_data:
            if isinstance(job_data["hooks"], dict) and "pre_get_sources_script" in job_data["hooks"]:
                logger.info(f"Processing pre_get_sources_script: {job_name}")
                inlined_count += process_job(job_data["hooks"], scripts_root, script_sources)
        if isinstance(job_data, dict) and "run" in job_data:
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
            raw_text, scripts_path, script_sources, global_vars  # Pass parsed variables
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
                inlined_count, compiled = inline_gitlab_scripts(
                    raw_text,
                    scripts_path,
                    script_sources,
                    {},  # Do not pass global variables to templates
                )

                if not dry_run:
                    if inlined_count > 0:
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
```
## File: logging_config.py
```python
"""
Logging configuration.
"""

from __future__ import annotations

import os
from typing import Any

try:
    import colorlog  # noqa

    # This is only here so that I can see if colorlog is installed
    # and to keep autofixers from removing an "unused import"
    if False:  # pylint: disable=using-constant-test
        assert colorlog  # noqa # nosec
    colorlog_available = True
except ImportError:  # no qa
    colorlog_available = False


def generate_config(level: str = "DEBUG") -> dict[str, Any]:
    """
    Generate a logging configuration.
    Args:
        level: The logging level.

    Returns:
        dict: The logging configuration.
    """
    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": True,
        "formatters": {
            "standard": {"format": "[%(levelname)s] %(name)s: %(message)s"},
            "colored": {
                "()": "colorlog.ColoredFormatter",
                "format": "%(log_color)s%(levelname)-8s%(reset)s %(green)s%(message)s",
            },
        },
        "handlers": {
            "default": {
                "level": level,
                "formatter": "colored",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",  # Default is stderr
            },
        },
        "loggers": {
            "bash2gitlab": {
                "handlers": ["default"],
                "level": level,
                "propagate": False,
            }
        },
    }
    if not colorlog_available:
        del config["formatters"]["colored"]
        config["handlers"]["default"]["formatter"] = "standard"

    if os.environ.get("NO_COLOR") or os.environ.get("CI"):
        config["handlers"]["default"]["formatter"] = "standard"

    return config
```
## File: py.typed
```
# when type checking dependents, tell type checkers to use this package's types
```
## File: shred_all.py
```python
from __future__ import annotations

import io
import logging
import re
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import FoldedScalarString

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


def shred_script_block(
    script_content: list[str] | str,
    job_name: str,
    script_key: str,
    scripts_output_path: Path,
    dry_run: bool = False,
) -> tuple[str | None, str | None]:
    """
    Extracts a script block into a .sh file and returns the command to run it.

    Args:
        script_content (Union[list[str], str]): The script content from the YAML.
        job_name (str): The name of the job.
        script_key (str): The key of the script ('script', 'before_script', etc.).
        scripts_output_path (Path): The directory to save the new .sh file.
        dry_run (bool): If True, don't write any files.

    Returns:
        A tuple containing:
        - The path to the new script file (or None if no script was created).
        - The command to execute the new script (e.g., './scripts/my-job.sh').
    """
    if not script_content:
        return None, None

    # This block will handle converting CommentedSeq and its contents (which may include
    # CommentedMap objects) into a simple list of strings.
    processed_lines = []
    if isinstance(script_content, str):
        processed_lines.extend(script_content.splitlines())
    elif script_content:  # It's a list-like object (e.g., ruamel.yaml.CommentedSeq)
        yaml = YAML()
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

    full_script_content = f"{SHEBANG}\n" + "\n".join(script_lines) + "\n"

    logger.info(f"Shredding script from '{job_name}:{script_key}' to '{script_filepath}'")

    if not dry_run:
        script_filepath.parent.mkdir(parents=True, exist_ok=True)
        script_filepath.write_text(full_script_content, encoding="utf-8")
        # Make the script executable
        script_filepath.chmod(0o755)

    return str(script_filepath), execution_command


def process_shred_job(
    job_name: str,
    job_data: dict,
    scripts_output_path: Path,
    dry_run: bool = False,
) -> int:
    """
    Processes a single job definition to shred its script blocks.

    Args:
        job_name (str): The name of the job.
        job_data (dict): The dictionary representing the job's configuration.
        scripts_output_path (Path): The directory to save shredded scripts.
        dry_run (bool): If True, simulate without writing files.

    Returns:
        int: The number of script blocks shredded from this job.
    """
    shredded_count = 0
    script_keys = ["script", "before_script", "after_script", "pre_get_sources_script"]

    for key in script_keys:
        if key in job_data and job_data[key]:
            _, command = shred_script_block(job_data[key], job_name, key, scripts_output_path, dry_run)
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
    Loads a GitLab CI YAML file, shreds all script blocks into separate .sh files,
    and saves the modified YAML.

    Args:
        input_yaml_path (Path): Path to the input .gitlab-ci.yml file.
        output_yaml_path (Path): Path to write the modified .gitlab-ci.yml file.
        scripts_output_path (Path): Directory to store the generated .sh files.
        dry_run (bool): If True, simulate the process without writing any files.

    Returns:
        A tuple containing:
        - The total number of jobs processed.
        - The total number of script files created.
    """
    if not input_yaml_path.is_file():
        raise FileNotFoundError(f"Input YAML file not found: {input_yaml_path}")

    if output_yaml_path.is_dir():
        output_yaml_path = output_yaml_path / input_yaml_path.name

    logger.info(f"Loading GitLab CI configuration from: {input_yaml_path}")
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    data = yaml.load(input_yaml_path)

    jobs_processed = 0
    scripts_created = 0

    # Process all top-level keys that look like jobs
    for key, value in data.items():
        # Heuristic: A job is a dictionary that contains a 'script' key.
        if isinstance(value, dict) and "script" in value:
            logger.debug(f"Processing job: {key}")
            jobs_processed += 1
            scripts_created += process_shred_job(key, value, scripts_output_path, dry_run)

    if scripts_created > 0:
        logger.info(f"Shredded {scripts_created} script(s) from {jobs_processed} job(s).")
        if not dry_run:
            logger.info(f"Writing modified YAML to: {output_yaml_path}")
            output_yaml_path.parent.mkdir(parents=True, exist_ok=True)
            with output_yaml_path.open("w", encoding="utf-8") as f:
                yaml.dump(data, f)
    else:
        logger.info("No script blocks found to shred.")

    return jobs_processed, scripts_created
```
## File: __about__.py
```python
"""Metadata for bash2gitlab."""

__all__ = [
    "__title__",
    "__version__",
    "__description__",
    "__readme__",
    "__keywords__",
    "__license__",
    "__requires_python__",
    "__status__",
]

__title__ = "bash2gitlab"
__version__ = "0.2.0"
__description__ = "Compile bash to gitlab pipeline yaml"
__readme__ = "README.md"
__keywords__ = ["bash", "gitlab"]
__license__ = "MIT"
__requires_python__ = ">=3.8"
__status__ = "4 - Beta"
```
## File: __main__.py
```python
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
from bash2gitlab.shred_all import shred_gitlab_ci


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
        "compile", help="Compile an uncompiled directory into a standard GitLab CI structure."
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

    # --- Shred Command (add this section) ---
    shred_parser = subparsers.add_parser(
        "shred", help="Shred a GitLab CI file, extracting inline scripts into separate .sh files."
    )
    shred_parser.add_argument(
        "--in",
        dest="input_file",
        required=True,
        help="Input GitLab CI file to shred (e.g., .gitlab-ci.yml).",
    )
    shred_parser.add_argument(
        "--out",
        dest="output_file",
        required=True,
        help="Output path for the modified GitLab CI file.",
    )
    shred_parser.add_argument(
        "--scripts-out",
        required=False,
        help="Output directory to save the shredded .sh script files.",
    )
    shred_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the shredding process without writing any files.",
    )
    shred_parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose (DEBUG) logging output.")
    shred_parser.add_argument("-q", "--quiet", action="store_true", help="Disable output.")
    shred_parser.set_defaults(func=shred_handler)

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


def shred_handler(args: argparse.Namespace):
    """Handler for the 'shred' command."""
    logger = logging.getLogger(__name__)
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


if __name__ == "__main__":
    sys.exit(main())
```
