"""Command to inline bash or powershell into gitlab pipeline yaml."""

from __future__ import annotations

import base64
import io
import logging
import multiprocessing
from pathlib import Path
from typing import Any

from ruamel.yaml import CommentedMap, CommentedSeq
from ruamel.yaml.comments import TaggedScalar
from ruamel.yaml.error import YAMLError
from ruamel.yaml.scalarstring import LiteralScalarString

from bash2gitlab.commands.clean_all import report_targets
from bash2gitlab.commands.compile_bash_reader import read_bash_script
from bash2gitlab.commands.compile_not_bash import maybe_inline_interpreter_command
from bash2gitlab.commands.input_change_detector import mark_compilation_complete, needs_compilation
from bash2gitlab.config import config
from bash2gitlab.errors.exceptions import Bash2GitlabError, CompileError, ValidationFailed
from bash2gitlab.plugins import get_pm
from bash2gitlab.utils import diff_helpers
from bash2gitlab.utils.dotenv import parse_env_file
from bash2gitlab.utils.parse_bash import extract_script_path
from bash2gitlab.utils.utils import remove_leading_blank_lines, short_path
from bash2gitlab.utils.validate_pipeline import GitLabCIValidator
from bash2gitlab.utils.yaml_factory import get_yaml
from bash2gitlab.utils.yaml_file_same import normalize_for_compare, yaml_is_same

logger = logging.getLogger(__name__)

__all__ = ["run_compile_all"]


def infer_cli(
    input_dir: Path,
    output_path: Path,
    dry_run: bool = False,
    parallelism: int | None = None,
) -> str:
    command = f"bash2gitlab compile --in {short_path(input_dir)} --out {short_path(output_path)}"
    if dry_run:
        command += " --dry-run"
    if parallelism:
        command += f" --parallelism {parallelism}"
    return command


def get_banner(inferred_cli_command: str) -> str:
    if config.custom_header:
        return config.custom_header + "\n"

    # Original banner content as fallback
    return f"""# DO NOT EDIT
# This is a compiled file, compiled with bash2gitlab
# Recompile instead of editing this file.
#
# Compiled with the command: 
#     {inferred_cli_command}

"""


def as_items(
    seq_or_list: list[TaggedScalar | str] | CommentedSeq | str,
) -> tuple[list[Any], bool, CommentedSeq | None]:
    """Normalize input to a Python list of items.

    Args:
        seq_or_list (list[TaggedScalar | str] | CommentedSeq | str): Script block input.

    Returns:
        tuple[list[Any], bool, CommentedSeq | None]:
            - items as a list for processing,
            - flag indicating original was a CommentedSeq,
            - the original CommentedSeq (if any) for potential metadata reuse.
    """
    if isinstance(seq_or_list, str):
        return [seq_or_list], False, None
    if isinstance(seq_or_list, CommentedSeq):
        # Make a shallow list copy to manipulate while preserving the original node
        return list(seq_or_list), True, seq_or_list
    # Already a Python list (possibly containing ruamel nodes)
    return list(seq_or_list), False, None


def rebuild_seq_like(
    processed: list[Any],
    was_commented_seq: bool,
    original_seq: CommentedSeq | None,
) -> list[Any] | CommentedSeq:
    """Rebuild a sequence preserving ruamel type when appropriate.

    Args:
        processed (list[Any]): Final items after processing.
        was_commented_seq (bool): True if input was a CommentedSeq.
        original_seq (CommentedSeq | None): Original node to borrow metadata from.

    Returns:
        list[Any] | CommentedSeq: A list or a CommentedSeq preserving anchors/comments when possible.
    """
    if not was_commented_seq:
        return processed
    # Keep ruamel node type to preserve anchors and potential comments.
    new_seq = CommentedSeq(processed)
    # Best-effort carry over comment association metadata to reduce churn.
    try:
        if original_seq is not None and hasattr(original_seq, "ca"):
            new_seq.ca = original_seq.ca  # type: ignore[misc]
    # metadata copy is best-effort
    except Exception:  # nosec
        pass
    return new_seq


