"""
Handles CLI interactions for bash2gitlab

usage: bash2gitlab [-h] [--version]
                   {compile,decompile,detect-drift,copy2local,init,map-deploy,commit-map,clean,
                    lint,install-precommit,uninstall-precommit,check-pins,trigger-pipelines,
                    doctor,graph,show-config,run,detect-uncompiled,validate,autogit}
                   ...

A tool for making development of centralized yaml gitlab templates more pleasant.

positional arguments:
  {compile,decompile,detect-drift,copy2local,init,map-deploy,commit-map,clean,lint,
   install-precommit,uninstall-precommit,check-pins,trigger-pipelines,doctor,graph,
   show-config,run,detect-uncompiled,validate,autogit}
    compile             Compile an uncompiled directory into a standard GitLab CI structure.
    decompile           Decompile a GitLab CI file, extracting inline scripts into separate .sh files.
    detect-drift        Detect if generated files have been edited and display what the edits are.
    copy2local          Copy folder(s) from a repo to local, for testing bash in the dependent repo
    init                Initialize a new bash2gitlab project and config file.
    map-deploy          Deploy files from source to target directories based on a mapping in pyproject.toml.
    commit-map          Copy changed files from deployed directories back to their source locations based on a mapping in pyproject.toml.
    clean               Clean output folder, removing only unmodified files previously written by bash2gitlab.
    lint                Validate compiled GitLab CI YAML against a GitLab instance (global or project-scoped CI Lint).
    install-precommit   Install a Git pre-commit hook that runs `bash2gitlab compile` (honors core.hooksPath/worktrees).
    uninstall-precommit Remove the bash2gitlab pre-commit hook.
    check-pins          Analyze GitLab CI 'include' statements and suggest pinning to tags.
    trigger-pipelines   Trigger pipelines in one or more GitLab projects and optionally wait for completion.
    doctor              Run a series of health checks on the project and environment.
    graph               Generate a DOT language dependency graph of your project's YAML and script files.
    show-config         Display the current bash2gitlab configuration and its sources.
    run                 Best efforts to run a .gitlab-ci.yml file locally.
    detect-uncompiled   Detect if input files have changed since last compilation.
    validate            Validate yaml pipelines against Gitlab json schema.
    autogit             Manually trigger the autogit process based on your configuration.

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
"""

from __future__ import annotations

import argparse
import logging
import logging.config
import sys
from pathlib import Path
from typing import Any
from urllib import error as _urlerror

# Import urllib3 for the new pin checker's exceptions
import urllib3

try:
    import argcomplete
except ModuleNotFoundError:
    argcomplete = None  # type: ignore[assignment]

from gitlab.exceptions import GitlabAuthenticationError, GitlabHttpError

# Core
from bash2gitlab import __about__
from bash2gitlab import __doc__ as root_doc
from bash2gitlab.commands.autogit import run_autogit
from bash2gitlab.commands.best_effort_runner import best_efforts_run
from bash2gitlab.commands.clean_all import clean_targets
from bash2gitlab.commands.compile_all import run_compile_all
from bash2gitlab.commands.decompile_all import run_decompile_gitlab_file, run_decompile_gitlab_tree
from bash2gitlab.commands.detect_drift import run_detect_drift
from bash2gitlab.commands.input_change_detector import get_changed_files, needs_compilation
from bash2gitlab.commands.lint_all import lint_output_folder, summarize_results
from bash2gitlab.commands.pipeline_trigger import (
    ProjectSpec,
    get_gitlab_client,
    poll_pipelines_until_complete,
    trigger_pipelines,
)
from bash2gitlab.commands.show_config import run_show_config
from bash2gitlab.commands.upgrade_pinned_templates import analyses_to_json, analyses_to_table, suggest_include_pins
from bash2gitlab.commands.validate_all import run_validate_all
from bash2gitlab.config import config
from bash2gitlab.errors.exceptions import Bash2GitlabError, CompilationNeeded, NetworkIssue, NotFound
from bash2gitlab.errors.exit_codes import ExitCode, resolve_exit_code
from bash2gitlab.install_help import print_install_help
from bash2gitlab.plugins import get_pm
from bash2gitlab.utils.cli_suggestions import SmartParser
from bash2gitlab.utils.logging_config import generate_config

# Interactive
try:
    from bash2gitlab.commands.copy2local import clone_repository_ssh, fetch_repository_archive
    from bash2gitlab.commands.doctor import run_doctor
    from bash2gitlab.commands.graph_all import generate_dependency_graph
    from bash2gitlab.commands.init_project import run_init
    from bash2gitlab.commands.map_commit import run_commit_map
    from bash2gitlab.commands.map_deploy import run_map_deploy
    from bash2gitlab.commands.precommit import PrecommitHookError, install, uninstall
    from bash2gitlab.utils.update_checker import start_background_update_check
    from bash2gitlab.watch_files import start_watch
except ModuleNotFoundError:
    start_background_update_check = None  # type: ignore[assignment]
    start_watch = None  # type: ignore[assignment]

