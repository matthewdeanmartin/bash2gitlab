## Tree for bash2gitlab
```
├── bash_reader.py
├── commands/
│   ├── clean_all.py
│   ├── clone2local.py
│   ├── commit_map.py
│   ├── compile_all.py
│   ├── compile_not_bash.py
│   ├── detect_drift.py
│   ├── init_project.py
│   ├── lint_all.py
│   ├── map_deploy.py
│   └── shred_all.py
├── config.py
├── py.typed
├── utils/
│   ├── cli_suggestions.py
│   ├── dotenv.py
│   ├── logging_config.py
│   ├── mock_ci_vars.py
│   ├── parse_bash.py
│   ├── update_checker.py
│   ├── utils.py
│   ├── yaml_factory.py
│   └── yaml_file_same.py
├── watch_files.py
├── __about__.py
└── __main__.py
```

## File: bash_reader.py
```python
"""Read a bash script and inline any `source script.sh` patterns."""

from __future__ import annotations

import logging
import os
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
# SOURCE_COMMAND_REGEX = re.compile(r"^\s*(?:source|\.)\s+(?P<path>[\w./\\-]+)\s*$")
# Handle optional comment.
SOURCE_COMMAND_REGEX = re.compile(r"^\s*(?:source|\.)\s+(?P<path>[\w./\\-]+)\s*(?:#.*)?$")


class SourceSecurityError(RuntimeError):
    pass


def _is_relative_to(child: Path, parent: Path) -> bool:
    """Py<3.9-compatible variant of Path.is_relative_to()."""
    # pylint: disable=broad-exception-caught
    try:
        child.relative_to(parent)
        return True
    except Exception:
        return False


def _secure_join(base_dir: Path, user_path: str, allowed_root: Path) -> Path:
    """
    Resolve 'user_path' (which may contain ../ and symlinks) against base_dir,
    then ensure the final real path is inside allowed_root.
    """
    # Normalize separators and strip quotes/whitespace
    user_path = user_path.strip().strip('"').strip("'").replace("\\", "/")

    # Resolve relative to the including script's directory
    candidate = (base_dir / user_path).resolve(strict=True)

    # Ensure the real path (after following symlinks) is within allowed_root
    allowed_root = allowed_root.resolve(strict=True)
    if not os.environ.get("BASH2GITLAB_SKIP_ROOT_CHECKS"):
        if not _is_relative_to(candidate, allowed_root):
            raise SourceSecurityError(f"Refusing to source '{candidate}': escapes allowed root '{allowed_root}'.")
    return candidate


def read_bash_script(path: Path) -> str:
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

    final = "".join(lines)
    if not final.endswith("\n"):
        return final + "\n"
    return final


def inline_bash_source(
    main_script_path: Path,
    processed_files: set[Path] | None = None,
    *,
    allowed_root: Path | None = None,
    max_depth: int = 64,
    _depth: int = 0,
) -> str:
    """
    Reads a bash script and recursively inlines content from sourced files.

    This function processes a bash script, identifies any 'source' or '.' commands,
    and replaces them with the content of the specified script. It handles
    nested sourcing and prevents infinite loops from circular dependencies.

    Safely inline bash sources by confining resolution to 'allowed_root' (default: CWD).
    Blocks directory traversal and symlink escapes. Detects cycles and runaway depth.

    Args:
        main_script_path: The absolute path to the main bash script to process.
        processed_files: A set used internally to track already processed files
                         to prevent circular sourcing. Should not be set manually.
        allowed_root: Root to prevent parent traversal
        max_depth: Depth
        _depth: For recursion


    Returns:
        A string containing the script content with all sourced files inlined.

    Raises:
        FileNotFoundError: If the main_script_path or any sourced script does not exist.
    """
    if processed_files is None:
        processed_files = set()

    if allowed_root is None:
        allowed_root = Path.cwd()

    # Normalize and security-check the entry script itself
    try:
        main_script_path = _secure_join(
            base_dir=main_script_path.parent if main_script_path.is_absolute() else Path.cwd(),
            user_path=str(main_script_path),
            allowed_root=allowed_root,
        )
    except FileNotFoundError:
        raise FileNotFoundError(f"Script not found: {main_script_path}") from None

    if _depth > max_depth:
        raise RecursionError(f"Max include depth ({max_depth}) exceeded at {main_script_path}")

    if main_script_path in processed_files:
        logger.warning("Circular source detected and skipped: %s", main_script_path)
        return ""

    # Check if the script exists before trying to read it
    if not main_script_path.is_file():
        raise FileNotFoundError(f"Script not found: {main_script_path}")

    logger.debug(f"Processing script: {main_script_path}")
    processed_files.add(main_script_path)

    final_content_lines: list[str] = []
    try:
        with main_script_path.open("r", encoding="utf-8") as f:
            for line in f:
                match = SOURCE_COMMAND_REGEX.match(line)
                if match:
                    # A source command was found, process the sourced file
                    sourced_script_name = match.group("path")
                    try:
                        sourced_script_path = _secure_join(
                            base_dir=main_script_path.parent,
                            user_path=sourced_script_name,
                            allowed_root=allowed_root,
                        )
                    except (FileNotFoundError, SourceSecurityError) as e:
                        logger.error(
                            "Blocked or missing source '%s' included from '%s': %s",
                            sourced_script_name,
                            main_script_path,
                            e,
                        )
                        raise

                    logger.info(
                        "Inlining sourced file: %s -> %s",
                        sourced_script_name,
                        sourced_script_path,
                    )
                    inlined = inline_bash_source(
                        sourced_script_path,
                        processed_files,
                        allowed_root=allowed_root,
                        max_depth=max_depth,
                        _depth=_depth + 1,
                    )
                    final_content_lines.append(inlined)
                else:
                    # This line is not a source command, so keep it as is
                    final_content_lines.append(line)
    except Exception:
        # Propagate after logging context
        logger.exception("Failed to read or process %s", main_script_path)
        raise

    final = "".join(final_content_lines)
    if not final.endswith("\n"):
        return final + "\n"
    return final
```
## File: config.py
```python
"""TOML based configuration. A way to communicate command arguments without using CLI switches."""

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
                file_config = data.get("tool", {}).get("bash2gitlab", {})
            else:
                file_config = data

            logger.info(f"Loaded configuration from {config_path}")
            return file_config

        except tomllib.TOMLDecodeError as e:
            logger.error(f"Error decoding TOML file {config_path}: {e}")
            return {}
        except OSError as e:
            logger.error(f"Error reading file {config_path}: {e}")
            return {}

    def _load_env_config(self) -> dict[str, str]:
        """Loads configuration from environment variables."""
        file_config = {}
        for key, value in os.environ.items():
            if key.startswith(self._ENV_VAR_PREFIX):
                config_key = key[len(self._ENV_VAR_PREFIX) :].lower()
                file_config[config_key] = value
                logger.debug(f"Loaded from environment: {config_key}")
        return file_config

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
    # pylint: disable=global-statement
    global config
    config = _Config(config_path_override=config_path_override)
```
## File: py.typed
```
# when type checking dependents, tell type checkers to use this package's types
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

from bash2gitlab.commands.compile_all import run_compile_all

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
        dry_run: bool = False,
        parallelism: int | None = None,
    ) -> None:
        super().__init__()
        self._paths = {
            "uncompiled_path": uncompiled_path,
            "output_path": output_path,
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
            run_compile_all(**self._paths, **self._flags)  # type: ignore[arg-type]
            logger.info("✅ Recompiled successfully.")
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("❌ Recompilation failed: %s", exc, exc_info=True)


def start_watch(
    *,
    uncompiled_path: Path,
    output_path: Path,
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
        dry_run=dry_run,
        parallelism=parallelism,
    )

    observer = Observer()
    observer.schedule(handler, str(uncompiled_path), recursive=True)

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
__version__ = "0.8.8"
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
Handles CLI interactions for bash2gitlab

usage: bash2gitlab [-h] [--version]
                   {compile,shred,detect-drift,copy2local,init,map-deploy,commit-map,clean,lint}
                   ...

A tool for making development of centralized yaml gitlab templates more pleasant.

positional arguments:
  {compile,shred,detect-drift,copy2local,init,map-deploy,commit-map,clean,lint}
    compile             Compile an uncompiled directory into a standard GitLab CI structure.
    shred               Shred a GitLab CI file, extracting inline scripts into separate .sh files.
    detect-drift        Detect if generated files have been edited and display what the edits are.
    copy2local          Copy folder(s) from a repo to local, for testing bash in the dependent repo
    init                Initialize a new bash2gitlab project and config file.
    map-deploy          Deploy files from source to target directories based on a mapping in pyproject.toml.
    commit-map          Copy changed files from deployed directories back to their source locations based on a mapping in pyproject.toml.
    clean               Clean output folder, removing only unmodified files previously written by bash2gitlab.
    lint                Validate compiled GitLab CI YAML against a GitLab instance (global or project-scoped CI Lint).

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
from urllib import error as _urlerror

import argcomplete

from bash2gitlab import __about__
from bash2gitlab import __doc__ as root_doc
from bash2gitlab.commands.clean_all import clean_targets
from bash2gitlab.commands.clone2local import clone_repository_ssh, fetch_repository_archive
from bash2gitlab.commands.commit_map import run_commit_map
from bash2gitlab.commands.compile_all import run_compile_all
from bash2gitlab.commands.detect_drift import run_detect_drift
from bash2gitlab.commands.init_project import create_config_file, prompt_for_config
from bash2gitlab.commands.lint_all import lint_output_folder, summarize_results
from bash2gitlab.commands.map_deploy import get_deployment_map, run_map_deploy
from bash2gitlab.commands.shred_all import run_shred_gitlab
from bash2gitlab.config import config
from bash2gitlab.utils.cli_suggestions import SmartParser
from bash2gitlab.utils.logging_config import generate_config
from bash2gitlab.utils.update_checker import check_for_updates
from bash2gitlab.watch_files import start_watch

logger = logging.getLogger(__name__)


def clean_handler(args: argparse.Namespace) -> int:
    """Handles the `clean` command logic."""
    logger.info("Starting cleaning output folder...")
    out_dir = Path(args.output_dir).resolve()
    try:
        clean_targets(out_dir, dry_run=args.dry_run)
    except (KeyboardInterrupt, EOFError):
        logger.warning("\nClean cancelled by user.")
        return 1
    return 0


essential_gitlab_args_help = (
    "GitLab connection options. For private instances require --gitlab-url and possibly --token. "
    "Use --project-id for project-scoped lint when your config relies on includes or project context."
)


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
        return 10

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
        return 12
    # defensive logging of unexpected failures
    except Exception as e:  # nosec
        logger.error("Unexpected error during lint: %s", e)
        return 1

    ok, fail = summarize_results(results)
    return 0 if fail == 0 else 2


def init_handler(args: argparse.Namespace) -> int:
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


def clone2local_handler(args: argparse.Namespace) -> int:
    """
    Argparse handler for the clone2local command.

    This handler remains compatible with the new archive-based fetch function.
    """
    # This function now calls the new implementation, preserving the call stack.
    dry_run = bool(args.dry_run)

    if str(args.repo_url).startswith("ssh"):
        clone_repository_ssh(args.repo_url, args.branch, args.source_dir, args.copy_dir, dry_run)
    else:
        fetch_repository_archive(args.repo_url, args.branch, args.source_dir, args.copy_dir, dry_run)
    return 0


def compile_handler(args: argparse.Namespace) -> int:
    """Handler for the 'compile' command."""
    logger.info("Starting bash2gitlab compiler...")

    # Resolve paths, using sensible defaults if optional paths are not provided
    in_dir = Path(args.input_dir).resolve()
    out_dir = Path(args.output_dir).resolve()
    dry_run = bool(args.dry_run)
    parallelism = args.parallelism

    if args.watch:
        start_watch(
            uncompiled_path=in_dir,
            output_path=out_dir,
            dry_run=dry_run,
            parallelism=parallelism,
        )
        return 0

    try:
        run_compile_all(
            uncompiled_path=in_dir,
            output_path=out_dir,
            dry_run=dry_run,
            parallelism=parallelism,
        )

        logger.info("✅ GitLab CI processing complete.")

    except FileNotFoundError as e:
        logger.error(f"❌ An error occurred: {e}")
        return 10
    except (RuntimeError, ValueError) as e:
        logger.error(f"❌ An error occurred: {e}")
        return 1
    return 0


def drift_handler(args: argparse.Namespace) -> int:
    run_detect_drift(Path(args.out))
    return 0


def shred_handler(args: argparse.Namespace) -> int:
    """Handler for the 'shred' command."""
    logger.info("Starting bash2gitlab shredder...")

    # Resolve the file and directory paths
    in_file = Path(args.input_file).resolve()
    out_file = Path(args.output_file).resolve()

    dry_run = bool(args.dry_run)

    try:
        jobs, scripts = run_shred_gitlab(input_yaml_path=in_file, output_yaml_path=out_file, dry_run=dry_run)

        if dry_run:
            logger.info(f"DRY RUN: Would have processed {jobs} jobs and created {scripts} script(s).")
        else:
            logger.info(f"✅ Successfully processed {jobs} jobs and created {scripts} script(s).")
            logger.info(f"Modified YAML written to: {out_file}")
        return 0
    except FileNotFoundError as e:
        logger.error(f"❌ An error occurred: {e}")
        return 10


def commit_map_handler(args: argparse.Namespace) -> int:
    pyproject_path = Path(args.pyproject_path)
    try:
        mapping = get_deployment_map(pyproject_path)
    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        return 10
    except KeyError as ke:
        logger.error(f"❌ {ke}")
        return 11

    run_commit_map(mapping, dry_run=args.dry_run, force=args.force)
    return 0


def map_deploy_handler(args: argparse.Namespace) -> int:

    pyproject_path = Path(args.pyproject_path)
    try:
        mapping = get_deployment_map(pyproject_path)
    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        return 10
    except KeyError as ke:
        logger.error(f"❌ {ke}")
        return 11

    run_map_deploy(mapping, dry_run=args.dry_run, force=args.force)
    return 0


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the command without filesystem changes.",
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose (DEBUG) logging output.")
    parser.add_argument("-q", "--quiet", action="store_true", help="Disable output.")


def main() -> int:
    """Main CLI entry point."""
    check_for_updates(__about__.__title__, __about__.__version__)

    parser = SmartParser(
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
    add_common_arguments(compile_parser)
    compile_parser.set_defaults(func=compile_handler)

    # Clean Parser
    clean_parser = subparsers.add_parser(
        "clean",
        help="Clean output folder, only removes unmodified files that bash2gitlab wrote.",
    )
    clean_parser.add_argument(
        "--out",
        dest="output_dir",
        required=not bool(config.output_dir),
        help="Output directory for the compiled GitLab CI files.",
    )
    add_common_arguments(clean_parser)
    clean_parser.set_defaults(func=clean_handler)

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
    add_common_arguments(shred_parser)
    shred_parser.set_defaults(func=shred_handler)

    # detect drift command
    detect_drift_parser = subparsers.add_parser(
        "detect-drift", help="Detect if generated files have been edited and display what the edits are."
    )
    detect_drift_parser.add_argument(
        "--out",
        dest="out",
        help="Output path where generated files are.",
    )
    add_common_arguments(detect_drift_parser)
    detect_drift_parser.set_defaults(func=drift_handler)

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
    add_common_arguments(clone_parser)
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
    add_common_arguments(init_parser)
    init_parser.set_defaults(func=init_handler)

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
    map_deploy_parser.set_defaults(func=map_deploy_handler)

    # --- commit-map Command ---
    commit_map_parser = subparsers.add_parser(
        "commit-map",
        help=(
            "Copy changed files from deployed directories back to their source"
            " locations based on a mapping in pyproject.toml."
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
        dest="gitlab_url",
        required=True,
        help="Base GitLab URL (e.g., https://gitlab.com).",
    )
    lint_parser.add_argument(
        "--token",
        dest="token",
        help="PRIVATE-TOKEN or CI_JOB_TOKEN to authenticate with the API.",
    )
    lint_parser.add_argument(
        "--project-id",
        dest="project_id",
        type=int,
        help="Project ID for project-scoped lint (recommended for configs with includes).",
    )
    lint_parser.add_argument(
        "--ref",
        dest="ref",
        help="Git ref to evaluate includes/variables against (project lint only).",
    )
    lint_parser.add_argument(
        "--include-merged-yaml",
        dest="include_merged_yaml",
        action="store_true",
        help="Return merged YAML from project-scoped lint (slower).",
    )
    lint_parser.add_argument(
        "--parallelism",
        dest="parallelism",
        type=int,
        default=config.parallelism,
        help="Max concurrent lint requests (default: CPU count, capped to file count).",
    )
    lint_parser.add_argument(
        "--timeout",
        dest="timeout",
        type=float,
        default=20.0,
        help="HTTP timeout per request in seconds (default: 20).",
    )
    add_common_arguments(lint_parser)
    lint_parser.set_defaults(func=lint_handler)

    argcomplete.autocomplete(parser)
    args = parser.parse_args()

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
    elif args.command == "shred":
        args.input_file = args.input_file or config.input_file
        args.output_file = args.output_file or config.output_file
        # Validate required arguments after merging
        if not args.input_file:
            shred_parser.error("argument --in is required")
        if not args.output_file:
            shred_parser.error("argument --out is required")
    elif args.command == "clean":
        args.output_dir = args.output_dir or config.output_dir
        if not args.output_dir:
            clean_parser.error("argument --out is required")
    elif args.command == "lint":
        # Only merge --out from config; GitLab connection is explicit via CLI
        args.output_dir = args.output_dir or config.output_dir
        if not args.output_dir:
            lint_parser.error("argument --out is required")

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
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```
## File: commands\clean_all.py
```python
from __future__ import annotations

import base64
import logging
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger(__name__)

# --- Helpers -----------------------------------------------------------------


def _partner_hash_file(base_file: Path) -> Path:
    """Return the expected .hash file for a target file.

    Example: foo/bar.yml -> foo/bar.yml.hash
    """
    return base_file.with_suffix(base_file.suffix + ".hash")


def _base_from_hash(hash_file: Path) -> Path:
    """Return the expected base file for a .hash file.

    Works even on older Python without Path.removesuffix().
    Example: foo/bar.yml.hash -> foo/bar.yml
    """
    s = str(hash_file)
    suffix = ".hash"
    if s.endswith(suffix):
        return Path(s[: -len(suffix)])
    return hash_file  # unexpected, but avoid throwing


# --- Inspection utilities -----------------------------------------------------


def iter_target_pairs(root: Path) -> Iterator[tuple[Path, Path]]:
    """Yield (base_file, hash_file) pairs under *root* recursively.

    Only yields pairs where *both* files exist.
    """
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if p.name.endswith(".hash"):
            base = _base_from_hash(p)
            if base.exists() and base.is_file():
                yield (base, p)
        else:
            hashf = _partner_hash_file(p)
            if hashf.exists() and hashf.is_file():
                # Pair will also be seen when rglob hits the .hash file; skip duplicates
                continue


def list_stray_files(root: Path) -> list[Path]:
    """Return files under *root* that do **not** have a hash pair.

    A "stray" is either:
    - a non-.hash file with no corresponding ``<file>.hash``; or
    - a ``.hash`` file whose base file is missing.
    """
    strays: list[Path] = []

    # Track pairs we've seen to avoid extra disk checks
    paired_bases: set[Path] = set()
    paired_hashes: set[Path] = set()

    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if p.suffix == "":
            # still fine; pairing is based on full name + .hash
            pass

        if p.name.endswith(".hash"):
            base = _base_from_hash(p)
            if base.exists():
                paired_bases.add(base)
                paired_hashes.add(p)
            else:
                strays.append(p)
        else:
            hashf = _partner_hash_file(p)
            if hashf.exists():
                paired_bases.add(p)
                paired_hashes.add(hashf)
            else:
                strays.append(p)

    logger.info("Found %d stray file(s) under %s", len(strays), root)
    for s in strays:
        logger.debug("Stray: %s", s)
    return sorted(strays)


# --- Hash verification --------------------------------------------------------


def _read_current_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_hash_text(hash_file: Path) -> str | None:
    """Decode base64 content of *hash_file* to text.

    Returns None if decoding fails.
    """
    try:
        raw = hash_file.read_text(encoding="utf-8").strip()
        return base64.b64decode(raw).decode("utf-8")
    # best-effort guard
    except Exception as e:  # nosec
        logger.warning("Failed to decode hash file %s: %s", hash_file, e)
        return None


def is_target_unchanged(base_file: Path, hash_file: Path) -> bool | None:
    """Check if *base_file* matches the content recorded in *hash_file*.

    Returns:
        - True if contents match
        - False if they differ
        - None if the hash file cannot be decoded
    """
    expected = _read_hash_text(hash_file)
    if expected is None:
        return None
    current = _read_current_text(base_file)
    return current == expected


# --- Cleaning -----------------------------------------------------------------


def clean_targets(root: Path, *, dry_run: bool = False) -> tuple[int, int, int]:
    """Delete generated target files (and their .hash files) under *root*.

    Only deletes when a valid pair exists **and** the base file content matches
    the recorded hash. "Stray" files are always left alone.

    Args:
        root: Directory containing compiled outputs and ``*.hash`` files.
        dry_run: If True, log what would be deleted but do not delete.

    Returns:
        tuple of (deleted_pairs, skipped_changed, skipped_invalid_hash)
    """
    deleted = 0
    skipped_changed = 0
    skipped_invalid = 0

    # Build a unique set of pairs to consider
    seen_pairs: set[tuple[Path, Path]] = set()
    for p in root.rglob("*.hash"):
        if p.is_dir():
            continue
        base = _base_from_hash(p)
        if not base.exists() or not base.is_file():
            # Stray .hash; leave it
            continue
        seen_pairs.add((base, p))

    if not seen_pairs:
        logger.info("No target pairs found under %s", root)
        return (0, 0, 0)

    for base, hashf in sorted(seen_pairs):
        status = is_target_unchanged(base, hashf)
        if status is None:
            skipped_invalid += 1
            logger.warning("Refusing to remove %s (invalid/corrupt hash at %s)", base, hashf)
            continue
        if status is False:
            skipped_changed += 1
            logger.warning("Refusing to remove %s (content has changed since last write)", base)
            continue

        # status is True: safe to delete
        if dry_run:
            logger.info("[DRY RUN] Would delete %s and %s", base, hashf)
        else:
            try:
                base.unlink(missing_ok=False)
                hashf.unlink(missing_ok=True)
                logger.info("Deleted %s and %s", base, hashf)
            # narrow surface area; logs any fs issues
            except Exception as e:  # nosec
                logger.error("Failed to delete %s / %s: %s", base, hashf, e)
                continue
        deleted += 1

    logger.info(
        "Clean summary: %d pair(s) deleted, %d changed file(s) skipped, %d invalid hash(es) skipped",
        deleted,
        skipped_changed,
        skipped_invalid,
    )
    return (deleted, skipped_changed, skipped_invalid)


# --- Optional: quick report helper -------------------------------------------


def report_targets(root: Path) -> list[Path]:
    """Log a concise report of pairs, strays, and safety status.

    Useful for diagnostics before/after ``clean_targets``.
    """
    pairs = list(iter_target_pairs(root))
    strays = list_stray_files(root)

    logger.debug("Target report for %s", root)
    logger.debug("Pairs found: %d", len(pairs))
    for base, hashf in pairs:
        status = is_target_unchanged(base, hashf)
        if status is True:
            logger.debug("OK: %s (hash matches)", base)
        elif status is False:
            logger.warning("CHANGED: %s (hash mismatch)", base)
        else:
            logger.warning("INVALID HASH: %s (cannot decode %s)", base, hashf)

    logger.debug("Strays: %d", len(strays))
    for s in strays:
        logger.debug("Stray: %s", s)
    return strays
```
## File: commands\clone2local.py
```python
"""A command to copy just some of a centralized repo's bash commands to a local repo for debugging."""

from __future__ import annotations

import logging
import shutil
import subprocess  # nosec: B404
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["fetch_repository_archive", "clone_repository_ssh"]


def fetch_repository_archive(
    repo_url: str, branch: str, source_dir: str, clone_dir: str | Path, dry_run: bool = False
) -> None:
    """Fetches and extracts a specific directory from a repository archive.

    This function avoids using Git by downloading the repository as a ZIP archive.
    It unpacks the archive to a temporary location, copies the requested
    source directory to the final destination, and cleans up all temporary
    files upon completion or in case of an error.

    Args:
        repo_url: The base URL of the repository (e.g., 'https://github.com/user/repo').
        branch: The name of the branch to download (e.g., 'main', 'develop').
        source_dir: A single directory path (relative to the repo root) to
            extract and copy to the clone_dir.
        clone_dir: The destination directory. This directory must be empty.
        dry_run: Simulate action

    Raises:
        FileExistsError: If the clone_dir exists and is not empty.
        ConnectionError: If the specified branch archive cannot be found, accessed,
            or if a network error occurs.
        IOError: If the downloaded archive is empty or has an unexpected
            file structure.
        TypeError: If the repository URL does not use an http/https protocol.
        Exception: Propagates other exceptions from network, file, or
            archive operations after attempting to clean up.
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
    if not dry_run:
        clone_path.mkdir(parents=True, exist_ok=True)

    try:
        # Use a temporary directory that cleans itself up automatically.
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            archive_path = temp_path / "repo.zip"
            unzip_root = temp_path / "unzipped"
            if not dry_run:
                unzip_root.mkdir()

            # 2. Construct the archive URL and check for its existence.
            archive_url = f"{repo_url.rstrip('/')}/archive/refs/heads/{branch}.zip"
            if not archive_url.startswith("http"):
                raise TypeError(f"Expected http or https protocol, got {archive_url}")

            try:
                # Use a simple open to verify existence without a full download.
                # URL is constructed from trusted inputs in this context.
                with urllib.request.urlopen(archive_url, timeout=10) as _response:  # nosec: B310
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
            # URL is validated above.
            if not dry_run:
                urllib.request.urlretrieve(archive_url, archive_path)  # nosec: B310

            # 3. Unzip the downloaded archive.
            logger.info("Extracting archive to %s", unzip_root)
            if dry_run:
                # Nothing left meaningful to dry run
                return

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
            dest_dir = clone_path

            if repo_source_dir.is_dir():
                logger.debug("Copying '%s' to '%s'", repo_source_dir, dest_dir)
                # FIX: Use the correct source path `repo_source_dir` for the copy operation.
                shutil.copytree(repo_source_dir, dest_dir, dirs_exist_ok=True)
            else:
                logger.warning("Directory '%s' not found in repository archive, skipping.", repo_source_dir)

    except Exception as e:
        logger.error("Operation failed: %s. Cleaning up destination directory.", e)
        # 5. Clean up the destination on any failure.
        shutil.rmtree(clone_path, ignore_errors=True)
        # Re-raise the exception to notify the caller of the failure.
        raise

    logger.info("Successfully fetched directories into %s", clone_path)


def clone_repository_ssh(
    repo_url: str, branch: str, source_dir: str, clone_dir: str | Path, dry_run: bool = False
) -> None:
    """Clones a repo via Git and copies a specific directory.

    This function is designed for SSH or authenticated HTTPS URLs that require
    local Git and credential management (e.g., SSH keys). It performs an
    efficient, shallow clone of a specific branch into a temporary directory,
    then copies the requested source directory to the final destination.

    Args:
        repo_url: The repository URL (e.g., 'git@github.com:user/repo.git').
        branch: The name of the branch to check out (e.g., 'main', 'develop').
        source_dir: A single directory path (relative to the repo root) to copy.
        clone_dir: The destination directory. This directory must be empty.
        dry_run: Simulate action

    Raises:
        FileExistsError: If the clone_dir exists and is not empty.
        subprocess.CalledProcessError: If any Git command fails.
        Exception: Propagates other exceptions from file operations after
            attempting to clean up.
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
    if not dry_run:
        clone_path.mkdir(parents=True, exist_ok=True)

    try:
        # Use a temporary directory for the full clone, which will be auto-cleaned.
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_clone_path = Path(temp_dir)
            logger.info("Cloning '%s' to temporary location: %s", repo_url, temp_clone_path)

            # 2. Clone the repository.
            # We clone the specific branch directly to be more efficient.
            # repo_url is a variable, but is intended to be a trusted source.
            command = ["git", "clone", "--depth", "1", "--branch", branch, repo_url, str(temp_clone_path)]
            if dry_run:
                logger.info(f"Would have run {' '.join(command)}")
            else:
                subprocess.run(  # nosec: B603, B607
                    ["git", "clone", "--depth", "1", "--branch", branch, repo_url, str(temp_clone_path)],
                    check=True,
                    capture_output=True,  # Capture stdout/stderr to hide git's noisy output
                )

            logger.info("Clone successful. Copying specified directories.")
            # 3. Copy the specified directory to the final destination.
            repo_source_dir = temp_clone_path / source_dir
            dest_dir = clone_path

            if repo_source_dir.is_dir():
                logger.debug("Copying '%s' to '%s'", repo_source_dir, dest_dir)
                shutil.copytree(repo_source_dir, dest_dir, dirs_exist_ok=True)
            elif not dry_run:
                logger.warning("Directory '%s' not found in repository, skipping.", source_dir)

    except Exception as e:
        logger.error("Operation failed: %s. Cleaning up destination directory.", e)
        # 4. Clean up the destination on any failure.
        shutil.rmtree(clone_path, ignore_errors=True)
        # Re-raise the exception to notify the caller of the failure.
        raise

    logger.info("Successfully cloned directories into %s", clone_path)
```
## File: commands\commit_map.py
```python
"""Copy from many repos relevant shell scripts changes back to the central repo."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
from pathlib import Path

__all__ = ["run_commit_map"]


_VALID_SUFFIXES = {".sh", ".ps1", ".yml", ".yaml"}

logger = logging.getLogger(__name__)


def run_commit_map(
    source_to_target_map: dict[str, str],
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Copy modified deployed files back to their source directories.

    This function performs the inverse of :func:`bash2gitlab.map_deploy_command.map_deploy`.
    For every mapping of ``source`` to ``target`` directories it traverses the
    deployed ``target`` directory and copies changed files back to the
    corresponding ``source`` directory. Change detection relies on ``.hash``
    files created during deployment. A file is copied back when the content of
    the deployed file differs from the stored hash. After a successful copy the
    ``.hash`` file is updated to reflect the new content hash.

    Args:
        source_to_target_map: Mapping of source directories to deployed target
            directories.
        dry_run: If ``True`` the operation is only simulated and no files are
            written.
        force: If ``True`` a source file is overwritten even if it was modified
            locally since the last deployment.
    """
    for source_base, target_base in source_to_target_map.items():
        source_base_path = Path(source_base).resolve()
        target_base_path = Path(target_base).resolve()

        if not target_base_path.is_dir():
            print(f"Warning: Target directory '{target_base_path}' does not exist. Skipping.")
            continue

        print(f"\nProcessing map: '{target_base_path}' -> '{source_base_path}'")

        for root, _, files in os.walk(target_base_path):
            target_root_path = Path(root)

            for filename in files:
                if filename == ".gitignore" or filename.endswith(".hash"):
                    continue

                target_file_path = target_root_path / filename
                if target_file_path.suffix.lower() not in _VALID_SUFFIXES:
                    continue

                relative_path = target_file_path.relative_to(target_base_path)
                source_file_path = source_base_path / relative_path
                hash_file_path = target_file_path.with_suffix(target_file_path.suffix + ".hash")

                # Calculate hash of the deployed file
                with open(target_file_path, "rb") as f:
                    target_hash = hashlib.sha256(f.read()).hexdigest()

                stored_hash = ""
                if hash_file_path.exists():
                    with open(hash_file_path, encoding="utf-8") as f:
                        stored_hash = f.read().strip()

                source_hash_actual = ""
                if source_file_path.exists():
                    with open(source_file_path, "rb") as f:
                        source_hash_actual = hashlib.sha256(f.read()).hexdigest()

                if stored_hash and target_hash == stored_hash:
                    print(f"Unchanged: '{target_file_path}'")
                    continue

                if stored_hash and source_hash_actual and source_hash_actual != stored_hash and not force:
                    print(f"Warning: '{source_file_path}' was modified in source since last deployment.")
                    print("Skipping copy. Use --force to overwrite.")
                    continue

                action = "Copied" if not source_file_path.exists() else "Updated"
                print(f"{action}: '{target_file_path}' -> '{source_file_path}'")

                if dry_run:
                    continue

                if not source_file_path.parent.exists():
                    print(f"Creating directory: {source_file_path.parent}")
                    source_file_path.parent.mkdir(parents=True, exist_ok=True)

                shutil.copy2(target_file_path, source_file_path)
                with open(hash_file_path, "w", encoding="utf-8") as f:
                    f.write(target_hash)
```
## File: commands\compile_all.py
```python
"""Command to inline bash or powershell into gitlab pipeline yaml."""

from __future__ import annotations

import base64
import difflib
import io
import logging
import multiprocessing
import sys
from pathlib import Path
from typing import Any

from ruamel.yaml import CommentedMap, CommentedSeq
from ruamel.yaml.comments import TaggedScalar
from ruamel.yaml.error import YAMLError
from ruamel.yaml.scalarstring import LiteralScalarString

from bash2gitlab.bash_reader import read_bash_script
from bash2gitlab.commands.clean_all import report_targets
from bash2gitlab.commands.compile_not_bash import _maybe_inline_interpreter_command
from bash2gitlab.utils.dotenv import parse_env_file
from bash2gitlab.utils.parse_bash import extract_script_path
from bash2gitlab.utils.utils import remove_leading_blank_lines, short_path
from bash2gitlab.utils.yaml_factory import get_yaml
from bash2gitlab.utils.yaml_file_same import normalize_for_compare, yaml_is_same

logger = logging.getLogger(__name__)

__all__ = ["run_compile_all"]


def remove_excess(command: str) -> str:
    if "bash2gitlab" in command:
        return command[command.index("bash2gitlab") :]
    if "b2gl" in command:
        return command[command.index("b2gl") :]
    return command


BANNER = f"""# DO NOT EDIT
# This is a compiled file, compiled with bash2gitlab
# Recompile instead of editing this file.
#
# Compiled with the command: 
#     {remove_excess(' '.join(sys.argv))}

"""


def _as_items(
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


def _rebuild_seq_like(
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


def process_script_list(
    script_list: list[TaggedScalar | str] | CommentedSeq | str,
    scripts_root: Path,
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

    Returns:
        list[Any] | CommentedSeq | LiteralScalarString: Processed script block. Returns a
        ``LiteralScalarString`` when safe to collapse; otherwise returns a list or
        ``CommentedSeq`` (matching the input style) to preserve YAML features.
    """
    items, was_commented_seq, original_seq = _as_items(script_list)

    processed_items: list[Any] = []
    contains_tagged_scalar = False
    contains_anchors_or_tags = False

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
        script_path_str = extract_script_path(item)
        if script_path_str:
            rel_path = script_path_str.strip().lstrip("./")
            script_path = scripts_root / rel_path
            try:
                bash_code = read_bash_script(script_path)
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
            except (FileNotFoundError, ValueError) as e:
                logger.warning(
                    "Could not inline script '%s': %s. Preserving original line.",
                    script_path_str,
                    e,
                )
                processed_items.append(item)
        else:
            # NEW: interpreter-based script inlining (python/node/ruby/php/fish)
            interp_inline = _maybe_inline_interpreter_command(item, scripts_root)
            if interp_inline:
                processed_items.extend(interp_inline)
            else:
                processed_items.append(item)

    # Decide output representation
    only_plain_strings = all(isinstance(_, str) for _ in processed_items)
    has_yaml_features = (
        contains_tagged_scalar or contains_anchors_or_tags or was_commented_seq and not only_plain_strings
    )

    # Collapse to literal block only when no YAML features and sufficiently long
    if not has_yaml_features and only_plain_strings and len(processed_items) > 2:
        final_script_block = "\n".join(processed_items)
        logger.debug("Formatting script block as a single literal block (no anchors/tags detected).")
        return LiteralScalarString(final_script_block)

    # Preserve sequence shape; if input was a CommentedSeq, return one
    return _rebuild_seq_like(processed_items, was_commented_seq, original_seq)


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
    yaml = get_yaml()
    data = yaml.load(io.StringIO(gitlab_ci_yaml))

    # Merge global variables if provided
    # if global_vars:
    #     logger.debug("Merging global variables into the YAML configuration.")
    #     existing_vars = data.get("variables", {})
    #     merged_vars = global_vars.copy()
    #     # Update with existing vars, so YAML-defined vars overwrite global ones on conflict.
    #     merged_vars.update(existing_vars)
    #     data["variables"] = merged_vars
    #     inlined_count += 1
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
        inlined_count += 1

    for name in ["after_script", "before_script"]:
        if name in data:
            logger.warning(f"Processing top-level '{name}' section, even though gitlab has deprecated them.")
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

    output_file.write_text(new_content, encoding="utf-8")

    # Store a base64 encoded copy of the exact content we just wrote.
    encoded_content = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
    hash_file.write_text(encoded_content, encoding="utf-8")
    logger.debug(f"Updated hash file: {short_path(hash_file)}")


def _unified_diff(old: str, new: str, path: Path, from_label: str = "current", to_label: str = "new") -> str:
    """Return a unified diff between *old* and *new* content with filenames.

    keepends=True preserves newline structure for line-accurate diffs in logs.
    """
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"{path} ({from_label})",
            tofile=f"{path} ({to_label})",
        )
    )


def _diff_stats(diff_text: str) -> tuple[int, int, int]:
    """Compute (changed_lines, insertions, deletions) from unified diff text.

    We ignore headers (---, +++, @@). A changed line is any insertion or deletion.
    """
    ins = del_ = 0
    for line in diff_text.splitlines():
        if not line:
            continue
        # Skip headers/hunks
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        # Pure additions/deletions in unified diff start with '+' or '-'
        if line.startswith("+"):
            ins += 1
        elif line.startswith("-"):
            del_ += 1
    return ins + del_, ins, del_


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
            diff_text = _unified_diff(
                normalize_for_compare(current_content), normalize_for_compare(new_content), output_file
            )
            changed, ins, rem = _diff_stats(diff_text)
            logger.info(f"[DRY RUN] Would rewrite {short_path(output_file)}: {changed} lines changed (+{ins}, -{rem}).")
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
        last_known_content = base64.b64decode(last_known_base64).decode("utf-8")
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
    yaml = get_yaml()
    try:
        last_known_doc = yaml.load(last_known_content)
    except YAMLError as e:
        logger.error(
            "ERROR: Could not parse YAML from the .hash file for '%s'. It is corrupted. Error: %s",
            short_path(output_file),
            e,
        )
        raise SystemExit(1) from e

    try:
        current_doc = yaml.load(current_content)
        is_current_corrupt = False
    except YAMLError:
        current_doc = None
        is_current_corrupt = True
        logger.warning("Could not parse YAML from '%s'; it appears to be corrupt.", short_path(output_file))

    # An edit is detected if the current file is corrupt OR the parsed YAML documents are not identical.
    is_same = yaml_is_same(last_known_content, current_content)
    # current_doc != last_known_doc
    if is_current_corrupt or (current_doc != last_known_doc and not is_same):
        diff_text = _unified_diff(
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

        error_message = (
            f"\n--- MANUAL EDIT DETECTED ---\n"
            f"CANNOT OVERWRITE: The destination file below has been modified:\n"
            f"  {output_file}\n\n"
            f"{corruption_warning}"
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
    if not yaml_is_same(current_content, new_content):
        # NEW: log diff + counts before writing
        diff_text = _unified_diff(
            normalize_for_compare(current_content), normalize_for_compare(new_content), output_file
        )
        changed, ins, rem = _diff_stats(diff_text)
        logger.info(
            "(1) Rewriting %s: %d lines changed (+%d, -%d).",
            short_path(output_file),
            changed,
            ins,
            rem,
        )
        logger.debug(diff_text)

        write_yaml_and_hash(output_file, new_content, hash_file)
        return True

    logger.debug("Content of %s is already up to date. Skipping.", short_path(output_file))
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
    logger.debug(f"Processing {label}: {short_path(source_path)}")
    raw_text = source_path.read_text(encoding="utf-8")
    inlined_for_file, compiled_text = inline_gitlab_scripts(raw_text, scripts_path, variables, uncompiled_path)
    final_content = (BANNER + compiled_text) if inlined_for_file > 0 else raw_text
    written = write_compiled_file(output_file, final_content, dry_run)
    return inlined_for_file, int(written)


def run_compile_all(
    uncompiled_path: Path,
    output_path: Path,
    dry_run: bool = False,
    parallelism: int | None = None,
) -> int:
    """
    Main function to process a directory of uncompiled GitLab CI files.
    This version safely writes files by checking hashes to avoid overwriting manual changes.

    Args:
        uncompiled_path (Path): Path to the input .gitlab-ci.yml, other yaml and bash files.
        output_path (Path): Path to write the .gitlab-ci.yml file and other yaml.
        dry_run (bool): If True, simulate the process without writing any files.
        parallelism (int | None): Maximum number of processes to use for parallel compilation.

    Returns:
        The total number of inlined sections across all files.
    """
    strays = report_targets(output_path)
    if strays:
        print("Stray files in output folder, halting")
        for stray in strays:
            print(f"  {stray}")
        sys.exit(200)

    total_inlined_count = 0
    written_files_count = 0

    if not dry_run:
        output_path.mkdir(parents=True, exist_ok=True)

    global_vars_path = uncompiled_path / "global_variables.sh"
    if global_vars_path.is_file():
        logger.info(f"Found and loading variables from {short_path(global_vars_path)}")
        content = global_vars_path.read_text(encoding="utf-8")
        parse_env_file(content)
        total_inlined_count += 1

    files_to_process: list[tuple[Path, Path, dict[str, str], str]] = []

    if uncompiled_path.is_dir():
        template_files = list(uncompiled_path.rglob("*.yml")) + list(uncompiled_path.rglob("*.yaml"))
        if not template_files:
            logger.warning(f"No template YAML files found in {uncompiled_path}")

        for template_path in template_files:
            relative_path = template_path.relative_to(uncompiled_path)
            output_file = output_path / relative_path
            files_to_process.append((template_path, output_file, {}, "template file"))

    total_files = len(files_to_process)
    max_workers = multiprocessing.cpu_count()
    if parallelism and parallelism > 0:
        max_workers = min(parallelism, max_workers)

    if total_files >= 5 and max_workers > 1 and parallelism:
        args_list = [
            (src, out, uncompiled_path, variables, uncompiled_path, dry_run, label)
            for src, out, variables, label in files_to_process
        ]
        with multiprocessing.Pool(processes=max_workers) as pool:
            results = pool.starmap(_compile_single_file, args_list)
        total_inlined_count += sum(inlined for inlined, _ in results)
        written_files_count += sum(written for _, written in results)
    else:
        for src, out, variables, label in files_to_process:
            inlined_for_file, wrote = _compile_single_file(
                src, out, uncompiled_path, variables, uncompiled_path, dry_run, label
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
## File: commands\compile_not_bash.py
```python
"""Support for inlining many types of scripts"""