def compact_runs_to_literal(items: list[Any], *, min_lines: int = 2) -> list[Any]:
    """
    Merge consecutive plain strings into a single LiteralScalarString,
    leaving YAML nodes (e.g., TaggedScalar) as boundaries.
    """
    out: list[Any] = []
    buf: list[str] = []

    def flush():
        nonlocal buf, out
        if not buf:
            return
        # If there are multiple lines (or any newline already), collapse to literal block
        if len(buf) >= min_lines or any("\n" in s for s in buf):
            out.append(LiteralScalarString("\n".join(buf)))
        else:
            out.extend(buf)
        buf = []

    for it in items:
        # Treat existing LiteralScalarString as a plain string; it can join with neighbors
        if isinstance(it, str) and not isinstance(it, TaggedScalar):
            buf.append(it)
            continue
        # Boundary (TaggedScalar or any non-str ruamel node): flush and keep node
        flush()
        out.append(it)

    flush()
    return out


def process_script_list(
    script_list: list[TaggedScalar | str] | CommentedSeq | str, scripts_root: Path, collapse_lists: bool = True
) -> list[Any] | CommentedSeq | LiteralScalarString:
    """Process a script list, inlining shell files while preserving YAML features.

    The function accepts plain Python lists, ruamel ``CommentedSeq`` nodes, or a single
    string. It attempts to inline shell script references (e.g., ``bash foo.sh`` or
    ``./foo.sh``) into the YAML script block. If the resulting content contains only
    plain strings and exceeds a small threshold, it collapses the block into a single
    literal scalar string (``|``). If any YAML features such as anchors, tags, or
    ``TaggedScalar`` nodes are present, it preserves list form to avoid losing semantics.

    Args:
        script_list (list[TaggedScalar | str] | CommentedSeq | str): YAML script lines.
        scripts_root (Path): Root directory used to resolve script paths for inlining.
        collapse_lists (bool): Turn lists into string block. Safe if it is indeed a script.

    Returns:
        list[Any] | CommentedSeq | LiteralScalarString: Processed script block. Returns a
        ``LiteralScalarString`` when safe to collapse; otherwise returns a list or
        ``CommentedSeq`` (matching the input style) to preserve YAML features.
    """
    items, was_commented_seq, original_seq = as_items(script_list)

    processed_items: list[Any] = []
    contains_tagged_scalar = False
    contains_anchors_or_tags = False

    scripts_found = []
    for item in items:
        # Non-plain strings: preserve and mark that YAML features exist
        if not isinstance(item, str):
            if isinstance(item, TaggedScalar):
                contains_tagged_scalar = True
                anchor_val = getattr(getattr(item, "anchor", None), "value", None)
                if anchor_val:
                    contains_anchors_or_tags = True
            # Preserve any non-string node (e.g., TaggedScalar, Commented* nodes)
            processed_items.append(item)
            continue

        # Plain string: attempt to detect and inline scripts
        pm = get_pm()
        script_path_str = pm.hook.extract_script_path(line=item) or None
        if script_path_str is None:
            # try existing extract_script_path fallback
            script_path_str = extract_script_path(item)
            scripts_found.append(script_path_str)
        else:
            scripts_found.append(script_path_str)

        if script_path_str:
            if script_path_str.strip().startswith("./") or script_path_str.strip().startswith("\\."):
                rel_path = script_path_str.strip()[2:]
            else:
                rel_path = script_path_str.strip()
            script_path = scripts_root / rel_path
            try:
                bash_code = read_bash_script(script_path)
            except (FileNotFoundError, ValueError) as e:
                logger.warning(f"Could not inline script '{script_path_str}': {e}. Preserving original line.")
                raise Bash2GitlabError(
                    f"Could not inline script '{script_path_str}': {e}. Preserving original line."
                ) from e
            bash_lines = bash_code.splitlines()
            logger.debug(
                "Inlining script '%s' (%d lines).",
                Path(rel_path).as_posix(),
                len(bash_lines),
            )
            begin_marker = f"# >>> BEGIN inline: {Path(rel_path).as_posix()}"
            end_marker = "# <<< END inline"
            processed_items.append(begin_marker)
            processed_items.extend(bash_lines)
            processed_items.append(end_marker)

        else:
            # NEW: interpreter-based script inlining (python/node/ruby/php/fish)
            interp_inline, script_path_str_other = pm.hook.inline_command(line=item, scripts_root=scripts_root) or (
                None,
                None,
            )
            if interp_inline:
                scripts_found.append(script_path_str_other)
                processed_items.extend(interp_inline)
            else:
                interp_inline, script_path_str_other = maybe_inline_interpreter_command(item, scripts_root)
                if interp_inline and isinstance(interp_inline, list) and script_path_str_other:
                    scripts_found.append(str(script_path_str_other))
                    processed_items.extend(interp_inline)
                elif interp_inline and isinstance(interp_inline, str) and script_path_str_other:
                    scripts_found.append(str(script_path_str_other))
                    processed_items.append(interp_inline)
                else:
                    processed_items.append(item)

    # Decide output representation
    only_plain_strings = all(isinstance(_, str) for _ in processed_items)
    has_yaml_features = (
        contains_tagged_scalar or contains_anchors_or_tags or was_commented_seq or not only_plain_strings
    )

    # Collapse to literal block only when no YAML features and sufficiently long
    if not has_yaml_features and only_plain_strings and len(processed_items) > 1 and collapse_lists and scripts_found:
        final_script_block = "\n".join(processed_items)

        logger.debug("Formatting script block as a single literal block (no anchors/tags detected).")
        return LiteralScalarString(final_script_block)

    # Preserve sequence shape; if input was a CommentedSeq, return one
    # Case 2: Keep sequence shape but compact adjacent plain strings into a single literal
    if collapse_lists and scripts_found:
        compact_items = compact_runs_to_literal(processed_items, min_lines=2)
    else:
        compact_items = processed_items

    # Preserve sequence style (CommentedSeq vs list) to match input
    return rebuild_seq_like(compact_items, was_commented_seq, original_seq)


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


