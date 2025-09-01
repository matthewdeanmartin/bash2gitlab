"""
Rich-based interactive Q&A interface for bash2gitlab.

This module provides an interactive command-line interface using Rich library
for a more user-friendly experience with bash2gitlab commands.
"""

from __future__ import annotations

import sys
from typing import Any

from bash2gitlab.install_help import print_install_help

try:
    from rich import box
except (NameError, ModuleNotFoundError):
    print_install_help()
    sys.exit(111)

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

from bash2gitlab import __about__
from bash2gitlab.config import config


class InteractiveInterface:
    """Rich-based interactive interface for bash2gitlab."""

    def __init__(self) -> None:
        self.console = Console()
        self.current_config: dict[str, Any] = {}

    def show_welcome(self) -> None:
        """Display welcome screen with application info."""
        welcome_text = Text()
        welcome_text.append("bash2gitlab", style="bold blue")
        welcome_text.append(" Interactive Interface\n", style="bold")
        welcome_text.append(f"Version: {__about__.__version__}\n", style="dim")
        welcome_text.append(
            "A tool for making development of centralized yaml gitlab templates more pleasant.", style="italic"
        )

        panel = Panel(Align.center(welcome_text), box=box.ROUNDED, style="blue", padding=(1, 2))

        self.console.print()
        self.console.print(panel)
        self.console.print()

    def show_main_menu(self) -> str:
        """Display main menu and get user choice."""
        menu_options = [
            ("1", "compile", "Compile uncompiled directory into GitLab CI structure"),
            ("2", "decompile", "Extract inline scripts from GitLab CI YAML files"),
            ("3", "clean", "Clean output folder (remove unmodified generated files)"),
            ("4", "lint", "Validate compiled GitLab CI YAML against GitLab instance"),
            ("5", "init", "Initialize new bash2gitlab project"),
            ("6", "copy2local", "Copy folder(s) from repository to local"),
            ("7", "map-deploy", "Deploy files based on pyproject.toml mapping"),
            ("8", "commit-map", "Copy changed files back to source locations"),
            ("9", "detect-drift", "Detect if generated files have been edited"),
            ("10", "doctor", "Run health checks on project and environment"),
            ("11", "graph", "Generate dependency graph of project files"),
            ("12", "show-config", "Display current configuration"),
            ("13", "install-precommit", "Install Git pre-commit hook"),
            ("14", "uninstall-precommit", "Remove Git pre-commit hook"),
            ("q", "quit", "Exit interactive interface"),
        ]

        table = Table(title="Available Commands", box=box.ROUNDED)
        table.add_column("Option", style="cyan", no_wrap=True)
        table.add_column("Command", style="magenta", no_wrap=True)
        table.add_column("Description", style="white")

        for option, command, description in menu_options:
            table.add_row(option, command, description)

        self.console.print(table)
        self.console.print()

        choice = Prompt.ask("Select a command", choices=[opt[0] for opt in menu_options], default="q")

        return choice

    def get_common_options(self) -> dict[str, Any]:
        """Get common options that apply to most commands."""
        options = {}

        self.console.print("\n[bold]Common Options:[/bold]")

        options["dry_run"] = Confirm.ask("Enable dry run mode?", default=False)
        options["verbose"] = Confirm.ask("Enable verbose logging?", default=False)
        options["quiet"] = Confirm.ask("Enable quiet mode?", default=False)

        return options

    def handle_compile_command(self) -> dict[str, Any]:
        """Handle compile command configuration."""
        self.console.print("\n[bold cyan]Compile Command Configuration[/bold cyan]")

        params: dict[str, Any] = {}

        # Input directory
        default_input = str(config.input_dir) if config.input_dir else "."
        input_dir = Prompt.ask("Input directory", default=default_input)
        params["input_dir"] = input_dir

        # Output directory
        default_output = str(config.output_dir) if config.output_dir else "./output"
        output_dir = Prompt.ask("Output directory", default=default_output)
        params["output_dir"] = output_dir

        # Parallelism
        default_parallelism = config.parallelism if config.parallelism else 4
        parallelism = IntPrompt.ask("Number of parallel processes", default=default_parallelism)
        params["parallelism"] = parallelism

        # Watch mode
        params["watch"] = Confirm.ask("Enable watch mode (auto-recompile on changes)?", default=False)

        # Common options
        params.update(self.get_common_options())

        return params

    def handle_decompile_command(self) -> dict[str, Any]:
        """Handle decompile command configuration."""
        self.console.print("\n[bold cyan]Decompile Command Configuration[/bold cyan]")

        params = {}

        # Input choice
        input_choice = Prompt.ask("Input type", choices=["file", "folder"], default="file")

        if input_choice == "file":
            input_file = Prompt.ask("Input GitLab CI YAML file path")
            params["input_file"] = input_file
        else:
            input_folder = Prompt.ask("Input folder path")
            params["input_folder"] = input_folder

        # Output directory
        output_dir = Prompt.ask("Output directory", default="./decompiled_output")
        params["output_dir"] = output_dir

        # Common options
        params.update(self.get_common_options())

        return params

    def handle_clean_command(self) -> dict[str, Any]:
        """Handle clean command configuration."""
        self.console.print("\n[bold cyan]Clean Command Configuration[/bold cyan]")

        params = {}

        # Output directory
        default_output = str(config.output_dir) if config.output_dir else "./output"
        output_dir = Prompt.ask("Output directory to clean", default=default_output)
        params["output_dir"] = output_dir

        # Common options
        params.update(self.get_common_options())

        return params

    def handle_lint_command(self) -> dict[str, Any]:
        """Handle lint command configuration."""
        self.console.print("\n[bold cyan]Lint Command Configuration[/bold cyan]")

        params: dict[str, Any] = {}

        # Output directory
        default_output = str(config.output_dir) if config.output_dir else "./output"
        output_dir = Prompt.ask("Output directory containing YAML files", default=default_output)
        params["output_dir"] = output_dir

        # GitLab URL
        gitlab_url = Prompt.ask("GitLab URL", default="https://gitlab.com")
        params["gitlab_url"] = gitlab_url

        # Token (optional)
        token = Prompt.ask("GitLab token (optional, press Enter to skip)", default="")
        if token:
            params["token"] = token

        # Project ID (optional)
        project_id_str = Prompt.ask("Project ID for project-scoped lint (optional)", default="")
        if project_id_str:
            try:
                params["project_id"] = int(project_id_str)
            except ValueError:
                self.console.print("[red]Invalid project ID, skipping[/red]")

        # Git ref (optional)
        ref = Prompt.ask("Git ref (optional)", default="")
        if ref:
            params["ref"] = ref

        # Include merged YAML
        params["include_merged_yaml"] = Confirm.ask("Include merged YAML?", default=False)

        # Parallelism
        default_parallelism = config.parallelism if config.parallelism else 4
        parallelism = IntPrompt.ask("Number of parallel requests", default=default_parallelism)
        params["parallelism"] = parallelism

        # Timeout
        timeout = Prompt.ask("HTTP timeout (seconds)", default="20.0")
        try:
            params["timeout"] = float(timeout)
        except ValueError:
            params["timeout"] = 20.0

        # Common options
        params.update(self.get_common_options())

        return params

    def handle_init_command(self) -> dict[str, Any]:
        """Handle init command configuration."""
        self.console.print("\n[bold cyan]Init Command Configuration[/bold cyan]")

        params = {}

        # Directory
        directory = Prompt.ask("Directory to initialize", default=".")
        params["directory"] = directory

        # Common options
        params.update(self.get_common_options())

        return params

    def handle_copy2local_command(self) -> dict[str, Any]:
        """Handle copy2local command configuration."""
        self.console.print("\n[bold cyan]Copy2Local Command Configuration[/bold cyan]")

        params = {}

        # Repository URL
        repo_url = Prompt.ask("Repository URL")
        params["repo_url"] = repo_url

        # Branch
        branch = Prompt.ask("Branch name", default="main")
        params["branch"] = branch

        # Source directory
        source_dir = Prompt.ask("Source directory in repository")
        params["source_dir"] = source_dir

        # Copy directory
        copy_dir = Prompt.ask("Local destination directory")
        params["copy_dir"] = copy_dir

        # Common options
        params.update(self.get_common_options())

        return params

    def handle_map_deploy_command(self) -> dict[str, Any]:
        """Handle map-deploy command configuration."""
        self.console.print("\n[bold cyan]Map-Deploy Command Configuration[/bold cyan]")

        params: dict[str, Any] = {}

        # Pyproject.toml path
        pyproject_path = Prompt.ask("Path to pyproject.toml", default="pyproject.toml")
        params["pyproject_path"] = pyproject_path

        # Force option
        params["force"] = Confirm.ask("Force overwrite target files?", default=False)

        # Common options
        params.update(self.get_common_options())

        return params

    def handle_commit_map_command(self) -> dict[str, Any]:
        """Handle commit-map command configuration."""
        self.console.print("\n[bold cyan]Commit-Map Command Configuration[/bold cyan]")

        params: dict[str, Any] = {}

        # Pyproject.toml path
        pyproject_path = Prompt.ask("Path to pyproject.toml", default="pyproject.toml")
        params["pyproject_path"] = pyproject_path

        # Force option
        params["force"] = Confirm.ask("Force overwrite source files?", default=False)

        # Common options
        params.update(self.get_common_options())

        return params

    def handle_detect_drift_command(self) -> dict[str, Any]:
        """Handle detect-drift command configuration."""
        self.console.print("\n[bold cyan]Detect-Drift Command Configuration[/bold cyan]")

        params = {}

        # Output path
        default_output = str(config.output_dir) if config.output_dir else "./output"
        out_path = Prompt.ask("Output path to check for drift", default=default_output)
        params["out"] = out_path

        # Common options
        params.update(self.get_common_options())

        return params

    def handle_doctor_command(self) -> dict[str, Any]:
        """Handle doctor command configuration."""
        self.console.print("\n[bold cyan]Doctor Command Configuration[/bold cyan]")
        self.console.print("Running health checks...")

        params = {}

        # Common options
        params.update(self.get_common_options())

        return params

    def handle_graph_command(self) -> dict[str, Any]:
        """Handle graph command configuration."""
        self.console.print("\n[bold cyan]Graph Command Configuration[/bold cyan]")

        params = {}

        # Input directory
        default_input = str(config.input_dir) if config.input_dir else "."
        input_dir = Prompt.ask("Input directory", default=default_input)
        params["input_dir"] = input_dir

        # Common options
        params.update(self.get_common_options())

        return params

    def handle_show_config_command(self) -> dict[str, Any]:
        """Handle show-config command configuration."""
        self.console.print("\n[bold cyan]Show-Config Command[/bold cyan]")
        self.console.print("Displaying current configuration...")

        params = {}

        # Common options
        params.update(self.get_common_options())

        return params

    def handle_precommit_command(self, install: bool = True) -> dict[str, Any]:
        """Handle pre-commit install/uninstall command configuration."""
        action = "Install" if install else "Uninstall"
        self.console.print(f"\n[bold cyan]{action} Pre-commit Command Configuration[/bold cyan]")

        params: dict[str, Any] = {}

        # Repository root
        repo_root = Prompt.ask("Repository root", default=".")
        params["repo_root"] = repo_root

        # Force option
        params["force"] = Confirm.ask(f"Force {action.lower()}?", default=False)

        # Only verbose and quiet for precommit commands
        params["verbose"] = Confirm.ask("Enable verbose logging?", default=False)
        params["quiet"] = Confirm.ask("Enable quiet mode?", default=False)

        return params

    def display_command_summary(self, command: str, params: dict[str, Any]) -> bool:
        """Display summary of command configuration before execution."""
        self.console.print(f"\n[bold green]Command Summary: {command}[/bold green]")

        table = Table(box=box.SIMPLE)
        table.add_column("Parameter", style="cyan")
        table.add_column("Value", style="white")

        for key, value in params.items():
            table.add_row(str(key), str(value))

        self.console.print(table)

        if not Confirm.ask("\nExecute this command?", default=True):
            return False

        return True

    def execute_command(self, command: str, params: dict[str, Any]) -> None:
        """Execute the configured command."""
        self.console.print(f"\n[bold yellow]Executing: {command}[/bold yellow]")

        # Import the main CLI module to reuse handlers
        import argparse

        from bash2gitlab.__main__ import (
            clean_handler,
            commit_map_handler,
            compile_handler,
            copy2local_handler,
            decompile_handler,
            doctor_handler,
            drift_handler,
            graph_handler,
            init_handler,
            install_precommit_handler,
            lint_handler,
            map_deploy_handler,
            show_config_handler,
            uninstall_precommit_handler,
        )

        # Create a namespace object with the parameters
        args = argparse.Namespace(**params)

        # Map commands to their handlers
        handlers = {
            "compile": compile_handler,
            "decompile": decompile_handler,
            "clean": clean_handler,
            "lint": lint_handler,
            "init": init_handler,
            "copy2local": copy2local_handler,
            "map-deploy": map_deploy_handler,
            "commit-map": commit_map_handler,
            "detect-drift": drift_handler,
            "doctor": doctor_handler,
            "graph": graph_handler,
            "show-config": show_config_handler,
            "install-precommit": install_precommit_handler,
            "uninstall-precommit": uninstall_precommit_handler,
        }

        handler = handlers.get(command)
        if handler:
            try:
                exit_code = handler(args)
                if exit_code == 0:
                    self.console.print("\n[bold green]✅ Command completed successfully![/bold green]")
                else:
                    self.console.print(f"\n[bold red]❌ Command failed with exit code: {exit_code}[/bold red]")
            except Exception as e:
                self.console.print(f"\n[bold red]❌ Error executing command: {e}[/bold red]")
        else:
            self.console.print(f"\n[bold red]❌ Unknown command: {command}[/bold red]")

    def run(self) -> None:
        """Main interactive loop."""
        self.show_welcome()

        while True:
            try:
                choice = self.show_main_menu()

                if choice == "q":
                    self.console.print("\n[bold blue]Thank you for using bash2gitlab! 👋[/bold blue]")
                    break

                # Map choices to commands and handlers
                command_map = {
                    "1": ("compile", self.handle_compile_command),
                    "2": ("decompile", self.handle_decompile_command),
                    "3": ("clean", self.handle_clean_command),
                    "4": ("lint", self.handle_lint_command),
                    "5": ("init", self.handle_init_command),
                    "6": ("copy2local", self.handle_copy2local_command),
                    "7": ("map-deploy", self.handle_map_deploy_command),
                    "8": ("commit-map", self.handle_commit_map_command),
                    "9": ("detect-drift", self.handle_detect_drift_command),
                    "10": ("doctor", self.handle_doctor_command),
                    "11": ("graph", self.handle_graph_command),
                    "12": ("show-config", self.handle_show_config_command),
                    "13": ("install-precommit", lambda: self.handle_precommit_command(True)),
                    "14": ("uninstall-precommit", lambda: self.handle_precommit_command(False)),
                }

                if choice in command_map:
                    command, handler = command_map[choice]
                    params = handler()

                    if self.display_command_summary(command, params):
                        self.execute_command(command, params)

                    self.console.print("\n" + "=" * 60)

                    if not Confirm.ask("Continue with another command?", default=True):
                        break

            except KeyboardInterrupt:
                self.console.print("\n\n[bold yellow]Interrupted by user. Goodbye! 👋[/bold yellow]")
                break
            except EOFError:
                self.console.print("\n\n[bold yellow]EOF received. Goodbye! 👋[/bold yellow]")
                break


def main() -> int:
    """Main entry point for the interactive interface."""
    try:
        interface = InteractiveInterface()
        interface.run()
        return 0
    except Exception as e:
        console = Console()
        console.print(f"[bold red]Fatal error: {e}[/bold red]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