# emoji support
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

logger = logging.getLogger(__name__)


def clean_handler(args: argparse.Namespace) -> None:
    """Handles the `clean` command logic."""
    logger.info("Starting cleaning output folder...")
    out_dir = Path(args.output_dir).resolve()
    clean_targets(out_dir, dry_run=args.dry_run)


essential_gitlab_args_help = "GitLab connection options. For private instances require --gitlab-url and possibly --token. Use --project-id for project-scoped lint when your config relies on includes or project context."


def lint_handler(args: argparse.Namespace) -> int:
    """Handler for the `lint` command.

    Runs GitLab CI Lint against all YAML files in the output directory.

    Exit codes:
        0  All files valid
        2  One or more files invalid
        10 Configuration / path error
        12 Network / HTTP error communicating with GitLab
    """
    out_dir = Path(args.output_dir).resolve()
    if not out_dir.exists():
        logger.error("Output directory does not exist: %s", out_dir)
        raise NotFound(out_dir)

    try:
        results = lint_output_folder(
            output_root=out_dir,
            gitlab_url=args.gitlab_url,
            private_token=args.token,
            project_id=args.project_id,
            ref=args.ref,
            include_merged_yaml=args.include_merged_yaml,
            parallelism=args.parallelism,
            timeout=args.timeout,
        )
    except (_urlerror.URLError, _urlerror.HTTPError) as e:  # pragma: no cover - network
        logger.error("Failed to contact GitLab CI Lint API: %s", e)
        raise NetworkIssue() from e
    # defensive logging of unexpected failures
    except Exception as e:  # nosec
        logger.error("Unexpected error during lint: %s", e)
        raise

    _ok, fail = summarize_results(results)
    return 0 if fail == 0 else 2


def check_pins_handler(args: argparse.Namespace) -> int:
    """Handler for the `check-pins` command."""
    logger.info("Analyzing include pins for %s...", args.file)
    try:
        analyses = suggest_include_pins(
            gitlab_ci_path=args.file,
            gitlab_base_url=args.gitlab_url,
            token=args.token,
            oauth_token=args.oauth_token,
            pin_tags_only=args.pin_tags_only,
        )

        if args.json:
            print(analyses_to_json(analyses))
        else:
            print(analyses_to_table(analyses))

    except (urllib3.exceptions.HTTPError, RuntimeError) as e:
        logger.error("Failed to contact GitLab API: %s", e)
        raise NetworkIssue() from e
    except FileNotFoundError as e:
        logger.error("Input file not found: %s", e.filename)
        raise NotFound(Path(e.filename)) from e
    except ValueError as e:  # Raised by _load_yaml for bad root element
        logger.error("Invalid YAML file structure: %s", e)
        raise Bash2GitlabError(f"Invalid YAML file structure: {e}") from e

    return 0


def trigger_pipelines_handler(args: argparse.Namespace) -> int:
    """Handler for the 'trigger-pipelines' command."""
    # 1. Parse variables
    variables = {}
    if args.variable:
        for var_str in args.variable:
            if "=" not in var_str:
                msg = f"Invalid variable format: '{var_str}'. Must be 'KEY=VALUE'."
                logger.error(msg)
                raise Bash2GitlabError(msg)
            key, value = var_str.split("=", 1)
            variables[key] = value

    # 2. Parse project specs
    specs = []
    for proj_str in args.project:
        if ":" not in proj_str:
            msg = f"Invalid project format: '{proj_str}'. Must be 'PROJECT_ID:REF'."
            logger.error(msg)
            raise Bash2GitlabError(msg)
        try:
            pid_str, ref = proj_str.split(":", 1)
            specs.append(ProjectSpec(project_id=int(pid_str), ref=ref, variables=variables))
        except ValueError as e:
            msg = f"Project ID in '{proj_str}' must be a number."
            logger.error(msg)
            raise Bash2GitlabError(msg) from e

    # 3. Connect and trigger
    try:
        gl = get_gitlab_client(url=args.gitlab_url, token=args.token)
        triggered = trigger_pipelines(gl, specs)
        for t in triggered:
            logger.info(f"✅ Triggered pipeline for project {t.project_id}: {t.web_url}")

        if not args.wait:
            return 0

        # 4. Poll if requested
        logger.info("Polling pipelines until completion (Timeout: %s seconds)...", args.timeout)
        final_results = poll_pipelines_until_complete(
            gl,
            triggered,
            timeout_seconds=args.timeout,
            poll_interval_seconds=args.poll_interval,
        )

        # 5. Report final status and determine exit code
        logger.info("--- Final Pipeline Statuses ---")
        failures = 0
        for r in final_results:
            log_func = logger.error if r.status == "failed" else logger.info
            log_func(f"Project {r.project_id} | Pipeline {r.pipeline_id} | Status: {r.status.upper()} | {r.web_url}")
            if r.status in ("failed", "canceled"):
                failures += 1

        if failures > 0:
            logger.error("\n%d pipeline(s) did not succeed.", failures)
            return 1  # Return a non-zero exit code for failure

        logger.info("\nAll pipelines succeeded.")
        return 0

    except GitlabAuthenticationError as gae:
        logger.error("GitLab authentication failed. Check your token and permissions.")
        raise Bash2GitlabError("GitLab authentication failed") from gae
    except GitlabHttpError as ghe:
        logger.error("GitLab API error: %s", ghe.error_message)
        raise NetworkIssue(f"GitLab API Error: {ghe.error_message}") from ghe
    except ValueError as e:
        logger.error("Configuration error: %s", e)
        raise Bash2GitlabError(str(e)) from e