def has_must_inline_pragma(job_data: dict | str) -> bool:
    if isinstance(job_data, list):
        for item_id, _item in enumerate(job_data):
            if hasattr(job_data, "ca"):
                comment = job_data.ca.items.get(item_id)
                if comment:
                    comment_value = comment[0].value
                    if "pragma" in comment_value.lower() and "must-inline" in comment_value.lower():
                        return True
        for item in job_data:
            if "pragma" in item.lower() and "must-inline" in item.lower():
                return True
    if isinstance(job_data, str):
        if "pragma" in job_data.lower() and "must-inline" in job_data.lower():
            return True
    elif isinstance(job_data, dict):
        for _key, value in job_data.items():
            if "pragma" in str(value).lower() and "must-inline" in str(value).lower():
                return True
    return False


def inline_gitlab_scripts(
    gitlab_ci_yaml: str,
    scripts_root: Path,
    global_vars: dict[str, str],
    input_dir: Path,  # Path to look for job_name_variables.sh files
) -> tuple[int, str]:
    """
    Loads a GitLab CI YAML file, inlines scripts, merges global and job-specific variables,
    reorders top-level keys, and returns the result as a string.
    This version now supports inlining scripts in top-level lists used as YAML anchors.
    """
    inlined_count = 0
    yaml = get_yaml()
    data = yaml.load(io.StringIO(gitlab_ci_yaml))

    if global_vars:
        logger.debug("Merging global variables into the YAML configuration.")
        existing_vars = data.get("variables", CommentedMap())

        merged_vars = CommentedMap()
        # global first, then YAML-defined wins on conflict
        for k, v in (global_vars or {}).items():
            merged_vars[k] = v
        for k, v in existing_vars.items():
            merged_vars[k] = v

        data["variables"] = merged_vars

    for name in ["after_script", "before_script"]:
        if name in data:
            logger.warning(f"Processing top-level '{name}' section, even though gitlab has deprecated them.")
            result = process_script_list(data[name], scripts_root)
            if result != data[name]:
                data[name] = result

    # Process all jobs and top-level script lists (which are often used for anchors)
    for job_name, job_data in data.items():
        if job_name in [
            "stages",
            "variables",
            "include",
            "rules",
            "image",
            "services",
            "cache",
            "true",
            "false",
            "nil",
        ]:
            # that's not a job.
            continue
        if hasattr(job_data, "tag") and job_data.tag.value:
            # Can't deal with !reference tagged jobs at all
            continue
        if hasattr(job_data, "anchor") and job_data.anchor.value:
            # Can't deal with &anchor tagged jobs at all
            # Okay, more exactly, we can inline, but we can't collapse lists because you can't tell if it is
            # going into a script or some other block.
            if not has_must_inline_pragma(job_data):
                continue

        # Handle top-level keys that are lists of scripts. This pattern is commonly
        # used to create reusable script blocks with YAML anchors, e.g.:
        # .my-script-template: &my-script-anchor
        #   - ./scripts/my-script.sh
        if isinstance(job_data, list):
            logger.debug(f"Processing top-level list key '{job_name}', potentially a script anchor.")
            result = process_script_list(job_data, scripts_root, collapse_lists=False)
            if result != job_data:
                data[job_name] = result
                inlined_count += 1
        elif isinstance(job_data, dict):
            # Look for and process job-specific variables file
            safe_job_name = job_name.replace(":", "_")
            job_vars_filename = f"{safe_job_name}_variables.sh"
            job_vars_path = input_dir / job_vars_filename

            if job_vars_path.is_file():
                logger.debug(f"Found and loading job-specific variables for '{job_name}' from {job_vars_path}")
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
                logger.debug(f"Processing job: {job_name}")
                inlined_count += process_job(job_data, scripts_root)
            if "hooks" in job_data:
                if isinstance(job_data["hooks"], dict) and "pre_get_sources_script" in job_data["hooks"]:
                    logger.debug(f"Processing pre_get_sources_script: {job_name}")
                    inlined_count += process_job(job_data["hooks"], scripts_root)
            if "run" in job_data:
                if isinstance(job_data["run"], list):
                    for item in job_data["run"]:
                        if isinstance(item, dict) and "script" in item:
                            logger.debug(f"Processing run/script: {job_name}")
                            inlined_count += process_job(item, scripts_root)

    out_stream = io.StringIO()
    yaml.dump(data, out_stream)  # Dump the reordered data

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

    validator = GitLabCIValidator()
    ok, problems = validator.validate_ci_config(new_content)
    if not ok:
        raise ValidationFailed(problems)
    output_file.write_text(new_content, encoding="utf-8")

    # Store a base64 encoded copy of the exact content we just wrote.
    encoded_content = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
    hash_file.write_text(encoded_content, encoding="utf-8")
    logger.debug(f"Updated hash file: {short_path(hash_file)}")