from __future__ import annotations

import logging
import re
from pathlib import Path

__all__ = ["_maybe_inline_interpreter_command"]


logger = logging.getLogger(__name__)

_INTERPRETER_FLAGS = {
    "python": "-c",
    "node": "-e",
    "ruby": "-e",
    "php": "-r",
    "fish": "-c",
}

# Simple extension mapping to help sanity-check paths by interpreter
_INTERPRETER_EXTS = {
    "python": (".py",),
    "node": (".js", ".mjs", ".cjs"),
    "ruby": (".rb",),
    "php": (".php",),
    "fish": (".fish", ".sh"),  # a lot of folks keep fish scripts as .fish; allow .sh too
}

_INTERP_LINE = re.compile(
    r"""
    ^\s*
    (?P<interp>python|node|ruby|php|fish)      # interpreter
    \s+
    (?:
        -m\s+(?P<module>[A-Za-z0-9_\.]+)       # python -m package.module
        |
        (?P<path>\.?/?[^\s]+)                  # or a path like scripts/foo.py
    )
    (?:\s+.*)?                                 # allow trailing args (ignored for now)
    \s*$
    """,
    re.VERBOSE,
)


def _shell_single_quote(s: str) -> str:
    """
    Safely single-quote *s* for POSIX shell.
    Turns: abc'def  ->  'abc'"'"'def'
    """
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _resolve_interpreter_target(
    interp: str, module: str | None, path_str: str | None, scripts_root: Path
) -> tuple[Path, str]:
    """
    Resolve the target file and a display label from either a module or a path.
    For python -m, we map "a.b.c" -> a/b/c.py.
    """
    if module:
        if interp != "python":
            raise ValueError(f"-m is only supported for python, got: {interp}")
        rel = Path(module.replace(".", "/") + ".py")
        return scripts_root / rel, f"{interp} -m {module}"
    if path_str:
        # normalize ./ and leading slashes relative to scripts_root
        rel_str = Path(path_str.strip()).as_posix().lstrip("./")
        return scripts_root / rel_str, f"{interp} {Path(rel_str).as_posix()}"
    raise ValueError("Neither module nor path provided.")


