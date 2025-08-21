"""Interactively setup a config file"""

from __future__ import annotations

import logging
import subprocess  # nosec
from pathlib import Path
from typing import Any

import tomlkit
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.syntax import Syntax

from bash2gitlab.utils.utils import short_path

logger = logging.getLogger(__name__)

__all__ = ["run_init"]


def _get_git_remote_url() -> str | None:
    """Attempts to get the origin URL from the local git repository."""
    try:
        # Using get-url is more reliable than parsing 'remote -v'
        result = subprocess.run(  # nosec
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        # This is an expected failure if not in a git repo or git isn't installed.
        return None


def prompt_for_config(console: Console, output_dir_default: str) -> dict[str, Any]:
    """
    Interactively prompts the user for project configuration details using rich.
    This function is separate from file I/O to be easily testable.
    """
    config: dict[str, Any] = {}

    console.print(Panel.fit("[bold cyan]Core Settings[/bold cyan]", border_style="cyan"))
    config["input_dir"] = Prompt.ask("Enter the input directory for source files", default="src")
    config["output_dir"] = Prompt.ask("Enter the output directory for compiled files", default=output_dir_default)

    # --- LINT COMMAND ---
    if Confirm.ask("\n[bold]Configure `lint` command settings?[/bold]", default=False):
        console.print(Panel.fit("[bold cyan]Lint Settings[/bold cyan]", border_style="cyan"))
        lint_config = {
            "gitlab_url": Prompt.ask("Enter your GitLab instance URL", default="https://gitlab.com"),
            "project_id": IntPrompt.ask(
                "Enter the GitLab Project ID for project-scoped linting (optional)", default=None
            ),
        }
        # Filter out None values
        config["lint"] = {k: v for k, v in lint_config.items() if v is not None}

    # --- DECOMPILE COMMAND ---
    if Confirm.ask("\n[bold]Configure `decompile` command settings?[/bold]", default=False):
        console.print(Panel.fit("[bold cyan]Decompile Settings[/bold cyan]", border_style="cyan"))
        decompile_config = {
            # Since input_dir is the most common case for a folder, default to that.
            "input_folder": Prompt.ask(
                "Enter the default folder to decompile from", default=config.get("input_dir", "src")
            ),
            "output_dir": Prompt.ask(
                "Enter the default directory for decompiled output", default=config.get("output_dir", "out")
            ),
        }
        config["decompile"] = decompile_config

    # --- COPY2LOCAL COMMAND ---
    if Confirm.ask("\n[bold]Configure `copy2local` command settings?[/bold]", default=False):
        console.print(Panel.fit("[bold cyan]copy2local Settings[/bold cyan]", border_style="cyan"))
        repo_url_default = _get_git_remote_url()
        copy2local_config = {
            "repo_url": Prompt.ask("Enter the repository URL to copy from", default=repo_url_default),
            "branch": Prompt.ask("Enter the branch to copy from", default="main"),
            "source_dir": Prompt.ask("Enter the source directory within the repo to copy", default="."),
            "copy_dir": Prompt.ask(
                "Enter the local directory to copy files to", default=config.get("output_dir", "out")
            ),
        }
        config["copy2local"] = copy2local_config

    # --- MAP COMMANDS ---
    if Confirm.ask("\n[bold]Configure `map-deploy` / `commit-map` settings?[/bold]", default=False):
        console.print(Panel.fit("[bold cyan]Map Settings[/bold cyan]", border_style="cyan"))
        map_config = {}
        console.print("Define source-to-target directory mappings. Press Enter with no source to finish.")
        while True:
            source = Prompt.ask("  -> Enter a [cyan]source[/cyan] directory to map (e.g., 'src/common')")
            if not source:
                break
            target = Prompt.ask(
                f"  -> Enter the [cyan]target[/cyan] directory for '{source}'",
                default="my_service/gitlab-scripts",
            )
            map_config[source] = target
        if map_config:
            config["map"] = {"map": map_config}

    # Structure for pyproject.toml
    return {"tool": {"bash2gitlab": config}}


def create_or_update_config_file(base_path: Path, config_data: dict[str, Any], force: bool = False):
    """
    Creates or updates pyproject.toml with the bash2gitlab configuration.
    Uses tomlkit to preserve existing file structure and comments.
    """
    toml_path = base_path / "pyproject.toml"
    b2gl_config = config_data.get("tool", {}).get("bash2gitlab", {})

    if toml_path.exists():
        logger.info(f"Found existing 'pyproject.toml' at '{short_path(base_path)}'.")
        doc = tomlkit.parse(toml_path.read_text(encoding="utf-8"))

        if "tool" in doc and "bash2gitlab" in doc["tool"] and not force:  # type: ignore[operator]
            raise FileExistsError(
                "A '[tool.bash2gitlab]' section already exists in pyproject.toml. Use the --force flag to overwrite it."
            )
    else:
        logger.info(f"No 'pyproject.toml' found. A new one will be created at '{short_path(base_path)}'.")
        doc = tomlkit.document()

    # Create/get the [tool] table
    if "tool" not in doc:
        doc.add("tool", tomlkit.table())
    tool_table = doc["tool"]

    # Create/replace the [tool.bash2gitlab] table
    b2gl_table = tomlkit.table()
    for section, values in b2gl_config.items():
        if isinstance(values, dict):
            sub_table = tomlkit.table()
            for k, v in values.items():
                sub_table[k] = v
            b2gl_table[section] = sub_table
        else:
            b2gl_table[section] = values

    tool_table["bash2gitlab"] = b2gl_table  # type: ignore[index]

    # Add comments for clarity
    tool_table["bash2gitlab"].comment("Configuration for bash2gitlab")  # type: ignore[union-attr,index]
    if "input_dir" in tool_table["bash2gitlab"]:  # type: ignore[operator,index]
        tool_table["bash2gitlab"].item("input_dir").comment("Directory for source .yml and .sh files")  # type: ignore[union-attr,index]
    if "output_dir" in tool_table["bash2gitlab"]:  # type: ignore[union-attr,index,operator]
        tool_table["bash2gitlab"].item("output_dir").comment("Directory for compiled GitLab CI files")  # type: ignore[union-attr,index]

    toml_path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    logger.info(f"Successfully wrote configuration to '{toml_path}'.")


def run_init(directory, force) -> int:
    """Handles the `init` command logic using the new interactive wizard."""
    console = Console()
    console.print("\n[bold]Initializing a new bash2gitlab project...[/bold]\n")
    base_path = Path(directory).resolve()
    base_path.mkdir(parents=True, exist_ok=True)

    try:
        user_config = prompt_for_config(console, "out")
        final_toml_string = tomlkit.dumps(user_config)

        console.print("\n" + "=" * 60)
        console.print("[bold green]Configuration Preview:[/bold green]")
        console.print(Syntax(final_toml_string, "toml", theme="monokai", line_numbers=True))
        console.print("=" * 60)

        if not Confirm.ask(
            f"\nWrite this configuration to [cyan]{short_path(base_path / 'pyproject.toml')} [/cyan]?", default=True
        ):
            console.print("\n[yellow]Initialization cancelled by user.[/yellow]")
            return 1

        create_or_update_config_file(base_path, user_config, force)

        # Create the source directory as a helpful next step
        input_dir = Path(base_path / user_config["tool"]["bash2gitlab"]["input_dir"])
        if not input_dir.exists():
            input_dir.mkdir(parents=True)
            console.print(f"Created source directory: [cyan]{short_path(input_dir)}[/cyan]")

        console.print("\n[bold green]✅ Project initialization complete.[/bold green]")
        console.print("You can now add your template `.yml` and `.sh` files to the source directory.")
        return 0

    except (KeyboardInterrupt, EOFError):
        console.print("\n\n[yellow]Initialization cancelled by user.[/yellow]")
        return 1
    except FileExistsError as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        return 1
    except Exception as e:
        console.print(f"\n[bold red]An unexpected error occurred:[/bold red] {e}")
        logger.exception("Unexpected error during init.")
        return 1