def write_compiled_file(output_file: Path, new_content: str, dry_run: bool = False) -> bool:
    """
    Writes a compiled file safely. If the destination file was manually edited in a meaningful way
    (i.e., the YAML data structure changed), it aborts with a descriptive error and a diff.

    Returns True if a file was written (or would be in dry run), False otherwise.
    """
    if dry_run:
        logger.info(f"[DRY RUN] Would evaluate writing to {short_path(output_file)}")
        if not output_file.exists():
            logger.info(f"[DRY RUN] Would create {short_path(output_file)} ({len(new_content.splitlines())} lines).")
            return True
        current_content = output_file.read_text(encoding="utf-8")

        if not yaml_is_same(current_content, new_content):
            diff_text = diff_helpers.unified_diff(
                normalize_for_compare(current_content), normalize_for_compare(new_content), output_file
            )
            different = diff_helpers.diff_stats(diff_text)
            logger.info(
                f"[DRY RUN] Would rewrite {short_path(output_file)}: {different.changed} lines changed (+{different.insertions}, -{different.deletions})."
            )
            logger.debug(diff_text)
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
        error_message = f"ERROR: Destination file '{short_path(output_file)}' exists but its .hash file is missing. Aborting to prevent data loss. If you want to regenerate this file, please remove it and run the script again."
        logger.error(error_message)
        raise CompileError()

    # Decode the last known content from the hash file
    last_known_base64 = hash_file.read_text(encoding="utf-8").strip()
    try:
        last_known_content = base64.b64decode(last_known_base64).decode("utf-8")
    except (ValueError, TypeError) as e:
        error_message = f"ERROR: Could not decode the .hash file for '{short_path(output_file)}'. It may be corrupted.\nError: {e}\nAborting to prevent data loss. Please remove the file and its .hash file to regenerate."
        logger.error(error_message)
        raise CompileError() from e

    current_content = output_file.read_text(encoding="utf-8")

    # Load both YAML versions to compare their data structures
    yaml = get_yaml()
    try:
        last_known_doc = yaml.load(last_known_content)
    except YAMLError as e:
        logger.error(
            "ERROR: Could not parse YAML from the .hash file for '%s'. It is corrupted. Error: %s",
            short_path(output_file),
            e,
        )
        raise CompileError() from e

    try:
        current_doc = yaml.load(current_content)
        is_current_corrupt = False
    except YAMLError:
        current_doc = None
        is_current_corrupt = True
        logger.warning("Could not parse YAML from '%s'; it appears to be corrupt.", short_path(output_file))

    # An edit is detected if the current file is corrupt OR the parsed YAML documents are not identical.
    is_same = yaml_is_same(last_known_content, current_content)

    if is_current_corrupt or (current_doc != last_known_doc and not is_same):
        diff_text = diff_helpers.unified_diff(
            normalize_for_compare(last_known_content),
            normalize_for_compare(current_content),
            output_file,
            "last known good",
            "current",
        )
        corruption_warning = (
            "The file is also syntactically invalid YAML, which is why it could not be processed.\n\n"
            if is_current_corrupt
            else ""
        )

        error_message = f"\n--- MANUAL EDIT DETECTED ---\nCANNOT OVERWRITE: The destination file below has been modified:\n  {output_file}\n\n{corruption_warning}The script detected that its data no longer matches the last generated version.\nTo prevent data loss, the process has been stopped.\n\n--- DETECTED CHANGES ---\n{diff_text if diff_text else 'No visual differences found, but YAML data structure has changed.'}\n--- HOW TO RESOLVE ---\n1. Revert the manual changes in '{output_file}' and run this script again.\nOR\n2. If the manual changes are desired, incorporate them into the source files\n   (e.g., the .sh or uncompiled .yml files), then delete the generated file\n   ('{output_file}') and its '.hash' file ('{hash_file}') to allow the script\n   to regenerate it from the new base.\n"
        print(error_message)
        raise CompileError()

    # If we reach here, the current file is valid (or just reformatted).
    # Now, we check if the *newly generated* content is different from the current content.
    if not yaml_is_same(current_content, new_content):
        # NEW: log diff + counts before writing
        diff_text = diff_helpers.unified_diff(
            normalize_for_compare(current_content), normalize_for_compare(new_content), output_file
        )
        different = diff_helpers.diff_stats(diff_text)
        logger.info(
            "(1) Rewriting %s: %d lines changed (+%d, -%d).",
            short_path(output_file),
            different.changed,
            different.insertions,
            different.deletions,
        )
        logger.debug(diff_text)

        write_yaml_and_hash(output_file, new_content, hash_file)
        return True

    logger.debug("Content of %s is already up to date. Skipping.", short_path(output_file))
    return False