def _is_reasonable_ext(interp: str, file: Path) -> bool:
    exts = _INTERPRETER_EXTS.get(interp)
    if not exts:
        return True
    return file.suffix.lower() in exts


def _maybe_inline_interpreter_command(line: str, scripts_root: Path) -> list[str] | None:
    """
    If *line* looks like an interpreter execution (python/node/ruby/php/fish),
    return [BEGIN, <interp -flag 'code'>, END]; else return None.
    """
    m = _INTERP_LINE.match(line)
    if not m:
        return None

    interp = m.group("interp")
    module = m.group("module")
    path_str = m.group("path")

    try:
        target_file, shown = _resolve_interpreter_target(interp, module, path_str, scripts_root)
    except ValueError as e:
        logger.debug("Interpreter inline skip: %s", e)
        return None

    if not target_file.is_file():
        logger.warning("Could not inline %s: file not found at %s; preserving original.", shown, target_file)
        return None

    if not _is_reasonable_ext(interp, target_file):
        logger.debug("Interpreter inline skip: extension %s not expected for %s", target_file.suffix, interp)
        return None

    try:
        code = target_file.read_text(encoding="utf-8")
    except Exception as e:  # nosec
        logger.warning("Could not read %s: %s; preserving original.", target_file, e)
        return None

    # Strip shebang if present
    if code.startswith("#!"):
        code = "\n".join(code.splitlines()[1:])

    flag = _INTERPRETER_FLAGS.get(interp)
    if not flag:
        return None

    quoted = _shell_single_quote(code)
    begin_marker = f"# >>> BEGIN inline: {shown}"
    end_marker = "# <<< END inline"
    inlined_cmd = f"{interp} {flag} {quoted}"
    logger.debug("Inlining interpreter command '%s' (%d chars).", shown, len(code))
    return [begin_marker, inlined_cmd, end_marker]