def init_handler(args: argparse.Namespace) -> int:
    """Handles the `init` command logic."""
    logger.info("Starting interactive project initializer...")
    directory = args.directory
    force = args.force
    return run_init(directory, force)


def copy2local_handler(args: argparse.Namespace) -> int:
    """
    Argparse handler for the copy2local command.

    This handler remains compatible with the new archive-based fetch function.
    """
    # This function now calls the new implementation, preserving the call stack.
    dry_run = bool(args.dry_run)

    if str(args.repo_url).startswith("ssh"):
        clone_repository_ssh(args.repo_url, args.branch, Path(args.source_dir), Path(args.copy_dir), dry_run)
    else:
        fetch_repository_archive(args.repo_url, args.branch, Path(args.source_dir), Path(args.copy_dir), dry_run)
    return 0


def compile_handler(args: argparse.Namespace) -> int:
    """Handler for the 'compile' command."""
    logger.info("Starting bash2gitlab compiler...")

    # Resolve paths, using sensible defaults if optional paths are not provided
    in_dir = Path(args.input_dir).resolve()
    out_dir = Path(args.output_dir).resolve()
    dry_run = bool(args.dry_run)
    force = bool(args.force)
    parallelism = args.parallelism

    if args.watch and not start_watch:  # type: ignore[truthy-function]
        print_install_help()
        sys.exit(ExitCode.UNINSTALLED_DEPENDENCIES)

    if args.watch:
        start_watch(
            input_dir=in_dir,
            output_path=out_dir,
            dry_run=dry_run,
            parallelism=parallelism,
        )
        return 0

    result = run_compile_all(
        input_dir=in_dir,
        output_path=out_dir,
        dry_run=dry_run,
        parallelism=parallelism,
        force=force,
    )
    logger.info("✅ GitLab CI processing complete.")
    return result


def validate_handler(args: argparse.Namespace) -> int:
    """Handler for the 'validate' command."""
    logger.info("Starting bash2gitlab validator...")

    # Resolve paths, using sensible defaults if optional paths are not provided
    in_dir = Path(args.input_dir).resolve()
    out_dir = Path(args.output_dir).resolve()
    parallelism = args.parallelism

    result = run_validate_all(
        input_dir=in_dir,
        _output_path=out_dir,
        parallelism=parallelism,
    )

    logger.info("✅ GitLab CI validating complete.")
    return result


def drift_handler(args: argparse.Namespace) -> int:
    """Handler for the 'detect-drift' command."""
    return run_detect_drift(Path(args.out))


def decompile_handler(args: argparse.Namespace) -> int:
    """Handler for the 'decompile' command (file *or* folder)."""
    logger.info("Starting bash2gitlab decompiler...")

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)  # force folder semantics

    dry_run = bool(args.dry_run)

    if args.input_file:
        jobs, scripts, out_yaml = run_decompile_gitlab_file(
            input_yaml_path=Path(args.input_file).resolve(),
            output_dir=out_dir,
            dry_run=dry_run,
        )
        if dry_run:
            logger.info("DRY RUN: Would have processed %s jobs and created %s script(s).", jobs, scripts)
        else:
            logger.info("✅ Processed %s jobs and created %s script(s).", jobs, scripts)
            logger.info("Modified YAML written to: %s", out_yaml)
    else:
        yml_count, jobs, scripts = run_decompile_gitlab_tree(
            input_root=Path(args.input_folder).resolve(),
            output_dir=out_dir,
            dry_run=dry_run,
        )
        if dry_run:
            logger.info(
                "DRY RUN: Would have processed %s YAML file(s), %s jobs, and created %s script(s).",
                yml_count,
                jobs,
                scripts,
            )
        else:
            logger.info(
                "✅ Processed %s YAML file(s), %s jobs, and created %s script(s).",
                yml_count,
                jobs,
                scripts,
            )
    return 0


def commit_map_handler(args: argparse.Namespace) -> int:
    """Handler for the 'commit-map' command."""
    mapping = config.map_folders

    run_commit_map(mapping, dry_run=args.dry_run, force=args.force)
    return 0


def map_deploy_handler(args: argparse.Namespace) -> int:
    """Handler for the 'map-deploy' command."""
    mapping = config.map_folders
    run_map_deploy(mapping, dry_run=args.dry_run, force=args.force)
    return 0