def compile_single_file(
    source_path: Path,
    output_file: Path,
    scripts_path: Path,
    variables: dict[str, str],
    input_dir: Path,
    dry_run: bool,
    inferred_cli_command: str,
) -> tuple[int, int]:
    """Compile a single YAML file and write the result.

    Returns a tuple of the number of inlined sections and whether a file was written (0 or 1).
    """
    logger.debug(f"Processing template: {short_path(source_path)}")
    raw_text = source_path.read_text(encoding="utf-8")
    inlined_for_file, compiled_text = inline_gitlab_scripts(raw_text, scripts_path, variables, input_dir)
    final_content = (get_banner(inferred_cli_command) + compiled_text) if inlined_for_file > 0 else raw_text
    written = write_compiled_file(output_file, final_content, dry_run)
    return inlined_for_file, int(written)


def run_compile_all(
    input_dir: Path,
    output_path: Path,
    dry_run: bool = False,
    parallelism: int | None = None,
    force: bool = False,
) -> int:
    """
    Main function to process a directory of uncompiled GitLab CI files.
    This version safely writes files by checking hashes to avoid overwriting manual changes.

    Args:
        input_dir (Path): Path to the input .gitlab-ci.yml, other yaml and bash files.
        output_path (Path): Path to write the .gitlab-ci.yml file and other yaml.
        dry_run (bool): If True, simulate the process without writing any files.
        parallelism (int | None): Maximum number of processes to use for parallel compilation.
        force (bool): If True, compile even if it appears to not be need because nothing changed.

    Returns:
        The total number of inlined sections across all files.
    """
    # Check if compilation is needed (unless forced)
    if not force:
        if not needs_compilation(input_dir):
            logger.info("No input changes detected since last compilation. Skipping compilation.")
            logger.info("Use --force to compile anyway, or modify input files to trigger compilation.")
            return 0
        logger.info("Input changes detected, proceeding with compilation...")

    inferred_cli_command = infer_cli(input_dir, output_path, dry_run, parallelism)
    strays = report_targets(output_path)
    if strays:
        print("Stray files in output folder, halting")
        for stray in strays:
            print(f"  {stray}")
        raise CompileError()

    total_inlined_count = 0
    written_files_count = 0

    if not dry_run:
        output_path.mkdir(parents=True, exist_ok=True)

    global_vars_path = input_dir / "global_variables.sh"
    global_vars_data = {}
    if global_vars_path.is_file():
        logger.info(f"Found and loading variables from {short_path(global_vars_path)}")
        content = global_vars_path.read_text(encoding="utf-8")
        global_vars_data = parse_env_file(content)
        total_inlined_count += 1

    files_to_process: list[tuple[Path, Path, dict[str, str]]] = []

    if input_dir.is_dir():
        template_files = list(input_dir.rglob("*.yml")) + list(input_dir.rglob("*.yaml"))
        if not template_files:
            logger.warning(f"No template YAML files found in {input_dir}")

        for template_path in template_files:
            relative_path = template_path.relative_to(input_dir)
            output_file = output_path / relative_path
            files_to_process.append((template_path, output_file, global_vars_data))

    total_files = len(files_to_process)
    max_workers = multiprocessing.cpu_count()
    if parallelism and parallelism > 0:
        max_workers = min(parallelism, max_workers)

    if total_files >= 5 and max_workers > 1 and parallelism:
        args_list = [
            (src, out, input_dir, variables, input_dir, dry_run, inferred_cli_command)
            for src, out, variables in files_to_process
        ]
        with multiprocessing.Pool(processes=max_workers) as pool:
            results = pool.starmap(compile_single_file, args_list)
        total_inlined_count += sum(inlined for inlined, _ in results)
        written_files_count += sum(written for _, written in results)
    else:
        for src, out, variables in files_to_process:
            inlined_for_file, wrote = compile_single_file(
                src, out, input_dir, variables, input_dir, dry_run, inferred_cli_command
            )
            total_inlined_count += inlined_for_file
            written_files_count += wrote

    # After successful compilation, mark as complete
    if not dry_run and (total_inlined_count > 0 or written_files_count > 0):
        try:
            mark_compilation_complete(input_dir)
            logger.debug("Marked compilation as complete - updated input file hashes")
        except Exception as e:
            logger.warning(f"Failed to update input hashes: {e}")

    if written_files_count == 0 and not dry_run:
        logger.warning(
            "No output files were written. This could be because all files are up-to-date, or due to errors."
        )
    elif not dry_run:
        logger.info(f"Successfully processed files. {written_files_count} file(s) were created or updated.")
    elif dry_run:
        logger.info(f"[DRY RUN] Simulation complete. Would have processed {written_files_count} file(s).")

    return total_inlined_count