```
## File: commands\detect_drift.py
```python
"""
Detects "drift" in compiled files by comparing them against their .hash files.

This module provides functionality to verify the integrity of compiled YAML files
generated by the main compiler. The compiler creates a `.hash` file for each
YAML file it writes, containing a base64 encoded snapshot of the file's exact
content at the time of creation.

This checker iterates through all `.hash` files, decodes their contents, and
compares them with the current contents of the corresponding compiled files.
If any discrepancies are found, it indicates that a file has been manually
edited after compilation. The module will then print a user-friendly diff
report for each modified file and return a non-zero exit code, which is
useful for integration into CI/CD pipelines to prevent unintended changes.
"""

from __future__ import annotations

import base64
import difflib
import logging
import os
from collections.abc import Generator
from pathlib import Path

__all__ = ["run_detect_drift"]


# ANSI color codes for pretty printing the diff.
# This class now checks for NO_COLOR and CI environment variables to automatically
# disable color and other ANSI escape codes for better accessibility and CI/CD logs.
class Colors:
    # The NO_COLOR spec (no-color.org) and the common 'CI' variable for Continuous Integration
    # environments are used to disable ANSI escape codes.
    _enabled = "NO_COLOR" not in os.environ and "CI" not in os.environ

    if _enabled:
        HEADER = "\033[95m"
        OKBLUE = "\033[94m"
        OKCYAN = "\033[96m"
        OKGREEN = "\033[92m"
        WARNING = "\033[93m"
        FAIL = "\033[91m"
        ENDC = "\033[0m"
        BOLD = "\033[1m"
        UNDERLINE = "\033[4m"
        RED_BG = "\033[41m"
        GREEN_BG = "\033[42m"
    else:
        # If colors are disabled, all attributes are empty strings.
        HEADER, OKBLUE, OKCYAN, OKGREEN, WARNING, FAIL, ENDC, BOLD, UNDERLINE, RED_BG, GREEN_BG = (
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        )