# NEW: install/uninstall pre-commit handlers
def install_precommit_handler(args: argparse.Namespace) -> int:
    """Install the Git pre-commit hook that runs `bash2gitlab compile`.

    Honors `core.hooksPath` and Git worktrees. Fails if required configuration
    (input/output) is missing; see `bash2gitlab init` or set appropriate env vars.

    Args:
        args: Parsed CLI arguments containing:
            - repo_root: Optional repository root (defaults to CWD).
            - force: Overwrite an existing non-matching hook if True.

    Returns:
        Process exit code (0 on success, non-zero on error).
    """
    repo_root = Path(args.repo_root).resolve()
    try:
        install(repo_root=repo_root, force=args.force)
        logger.info("Pre-commit hook installed.")
        return 0
    except PrecommitHookError as e:
        logger.error("Failed to install pre-commit hook: %s", e)
        raise


def uninstall_precommit_handler(args: argparse.Namespace) -> int:
    """Uninstall the bash2gitlab pre-commit hook.

    Args:
        args: Parsed CLI arguments containing:
            - repo_root: Optional repository root (defaults to CWD).
            - force: Remove even if the hook content doesn't match.

    Returns:
        Process exit code (0 on success, non-zero on error).
    """
    repo_root = Path(args.repo_root).resolve()
    try:
        uninstall(repo_root=repo_root, force=args.force)
        logger.info("Pre-commit hook removed.")
        return 0
    except PrecommitHookError as e:
        logger.error("Failed to uninstall pre-commit hook: %s", e)
        raise


def doctor_handler(_args: argparse.Namespace) -> int:
    """Handler for the 'doctor' command."""
    # The run_doctor function already prints messages and returns an exit code.
    return run_doctor()


def graph_handler(args: argparse.Namespace) -> int:
    """Handler for the 'graph' command."""
    in_dir = Path(args.input_dir).resolve()
    if not in_dir.is_dir():
        logger.error(f"Input directory does not exist or is not a directory: {in_dir}")
        raise NotFound(in_dir)

    dot_output = generate_dependency_graph(in_dir)
    if dot_output:
        print(dot_output)
        return 0
    logger.warning("No graph data generated. Check input directory and file structure.")
    return 0


def show_config_handler(_args: argparse.Namespace) -> int:
    """Handler for the 'show-config' command."""
    # The run_show_config function already prints messages and returns an exit code.
    return run_show_config()


def best_effort_run_handler(args: argparse.Namespace) -> None:
    """Handler for the 'run' command."""
    best_efforts_run(Path(args.input_file))


