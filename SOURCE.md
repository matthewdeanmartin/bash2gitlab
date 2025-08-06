## Tree for bash2gitlab
```
├── bash_reader.py
├── clone2local.py
├── compile_all.py
├── config.py
├── init_project.py
├── logging_config.py
├── mock_ci_vars.py
├── py.typed
├── shred_all.py
├── update_checker.py
├── utils.py
├── watch_files.py
├── __about__.py
└── __main__.py
```

## File: bash_reader.py
```python
from __future__ import annotations

import logging
import re
from pathlib import Path

# Set up a logger for this module
logger = logging.getLogger(__name__)

# Regex to match 'source file.sh' or '. file.sh'
# It ensures the line contains nothing else but the sourcing command.
# - ^\s* - Start of the line with optional whitespace.
# - (?:source|\.) - Non-capturing group for 'source' or '.'.
# - \s+         - At least one whitespace character.
# - (?P<path>[\w./\\-]+) - Captures the file path.
# - \s*$        - Optional whitespace until the end of the line.
SOURCE_COMMAND_REGEX = re.compile(r"^\s*(?:source|\.)\s+(?P<path>[\w./\\-]+)\s*$")


def inline_bash_source(main_script_path: Path, processed_files: set[Path] | None = None) -> str:
    """
    Reads a bash script and recursively inlines content from sourced files.

    This function processes a bash script, identifies any 'source' or '.' commands,
    and replaces them with the content of the specified script. It handles
    nested sourcing and prevents infinite loops from circular dependencies.

    Args:
        main_script_path: The absolute path to the main bash script to process.
        processed_files: A set used internally to track already processed files
                         to prevent circular sourcing. Should not be set manually.

    Returns:
        A string containing the script content with all sourced files inlined.

    Raises:
        FileNotFoundError: If the main_script_path or any sourced script does not exist.
    """
    # Initialize the set to track processed files on the first call
    if processed_files is None:
        processed_files = set()

    # Resolve the absolute path to handle relative paths correctly
    main_script_path = main_script_path.resolve()

    # Prevent circular sourcing by checking if the file has been processed
    if main_script_path in processed_files:
        logger.warning(f"Circular source detected and skipped: {main_script_path}")
        return ""

    # Check if the script exists before trying to read it
    if not main_script_path.is_file():
        raise FileNotFoundError(f"Script not found: {main_script_path}")

    logger.debug(f"Processing script: {main_script_path}")
    processed_files.add(main_script_path)

    final_content_lines = []
    try:
        with main_script_path.open("r", encoding="utf-8") as f:
            for line in f:
                match = SOURCE_COMMAND_REGEX.match(line)
                if match:
                    # A source command was found, process the sourced file
                    sourced_script_name = match.group("path")
                    # Resolve the path relative to the current script's directory
                    sourced_script_path = (main_script_path.parent / sourced_script_name).resolve()

                    logger.info(f"Inlining sourced file: {sourced_script_name} -> {sourced_script_path}")

                    # Recursively call the function to inline the nested script
                    inlined_content = inline_bash_source(sourced_script_path, processed_files)
                    final_content_lines.append(inlined_content)
                else:
                    # This line is not a source command, so keep it as is
                    final_content_lines.append(line)
    except Exception as e:
        logger.error(f"Failed to read or process {main_script_path}: {e}")
        # Re-raise the exception to notify the caller of the failure
        raise

    return "".join(final_content_lines)
```
## File: clone2local.py
```python
from __future__ import annotations

import logging
import shutil
import subprocess  # nosec
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


def fetch_repository_archive(repo_url: str, branch: str, source_dir: str, clone_dir: str | Path) -> None:
    """
    Fetches a repository archive for a specific branch, extracts it, and copies directories.

    This function avoids using Git. It downloads the repository as a ZIP archive,
    unpacks it to a temporary location, and then copies only the requested
    directories to the final destination. It performs cleanup of all temporary
    files upon completion or in case of an error.

    Args:
        repo_url:
            The URL of the repository (e.g., 'https://github.com/user/repo').
        branch:
            The name of the branch to download (e.g., 'main', 'develop').
        source_dir:
            A sequence of directory paths (relative to the repo root) to
            extract and copy to the clone_dir.
        clone_dir:
            The destination directory. This directory must be empty before the
            operation begins.

    Raises:
        FileExistsError:
            If the clone_dir exists and is not empty.
        ConnectionError:
            If the specified branch archive cannot be found or accessed.
        IOError:
            If the downloaded archive has an unexpected file structure.
        Exception:
            Propagates exceptions from network, file, or archive operations.
    """
    clone_path = Path(clone_dir)
    logger.debug(
        "Fetching archive for repo %s (branch: %s) into %s with dir %s",
        repo_url,
        branch,
        clone_path,
        source_dir,
    )

    # 1. Validate that the destination directory is empty.
    if clone_path.exists() and any(clone_path.iterdir()):
        raise FileExistsError(f"Destination directory '{clone_path}' exists and is not empty.")
    # Ensure the directory exists, but don't error if it's already there (as long as it's empty)
    clone_path.mkdir(parents=True, exist_ok=True)

    try:
        # Use a temporary directory that cleans itself up automatically.
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            archive_path = temp_path / "repo.zip"
            unzip_root = temp_path / "unzipped"
            unzip_root.mkdir()

            # 2. Construct the archive URL and check for its existence.
            archive_url = f"{repo_url.rstrip('/')}/archive/refs/heads/{branch}.zip"
            if not archive_url.startswith("http"):
                raise TypeError(f"Expected http or https protocol, got {archive_url}")
            try:
                # Use a simple open to verify existence without a full download.

                with urllib.request.urlopen(archive_url, timeout=10) as _response:  # nosec
                    # The 'with' block itself confirms a 2xx status.
                    logger.info("Confirmed repository archive exists at: %s", archive_url)
            except urllib.error.HTTPError as e:
                # Re-raise with a more specific message for clarity.
                raise ConnectionError(
                    f"Could not find archive for branch '{branch}' at '{archive_url}'. "
                    f"Please check the repository URL and branch name. (HTTP Status: {e.code})"
                ) from e
            except urllib.error.URLError as e:
                raise ConnectionError(f"A network error occurred while verifying the URL: {e.reason}") from e

            logger.info("Downloading archive to %s", archive_path)

            urllib.request.urlretrieve(archive_url, archive_path)  # nosec

            # 3. Unzip the downloaded archive.
            logger.info("Extracting archive to %s", unzip_root)
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(unzip_root)

            # The archive usually extracts into a single sub-directory (e.g., 'repo-name-main').
            # We need to find this directory to locate the source files.
            extracted_items = list(unzip_root.iterdir())
            if not extracted_items:
                raise OSError("Archive is empty.")

            # Find the single root directory within the extracted files.
            source_repo_root = None
            if len(extracted_items) == 1 and extracted_items[0].is_dir():
                source_repo_root = extracted_items[0]
            else:
                # Fallback for archives that might not have a single root folder.
                logger.warning("Archive does not contain a single root directory. Using extraction root.")
                source_repo_root = unzip_root

            # 4. Copy the specified directory to the final destination.
            logger.info("Copying specified directories to final destination.")

            repo_source_dir = source_repo_root / source_dir
            dest_dir = clone_path  # / Path(dir_name).name  # Use the basename for the destination

            if repo_source_dir.is_dir():
                logger.debug("Copying '%s' to '%s'", repo_source_dir, dest_dir)
                shutil.copytree(source_dir, dest_dir, dirs_exist_ok=True)
            else:
                logger.warning("Directory '%s' not found in repository archive, skipping.", repo_source_dir)

    except Exception as e:
        logger.error("Operation failed: %s. Cleaning up destination directory.", e)
        # 5. Clean up the destination on any failure.
        shutil.rmtree(clone_path, ignore_errors=True)
        # Re-raise the exception to notify the caller of the failure.
        raise

    logger.info("Successfully fetched directories into %s", clone_path)


def clone_repository_ssh(repo_url: str, branch: str, source_dir: str, clone_dir: str | Path) -> None:
    """
    Clones a repository using Git, checks out a branch, and copies specified directories.

    This function is designed for SSH or authenticated HTTPS URLs that require local
    Git and credential management (e.g., SSH keys). It performs a full clone into a
    temporary directory, checks out the target branch, and then copies only the
    requested directories to the final destination.

    Parameters
    ----------
    repo_url:
        The repository URL (e.g., 'git@github.com:user/repo.git').
    branch:
        The name of the branch to check out (e.g., 'main', 'develop').
    source_dir:
        Directory paths (relative to the repo root) to copy.
    clone_dir:
        The destination directory. This directory must be empty.

    Raises:
    ------
    FileExistsError:
        If the clone_dir exists and is not empty.
    subprocess.CalledProcessError:
        If any Git command fails.
    Exception:
        Propagates other exceptions from file operations.
    """
    clone_path = Path(clone_dir)
    logger.debug(
        "Cloning repo %s (branch: %s) into %s with source dir %s",
        repo_url,
        branch,
        clone_path,
        source_dir,
    )

    # 1. Validate that the destination directory is empty.
    if clone_path.exists() and any(clone_path.iterdir()):
        raise FileExistsError(f"Destination directory '{clone_path}' exists and is not empty.")
    clone_path.mkdir(parents=True, exist_ok=True)

    try:
        # Use a temporary directory for the full clone, which will be auto-cleaned.
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_clone_path = Path(temp_dir)
            logger.info("Cloning '%s' to temporary location: %s", repo_url, temp_clone_path)

            # 2. Clone the repository.
            # We clone the specific branch directly to be more efficient.
            subprocess.run(  # nosec
                ["git", "clone", "--depth", "1", "--branch", branch, repo_url, str(temp_clone_path)],
                check=True,
                capture_output=True,  # Capture stdout/stderr to hide git's noisy output
            )

            logger.info("Clone successful. Copying specified directories.")
            # 3. Copy the specified directory to the final destination.

            repo_source_dir = temp_clone_path / source_dir
            # Use the basename of the source for the destination path.
            dest_dir = clone_path

            if repo_source_dir.is_dir():
                logger.debug("Copying '%s' to '%s'", repo_source_dir, dest_dir)
                shutil.copytree(repo_source_dir, dest_dir, dirs_exist_ok=True)
            else:
                logger.warning("Directory '%s' not found in repository, skipping.", source_dir)

    except Exception as e:
        logger.error("Operation failed: %s. Cleaning up destination directory.", e)
        # 4. Clean up the destination on any failure.
        shutil.rmtree(clone_path, ignore_errors=True)
        # Re-raise the exception to notify the caller of the failure.
        raise

    logger.info("Successfully cloned directories into %s", clone_path)


def clone2local_handler(args) -> None:
    """
    Argparse handler for the clone2local command.

    This handler remains compatible with the new archive-based fetch function.
    """
    # This function now calls the new implementation, preserving the call stack.
    if str(args.repo_url).startswith("ssh"):
        return clone_repository_ssh(args.repo_url, args.branch, args.source_dir, args.copy_dir)
    return fetch_repository_archive(args.repo_url, args.branch, args.source_dir, args.copy_dir)
```
## File: compile_all.py
```python
from __future__ import annotations

import base64
import difflib
import io
import logging
import multiprocessing
import re
import shlex
import sys
from pathlib import Path
from typing import Any, Union

from ruamel.yaml import YAML, CommentedMap
from ruamel.yaml.comments import TaggedScalar
from ruamel.yaml.error import YAMLError
from ruamel.yaml.scalarstring import LiteralScalarString

from bash2gitlab.bash_reader import inline_bash_source
from bash2gitlab.utils import remove_leading_blank_lines

logger = logging.getLogger(__name__)

BANNER = """# DO NOT EDIT
# This is a compiled file, compiled with bash2gitlab
# Recompile instead of editing this file.

"""


def short_path(path: Path) -> str:
    """
    Return the path relative to the current working directory if possible.
    Otherwise, return the absolute path.

    Args:
        path (Path): The path to format for debugging.

    Returns:
        str: Relative path or absolute path as a fallback.
    """
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path.resolve())


def parse_env_file(file_content: str) -> dict[str, str]:
    """
    Parses a .env-style file content into a dictionary.
    Handles lines like 'KEY=VALUE' and 'export KEY=VALUE'.

    Args:
        file_content (str): The content of the variables file.

    Returns:
        dict[str, str]: A dictionary of the parsed variables.
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


# def read_bash_script(path: Path, script_sources: dict[str, str]) -> str:
#     """Reads a bash script's content from the pre-collected source map and strips the shebang if present."""
#     if str(path) not in script_sources:
#         raise FileNotFoundError(f"Script not found in source map: {path}")
#     logger.debug(f"Reading script from source map: {path}")
#     content = script_sources[str(path)].strip()
#     if not content:
#         raise ValueError(f"Script is empty: {path}")
#
#     lines = content.splitlines()
#     if lines and lines[0].startswith("#!"):
#         logger.debug(f"Stripping shebang from script: {lines[0]}")
#         lines = lines[1:]
#     return "\n".join(lines)


def read_bash_script(path: Path, _script_sources: dict[str, str]) -> str:
    """Reads a bash script and inlines any sourced files."""
    logger.debug(f"Reading and inlining script from: {path}")

    # Use the new bash_reader to recursively inline all `source` commands
    content = inline_bash_source(path)

    if not content.strip():
        raise ValueError(f"Script is empty or only contains whitespace: {path}")

    lines = content.splitlines()
    if lines and lines[0].startswith("#!"):
        logger.debug(f"Stripping shebang from script: {lines[0]}")
        lines = lines[1:]

    return "\n".join(lines)


def process_script_list(
    script_list: Union[list[Any], str], scripts_root: Path, script_sources: dict[str, str]
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
    is_long = False

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
                bash_code = read_bash_script(script_path, script_sources)
                bash_lines = bash_code.splitlines()

                # Check if this specific script is long
                if len(bash_lines) > 3:
                    is_long = True

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
    if not contains_tagged_scalar and (is_long or len(processed_items) > 5):
        # We can safely convert to a single string block.
        final_script_block = "\n".join(map(str, processed_items))
        logger.info("Formatting script block as a single literal block for clarity.")
        return LiteralScalarString(final_script_block)
    else:
        # We must return a list to preserve YAML tags or because it's short.
        if contains_tagged_scalar:
            logger.debug("Preserving script block as a list to support YAML tags (!reference).")
        return processed_items


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
            result = process_script_list(data[name], scripts_root, script_sources)
            if result != data[name]:
                data[name] = result
                inlined_count += 1

    # Process all jobs and top-level script lists (which are often used for anchors)
    for job_name, job_data in data.items():
        # --- MODIFICATION START ---
        # Handle top-level keys that are lists of scripts. This pattern is commonly
        # used to create reusable script blocks with YAML anchors, e.g.:
        # .my-script-template: &my-script-anchor
        #   - ./scripts/my-script.sh
        if isinstance(job_data, list):
            logger.debug(f"Processing top-level list key '{job_name}', potentially a script anchor.")
            result = process_script_list(job_data, scripts_root, script_sources)
            if result != job_data:
                data[job_name] = result
                inlined_count += 1
        # --- MODIFICATION END ---
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

    for script_file in scripts_dir.glob("**/*.ps1"):
        content = script_file.read_text(encoding="utf-8").strip()
        if not content:
            logger.warning(f"Script is empty and will be ignored: {script_file}")
            continue
        script_sources[str(script_file)] = content

    if not script_sources:
        raise RuntimeError(f"No non-empty scripts found in '{scripts_dir}'.")

    return script_sources


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
    script_sources: dict[str, str],
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
    inlined_for_file, compiled_text = inline_gitlab_scripts(
        raw_text, scripts_path, script_sources, variables, uncompiled_path
    )
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

    script_sources = collect_script_sources(scripts_path)

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
            (src, out, scripts_path, script_sources, vars, uncompiled_path, dry_run, label)
            for src, out, vars, label in files_to_process
        ]
        with multiprocessing.Pool(processes=max_workers) as pool:
            results = pool.starmap(_compile_single_file, args_list)
        total_inlined_count += sum(inlined for inlined, _ in results)
        written_files_count += sum(written for _, written in results)
    else:
        for src, out, vars, label in files_to_process:
            inlined_for_file, wrote = _compile_single_file(
                src, out, scripts_path, script_sources, vars, uncompiled_path, dry_run, label
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

    def _get_int(self, key: str) -> int | None:
        """Gets an integer value, respecting precedence."""
        value = self._env_config.get(key)
        if value is not None:
            try:
                return int(value)
            except ValueError:
                logger.warning(f"Config value for '{key}' is not an int. Ignoring.")
                return None

        value = self._file_config.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                logger.warning(f"Config value for '{key}' is not an int. Ignoring.")
                return None

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

    @property
    def parallelism(self) -> int | None:
        return self._get_int("parallelism")

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
```
## File: update_checker.py
```python
"""
A reusable Python submodule to check for package updates on PyPI using only stdlib.

This module provides a function to check if a newer version of a specified
package is available on PyPI. It is designed to be fault-tolerant, efficient,
and dependency-light with the following features:

- Uses only the Python standard library for networking (urllib).
- Caches results to limit network requests. Cache lifetime is configurable.
- Provides a function to manually reset the cache.
- Stores the cache in an OS-appropriate temporary directory.
- Logs a warning if the package is not found on PyPI (404).
- Provides optional colorized output for terminals that support it.
- Uses the `packaging` library for robust version parsing and comparison.
- Includes an option to check for pre-releases (e.g., alpha, beta, rc).

Requirements:
- packaging: `pip install packaging`

To use, simply import and call the `check_for_updates` function.

"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from urllib import error, request

# The 'packaging' library is highly recommended for robust version handling.
from packaging import version

# --- ANSI Color Codes ---
YELLOW = "\033[93m"
GREEN = "\033[92m"
ENDC = "\033[0m"


# --- Custom Exception ---
class PackageNotFoundError(Exception):
    """Custom exception for when a package is not found on PyPI."""


def check_for_updates(
    package_name: str,
    current_version: str,
    logger: logging.Logger | None = None,
    cache_ttl_seconds: int = 86400,
    include_prereleases: bool = False,
) -> str | None:
    """
    Checks for a new version of a package on PyPI.

    If an update is available, it returns a formatted message string.
    Otherwise, it returns None. It fails fast and silently on errors.

    Args:
        package_name: The name of the package as it appears on PyPI.
        current_version: The current version string of the running application.
        logger: An optional logging.Logger instance. Used ONLY to log a
                warning if the package is not found on PyPI.
        cache_ttl_seconds: The number of seconds to cache the result.
        include_prereleases: If True, include alpha/beta/rc versions.

    Returns:
        A formatted message string if an update is available, else None.
    """
    try:
        cache_dir = os.path.join(tempfile.gettempdir(), "python_update_checker")
        cache_file = os.path.join(cache_dir, f"{package_name}_cache.json")

        if _is_check_recently_done(cache_file, cache_ttl_seconds):
            return None

        latest_version_str = _get_latest_version_from_pypi(package_name, include_prereleases)
        if not latest_version_str:
            return None

        current = version.parse(current_version)
        latest = version.parse(latest_version_str)

        if latest > current:
            pypi_url = f"https://pypi.org/project/{package_name}/"
            use_color = _can_use_color()

            if use_color:
                message = (
                    f"{YELLOW}A new version of {package_name} is available: {GREEN}{latest}{YELLOW} "
                    f"(you are using {current}).\n"
                    f"Please upgrade using your preferred package manager.\n"
                    f"More info: {pypi_url}{ENDC}"
                )
            else:
                message = (
                    f"A new version of {package_name} is available: {latest} "
                    f"(you are using {current}).\n"
                    f"Please upgrade using your preferred package manager.\n"
                    f"More info: {pypi_url}"
                )
            _update_cache(cache_dir, cache_file)
            return message

        _update_cache(cache_dir, cache_file)
        return None

    except PackageNotFoundError:
        _log = _get_logger(logger)
        _log(f"WARNING: Package '{package_name}' not found on PyPI.")
        return None
    except Exception:
        return None


def reset_cache(package_name: str) -> None:
    """
    Deletes the cache file for a specific package, forcing a fresh check
    on the next run. Fails silently if the file cannot be removed.

    Args:
        package_name: The name of the package whose cache should be reset.
    """
    try:
        cache_dir = os.path.join(tempfile.gettempdir(), "python_update_checker")
        cache_file = os.path.join(cache_dir, f"{package_name}_cache.json")
        if os.path.exists(cache_file):
            os.remove(cache_file)
    except (OSError, PermissionError):
        # Fail silently if cache cannot be removed
        pass


def _get_logger(logger: logging.Logger | None):
    """Returns a callable for logging or printing."""
    if logger:
        return logger.warning  # Use warning level for 404s
    return print


def _can_use_color() -> bool:
    """
    Checks if the terminal supports color. Returns False if in a CI environment,
    if NO_COLOR is set, or if the terminal is 'dumb'.
    """
    if "NO_COLOR" in os.environ:
        return False
    if "CI" in os.environ and os.environ["CI"]:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return sys.stdout.isatty()


def _is_check_recently_done(cache_file: str, ttl_seconds: int) -> bool:
    """Checks if an update check was performed within the TTL."""
    try:
        if os.path.exists(cache_file):
            last_check_time = os.path.getmtime(cache_file)
            if (time.time() - last_check_time) < ttl_seconds:
                return True
    except (OSError, PermissionError):
        return False
    return False


def _get_latest_version_from_pypi(package_name: str, include_prereleases: bool) -> str | None:
    """
    Fetches the latest version string of a package from PyPI's JSON API.
    Raises PackageNotFoundError for 404 errors.
    """
    url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        req = request.Request(url, headers={"User-Agent": "python-update-checker/1.1"})
        with request.urlopen(req, timeout=10) as response:  # nosec
            data = json.loads(response.read().decode("utf-8"))

        releases = data.get("releases", {})
        if not releases:
            return data.get("info", {}).get("version")

        all_versions: list[version.Version] = []
        for v_str in releases.keys():
            try:
                parsed_v = version.parse(v_str)
                if not parsed_v.is_prerelease or include_prereleases:
                    all_versions.append(parsed_v)
            except version.InvalidVersion:
                continue

        if not all_versions:
            return None

        return str(max(all_versions))

    except error.HTTPError as e:
        if e.code == 404:
            raise PackageNotFoundError from e
        return None
    except (error.URLError, json.JSONDecodeError, TimeoutError, OSError):
        return None


def _update_cache(cache_dir: str, cache_file: str) -> None:
    """Creates or updates the cache file with the current timestamp."""
    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache_file, "w") as f:
            f.write(json.dumps({"last_check": time.time()}))
    except (OSError, PermissionError):
        pass
```
## File: utils.py
```python
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
        parallelism: int | None = None,
    ) -> None:
        super().__init__()
        self._paths = {
            "uncompiled_path": uncompiled_path,
            "output_path": output_path,
            "scripts_path": scripts_path,
            "templates_dir": templates_dir,
            "output_templates_dir": output_templates_dir,
        }
        self._flags = {"dry_run": dry_run, "parallelism": parallelism}
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
            process_uncompiled_directory(**self._paths, **self._flags)  # type: ignore[arg-type]
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
    parallelism: int | None = None,
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
        parallelism=parallelism,
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
__version__ = "0.8.3"
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
                           [--templates-out TEMPLATES_OUT] [-v]

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
  -v, --verbose         Enable verbose (DEBUG) logging output.

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
from bash2gitlab.clone2local import clone2local_handler
from bash2gitlab.compile_all import process_uncompiled_directory
from bash2gitlab.config import config
from bash2gitlab.init_project import init_handler
from bash2gitlab.logging_config import generate_config
from bash2gitlab.shred_all import shred_gitlab_ci
from bash2gitlab.update_checker import check_for_updates
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
    parallelism = args.parallelism

    if args.watch:
        start_watch(
            uncompiled_path=in_dir,
            output_path=out_dir,
            scripts_path=scripts_dir,
            templates_dir=templates_in_dir,
            output_templates_dir=templates_out_dir,
            dry_run=dry_run,
            parallelism=parallelism,
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
            parallelism=parallelism,
        )

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
    check_for_updates(__about__.__title__, __about__.__version__)

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
        "--parallelism",
        type=int,
        default=config.parallelism,
        help="Number of files to compile in parallel (default: CPU count).",
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

    argcomplete.autocomplete(parser)
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
```
