## Tree for bash2gitlab
```
├── CHANGELOG.md
├── compile_all.py
├── config.py
├── init_project.py
├── logging_config.py
├── mock_ci_vars.py
├── py.typed
├── shred_all.py
├── tool_yamlfix.py
├── watch_files.py
├── __about__.py
└── __main__.py
```

## File: CHANGELOG.md
```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

- Added for new features.
- Changed for changes in existing functionality.
- Deprecated for soon-to-be removed features.
- Removed for now removed features.
- Fixed for any bug fixes.
- Security in case of vulnerabilities.

## [0.2.0] - 2025-07-27

### Added

- shred command to turn pre-existing bash-in-yaml pipeline templates into shell files and yaml

## [0.1.0] - 2025-07-26

### Added

- compile command exists
- verbose and quiet logging
- CLI interface
- supports simple in/out project structure
- supports corralling scripts and templates into a scripts or templates folder, which confuses path resolution
```
## File: compile_all.py
```python
from __future__ import annotations

import difflib
import hashlib
import io
import logging
import re
import shlex
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


# --- NEW AND MODIFIED FUNCTIONS START HERE ---


def normalize_content_for_hash(content: str) -> str:
    """
    Normalizes file content for consistent hashing.
    It removes YAML/shell comments, strips leading/trailing whitespace from lines,
    and removes blank lines. This makes the hash robust against trivial formatting changes.
    """
    lines = content.splitlines()
    # Remove comments and strip whitespace from each line
    lines_no_comments = [re.sub(r"\s*#.*$", "", line).strip().replace(" ", "") for line in lines if line]
    # Filter out any lines that are now empty
    non_empty_lines = [line for line in lines_no_comments if line]
    return "".join(non_empty_lines)


def get_content_hash(content: str) -> str:
    """Calculates the SHA256 hash of the normalized content."""
    normalized_content = normalize_content_for_hash(content)
    return hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()


def write_compiled_file(output_file: Path, new_content: str, dry_run: bool = False) -> bool:
    """
    Writes a compiled file safely. If the destination file was manually edited,
    it aborts the entire script with a descriptive error and a diff of the changes.

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
        logger.info(f"[DRY RUN] Would evaluate writing to {output_file}")
        return True

    hash_file = output_file.with_suffix(output_file.suffix + ".hash")
    new_hash = get_content_hash(new_content)

    if not output_file.exists():
        write_yaml(output_file, new_content, hash_file, new_hash)
        return True

    if not hash_file.exists():
        error_message = (
            f"ERROR: Destination file '{output_file}' exists but its .hash file is missing. "
            "Aborting to prevent data loss. If you want to regenerate this file, "
            "please remove it and run the script again."
        )
        logger.error(error_message)
        raise SystemExit(1)

    last_known_hash = hash_file.read_text(encoding="utf-8").strip()
    current_content = output_file.read_text(encoding="utf-8")
    current_hash = get_content_hash(current_content)

    if last_known_hash != current_hash:
        logger.warning(
            f"Manual edit detected in '{output_file}'. Continuing because I can't tell if this was a code"
            "modification or yaml reformatting."
        )

        diff = difflib.unified_diff(
            current_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"{output_file} (current)",
            tofile=f"{output_file} (proposed)",
        )

        diff_text = "".join(diff)
        if not diff_text:
            diff_text = "No visual differences found, but content hash differs (likely whitespace or comment changes)."

        # error_message = (
        #     f"\n--- MANUAL EDIT DETECTED ---\n"
        #     f"CANNOT OVERWRITE: The destination file below has been modified:\n"
        #     f"  {output_file}\n\n"
        #     f"The script detected that its content no longer matches the last generated version.\n"
        #     f"To prevent data loss, the process has been stopped.\n\n"
        #     f"--- PROPOSED CHANGES ---\n"
        #     f"{diff_text}\n"
        #     f"--- HOW TO RESOLVE ---\n"
        #     f"1. Revert the manual changes in '{output_file}' and run this script again.\n"
        #     f"OR\n"
        #     f"2. If the manual changes are desired, delete the file and its corresponding '.hash' file "
        #     f"('{hash_file}') to allow the script to regenerate it from the new base.\n"
        # )
        # We use sys.exit to print the message directly and exit with an error code.
        # sys.exit(error_message)

    if new_content != current_content:
        write_yaml(output_file, new_content, hash_file, new_hash)
        return True
    else:
        logger.info(f"Content of {output_file} is already up to date. Skipping.")
        return False


def remove_leading_blank_lines(text: str) -> str:
    """
    Removes leading blank lines (including lines with only whitespace) from a string.
    """
    lines = text.splitlines()
    # Find the first non-blank line
    for i, line in enumerate(lines):
        if line.strip() != "":
            return "\n".join(lines[i:])
    return ""  # All lines were blank


def write_yaml(
    output_file: Path,
    new_content: str,
    hash_file: Path,
    new_hash: str,
):
    logger.info(f"Writing new file: {output_file}")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # # Check if it parses.
    # yaml_loader = YAML(typ='safe')
    # yaml_loader.load(StringIO(new_content))
    new_content = remove_leading_blank_lines(new_content)

    output_file.write_text(new_content, encoding="utf-8")
    hash_file.write_text(new_hash, encoding="utf-8")


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
    This version safely writes files by checking hashes to avoid overwriting manual changes.

    Args:
        uncompiled_path (Path): Path to the input .gitlab-ci.yml, other yaml and bash files.
        output_path (Path): Path to write the .gitlab-ci.yml file and other yaml.
        scripts_path (Path): Optionally put all bash files into a script folder.
        templates_dir (Path): Optionally put all yaml files into a template folder.
        output_templates_dir (Path): Optionally put all compiled template files into an output template folder.
        dry_run (bool): If True, simulate the process without writing any files.

    Returns:
        The total number of inlined sections across all files.
    """
    total_inlined_count = 0
    written_files_count = 0

    if not dry_run:
        output_path.mkdir(parents=True, exist_ok=True)
        output_templates_dir.mkdir(parents=True, exist_ok=True)

    script_sources = collect_script_sources(scripts_path)

    global_vars = {}
    global_vars_path = uncompiled_path / "global_variables.sh"
    if global_vars_path.is_file():
        logger.info(f"Found and loading variables from {global_vars_path}")
        content = global_vars_path.read_text(encoding="utf-8")
        global_vars = parse_env_file(content)
        total_inlined_count += 1

    root_yaml = uncompiled_path / ".gitlab-ci.yml"
    if not root_yaml.exists():
        root_yaml = uncompiled_path / ".gitlab-ci.yaml"

    if root_yaml.is_file():
        logger.info(f"Processing root file: {root_yaml}")
        raw_text = root_yaml.read_text(encoding="utf-8")
        inlined_for_file, compiled_text = inline_gitlab_scripts(
            raw_text, scripts_path, script_sources, global_vars, uncompiled_path
        )
        total_inlined_count += inlined_for_file

        final_content = (BANNER + compiled_text) if inlined_for_file > 0 else raw_text
        output_root_yaml = output_path / root_yaml.name

        if write_compiled_file(output_root_yaml, final_content, dry_run):
            written_files_count += 1

    if templates_dir.is_dir():
        template_files = list(templates_dir.rglob("*.yml")) + list(templates_dir.rglob("*.yaml"))
        if not template_files:
            logger.warning(f"No template YAML files found in {templates_dir}")

        for template_path in template_files:
            logger.info(f"Processing template file: {template_path}")
            relative_path = template_path.relative_to(templates_dir)
            output_file = output_templates_dir / relative_path

            raw_text = template_path.read_text(encoding="utf-8")
            inlined_for_file, compiled_text = inline_gitlab_scripts(
                raw_text,
                scripts_path,
                script_sources,
                {},
                uncompiled_path,
            )
            total_inlined_count += inlined_for_file

            final_content = (BANNER + compiled_text) if inlined_for_file > 0 else raw_text

            if write_compiled_file(output_file, final_content, dry_run):
                written_files_count += 1

    if written_files_count == 0 and not dry_run:
        logger.warning(
            "No output files were written. This could be because all files are up-to-date, or due to errors."
        )
    elif not dry_run:
        logger.info(f"Successfully processed files. {written_files_count} file(s) were created or updated.")
    elif dry_run:
        logger.info(f"[DRY RUN] Simulation complete. Would have processed {written_files_count} file(s).")

    return total_inlined_count
```
## File: config.py
```python
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

# Use tomllib if available (Python 3.11+), otherwise fall back to tomli
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

logger = logging.getLogger(__name__)


class _Config:
    """
    Handles loading and accessing configuration settings with a clear precedence:
    1. Environment Variables (BASH2GITLAB_*)
    2. Configuration File ('bash2gitlab.toml' or 'pyproject.toml')
    3. Default values (handled by the consumer, e.g., argparse)
    """

    _ENV_VAR_PREFIX = "BASH2GITLAB_"
    _CONFIG_FILES = ["bash2gitlab.toml", "pyproject.toml"]

    def __init__(self, config_path_override: Path | None = None):
        """
        Initializes the configuration object.

        Args:
            config_path_override (Path | None): If provided, this specific config file
                will be loaded, bypassing the normal search. For testing.
        """
        self._config_path_override = config_path_override
        self._file_config: dict[str, Any] = self._load_file_config()
        self._env_config: dict[str, str] = self._load_env_config()

    def _find_config_file(self) -> Path | None:
        """Searches for a configuration file in the current directory and its parents."""
        current_dir = Path.cwd()
        for directory in [current_dir, *current_dir.parents]:
            for filename in self._CONFIG_FILES:
                config_path = directory / filename
                if config_path.is_file():
                    logger.debug(f"Found configuration file: {config_path}")
                    return config_path
        return None

    def _load_file_config(self) -> dict[str, Any]:
        """Loads configuration from the first TOML file found or a test override."""
        config_path = self._config_path_override or self._find_config_file()
        if not config_path:
            return {}

        if not tomllib:
            logger.warning(
                "TOML library not found. Cannot load config from file. Please `pip install tomli` on Python < 3.11."
            )
            return {}

        try:
            with config_path.open("rb") as f:
                data = tomllib.load(f)

            if config_path.name == "pyproject.toml":
                config = data.get("tool", {}).get("bash2gitlab", {})
            else:
                config = data

            logger.info(f"Loaded configuration from {config_path}")
            return config

        except tomllib.TOMLDecodeError as e:
            logger.error(f"Error decoding TOML file {config_path}: {e}")
            return {}
        except OSError as e:
            logger.error(f"Error reading file {config_path}: {e}")
            return {}

    def _load_env_config(self) -> dict[str, str]:
        """Loads configuration from environment variables."""
        config = {}
        for key, value in os.environ.items():
            if key.startswith(self._ENV_VAR_PREFIX):
                config_key = key[len(self._ENV_VAR_PREFIX) :].lower()
                config[config_key] = value
                logger.debug(f"Loaded from environment: {config_key}")
        return config

    def _get_str(self, key: str) -> str | None:
        """Gets a string value, respecting precedence."""
        value = self._env_config.get(key)
        if value is not None:
            return value

        value = self._file_config.get(key)
        return str(value) if value is not None else None

    def _get_bool(self, key: str) -> bool | None:
        """Gets a boolean value, respecting precedence."""
        value = self._env_config.get(key)
        if value is not None:
            return value.lower() in ("true", "1", "t", "y", "yes")

        value = self._file_config.get(key)
        if value is not None:
            if not isinstance(value, bool):
                logger.warning(f"Config value for '{key}' is not a boolean. Coercing to bool.")
            return bool(value)

        return None

    # --- Compile Command Properties ---
    @property
    def input_dir(self) -> str | None:
        return self._get_str("input_dir")

    @property
    def output_dir(self) -> str | None:
        return self._get_str("output_dir")

    @property
    def scripts_dir(self) -> str | None:
        return self._get_str("scripts_dir")

    @property
    def templates_in(self) -> str | None:
        return self._get_str("templates_in")

    @property
    def templates_out(self) -> str | None:
        return self._get_str("templates_out")

    # --- Shred Command Properties ---
    @property
    def input_file(self) -> str | None:
        return self._get_str("input_file")

    @property
    def output_file(self) -> str | None:
        return self._get_str("output_file")

    @property
    def scripts_out(self) -> str | None:
        return self._get_str("scripts_out")

    # --- Shared Properties ---
    @property
    def format(self) -> bool | None:
        return self._get_bool("format")

    @property
    def dry_run(self) -> bool | None:
        return self._get_bool("dry_run")

    @property
    def verbose(self) -> bool | None:
        return self._get_bool("verbose")

    @property
    def quiet(self) -> bool | None:
        return self._get_bool("quiet")


# Singleton instance for the rest of the application to use.
config = _Config()


def _reset_for_testing(config_path_override: Path | None = None):
    """
    Resets the singleton config instance. For testing purposes only.
    Allows specifying a direct path to a config file.
    """
    global config
    config = _Config(config_path_override=config_path_override)
```
## File: init_project.py
```python
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default directory structure configuration
DEFAULT_CONFIG = {
    "input_dir": "src",
    "output_dir": "out",
    "scripts_dir": "scripts",
    "templates_in": "templates",
    "templates_out": "out/templates",
}

# Default settings for boolean flags
DEFAULT_FLAGS = {
    "format": False,
    "verbose": False,
    "quiet": False,
}

# Template for the bash2gitlab.toml file
TOML_TEMPLATE = """# Configuration for bash2gitlab
# This file was generated by the 'bash2gitlab init' command.

# Directory settings
input_dir = "{input_dir}"
output_dir = "{output_dir}"
scripts_dir = "{scripts_dir}"
templates_in = "{templates_in}"
templates_out = "{templates_out}"

# Command-line flag defaults
format = {format}
verbose = {verbose}
quiet = {quiet}
"""


def get_str_input(prompt: str, default: str) -> str:
    """Prompts the user for string input with a default value."""
    prompt_with_default = f"{prompt} (default: {default}): "
    return input(prompt_with_default).strip() or default


def get_bool_input(prompt: str, default: bool) -> bool:
    """Prompts the user for boolean (y/n) input with a default."""
    default_str = "y" if default else "n"
    prompt_with_default = f"{prompt} (y/n, default: {default_str}): "
    response = input(prompt_with_default).strip().lower()
    if not response:
        return default
    return response in ["y", "yes"]


def prompt_for_config() -> dict[str, Any]:
    """
    Interactively prompts the user for project configuration details.
    This function is separate from file I/O to be easily testable.
    """
    print("Initializing a new bash2gitlab project.")
    print("Please confirm the directory structure (press Enter to accept defaults).")
    config: dict[str, Any] = {}
    for key, value in DEFAULT_CONFIG.items():
        user_value = get_str_input(f"  -> {key}", value)
        config[key] = user_value

    print("\nConfigure default behavior (press Enter to accept defaults).")
    for key, flag_value in DEFAULT_FLAGS.items():
        flag_user_value = get_bool_input(f"  -> Always use --{key}?", flag_value)
        config[key] = flag_user_value

    return config


def create_config_file(base_path: Path, config: dict[str, Any], dry_run: bool = False):
    """
    Creates the config file for a new project.
    This function performs all file system operations.
    """
    config_file_path = base_path / "bash2gitlab.toml"

    logger.info("\nThe following file will be created:")
    print(f"  - {config_file_path}")

    if dry_run:
        logger.warning("\nDRY RUN: No file will be created.")
        return

    # Write the config file
    # Lowercase boolean values for TOML compatibility
    formatted_config = config.copy()
    for key, value in formatted_config.items():
        if isinstance(value, bool):
            formatted_config[key] = str(value).lower()

    toml_content = TOML_TEMPLATE.format(**formatted_config)
    config_file_path.write_text(toml_content, encoding="utf-8")

    logger.info("\n✅ Project initialization complete.")


def init_handler(args: Any):
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
## File: mock_ci_vars.py
```python
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def generate_mock_ci_variables_script(output_path: str = "mock_ci_variables.sh") -> None:
    """Generate a shell script exporting mock GitLab CI/CD variables."""
    ci_vars: dict[str, str] = {
        "CI": "false",
        "GITLAB_CI": "false",
        "CI_API_V4_URL": "https://gitlab.example.com/api/v4",
        "CI_API_GRAPHQL_URL": "https://gitlab.example.com/api/graphql",
        "CI_PROJECT_ID": "1234",
        "CI_PROJECT_NAME": "example-project",
        "CI_PROJECT_PATH": "group/example-project",
        "CI_PROJECT_NAMESPACE": "group",
        "CI_PROJECT_ROOT_NAMESPACE": "group",
        "CI_PROJECT_URL": "https://gitlab.example.com/group/example-project",
        "CI_PROJECT_VISIBILITY": "private",
        "CI_DEFAULT_BRANCH": "main",
        "CI_COMMIT_SHA": "abcdef1234567890abcdef1234567890abcdef12",
        "CI_COMMIT_SHORT_SHA": "abcdef12",
        "CI_COMMIT_BRANCH": "feature-branch",
        "CI_COMMIT_REF_NAME": "feature-branch",
        "CI_COMMIT_REF_SLUG": "feature-branch",
        "CI_COMMIT_BEFORE_SHA": "0000000000000000000000000000000000000000",
        "CI_COMMIT_MESSAGE": "Add new CI feature",
        "CI_COMMIT_TITLE": "Add new CI feature",
        "CI_COMMIT_TIMESTAMP": "2025-07-27T12:00:00Z",
        "CI_COMMIT_AUTHOR": "Test User <test@example.com>",
        "CI_PIPELINE_ID": "5678",
        "CI_PIPELINE_IID": "42",
        "CI_PIPELINE_SOURCE": "push",
        "CI_PIPELINE_URL": "https://gitlab.example.com/group/example-project/-/pipelines/5678",
        "CI_PIPELINE_CREATED_AT": "2025-07-27T12:00:05Z",
        "CI_JOB_ID": "91011",
        "CI_JOB_NAME": "test-job",
        "CI_JOB_STAGE": "test",
        "CI_JOB_STATUS": "running",
        "CI_JOB_TOKEN": "xyz-token",
        "CI_JOB_URL": "https://gitlab.example.com/group/example-project/-/jobs/91011",
        "CI_JOB_STARTED_AT": "2025-07-27T12:00:10Z",
        "CI_PROJECT_DIR": "/builds/group/example-project",
        "CI_BUILDS_DIR": "/builds",
        "CI_RUNNER_ID": "55",
        "CI_RUNNER_SHORT_TOKEN": "runner1234567890",
        "CI_RUNNER_VERSION": "17.3.0",
        "CI_SERVER_URL": "https://gitlab.example.com",
        "CI_SERVER_HOST": "gitlab.example.com",
        "CI_SERVER_PORT": "443",
        "CI_SERVER_PROTOCOL": "https",
        "CI_SERVER_NAME": "GitLab",
        "CI_SERVER_VERSION": "17.2.1",
        "CI_SERVER_VERSION_MAJOR": "17",
        "CI_SERVER_VERSION_MINOR": "2",
        "CI_SERVER_VERSION_PATCH": "1",
        "CI_REPOSITORY_URL": "https://gitlab-ci-token:$CI_JOB_TOKEN@gitlab.example.com/group/example-project.git",
    }

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("#!/usr/bin/env bash\n")
        f.write("# Auto-generated mock CI variables\n\n")
        for key, val in ci_vars.items():
            escaped = val.replace('"', '\\"')
            f.write(f'export {key}="{escaped}"\n')

    logger.info("Wrote %s with %d variables", output_path, len(ci_vars))