# Setting up a logger for this module. The calling application can configure the handler.
logger = logging.getLogger(__name__)


def _decode_hash_content(hash_file: Path) -> str | None:
    """
    Reads and decodes the base64 content of a .hash file.

    Args:
        hash_file: The path to the .hash file.

    Returns:
        The decoded string content, or None if an error occurs.
    """
    try:
        last_known_base64 = hash_file.read_text(encoding="utf-8").strip()
        if not last_known_base64:
            logger.warning(f"Hash file is empty: {hash_file}")
            return None
        last_known_content_bytes = base64.b64decode(last_known_base64)
        return last_known_content_bytes.decode("utf-8")
    except (ValueError, TypeError) as e:
        logger.error(f"Could not decode the .hash file '{hash_file}'. It may be corrupted. Error: {e}")
        return None
    except FileNotFoundError:
        logger.error(f"Hash file not found: {hash_file}")
        return None


def _get_source_file_from_hash(hash_file: Path) -> Path:
    """
    Derives the original source file path from a hash file path.
    Example: /path/to/file.yml.hash -> /path/to/file.yml

    Args:
        hash_file: The path to the .hash file.

    Returns:
        The corresponding Path object for the original file.
    """
    s = str(hash_file)
    if hasattr(s, "removesuffix"):  # Python 3.9+
        return Path(s.removesuffix(".hash"))
    # Python < 3.9
    if s.endswith(".hash"):
        return Path(s[: -len(".hash")])
    return Path(s)


def _generate_pretty_diff(source_content: str, decoded_content: str, source_file_path: Path) -> str:
    """
    Generates a colorized (if enabled), unified diff string between two content strings.

    Args:
        source_content: The current content of the file.
        decoded_content: The original content from the hash.
        source_file_path: The path to the source file (for labeling the diff).

    Returns:
        A formatted and colorized diff string.
    """
    diff_lines = difflib.unified_diff(
        decoded_content.splitlines(),
        source_content.splitlines(),
        fromfile=f"{source_file_path} (from hash)",
        tofile=f"{source_file_path} (current, with manual edits)",
        lineterm="",
    )

    colored_diff = []
    for line in diff_lines:
        if line.startswith("+"):
            colored_diff.append(f"{Colors.OKGREEN}{line}{Colors.ENDC}")
        elif line.startswith("-"):
            colored_diff.append(f"{Colors.FAIL}{line}{Colors.ENDC}")
        elif line.startswith("@@"):
            colored_diff.append(f"{Colors.OKCYAN}{line}{Colors.ENDC}")
        else:
            colored_diff.append(line)
    return "\n".join(colored_diff)


def find_hash_files(search_paths: list[Path]) -> Generator[Path, None, None]:
    """
    Finds all .hash files recursively in the given list of directories.

    Args:
        search_paths: A list of directories to search in.

    Yields:
        Path objects for each .hash file found.
    """
    for search_path in search_paths:
        if not search_path.is_dir():
            logger.warning(f"Search path is not a directory, skipping: {search_path}")
            continue
        logger.info(f"Searching for .hash files in: {search_path}")
        yield from search_path.rglob("*.hash")


def run_detect_drift(
    output_path: Path,
) -> int:
    """
    Checks for manual edits (drift) in compiled files by comparing them against their .hash files.

    This function iterates through all `.hash` files in the specified output directories,
    decodes their contents, and compares them with the current contents of the
    corresponding compiled files. It prints a diff for any files that have changed.

    Args:
        output_path: The main output directory containing compiled files (e.g., .gitlab-ci.yml).

    Returns:
        int: Returns 0 if no drift is detected.
             Returns 1 if drift is found or if errors occurred during the check.
    """
    drift_detected_count = 0
    error_count = 0
    search_paths = [output_path]

    hash_files = list(find_hash_files(search_paths))

    if not hash_files:
        logger.warning("No .hash files found to check for drift.")
        return 0  # No hashes means no drift to detect.

    print(f"Found {len(hash_files)} hash file(s). Checking for drift...")

    for hash_file in hash_files:
        source_file = _get_source_file_from_hash(hash_file)

        if not source_file.exists():
            logger.error(f"Drift check failed: Source file '{source_file}' is missing for hash file '{hash_file}'.")
            error_count += 1
            continue

        decoded_content = _decode_hash_content(hash_file)
        if decoded_content is None:
            # Error already logged in the helper function
            error_count += 1
            continue

        try:
            current_content = source_file.read_text(encoding="utf-8")
        except OSError as e:
            logger.error(f"Drift check failed: Could not read source file '{source_file}'. Error: {e}")
            error_count += 1
            continue

        if current_content != decoded_content:
            drift_detected_count += 1
            diff_text = _generate_pretty_diff(current_content, decoded_content, source_file)

            # Print a clear, formatted report for the user, adapting to color support.
            if Colors.ENDC:  # Check if colors are enabled
                print("\n" + f"{Colors.RED_BG}{Colors.BOLD} DRIFT DETECTED IN: {source_file} {Colors.ENDC}")
            else:
                print(f"\n--- DRIFT DETECTED IN: {source_file} ---")

            print(diff_text)

            if Colors.ENDC:
                print(f"{Colors.RED_BG}{' ' * 80}{Colors.ENDC}")

    if drift_detected_count > 0 or error_count > 0:
        # Print summary, adapting to color support
        if Colors.ENDC:
            print("\n" + f"{Colors.HEADER}{Colors.BOLD}{'-' * 25} DRIFT DETECTION SUMMARY {'-' * 25}{Colors.ENDC}")
            if drift_detected_count > 0:
                print(f"{Colors.FAIL}  - Found {drift_detected_count} file(s) with manual edits.{Colors.ENDC}")
            if error_count > 0:
                print(
                    f"{Colors.WARNING}  - Encountered {error_count} error(s) during the check (see logs for details).{Colors.ENDC}"
                )
        else:
            print("\n" + "--- DRIFT DETECTION SUMMARY ---")
            if drift_detected_count > 0:
                print(f"  - Found {drift_detected_count} file(s) with manual edits.")
            if error_count > 0:
                print(f"  - Encountered {error_count} error(s) during the check (see logs for details).")

        print("\n  To resolve, you can either:")
        print("    1. Revert the manual changes in the files listed above.")
        print("    2. Update the input files to match and recompile.")
        print("    3. Recompile and lose any changes to the above files.")

        if Colors.ENDC:
            print(f"{Colors.HEADER}{Colors.BOLD}{'-' * 79}{Colors.ENDC}")
        else:
            print(f"{'-' * 79}")

        return 1

    # Else, print success message, adapting to color support
    if Colors.ENDC:
        print(f"\n{Colors.OKGREEN}Drift detection complete. No drift detected.{Colors.ENDC}")
    else:
        print("\nDrift detection complete. No drift detected.")

    print("All compiled files match their hashes.")
    return 0