def autogit_handler(args: argparse.Namespace) -> int:
    """Handler for the 'autogit' command."""
    return run_autogit(config=config, commit_message=args.message)


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Add shared CLI flags to a subparser."""
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the command without filesystem changes.",
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose (DEBUG) logging output.")
    parser.add_argument("-q", "--quiet", action="store_true", help="Disable output.")


def add_autogit_argument(parser: argparse.ArgumentParser) -> None:
    """Adds the --autogit flag to a parser."""
    parser.add_argument(
        "--autogit",
        action="store_true",
        help="Automatically stage, commit, and/or push changes after the command succeeds. "
        "Behavior is configured in [tool.bash2gitlab.autogit].",
    )


def handle_change_detection_commands(args) -> None:
    """Handle change detection specific commands. Returns True if command was handled."""
    input_dir: Path = Path(args.input_dir or "")
    if args.check_only:
        if needs_compilation(input_dir):
            print("Compilation needed: input files have changed")
            raise CompilationNeeded()
        print("No compilation needed: no input changes detected")
        return

    if args.list_changed:
        changed = get_changed_files(input_dir)
        if changed:
            print("Changed files since last compilation:")
            for file_path in changed:
                print(f"  {file_path}")
            raise CompilationNeeded()
        print("No files have changed since last compilation")
        return


def main() -> int:
    """Main CLI entry point."""
    if start_background_update_check:  # type: ignore[truthy-function]
        start_background_update_check(__about__.__title__, __about__.__version__)

    try:
        from rich_argparse import RichHelpFormatter

        formatter_class: Any = RichHelpFormatter
    except (ImportError, ModuleNotFoundError):
        formatter_class = argparse.RawTextHelpFormatter

    parser = SmartParser(
        prog=__about__.__title__,
        description=root_doc,
        formatter_class=formatter_class,
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {__about__.__version__}")

    totalhelp: Any = None
    try:
        import totalhelp

        totalhelp.add_totalhelp_flag(parser)
    except (ImportError, ModuleNotFoundError, AttributeError):
        totalhelp = None

    subparsers = parser.add_subparsers(dest="command", required=False)

    # --- Compile Command ---
    compile_parser = subparsers.add_parser(
        "compile", help="Compile an uncompiled directory into a standard GitLab CI structure."
    )
    compile_parser.add_argument(
        "--in",
        dest="input_dir",
        required=not bool(config.compile_input_dir),
        help="Input directory containing the uncompiled `.gitlab-ci.yml` and other sources.",
    )
    compile_parser.add_argument(
        "--out",
        dest="output_dir",
        required=not bool(config.compile_output_dir),
        help="Output directory for the compiled GitLab CI files.",
    )
    compile_parser.add_argument(
        "--parallelism",
        type=int,
        default=config.parallelism,
        help="Number of files to compile in parallel (default: CPU count).",
    )

    compile_parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch source directories and auto-recompile on changes.",
    )
    compile_parser.add_argument(
        "--force", action="store_true", help="Force compilation even if no input changes detected"
    )
    add_common_arguments(compile_parser)
    add_autogit_argument(compile_parser)
    compile_parser.set_defaults(func=compile_handler)

    # Clean Parser
    clean_parser = subparsers.add_parser(
        "clean",
        help="Clean output folder, only removes unmodified files that bash2gitlab wrote.",
    )
    clean_parser.add_argument(
        "--out",
        dest="output_dir",
        required=not bool(config.compile_output_dir),
        help="Output directory for the compiled GitLab CI files.",
    )
    add_common_arguments(clean_parser)
    add_autogit_argument(clean_parser)
    clean_parser.set_defaults(func=clean_handler)

    # --- Decompile Command ---
    decompile_parser = subparsers.add_parser(
        "decompile",
        help="Decompile GitLab CI YAML: extract scripts/variables to .sh and rewrite YAML.",
        description=(
            "Use either --in-file (single YAML) or --in-folder (process tree).\n--out must be a directory; output YAML and scripts are written side-by-side."
        ),
    )

    group = decompile_parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--in-file",
        default=config.decompile_input_file,
        dest="input_file",
        help="Input GitLab CI YAML file to decompile (e.g., .gitlab-ci.yml).",
    )
    group.add_argument(
        "--in-folder",
        default=config.decompile_input_folder,
        dest="input_folder",
        help="Folder to recursively decompile (*.yml, *.yaml).",
    )

    decompile_parser.add_argument(
        "--out",
        dest="output_dir",
        default=config.decompile_output_dir,
        required=not bool(config.decompile_output_dir),
        help="Output directory (will be created). YAML and scripts are written here.",
    )

    add_common_arguments(decompile_parser)
    add_autogit_argument(decompile_parser)

    decompile_parser.set_defaults(func=decompile_handler)

    # detect drift command
    detect_drift_parser = subparsers.add_parser(
        "detect-drift",
        help="Detect if generated files have been edited and display what the edits are.",
    )
    detect_drift_parser.add_argument(
        "--out",
        dest="out",
        help="Output path where generated files are.",
    )
    add_common_arguments(detect_drift_parser)
    detect_drift_parser.set_defaults(func=drift_handler)

    # --- copy2local Command ---
    copy2local_parser = subparsers.add_parser(
        "copy2local",
        help="Copy folder(s) from a repo to local, for testing bash in the dependent repo",
    )
    copy2local_parser.add_argument(
        "--repo-url",
        default=config.copy2local_repo_url,
        required=True,
        help="Repository URL to copy.",
    )
    copy2local_parser.add_argument(
        "--branch",
        default=config.copy2local_branch,
        required=True,
        help="Branch to copy.",
    )
    copy2local_parser.add_argument(
        "--copy-dir",
        default=config.copy2local_copy_dir,
        required=True,
        help="Destination directory for the copy.",
    )
    copy2local_parser.add_argument(
        "--source-dir",
        default=config.copy2local_source_dir,
        required=True,
        help="Directory to include in the copy.",
    )
    add_common_arguments(copy2local_parser)
    copy2local_parser.set_defaults(func=copy2local_handler)

    # Init Parser
    # Init Parser
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a new bash2gitlab project in pyproject.toml.",
    )
    init_parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="The directory to initialize the project in. Defaults to the current directory.",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing [tool.bash2gitlab] section in pyproject.toml.",
    )
    add_common_arguments(init_parser)
    init_parser.set_defaults(func=init_handler)  # Changed from init_handler to run_init

    # --- map-deploy Command ---
    map_deploy_parser = subparsers.add_parser(
        "map-deploy",
        help="Deploy files from source to target directories based on a mapping in pyproject.toml.",
    )
    map_deploy_parser.add_argument(
        "--pyproject",
        dest="pyproject_path",
        default="pyproject.toml",
        help="Path to the pyproject.toml file containing the [tool.bash2gitlab.map] section.",
    )
    map_deploy_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite target files even if they have been modified since the last deployment.",
    )
    add_common_arguments(map_deploy_parser)
    add_autogit_argument(map_deploy_parser)
    map_deploy_parser.set_defaults(func=map_deploy_handler)

    # --- commit-map Command ---
    commit_map_parser = subparsers.add_parser(
        "commit-map",
        help=(
            "Copy changed files from deployed directories back to their source locations based on a mapping in pyproject.toml."
        ),
    )
    commit_map_parser.add_argument(
        "--pyproject",
        dest="pyproject_path",
        default="pyproject.toml",
        help="Path to the pyproject.toml file containing the [tool.bash2gitlab.map] section.",
    )
    commit_map_parser.add_argument(
        "--force",
        action="store_true",
        help=("Overwrite source files even if they have been modified since the last deployment."),
    )
    add_common_arguments(commit_map_parser)
    add_autogit_argument(commit_map_parser)

    commit_map_parser.set_defaults(func=commit_map_handler)

    # --- lint Command ---
    lint_parser = subparsers.add_parser(
        "lint",
        help="Validate compiled GitLab CI YAML against a GitLab instance (global or project-scoped).",
        description=(
            "Run GitLab CI Lint for every *.yml/*.yaml file under the output directory.\n\n"
            + essential_gitlab_args_help
        ),
    )
    lint_parser.add_argument(
        "--out",
        dest="output_dir",
        required=not bool(config.output_dir),
        help="Directory containing compiled YAML files to lint.",
    )
    lint_parser.add_argument(
        "--gitlab-url",
        default=config.lint_gitlab_url,
        dest="gitlab_url",
        help="Base GitLab URL (e.g., https://gitlab.com).",
    )
    lint_parser.add_argument(
        "--token",
        dest="token",
        help="PRIVATE-TOKEN or CI_JOB_TOKEN to authenticate with the API.",
    )
    lint_parser.add_argument(
        "--project-id",
        default=config.lint_project_id,
        dest="project_id",
        type=int,
        help="Project ID for project-scoped lint (recommended for configs with includes).",
    )
    lint_parser.add_argument(
        "--ref",
        default=config.lint_ref,
        dest="ref",
        help="Git ref to evaluate includes/variables against (project lint only).",
    )
    lint_parser.add_argument(
        "--include-merged-yaml",
        default=config.lint_include_merged_yaml,
        dest="include_merged_yaml",
        action="store_true",
        help="Return merged YAML from project-scoped lint (slower).",
    )
    lint_parser.add_argument(
        "--parallelism",
        default=config.lint_parallelism,
        dest="parallelism",
        type=int,
        help="Max concurrent lint requests (default: CPU count, capped to file count).",
    )
    lint_parser.add_argument(
        "--timeout",
        dest="timeout",
        type=float,
        default=config.lint_timeout or 20,
        help="HTTP timeout per request in seconds (default: 20).",
    )
    add_common_arguments(lint_parser)
    lint_parser.set_defaults(func=lint_handler)

    # --- check-pins Command ---
    check_pins_parser = subparsers.add_parser(
        "check-pins",
        help="Analyze GitLab CI 'include' statements and suggest pinning to tags.",
        description=(
            "Scans a .gitlab-ci.yml file for 'project' includes and checks their refs (tags, branches, commits).\n"
            "Suggests pinning to the latest semantic version tag for stability.\n\n"
            + "GitLab connection options are required via CLI or config."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    check_pins_parser.add_argument(
        "--file",
        dest="file",
        default=".gitlab-ci.yml",
        help="Path to the .gitlab-ci.yml file to analyze (default: .gitlab-ci.yml).",
    )
    check_pins_parser.add_argument(
        "--gitlab-url",
        default=config.lint_gitlab_url,
        dest="gitlab_url",
        required=not bool(config.lint_gitlab_url),
        help="Base GitLab URL (e.g., https://gitlab.com).",
    )
    check_pins_parser.add_argument(
        "--token",
        dest="token",
        help="PRIVATE-TOKEN for API authentication.",
    )
    check_pins_parser.add_argument(
        "--oauth-token",
        dest="oauth_token",
        default=None,
        help="OAuth bearer token, an alternative to --token.",
    )
    check_pins_parser.add_argument(
        "--pin-all",
        dest="pin_tags_only",
        action="store_false",
        help="Suggest pinning to latest commit SHA if no tags are available (default is to only suggest tags).",
    )
    check_pins_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format instead of a table.",
    )
    add_common_arguments(check_pins_parser)
    check_pins_parser.set_defaults(func=check_pins_handler)

    # --- Trigger Pipelines Command ---
    trigger_parser = subparsers.add_parser(
        "trigger-pipelines",
        help="Trigger pipelines in one or more GitLab projects and optionally wait for completion.",
        description=(
            "Triggers pipelines for specified projects and refs. Can pass variables and wait for results.\n\n"
            + "Requires GitLab connection options."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    trigger_parser.add_argument(
        "--project",
        action="append",
        required=True,
        dest="project",
        help="Specify a project and ref in 'PROJECT_ID:REF' format. Can be used multiple times.",
    )
    trigger_parser.add_argument(
        "--variable",
        action="append",
        dest="variable",
        help="A 'KEY=VALUE' variable to pass to all triggered pipelines. Can be used multiple times.",
    )
    trigger_parser.add_argument(
        "--gitlab-url",
        default=config.lint_gitlab_url,
        dest="gitlab_url",
        help="Base GitLab URL (e.g., https://gitlab.com).",
    )
    trigger_parser.add_argument(
        "--token",
        dest="token",
        help="PRIVATE-TOKEN for API authentication.",
    )
    trigger_parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for all triggered pipelines to complete.",
    )
    trigger_parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Polling timeout in seconds when --wait is used (default: 1800).",
    )
    trigger_parser.add_argument(
        "--poll-interval",
        type=int,
        default=30,
        help="Seconds between polls when --wait is used (default: 30, min: 30).",
    )
    add_common_arguments(trigger_parser)
    trigger_parser.set_defaults(func=trigger_pipelines_handler)

    # --- install-precommit Command ---
    install_pc = subparsers.add_parser(
        "install-precommit",
        help="Install a Git pre-commit hook that runs `bash2gitlab compile` (honors core.hooksPath/worktrees).",
    )
    install_pc.add_argument(
        "--repo-root",
        default=".",
        help="Repository root (defaults to current directory).",
    )
    install_pc.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing different hook.",
    )
    # Keep logging flags consistent with other commands
    install_pc.add_argument("-v", "--verbose", action="store_true", help="Enable verbose (DEBUG) logging output.")
    install_pc.add_argument("-q", "--quiet", action="store_true", help="Disable output.")
    install_pc.set_defaults(func=install_precommit_handler)

    # --- uninstall-precommit Command ---
    uninstall_pc = subparsers.add_parser(
        "uninstall-precommit",
        help="Remove the bash2gitlab pre-commit hook.",
    )
    uninstall_pc.add_argument(
        "--repo-root",
        default=".",
        help="Repository root (defaults to current directory).",
    )
    uninstall_pc.add_argument(
        "--force",
        action="store_true",
        help="Remove even if the hook content does not match.",
    )
    uninstall_pc.add_argument("-v", "--verbose", action="store_true", help="Enable verbose (DEBUG) logging output.")
    uninstall_pc.add_argument("-q", "--quiet", action="store_true", help="Disable output.")
    uninstall_pc.set_defaults(func=uninstall_precommit_handler)

    # --- Doctor Command ---
    doctor_parser = subparsers.add_parser(
        "doctor", help="Run a series of health checks on the project and environment."
    )
    add_common_arguments(doctor_parser)
    doctor_parser.set_defaults(func=doctor_handler)

    # --- Graph Command ---
    graph_parser = subparsers.add_parser(
        "graph", help="Generate a DOT language dependency graph of your project's YAML and script files."
    )
    graph_parser.add_argument(
        "--in",
        dest="input_dir",
        required=not bool(config.compile_input_dir),
        help="Input directory containing the uncompiled `.gitlab-ci.yml` and other sources.",
    )
    add_common_arguments(graph_parser)
    graph_parser.set_defaults(func=graph_handler)

    # --- Show Config Command ---
    show_config_parser = subparsers.add_parser(
        "show-config", help="Display the current bash2gitlab configuration and its sources."
    )
    add_common_arguments(show_config_parser)
    show_config_parser.set_defaults(func=show_config_handler)

    # --- Run command ---
    run_parser = subparsers.add_parser("run", help="Best efforts to run a .gitlab-ci.yml file locally.")
    run_parser.add_argument(
        "--in-file",
        default=".gitlab-ci.yml",
        dest="input_file",
        required=False,
        help="Path to `.gitlab-ci.yml`, defaults to current directory",
    )

    add_common_arguments(run_parser)
    run_parser.set_defaults(func=best_effort_run_handler)

    # --- Detect Uncompiled ----
    # Add change detection arguments to argument parser
    detect_uncompiled_parser = subparsers.add_parser(
        "detect-uncompiled", help="Detect if input files have changed since last compilation"
    )
    detect_uncompiled_parser.add_argument(
        "--check-only", action="store_true", help="Only check if compilation is needed, do not compile"
    )
    detect_uncompiled_parser.add_argument(
        "--list-changed", action="store_true", help="List files that have changed since last compilation"
    )
    detect_uncompiled_parser.add_argument(
        "--in",
        dest="input_dir",
        default=config.compile_input_dir,
        required=not bool(config.compile_input_dir),
        help="Input directory containing the uncompiled `.gitlab-ci.yml` and other sources.",
    )
    detect_uncompiled_parser.set_defaults(func=handle_change_detection_commands)

    # --- Compile Command ---
    validate_parser = subparsers.add_parser("validate", help="Validate yaml pipelines against Gitlab json schema.")
    validate_parser.add_argument(
        "--in",
        dest="input_dir",
        required=not bool(config.compile_input_dir),
        help="Input directory containing the `.gitlab-ci.yml` and other sources.",
    )
    validate_parser.add_argument(
        "--out",
        dest="output_dir",
        required=not bool(config.compile_output_dir),
        help="Output directory for the compiled GitLab CI files.",
    )
    validate_parser.add_argument(
        "--parallelism",
        type=int,
        default=config.parallelism,
        help="Number of files to validate in parallel (default: CPU count).",
    )
    add_common_arguments(validate_parser)
    validate_parser.set_defaults(func=validate_handler)

    # --- Autogit Command ---
    autogit_parser = subparsers.add_parser(
        "autogit",
        help="Manually trigger the autogit process based on your configuration.",
        description="Stages, commits, and/or pushes changes in your configured input_dir and output_dir.",
    )
    autogit_parser.add_argument(
        "-m",
        "--message",
        help="Override the commit message defined in your config file.",
    )
    add_common_arguments(autogit_parser)
    autogit_parser.set_defaults(func=autogit_handler)

    get_pm().hook.register_cli(subparsers=subparsers, config=config)

    if argcomplete:
        argcomplete.autocomplete(parser)
    args = parser.parse_args()

    if totalhelp and getattr(args, "totalhelp", False):
        doc = totalhelp.full_help_from_parser(parser, fmt=getattr(args, "format", "text"))
        totalhelp.print_output(doc, fmt=getattr(args, "format", "text"), open_browser=getattr(args, "open", False))
        sys.exit(0)

    # --- Configuration Precedence: CLI > ENV > TOML ---
    # Merge string/path arguments
    if args.command == "compile":
        args.input_dir = args.input_dir or config.input_dir
        args.output_dir = args.output_dir or config.output_dir
        # Validate required arguments after merging
        if not args.input_dir:
            compile_parser.error("argument --in is required")
        if not args.output_dir:
            compile_parser.error("argument --out is required")
    elif args.command == "decompile":
        if hasattr(args, "input_file"):
            args_input_file = args.input_file
        else:
            args_input_file = ""
        if hasattr(args, "input_folder"):
            args_input_folder = args.input_folder
        else:
            args_input_folder = ""
        if hasattr(args, "output_dir"):
            args_output_dir = args.output_dir
        else:
            args_output_dir = ""
        args.input_file = args_input_file or config.decompile_input_file
        args.input_folder = args_input_folder or config.input_dir
        args.output_dir = args_output_dir or config.output_dir

        # Validate required arguments after merging
        if not args.input_file and not args.input_folder:
            decompile_parser.error("argument --input-folder or --input-file is required")
        if not args.output_dir:
            decompile_parser.error("argument --out is required")
    elif args.command == "clean":
        args.output_dir = args.output_dir or config.output_dir
        if not args.output_dir:
            clean_parser.error("argument --out is required")
    elif args.command == "lint":
        # Only merge --out from config; GitLab connection is explicit via CLI
        args.output_dir = args.output_dir or config.output_dir
        if not args.output_dir:
            lint_parser.error("argument --out is required")
    elif args.command == "check-pins":
        args.gitlab_url = args.gitlab_url or config.lint_gitlab_url  # reuse lint config
        if not args.gitlab_url:
            check_pins_parser.error("argument --gitlab-url is required")
    elif args.command == "trigger-pipelines":
        args.gitlab_url = args.gitlab_url or config.lint_gitlab_url
        if not args.gitlab_url:
            trigger_parser.error("argument --gitlab-url is required")
    elif args.command == "graph":
        # Only merge --out from config; GitLab connection is explicit via CLI
        args.input_dir = args.input_dir or config.input_dir
        if not args.input_dir:
            lint_parser.error("argument --in is required")
    # install-precommit / uninstall-precommit / doctor / graph / show-config / autogit do not merge config

    # Merge boolean flags
    args.verbose = getattr(args, "verbose", False) or config.verbose or False
    args.quiet = getattr(args, "quiet", False) or config.quiet or False
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

    if not hasattr(args, "func"):
        print("Command required.")
        sys.exit(ExitCode.USAGE)
    return run_cli(args)


def run_cli(args: argparse.Namespace) -> ExitCode:
    try:
        for _ in get_pm().hook.before_command(args=args):
            pass
        # Execute the appropriate handler

        rc = args.func(args)
        for _ in get_pm().hook.after_command(result=rc, args=args):
            pass

        return ExitCode.OK

    except Bash2GitlabError as e:
        if (hasattr(args, "debug") and args.debug) or (hasattr(args, "verbose") and args.verbose):
            raise
        # Domain error: short, human message; details in debug logs
        msg = str(e)
        print(f"error: {msg}", file=sys.stderr)
        # if e.detail:
        #     logger.debug("detail: %s", e.detail)
        logger.debug("trace:", exc_info=e)
        return resolve_exit_code(e)

    except NameError:
        print_install_help()
        return ExitCode.UNINSTALLED_DEPENDENCIES

    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return ExitCode.INTERRUPTED

    except Exception as e:  # unexpected bug
        if (hasattr(args, "debug") and args.debug) or (hasattr(args, "verbose") and args.verbose):
            raise
        print("unexpected error; run with --debug for details", file=sys.stderr)
        logger.exception("unhandled exception: %s", e)
        return resolve_exit_code(e)


if __name__ == "__main__":
    sys.exit(main())