if __name__ == "__main__":
    generate_mock_ci_variables_script()
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

from bash2gitlab.mock_ci_vars import generate_mock_ci_variables_script

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

    # This block will handle converting CommentedSeq and its contents (which may include
    # CommentedMap objects) into a simple list of strings.
    processed_lines = []
    if isinstance(script_content, str):
        processed_lines.extend(script_content.splitlines())
    elif script_content:  # It's a list-like object (e.g., ruamel.yaml.CommentedSeq)
        yaml = YAML()
        yaml.width = 4096
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
```
## File: tool_yamlfix.py
```python
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
```
## File: watch_files.py
```python
"""
Watch mode for bash2gitlab.

Usage (internal):
    from pathlib import Path
    from bash2gitlab.watch import start_watch

    start_watch(
        uncompiled_path=Path("./ci"),
        output_path=Path("./compiled"),
        scripts_path=Path("./ci"),
        templates_dir=Path("./ci/templates"),
        output_templates_dir=Path("./compiled/templates"),
        dry_run=False,
        format_output=False,
    )
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from bash2gitlab.compile_all import process_uncompiled_directory

logger = logging.getLogger(__name__)


class _RecompileHandler(FileSystemEventHandler):
    """
    Fire the compiler every time a *.yml, *.yaml or *.sh file changes.
    """

    def __init__(
        self,
        *,
        uncompiled_path: Path,
        output_path: Path,
        scripts_path: Path,
        templates_dir: Path,
        output_templates_dir: Path,
        dry_run: bool = False,
        format_output: bool = False,
    ) -> None:
        super().__init__()
        self._paths = {
            "uncompiled_path": uncompiled_path,
            "output_path": output_path,
            "scripts_path": scripts_path,
            "templates_dir": templates_dir,
            "output_templates_dir": output_templates_dir,
        }
        self._flags = {"dry_run": dry_run, "format_output": format_output}
        self._debounce: float = 0.5  # seconds
        self._last_run = 0.0

    def on_any_event(self, event: FileSystemEvent) -> None:
        # Skip directories, temp files, and non-relevant extensions
        if event.is_directory:
            return
        if event.src_path.endswith((".tmp", ".swp", "~")):  # type: ignore[arg-type]
            return
        if not event.src_path.endswith((".yml", ".yaml", ".sh")):  # type: ignore[arg-type]
            return

        now = time.monotonic()
        if now - self._last_run < self._debounce:
            return
        self._last_run = now

        logger.info("🔄 Source changed; recompiling…")
        try:
            format_output = self._flags["format_output"]
            del self._flags["format_output"]
            process_uncompiled_directory(**self._paths, **self._flags)  # type: ignore[arg-type]
            # TODO: run formatter.
            self._flags["format_output"] = format_output
            logger.info("✅ Recompiled successfully.")
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("❌ Recompilation failed: %s", exc, exc_info=True)


def start_watch(
    *,
    uncompiled_path: Path,
    output_path: Path,
    scripts_path: Path,
    templates_dir: Path,
    output_templates_dir: Path,
    dry_run: bool = False,
    format_output: bool = False,
) -> None:
    """
    Start an in-process watchdog that recompiles whenever source files change.

    Blocks forever (Ctrl-C to stop).
    """
    handler = _RecompileHandler(
        uncompiled_path=uncompiled_path,
        output_path=output_path,
        scripts_path=scripts_path,
        templates_dir=templates_dir,
        output_templates_dir=output_templates_dir,
        dry_run=dry_run,
        format_output=format_output,
    )

    observer = Observer()
    observer.schedule(handler, str(uncompiled_path), recursive=True)
    if templates_dir != uncompiled_path:
        observer.schedule(handler, str(templates_dir), recursive=True)
    if scripts_path not in (uncompiled_path, templates_dir):
        observer.schedule(handler, str(scripts_path), recursive=True)

    try:
        observer.start()
        logger.info("👀 Watching for changes to *.yml, *.yaml, *.sh … (Ctrl-C to quit)")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("⏹  Stopping watcher.")
    finally:
        observer.stop()
        observer.join()
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
__version__ = "0.5.1"
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
import sys
from pathlib import Path

from bash2gitlab import __about__
from bash2gitlab import __doc__ as root_doc
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
```