```
## File: commands\init_project.py
```python
"""Interactively setup a config file"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default directory structure configuration
DEFAULT_CONFIG = {
    "input_dir": "src",
    "output_dir": "out",
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

# Command-line flag defaults
verbose = {verbose}
quiet = {quiet}
"""

__all__ = ["prompt_for_config", "create_config_file"]


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
```
## File: commands\lint_all.py
```python
"""Utilities to lint compiled GitLab CI YAML files against a GitLab instance.

This module scans an *output* directory for YAML files and submits each file's
content to GitLab's CI Lint API. It supports both the global lint endpoint and
project-scoped linting (recommended for configs that rely on `include:` or
project-level context).

The entrypoint is :func:`lint_output_folder`.

Design goals
------------
- Pure standard library HTTP (``urllib.request``) to avoid extra deps.
- Safe defaults, clear logging, and mypy-friendly type hints.
- Google-style docstrings, small focused helpers, and testable pieces.

Example:
-------
>>> from pathlib import Path
>>> results = lint_output_folder(
...     output_root=Path("dist"),
...     gitlab_url="https://gitlab.example.com",
...     private_token="glpat-...",
...     project_id=1234,
...     ref="main",
...     include_merged_yaml=True,
... )
>>> any(r.ok for r in results)
True

Notes:
-----
- The project-scoped endpoint provides more accurate validation for pipelines
  that depend on project context, variables, or remote includes.
- GitLab API reference:
  - Global lint:   ``POST /api/v4/ci/lint`` (body: {"content": "..."})
  - Project lint:  ``POST /api/v4/projects/:id/ci/lint`` with optional
    parameters such as ``ref`` and ``include_merged_yaml``.
"""

from __future__ import annotations

import json
import logging
import multiprocessing
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib import error, request

logger = logging.getLogger(__name__)

__all__ = ["LintIssue", "LintResult", "lint_single_text", "lint_single_file", "lint_output_folder", "summarize_results"]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LintIssue:
    """Represents a single message from GitLab CI Lint.

    Attributes:
        severity: Message severity (e.g., "error", "warning").
        message: Human-readable message.
        line: Optional line number in the YAML (GitLab may omit).
    """

    severity: str
    message: str
    line: int | None = None


@dataclass(frozen=True)
class LintResult:
    """Result of linting one YAML payload.

    Attributes:
        path: Source file path (``Path``) or synthetic path for raw text.
        ok: ``True`` when the configuration is valid according to GitLab.
        status: Raw status string from API (e.g., "valid", "invalid").
        errors: List of error messages (as :class:`LintIssue`).
        warnings: List of warning messages (as :class:`LintIssue`).
        merged_yaml: The resolved/merged YAML returned by project-scoped lint
            when ``include_merged_yaml=True``; otherwise ``None``.
        raw_response: The decoded API JSON for debugging.
    """

    path: Path
    ok: bool
    status: str
    errors: list[LintIssue]
    warnings: list[LintIssue]
    merged_yaml: str | None
    raw_response: dict


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _api_url(
    base_url: str,
    project_id: int | None,
) -> str:
    """Build the CI Lint API URL.

    Args:
        base_url: Base GitLab URL, e.g., ``https://gitlab.com``.
        project_id: If provided, use project-scoped lint endpoint.

    Returns:
        Fully-qualified API endpoint URL.
    """
    base = base_url.rstrip("/")
    if project_id is None:
        return f"{base}/api/v4/ci/lint"
    return f"{base}/api/v4/projects/{project_id}/ci/lint"


def _post_json(
    url: str,
    payload: dict,
    *,
    private_token: str | None,
    timeout: float,
) -> dict:
    """POST JSON to ``url`` and return decoded JSON response.

    Args:
        url: Target endpoint.
        payload: JSON payload to send.
        private_token: Optional GitLab token for authentication.
        timeout: Request timeout in seconds.

    Returns:
        Decoded JSON response as a ``dict``.

    Raises:
        URLError / HTTPError on network issues (logged and re-raised).
        ValueError if response cannot be parsed as JSON.
    """
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "bash2gitlab-lint/1.0",
    }
    if private_token:
        headers["PRIVATE-TOKEN"] = private_token

    req = request.Request(url=url, data=body, headers=headers, method="POST")

    try:
        #  controlled URL
        with request.urlopen(req, timeout=timeout) as resp:  # nosec
            raw = resp.read()
    except error.HTTPError as e:  # pragma: no cover - network dependent
        detail = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
        logger.error("HTTP %s from %s: %s", getattr(e, "code", "?"), url, detail)
        raise
    except error.URLError as e:  # pragma: no cover - network dependent
        logger.error("Network error calling %s: %s", url, e)
        raise

    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        logger.error("Failed to decode JSON from %s: %s", url, e)
        raise


# ---------------------------------------------------------------------------
# Lint operations
# ---------------------------------------------------------------------------


def lint_single_text(
    content: str,
    *,
    gitlab_url: str,
    private_token: str | None = None,
    project_id: int | None = None,
    ref: str | None = None,
    include_merged_yaml: bool = False,
    timeout: float = 20.0,
    synthetic_path: Path | None = None,
) -> LintResult:
    """Lint a single YAML *content* string via GitLab CI Lint API.

    Args:
        content: The YAML text to validate.
        gitlab_url: Base GitLab URL, e.g., ``https://gitlab.com``.
        private_token: Optional personal access token (PAT) or CI job token.
        project_id: If provided, use project-scoped endpoint.
        ref: Optional Git ref for project-scoped lint (e.g., "main").
        include_merged_yaml: If True, ask GitLab to resolve includes and return
            the merged YAML (project-scoped lint only).
        timeout: HTTP timeout in seconds.
        synthetic_path: Optional path label for reporting (used when linting
            text not originating from a file).

    Returns:
        A :class:`LintResult` with structured details.
    """
    url = _api_url(gitlab_url, project_id)

    payload: dict = {"content": content}

    # Project-scoped knobs
    if project_id is not None and ref is not None:
        payload["ref"] = ref
    if project_id is not None and include_merged_yaml:
        payload["include_merged_yaml"] = True

    resp = _post_json(url, payload, private_token=private_token, timeout=timeout)

    # GitLab returns varing shapes across versions. Normalize defensively.
    status = str(resp.get("status") or ("valid" if resp.get("valid") else "invalid"))
    valid = bool(resp.get("valid", status == "valid"))

    def _collect(kind: str) -> list[LintIssue]:
        out: list[LintIssue] = []
        items = resp.get(kind) or []
        if isinstance(items, list):
            for m in items:
                if isinstance(m, dict):
                    out.append(
                        LintIssue(
                            severity=str(m.get("severity", kind.rstrip("s"))),
                            message=str(m.get("message", m)),
                            line=m.get("line"),
                        )
                    )
                else:
                    out.append(LintIssue(severity=kind.rstrip("s"), message=str(m)))
        return out

    errors = _collect("errors")
    warnings = _collect("warnings")
    merged_yaml: str | None = None
    if include_merged_yaml:
        merged_yaml = resp.get("merged_yaml") or resp.get("mergedYaml")

    path = synthetic_path or Path("<string>")
    return LintResult(
        path=path,
        ok=valid,
        status=status,
        errors=errors,
        warnings=warnings,
        merged_yaml=merged_yaml,
        raw_response=resp,
    )


def lint_single_file(
    path: Path,
    *,
    gitlab_url: str,
    private_token: str | None = None,
    project_id: int | None = None,
    ref: str | None = None,
    include_merged_yaml: bool = False,
    timeout: float = 20.0,
    encoding: str = "utf-8",
) -> LintResult:
    """Lint one YAML file at *path*.

    Args:
        path: File to lint.
        gitlab_url: Base GitLab URL, e.g., ``https://gitlab.com``.
        private_token: Optional personal access token (PAT) or CI job token.
        project_id: Optional project id for project-scoped lint.
        ref: Optional git ref when using project-scoped lint.
        include_merged_yaml: Whether to return merged YAML (project lint only).
        timeout: HTTP timeout.
        encoding: File encoding.

    Returns:
        A :class:`LintResult`.
    """
    text = path.read_text(encoding=encoding)
    return lint_single_text(
        text,
        gitlab_url=gitlab_url,
        private_token=private_token,
        project_id=project_id,
        ref=ref,
        include_merged_yaml=include_merged_yaml,
        timeout=timeout,
        synthetic_path=path,
    )


# ---------------------------------------------------------------------------
# Folder scanning / orchestration
# ---------------------------------------------------------------------------

_YAML_GLOBS: tuple[str, ...] = ("*.yml", "*.yaml")


def _discover_yaml_files(root: Path) -> list[Path]:
    """Recursively find YAML files under *root*.

    Files with suffixes ``.yml`` or ``.yaml`` are included.
    """
    out: list[Path] = []
    for pat in _YAML_GLOBS:
        out.extend(root.rglob(pat))
    # Deterministic order aids testing and stable logs
    return sorted(p for p in out if p.is_file())


def lint_output_folder(
    output_root: Path,
    *,
    gitlab_url: str,
    private_token: str | None = None,
    project_id: int | None = None,
    ref: str | None = None,
    include_merged_yaml: bool = False,
    parallelism: int | None = None,
    timeout: float = 20.0,
) -> list[LintResult]:
    """Lint every YAML file under *output_root* using GitLab CI Lint.

    Args:
        output_root: Directory containing compiled YAML outputs to validate.
        gitlab_url: Base GitLab URL, e.g., ``https://gitlab.com``.
        private_token: Optional personal access token (PAT) or CI job token.
        project_id: Optional project id for project-scoped lint.
        ref: Optional git ref when using project-scoped lint.
        include_merged_yaml: Whether to return merged YAML (project lint only).
        parallelism: Max worker processes for concurrent lint requests. If
            ``None``, a reasonable default will be used for small sets.
        timeout: HTTP timeout per request.

    Returns:
        List of :class:`LintResult`, one per file.
    """
    files = _discover_yaml_files(output_root)
    if not files:
        logger.warning("No YAML files found under %s", output_root)
        return []

    # Heuristic: don't over-parallelize small sets
    if parallelism is None:
        parallelism = min(max(1, len(files)), multiprocessing.cpu_count())

    logger.info(
        "Linting %d YAML file(s) under %s using %s endpoint",
        len(files),
        output_root,
        "project" if project_id is not None else "global",
    )

    if parallelism <= 1:
        return [
            lint_single_file(
                p,
                gitlab_url=gitlab_url,
                private_token=private_token,
                project_id=project_id,
                ref=ref,
                include_merged_yaml=include_merged_yaml,
                timeout=timeout,
            )
            for p in files
        ]

    # Use processes for simple isolation; network-bound so processes vs threads
    # is not critical, but this avoids GIL considerations for file IO + json.
    from functools import partial

    worker = partial(
        lint_single_file,
        gitlab_url=gitlab_url,
        private_token=private_token,
        project_id=project_id,
        ref=ref,
        include_merged_yaml=include_merged_yaml,
        timeout=timeout,
    )

    with multiprocessing.Pool(processes=parallelism) as pool:
        results = pool.map(worker, files)

    return results


# ---------------------------------------------------------------------------
# Reporting helpers (optional)
# ---------------------------------------------------------------------------


def summarize_results(results: Sequence[LintResult]) -> tuple[int, int]:
    """Log a concise summary and return counts.

    Args:
        results: Sequence of lint results.

    Returns:
        Tuple of (ok_count, fail_count).
    """
    ok = sum(1 for r in results if r.ok)
    fail = len(results) - ok

    for r in results:
        if r.ok:
            logger.info("OK: %s", r.path)
            if r.warnings:
                for w in r.warnings:
                    logger.warning("%s: %s", r.path, w.message)
        else:
            logger.error("INVALID: %s (status=%s)", r.path, r.status)
            for e in r.errors:
                if e.line is not None:
                    logger.error("%s:%s: %s", r.path, e.line, e.message)
                else:
                    logger.error("%s: %s", r.path, e.message)

    logger.info("Lint summary: %d ok, %d failed", ok, fail)
    return ok, fail
```
## File: commands\map_deploy.py
```python
"""Copy from a central repos relevant shell scripts changes to many dependent repos for debugging."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

import toml

_VALID_SUFFIXES = {".sh", ".ps1", ".yml", ".yaml"}

__all__ = ["run_map_deploy", "get_deployment_map"]


def get_deployment_map(pyproject_path: Path) -> dict[str, str]:
    """Parses the pyproject.toml file to get the deployment map.

    Args:
        pyproject_path: The path to the pyproject.toml file.

    Returns:
        A dictionary mapping source directories to target directories.

    Raises:
        FileNotFoundError: If the pyproject.toml file is not found.
        KeyError: If the [tool.bash2gitlab.map] section is missing.
    """
    if not pyproject_path.is_file():
        raise FileNotFoundError(f"pyproject.toml not found at '{pyproject_path}'")

    data = toml.load(pyproject_path)
    try:
        return data["tool"]["bash2gitlab"]["map"]
    except KeyError as ke:
        raise KeyError("'[tool.bash2gitlab.map]' section not found in pyproject.toml") from ke


def run_map_deploy(
    source_to_target_map: dict[str, str],
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Copies files from source to target directories based on a map.

    This function iterates through a dictionary mapping source directories to
    target directories. It copies each file from the source to the corresponding
    target, creating a .hash file to track changes.

    - If a destination file has been modified since the last deployment (hash
      mismatch), it will be skipped unless 'force' is True.
    - A .gitignore file with '*' is created in each target directory to
      prevent accidental check-ins.
    - All necessary directories are created.

    Args:
        source_to_target_map: A dictionary where keys are source paths and
                              values are target paths.
        dry_run: If True, simulates the deployment without making changes.
        force: If True, overwrites target files even if they have been modified.
    """
    for source_base, target_base in source_to_target_map.items():
        source_base_path = Path(source_base).resolve()
        target_base_path = Path(target_base).resolve()

        if not source_base_path.is_dir():
            print(f"Warning: Source directory '{source_base_path}' does not exist. Skipping.")
            continue

        print(f"\nProcessing map: '{source_base_path}' -> '{target_base_path}'")

        # Create target base directory and .gitignore if they don't exist
        if not target_base_path.exists():
            print(f"Target directory '{target_base_path}' does not exist.")
            if not dry_run:
                print(f"Creating directory: {target_base_path}")
                target_base_path.mkdir(parents=True, exist_ok=True)

        gitignore_path = target_base_path / ".gitignore"
        if not gitignore_path.exists():
            if not dry_run:
                print(f"Creating .gitignore in '{target_base_path}'")
                with open(gitignore_path, "w", encoding="utf-8") as f:
                    f.write("*\n")
            else:
                print(f"DRY RUN: Would create .gitignore in '{target_base_path}'")

        for root, _, files in os.walk(source_base_path):
            source_root_path = Path(root)

            for filename in files:
                source_file_path = source_root_path / filename
                if source_file_path.suffix.lower() not in _VALID_SUFFIXES:
                    continue

                relative_path = source_file_path.relative_to(source_base_path)
                target_file_path = target_base_path / relative_path
                hash_file_path = target_file_path.with_suffix(target_file_path.suffix + ".hash")

                # Ensure parent directory of the target file exists
                if not target_file_path.parent.exists():
                    print(f"Target directory '{target_file_path.parent}' does not exist.")
                    if not dry_run:
                        print(f"Creating directory: {target_file_path.parent}")
                        target_file_path.parent.mkdir(parents=True, exist_ok=True)

                # Calculate source file hash
                with open(source_file_path, "rb") as f:
                    source_hash = hashlib.sha256(f.read()).hexdigest()

                # Check for modifications at the destination
                if target_file_path.exists():
                    with open(target_file_path, "rb") as f:
                        target_hash_actual = hashlib.sha256(f.read()).hexdigest()

                    stored_hash = ""
                    if hash_file_path.exists():
                        with open(hash_file_path, encoding="utf-8") as f:
                            stored_hash = f.read().strip()

                    if stored_hash and target_hash_actual != stored_hash:
                        print(f"Warning: '{target_file_path}' was modified since last deployment.")
                        if not force:
                            print("Skipping copy. Use --force to overwrite.")
                            continue
                        print("Forcing overwrite.")

                # Perform copy and write hash
                if not target_file_path.exists() or source_hash != target_hash_actual:
                    action = "Copied" if not target_file_path.exists() else "Updated"
                    print(f"{action}: '{source_file_path}' -> '{target_file_path}'")
                    if not dry_run:
                        shutil.copy2(source_file_path, target_file_path)
                        with open(hash_file_path, "w", encoding="utf-8") as f:
                            f.write(source_hash)
                else:
                    print(f"Unchanged: '{target_file_path}'")
```
## File: commands\shred_all.py
```python
"""Take a gitlab template with inline yaml and split it up into yaml and shell commands. Useful for project initialization"""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import FoldedScalarString

from bash2gitlab.utils.mock_ci_vars import generate_mock_ci_variables_script
from bash2gitlab.utils.yaml_factory import get_yaml

logger = logging.getLogger(__name__)

SHEBANG = "#!/bin/bash"

__all__ = ["run_shred_gitlab"]


def dump_inline_no_doc_markers(yaml: YAML, node) -> str:
    buf = io.StringIO()
    # Temporarily suppress doc markers, then restore whatever was set globally
    prev_start, prev_end = yaml.explicit_start, yaml.explicit_end
    try:
        yaml.explicit_start = False
        yaml.explicit_end = False
        yaml.dump(node, buf)
    finally:
        yaml.explicit_start, yaml.explicit_end = prev_start, prev_end
    # Trim a single trailing newline that ruamel usually adds
    return buf.getvalue().rstrip("\n")


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
    script_content: list[str | Any] | str,
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

    yaml = get_yaml()

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
                item_as_string = dump_inline_no_doc_markers(yaml, item)
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


def run_shred_gitlab(
    input_yaml_path: Path,
    output_yaml_path: Path,
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Loads a GitLab CI YAML file, shreds all script and variable blocks into
    separate .sh files, and saves the modified YAML.

    Args:
        input_yaml_path (Path): Path to the input .gitlab-ci.yml file.
        output_yaml_path (Path): Path to write the modified .gitlab-ci.yml file.
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
    yaml = get_yaml()
    yaml.indent(mapping=2, sequence=4, offset=2)
    data = yaml.load(input_yaml_path)

    jobs_processed = 0
    total_files_created = 0

    # First, process the top-level 'variables' block, if it exists.
    global_vars_filename = None
    if "variables" in data and isinstance(data.get("variables"), dict):
        logger.info("Processing global variables block.")
        global_vars_filename = shred_variables_block(data["variables"], "global", output_yaml_path.parent, dry_run)
        if global_vars_filename:
            total_files_created += 1

    # Process all top-level keys that look like jobs
    for key, value in data.items():
        # Heuristic: A job is a dictionary that contains a 'script' key.
        if isinstance(value, dict) and "script" in value:
            logger.debug(f"Processing job: {key}")
            jobs_processed += 1
            total_files_created += process_shred_job(key, value, output_yaml_path.parent, dry_run, global_vars_filename)

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
        output_yaml_path.parent.mkdir(exist_ok=True)
        generate_mock_ci_variables_script(str(output_yaml_path.parent / "mock_ci_variables.sh"))

    return jobs_processed, total_files_created
```
## File: utils\cli_suggestions.py
```python
import argparse
import sys


class SmartParser(argparse.ArgumentParser):
    def error(self, message: str):
        # Detect "invalid choice: 'foo' (choose from ...)"
        if "invalid choice" in message and "choose from" in message:
            bad = message.split("invalid choice:")[1].split("(")[0].strip().strip("'\"")
            choices_str = message.split("choose from")[1]
            choices = [c.strip().strip(",)'") for c in choices_str.split() if c.strip(",)")]
            from difflib import get_close_matches

            tips = get_close_matches(bad, choices, n=3, cutoff=0.6)
            if tips:
                message += f"\n\nDid you mean: {', '.join(tips)}?"
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n")


def cli(argv=None):
    p = SmartParser(prog="mycli")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ["init", "install", "inspect", "index"]:
        sp = sub.add_parser(name)
        sp.set_defaults(func=lambda args, n=name: print(f"ran {n}"))

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    cli()
```
## File: utils\dotenv.py
```python
""".env file support"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


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
```
## File: utils\logging_config.py
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
        "disable_existing_loggers": False,
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
## File: utils\mock_ci_vars.py
```python
"""Helper file for mocking common CI/CD variables"""

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
## File: utils\parse_bash.py
```python
"""Parser for detecting scripts that are safe to inline without changing semantics"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

_EXECUTORS = {"bash", "sh", "pwsh"}
_DOT_SOURCE = {"source", "."}
_VALID_SUFFIXES = {".sh", ".ps1"}
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def extract_script_path(cmd_line: str) -> str | None:
    """
    Return a *safe-to-inline* script path or ``None``.
    A path is safe when:

        • there are **no interpreter flags**
        • there are **no extra positional arguments**
        • there are **no leading ENV=val assignments**

    Examples that return a path
    ---------------------------
    ./build.sh
    bash build.sh
    source utils/helpers.sh
    . scripts/deploy.ps1          # pwsh default

    Examples that return ``None``
    ------------------------------
    bash -e build.sh
    FOO=bar ./build.sh
    ./build.sh arg1 arg2
    pwsh -NoProfile run.ps1
    """
    if not isinstance(cmd_line, str):
        raise Exception()

    try:
        tokens = shlex.split(cmd_line, posix=True)
    except ValueError:
        return None  # malformed quoting

    if not tokens:
        return None

    # ── Disallow leading VAR=val assignments ────────────────────────────────
    if _ENV_ASSIGN_RE.match(tokens[0]):
        return None

    # Case A ─ plain script call ------------------------------------------------
    if len(tokens) == 1 and _is_script(tokens[0]):
        return Path(tokens[0]).as_posix()

    # Case B ─ executor + script ------------------------------------------------
    if len(tokens) == 2 and _is_executor(tokens[0]) and _is_script(tokens[1]):
        return Path(tokens[1]).as_posix()

    # Case C ─ dot-source -------------------------------------------------------
    if len(tokens) == 2 and tokens[0] in _DOT_SOURCE and _is_script(tokens[1]):
        return Path(tokens[1]).as_posix()

    # Anything else is unsafe to inline
    return None


# ───────────────────────── helper predicates ────────────────────────────────
def _is_executor(tok: str) -> bool:
    """True if token is bash/sh/pwsh *without leading dash*."""
    return tok in _EXECUTORS


def _is_script(tok: str) -> bool:
    """True if token ends with .sh or .ps1 and is not an option flag."""
    return not tok.startswith("-") and Path(tok).suffix.lower() in _VALID_SUFFIXES
```
## File: utils\update_checker.py
```python
"""Improved update checker utility for bash2gitlab (standalone module).

Key improvements over prior version:
- Clear public API with docstrings and type hints
- Robust networking with timeouts, retries, and explicit User-Agent
- Safe, simple JSON cache with TTL to avoid frequent network calls
- Correct prerelease handling using packaging.version
- Optional colorized output that respects NO_COLOR/CI/TERM and TTY
- Non-invasive logging: caller may pass a logger or rely on a safe default
- Narrow exception surface with custom error types

Public functions:
- check_for_updates(package_name, current_version, ...)
- reset_cache(package_name)

Return contract:
- Returns a user-facing message string when an update is available; otherwise None.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib import error, request

from packaging import version as _version

__all__ = [
    "check_for_updates",
    "reset_cache",
    "PackageNotFoundError",
    "NetworkError",
]


class PackageNotFoundError(Exception):
    """Raised when the package does not exist on PyPI (HTTP 404)."""


class NetworkError(Exception):
    """Raised when a network error occurs while contacting PyPI."""


@dataclass(frozen=True)
class _Color:
    YELLOW: str = "\033[93m"
    GREEN: str = "\033[92m"
    ENDC: str = "\033[0m"


def _get_logger(user_logger: logging.Logger | None) -> Callable[[str], None]:
    """Get a warning logging function.

    Args:
        user_logger (logging.Logger | None): Logger instance or None.

    Returns:
        Callable[[str], None]: Logger warning method or built-in print.
    """
    if isinstance(user_logger, logging.Logger):
        return user_logger.warning
    return print


def _can_use_color() -> bool:
    """Determine if color output is allowed.

    Returns:
        bool: True if output can be colorized.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("CI"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _cache_paths(package_name: str) -> tuple[Path, Path]:
    """Compute cache directory and file path for a package.

    Args:
        package_name (str): Name of the package.

    Returns:
        tuple[Path, Path]: Cache directory and file path.
    """
    cache_dir = Path(tempfile.gettempdir()) / "python_update_checker"
    cache_file = cache_dir / f"{package_name}_cache.json"
    return cache_dir, cache_file


def _is_fresh(cache_file: Path, ttl_seconds: int) -> bool:
    """Check if cache file is fresh.

    Args:
        cache_file (Path): Path to cache file.
        ttl_seconds (int): TTL in seconds.

    Returns:
        bool: True if cache is within TTL.
    """
    try:
        if cache_file.exists():
            last_check_time = cache_file.stat().st_mtime
            return (time.time() - last_check_time) < ttl_seconds
    except (OSError, PermissionError):
        return False
    return False


def _save_cache(cache_dir: Path, cache_file: Path, payload: dict) -> None:
    """Save data to cache.

    Args:
        cache_dir (Path): Cache directory.
        cache_file (Path): Cache file path.
        payload (dict): Data to store.
    """
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with cache_file.open("w", encoding="utf-8") as f:
            json.dump({"last_check": time.time(), **payload}, f)
    except (OSError, PermissionError):
        pass


def reset_cache(package_name: str) -> None:
    """Remove cache entry for a given package.

    Args:
        package_name (str): Package name to clear from cache.
    """
    _, cache_file = _cache_paths(package_name)
    try:
        if cache_file.exists():
            cache_file.unlink(missing_ok=True)
    except (OSError, PermissionError):
        pass


def _fetch_pypi_json(url: str, timeout: float) -> dict:
    """Fetch JSON metadata from PyPI.

    Args:
        url (str): URL to fetch.
        timeout (float): Timeout in seconds.

    Returns:
        dict: Parsed JSON data.
    """
    req = request.Request(url, headers={"User-Agent": "bash2gitlab-update-checker/2"})
    with request.urlopen(req, timeout=timeout) as resp:  # nosec
        return json.loads(resp.read().decode("utf-8"))


def _get_latest_version_from_pypi(
    package_name: str,
    *,
    include_prereleases: bool,
    timeout: float = 5.0,
    retries: int = 2,
    backoff: float = 0.5,
) -> str | None:
    """Get latest version from PyPI.

    Args:
        package_name (str): Package name.
        include_prereleases (bool): Whether to include prereleases.
        timeout (float): Request timeout.
        retries (int): Number of retries.
        backoff (float): Backoff factor between retries.

    Returns:
        str | None: Latest version string, None if unavailable.

    Raises:
        PackageNotFoundError: If the package does not exist.
        NetworkError: If network error occurs after retries.
    """
    url = f"https://pypi.org/pypi/{package_name}/json"
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            data = _fetch_pypi_json(url, timeout)
            releases = data.get("releases", {})
            if not releases:
                info_ver = data.get("info", {}).get("version")
                return str(info_ver) if info_ver else None
            parsed: list[_version.Version] = []
            for v_str in releases.keys():
                try:
                    v = _version.parse(v_str)
                except _version.InvalidVersion:
                    continue
                if v.is_prerelease and not include_prereleases:
                    continue
                parsed.append(v)
            if not parsed:
                return None
            return str(max(parsed))
        except error.HTTPError as e:
            if e.code == 404:
                raise PackageNotFoundError from e
            last_err = e
        except (error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            last_err = e
        time.sleep(backoff * (attempt + 1))
    raise NetworkError(str(last_err))


def _format_update_message(
    package_name: str,
    current: _version.Version,
    latest: _version.Version,
) -> str:
    """Format the update notification message.

    Args:
        package_name (str): Package name.
        current (_version.Version): Current version.
        latest (_version.Version): Latest version.

    Returns:
        str: Formatted update message.
    """
    pypi_url = f"https://pypi.org/project/{package_name}/"
    if _can_use_color():
        c = _Color()
        return (
            f"{c.YELLOW}A new version of {package_name} is available: {c.GREEN}{latest}{c.YELLOW} "
            f"(you are using {current}).\n"
            f"Please upgrade using your preferred package manager.\n"
            f"More info: {pypi_url}{c.ENDC}"
        )
    return (
        f"A new version of {package_name} is available: {latest} (you are using {current}).\n"
        f"Please upgrade using your preferred package manager.\n"
        f"More info: {pypi_url}"
    )


def check_for_updates(
    package_name: str,
    current_version: str,
    logger: logging.Logger | None = None,
    *,
    cache_ttl_seconds: int = 86400,
    include_prereleases: bool = False,
) -> str | None:
    """Check PyPI for a newer version of a package.

    Args:
        package_name (str): The PyPI package name to check.
        current_version (str): The currently installed version string.
        logger (logging.Logger | None): Optional logger for warnings.
        cache_ttl_seconds (int): Cache time-to-live in seconds.
        include_prereleases (bool): Whether to consider prereleases newer.

    Returns:
        str | None: Formatted update message if update available, else None.
    """
    warn = _get_logger(logger)
    cache_dir, cache_file = _cache_paths(package_name)
    if _is_fresh(cache_file, cache_ttl_seconds):
        return None
    try:
        latest_str = _get_latest_version_from_pypi(package_name, include_prereleases=include_prereleases)
        if not latest_str:
            _save_cache(cache_dir, cache_file, {"latest": None})
            return None
        current = _version.parse(current_version)
        latest = _version.parse(latest_str)
        if latest > current:
            _save_cache(cache_dir, cache_file, {"latest": latest_str})
            return _format_update_message(package_name, current, latest)
        _save_cache(cache_dir, cache_file, {"latest": latest_str})
        return None
    except PackageNotFoundError:
        warn(f"Package '{package_name}' not found on PyPI.")
        _save_cache(cache_dir, cache_file, {"latest": None})
        return None
    except NetworkError:
        _save_cache(cache_dir, cache_file, {"latest": None})
        return None
    except Exception:
        _save_cache(cache_dir, cache_file, {"latest": None})
        return None


# if __name__ == "__main__":
#     msg = check_for_updates("bash2gitlab", "0.0.0")
#     if msg:
#         print(msg)
#     else:
#         print("No update message (cached or up-to-date).")
```
## File: utils\utils.py
```python
"""Utility functions with no strong link to the domain of the overall application."""

from pathlib import Path


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
```
## File: utils\yaml_factory.py
```python
"""Cache and centralize the YAML object"""

import functools

from ruamel.yaml import YAML


@functools.lru_cache(maxsize=1)
def get_yaml() -> YAML:
    y = YAML()
    y.width = 4096
    y.preserve_quotes = True  # Want to minimize quotes, but "1.0" -> 1.0 is a type change.
    # maximize quotes
    y.default_style = '"'  # type: ignore[assignment]
    y.explicit_start = False  # no '---'
    y.explicit_end = False  # no '...'
    return y
```
## File: utils\yaml_file_same.py
```python
import re

from ruamel.yaml.error import YAMLError

from bash2gitlab.utils.yaml_factory import get_yaml


def normalize_for_compare(text: str) -> str:
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Trim trailing whitespace per line
    text = "\n".join(line.rstrip() for line in text.splitlines())
    # Ensure exactly one newline at EOF
    if not text.endswith("\n"):
        text += "\n"
    # Collapse multiple blank lines at EOF to one (optional)
    text = re.sub(r"\n{3,}$", "\n\n", text)
    return text.strip(" \n")


def yaml_is_same(current_content: str, new_content: str):
    if current_content.strip("\n") == new_content.strip("\n"):
        # Simple match.
        return True

    current_norm = normalize_for_compare(current_content)
    new_norm = normalize_for_compare(new_content)

    if current_norm == new_norm:
        return True

    yaml = get_yaml()
    try:
        new_doc = yaml.load(new_content)
        curr_doc = yaml.load(current_content)
    except YAMLError:
        return False

    if curr_doc == new_doc:
        return True

    return False
```
