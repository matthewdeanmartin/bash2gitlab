"""
Textual TUI for bash2gitlab - Interactive terminal interface
"""

from __future__ import annotations

import logging
import logging.config
import os
import subprocess  # nosec
import sys
from typing import Any

from bash2gitlab.install_help import print_install_help

try:
    from textual import on, work
except (NameError, ModuleNotFoundError):
    print_install_help()
    sys.exit(111)

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    OptionList,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)

from bash2gitlab import __about__
from bash2gitlab.config import config
from bash2gitlab.utils.logging_config import generate_config

# emoji support
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


class CommandForm(Static):
    """Base class for command forms with common functionality."""

    def __init__(self, command_name: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.command_name = command_name

    def compose(self) -> ComposeResult:
        """Override in subclasses to define form layout."""
        yield Static("Override compose() in subclass")

    async def execute_command(self) -> None:
        """Override in subclasses to execute the command."""

    def get_common_args(self) -> list[str]:
        """Get common arguments like --dry-run, --verbose, etc."""
        args: list[str] = []

        # Check for dry run option
        dry_run_widget = self.query_one("#dry-run", Checkbox)
        if dry_run_widget.value:
            args.append("--dry-run")

        # Check for verbose option
        verbose_widget = self.query_one("#verbose", Checkbox)
        if verbose_widget.value:
            args.append("--verbose")

        # Check for quiet option
        quiet_widget = self.query_one("#quiet", Checkbox)
        if quiet_widget.value:
            args.append("--quiet")

        return args


class CompileForm(CommandForm):
    """Form for the compile command."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("📦 Compile Configuration", classes="form-title")

            with Horizontal():
                yield Label("Input Directory:", classes="label")
                yield Input(
                    value=str(config.input_dir) if config and config.input_dir else "",
                    placeholder="Path to uncompiled .gitlab-ci.yml directory",
                    id="input-dir",
                )

            with Horizontal():
                yield Label("Output Directory:", classes="label")
                yield Input(
                    value=str(config.output_dir) if config and config.output_dir else "",
                    placeholder="Path for compiled GitLab CI files",
                    id="output-dir",
                )

            with Horizontal():
                yield Label("Parallelism:", classes="label")
                yield Input(
                    value=str(config.parallelism) if config and config.parallelism else "4",
                    placeholder="Number of parallel processes",
                    id="parallelism",
                )

            with Horizontal():
                yield Checkbox("Watch for changes", id="watch")
                yield Checkbox("Dry run", id="dry-run")
                yield Checkbox("Verbose", id="verbose")
                yield Checkbox("Quiet", id="quiet")

            yield Button("🚀 Compile", variant="success", id="execute-btn")

    async def execute_command(self) -> None:
        """Execute the compile command."""
        args = ["bash2gitlab", "compile"]

        # Get input values
        input_dir = self.query_one("#input-dir", Input).value.strip()
        output_dir = self.query_one("#output-dir", Input).value.strip()
        parallelism = self.query_one("#parallelism", Input).value.strip()
        watch = self.query_one("#watch", Checkbox).value

        if input_dir:
            args.extend(["--in", input_dir])
        if output_dir:
            args.extend(["--out", output_dir])
        if parallelism:
            args.extend(["--parallelism", parallelism])
        if watch:
            args.append("--watch")

        args.extend(self.get_common_args())

        # Post message to main app to execute command
        self.post_message(ExecuteCommand(args))


class DecompileForm(CommandForm):
    """Form for the decompile command."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("✂️ Decompile Configuration", classes="form-title")

            with Horizontal():
                yield Label("Mode:", classes="label")
                yield OptionList("Single File", "Folder Tree", id="decompile-mode")

            with Horizontal():
                yield Label("Input File:", classes="label")
                yield Input(placeholder="Path to single .gitlab-ci.yml file", id="input-file")

            with Horizontal():
                yield Label("Input Folder:", classes="label")
                yield Input(placeholder="Folder to recursively decompile", id="input-folder")

            with Horizontal():
                yield Label("Output Directory:", classes="label")
                yield Input(placeholder="Output directory for decompiled files", id="output-dir")

            with Horizontal():
                yield Checkbox("Dry run", id="dry-run")
                yield Checkbox("Verbose", id="verbose")
                yield Checkbox("Quiet", id="quiet")

            yield Button("✂️ Decompile", variant="warning", id="execute-btn")

    async def execute_command(self) -> None:
        """Execute the decompile command."""
        args = ["bash2gitlab", "decompile"]

        # Get input values
        mode = self.query_one("#decompile-mode", OptionList).highlighted
        input_file = self.query_one("#input-file", Input).value.strip()
        input_folder = self.query_one("#input-folder", Input).value.strip()
        output_dir = self.query_one("#output-dir", Input).value.strip()

        if mode == 0:  # Single File
            if input_file:
                args.extend(["--in-file", input_file])
        else:  # Folder Tree
            if input_folder:
                args.extend(["--in-folder", input_folder])

        if output_dir:
            args.extend(["--out", output_dir])

        args.extend(self.get_common_args())

        self.post_message(ExecuteCommand(args))


class LintForm(CommandForm):
    """Form for the lint command."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("🔍 Lint Configuration", classes="form-title")

            with Horizontal():
                yield Label("Output Directory:", classes="label")
                yield Input(
                    value=str(config.output_dir) if config and config.output_dir else "",
                    placeholder="Directory with compiled YAML files",
                    id="output-dir",
                )

            with Horizontal():
                yield Label("GitLab URL:", classes="label")
                yield Input(placeholder="https://gitlab.com", id="gitlab-url")

            with Horizontal():
                yield Label("Token:", classes="label")
                yield Input(placeholder="Private or CI job token", password=True, id="token")

            with Horizontal():
                yield Label("Project ID:", classes="label")
                yield Input(placeholder="Optional project ID for project-scoped lint", id="project-id")

            with Horizontal():
                yield Label("Git Ref:", classes="label")
                yield Input(placeholder="Git ref (branch/tag/commit)", id="ref")

            with Horizontal():
                yield Label("Parallelism:", classes="label")
                yield Input(
                    value=str(config.parallelism) if config and config.parallelism else "4",
                    placeholder="Max concurrent requests",
                    id="parallelism",
                )

            with Horizontal():
                yield Label("Timeout:", classes="label")
                yield Input(value="20.0", placeholder="HTTP timeout in seconds", id="timeout")

            with Horizontal():
                yield Checkbox("Include merged YAML", id="include-merged")
                yield Checkbox("Dry run", id="dry-run")
                yield Checkbox("Verbose", id="verbose")
                yield Checkbox("Quiet", id="quiet")

            yield Button("🔍 Lint", variant="primary", id="execute-btn")

    async def execute_command(self) -> None:
        """Execute the lint command."""
        args = ["bash2gitlab", "lint"]

        # Get input values
        output_dir = self.query_one("#output-dir", Input).value.strip()
        gitlab_url = self.query_one("#gitlab-url", Input).value.strip()
        token = self.query_one("#token", Input).value.strip()
        project_id = self.query_one("#project-id", Input).value.strip()
        ref = self.query_one("#ref", Input).value.strip()
        parallelism = self.query_one("#parallelism", Input).value.strip()
        timeout = self.query_one("#timeout", Input).value.strip()
        include_merged = self.query_one("#include-merged", Checkbox).value

        if output_dir:
            args.extend(["--out", output_dir])
        if gitlab_url:
            args.extend(["--gitlab-url", gitlab_url])
        if token:
            args.extend(["--token", token])
        if project_id:
            args.extend(["--project-id", project_id])
        if ref:
            args.extend(["--ref", ref])
        if parallelism:
            args.extend(["--parallelism", parallelism])
        if timeout:
            args.extend(["--timeout", timeout])
        if include_merged:
            args.append("--include-merged-yaml")

        args.extend(self.get_common_args())

        self.post_message(ExecuteCommand(args))


class CleanForm(CommandForm):
    """Form for the clean command."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("🧹 Clean Configuration", classes="form-title")

            with Horizontal():
                yield Label("Output Directory:", classes="label")
                yield Input(
                    value=str(config.output_dir) if config and config.output_dir else "",
                    placeholder="Directory to clean",
                    id="output-dir",
                )

            with Horizontal():
                yield Checkbox("Dry run", id="dry-run")
                yield Checkbox("Verbose", id="verbose")
                yield Checkbox("Quiet", id="quiet")

            yield Static("⚠️ This will remove unmodified files that bash2gitlab wrote.", classes="warning")
            yield Button("🧹 Clean", variant="error", id="execute-btn")

    async def execute_command(self) -> None:
        """Execute the clean command."""
        args = ["bash2gitlab", "clean"]

        output_dir = self.query_one("#output-dir", Input).value.strip()

        if output_dir:
            args.extend(["--out", output_dir])

        args.extend(self.get_common_args())

        self.post_message(ExecuteCommand(args))


class InitForm(CommandForm):
    """Form for the init command."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("🆕 Initialize Project", classes="form-title")

            with Horizontal():
                yield Label("Directory:", classes="label")
                yield Input(value=".", placeholder="Directory to initialize", id="directory")

            with Horizontal():
                yield Checkbox("Dry run", id="dry-run")
                yield Checkbox("Verbose", id="verbose")
                yield Checkbox("Quiet", id="quiet")

            yield Button("🆕 Initialize", variant="success", id="execute-btn")

    async def execute_command(self) -> None:
        """Execute the init command."""
        args = ["bash2gitlab", "init"]

        directory = self.query_one("#directory", Input).value.strip()

        if directory and directory != ".":
            args.append(directory)

        args.extend(self.get_common_args())

        self.post_message(ExecuteCommand(args))


class Copy2LocalForm(CommandForm):
    """Form for the copy2local command."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("📥 Copy to Local", classes="form-title")

            with Horizontal():
                yield Label("Repository URL:", classes="label")
                yield Input(placeholder="Git repository URL", id="repo-url")

            with Horizontal():
                yield Label("Branch:", classes="label")
                yield Input(placeholder="Branch name", id="branch")

            with Horizontal():
                yield Label("Source Directory:", classes="label")
                yield Input(placeholder="Directory in repo to copy", id="source-dir")

            with Horizontal():
                yield Label("Destination:", classes="label")
                yield Input(placeholder="Local destination directory", id="copy-dir")

            with Horizontal():
                yield Checkbox("Dry run", id="dry-run")
                yield Checkbox("Verbose", id="verbose")
                yield Checkbox("Quiet", id="quiet")

            yield Button("📥 Copy", variant="primary", id="execute-btn")

    async def execute_command(self) -> None:
        """Execute the copy2local command."""
        args = ["bash2gitlab", "copy2local"]

        repo_url = self.query_one("#repo-url", Input).value.strip()
        branch = self.query_one("#branch", Input).value.strip()
        source_dir = self.query_one("#source-dir", Input).value.strip()
        copy_dir = self.query_one("#copy-dir", Input).value.strip()

        if repo_url:
            args.extend(["--repo-url", repo_url])
        if branch:
            args.extend(["--branch", branch])
        if source_dir:
            args.extend(["--source-dir", source_dir])
        if copy_dir:
            args.extend(["--copy-dir", copy_dir])

        args.extend(self.get_common_args())

        self.post_message(ExecuteCommand(args))


class MapDeployForm(CommandForm):
    """Form for the map-deploy command."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("🗺️ Map Deploy", classes="form-title")

            with Horizontal():
                yield Label("PyProject Path:", classes="label")
                yield Input(value="pyproject.toml", placeholder="Path to pyproject.toml", id="pyproject-path")

            with Horizontal():
                yield Checkbox("Force overwrite", id="force")
                yield Checkbox("Dry run", id="dry-run")
                yield Checkbox("Verbose", id="verbose")
                yield Checkbox("Quiet", id="quiet")

            yield Button("🗺️ Deploy", variant="primary", id="execute-btn")

    async def execute_command(self) -> None:
        """Execute the map-deploy command."""
        args = ["bash2gitlab", "map-deploy"]

        pyproject_path = self.query_one("#pyproject-path", Input).value.strip()
        force = self.query_one("#force", Checkbox).value

        if pyproject_path:
            args.extend(["--pyproject", pyproject_path])
        if force:
            args.append("--force")

        args.extend(self.get_common_args())

        self.post_message(ExecuteCommand(args))


class CommitMapForm(CommandForm):
    """Form for the commit-map command."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("↩️ Commit Map", classes="form-title")

            with Horizontal():
                yield Label("PyProject Path:", classes="label")
                yield Input(value="pyproject.toml", placeholder="Path to pyproject.toml", id="pyproject-path")

            with Horizontal():
                yield Checkbox("Force overwrite", id="force")
                yield Checkbox("Dry run", id="dry-run")
                yield Checkbox("Verbose", id="verbose")
                yield Checkbox("Quiet", id="quiet")

            yield Button("↩️ Commit", variant="warning", id="execute-btn")

    async def execute_command(self) -> None:
        """Execute the commit-map command."""
        args = ["bash2gitlab", "commit-map"]

        pyproject_path = self.query_one("#pyproject-path", Input).value.strip()
        force = self.query_one("#force", Checkbox).value

        if pyproject_path:
            args.extend(["--pyproject", pyproject_path])
        if force:
            args.append("--force")

        args.extend(self.get_common_args())

        self.post_message(ExecuteCommand(args))


class PrecommitForm(CommandForm):
    """Form for precommit install/uninstall commands."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("🪝 Precommit Hooks", classes="form-title")

            with Horizontal():
                yield Label("Repository Root:", classes="label")
                yield Input(value=".", placeholder="Git repository root", id="repo-root")

            with Horizontal():
                yield Checkbox("Force", id="force")
                yield Checkbox("Verbose", id="verbose")
                yield Checkbox("Quiet", id="quiet")

            with Horizontal():
                yield Button("🪝 Install Hook", variant="success", id="install-btn")
                yield Button("🗑️ Uninstall Hook", variant="error", id="uninstall-btn")

    @on(Button.Pressed, "#install-btn")
    async def on_install_pressed(self) -> None:
        """Handle install button press."""
        args = ["bash2gitlab", "install-precommit"]

        repo_root = self.query_one("#repo-root", Input).value.strip()
        force = self.query_one("#force", Checkbox).value
        verbose = self.query_one("#verbose", Checkbox).value
        quiet = self.query_one("#quiet", Checkbox).value

        if repo_root and repo_root != ".":
            args.extend(["--repo-root", repo_root])
        if force:
            args.append("--force")
        if verbose:
            args.append("--verbose")
        if quiet:
            args.append("--quiet")

        self.post_message(ExecuteCommand(args))

    @on(Button.Pressed, "#uninstall-btn")
    async def on_uninstall_pressed(self) -> None:
        """Handle uninstall button press."""
        args = ["bash2gitlab", "uninstall-precommit"]

        repo_root = self.query_one("#repo-root", Input).value.strip()
        force = self.query_one("#force", Checkbox).value
        verbose = self.query_one("#verbose", Checkbox).value
        quiet = self.query_one("#quiet", Checkbox).value

        if repo_root and repo_root != ".":
            args.extend(["--repo-root", repo_root])
        if force:
            args.append("--force")
        if verbose:
            args.append("--verbose")
        if quiet:
            args.append("--quiet")

        self.post_message(ExecuteCommand(args))


class UtilityForm(CommandForm):
    """Form for utility commands like doctor, graph, show-config, detect-drift."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("🔧 Utilities", classes="form-title")

            # Doctor command
            with Horizontal():
                yield Button("🩺 Doctor", variant="primary", id="doctor-btn")
                yield Static("Run health checks")

            # Show config command
            with Horizontal():
                yield Button("⚙️ Show Config", variant="primary", id="show-config-btn")
                yield Static("Display current configuration")

            # Graph command
            with Container():
                with Horizontal():
                    yield Label("Input Directory:", classes="label")
                    yield Input(
                        value=str(config.input_dir) if config and config.input_dir else "",
                        placeholder="Input directory for graph",
                        id="graph-input-dir",
                    )
                yield Button("📊 Generate Graph", variant="primary", id="graph-btn")

            # Detect drift command
            with Container():
                with Horizontal():
                    yield Label("Output Directory:", classes="label")
                    yield Input(
                        value=str(config.output_dir) if config and config.output_dir else "",
                        placeholder="Output directory to check",
                        id="drift-output-dir",
                    )
                yield Button("🔍 Detect Drift", variant="warning", id="drift-btn")

            with Horizontal():
                yield Checkbox("Verbose", id="verbose")
                yield Checkbox("Quiet", id="quiet")

    @on(Button.Pressed, "#doctor-btn")
    async def on_doctor_pressed(self) -> None:
        """Handle doctor button press."""
        args = ["bash2gitlab", "doctor"]

        verbose = self.query_one("#verbose", Checkbox).value
        quiet = self.query_one("#quiet", Checkbox).value

        if verbose:
            args.append("--verbose")
        if quiet:
            args.append("--quiet")

        self.post_message(ExecuteCommand(args))

    @on(Button.Pressed, "#show-config-btn")
    async def on_show_config_pressed(self) -> None:
        """Handle show-config button press."""
        args = ["bash2gitlab", "show-config"]

        verbose = self.query_one("#verbose", Checkbox).value
        quiet = self.query_one("#quiet", Checkbox).value

        if verbose:
            args.append("--verbose")
        if quiet:
            args.append("--quiet")

        self.post_message(ExecuteCommand(args))

    @on(Button.Pressed, "#graph-btn")
    async def on_graph_pressed(self) -> None:
        """Handle graph button press."""
        args = ["bash2gitlab", "graph"]

        input_dir = self.query_one("#graph-input-dir", Input).value.strip()
        verbose = self.query_one("#verbose", Checkbox).value
        quiet = self.query_one("#quiet", Checkbox).value

        if input_dir:
            args.extend(["--in", input_dir])
        if verbose:
            args.append("--verbose")
        if quiet:
            args.append("--quiet")

        self.post_message(ExecuteCommand(args))

    @on(Button.Pressed, "#drift-btn")
    async def on_drift_pressed(self) -> None:
        """Handle detect-drift button press."""
        args = ["bash2gitlab", "detect-drift"]

        output_dir = self.query_one("#drift-output-dir", Input).value.strip()
        verbose = self.query_one("#verbose", Checkbox).value
        quiet = self.query_one("#quiet", Checkbox).value

        if output_dir:
            args.extend(["--out", output_dir])
        if verbose:
            args.append("--verbose")
        if quiet:
            args.append("--quiet")

        self.post_message(ExecuteCommand(args))


class ExecuteCommand(Message):
    """Message to request command execution."""

    def __init__(self, args: list[str]) -> None:
        super().__init__()
        self.args = args


class CommandScreen(Screen):
    """Screen for executing commands and showing output."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("ctrl+c", "cancel", "Cancel"),
    ]

    def __init__(self, command_args: list[str], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.command_args = command_args
        self.process: subprocess.Popen | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label(f"Executing: {' '.join(self.command_args)}", classes="command-title")
            yield RichLog(id="output", wrap=True, highlight=True, markup=True)
            with Horizontal():
                yield Button("Cancel", variant="error", id="cancel-btn")
                yield Button("Close", variant="primary", id="close-btn", disabled=True)
        yield Footer()

    async def on_mount(self) -> None:
        """Start command execution when screen mounts."""
        self.execute_command()

    @work(exclusive=True)
    async def execute_command(self) -> None:
        """Execute the command and stream output."""
        log = self.query_one("#output", RichLog)

        try:
            log.write(f"[bold green]Starting command:[/bold green] {' '.join(self.command_args)}")

            env = {}
            for key, value in os.environ.items():
                env[key] = value
            env["NO_COLOR"] = "1"
            self.process = subprocess.Popen(  # nosec
                self.command_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                encoding="utf-8",
                bufsize=1,
                env=env,
            )

            # Stream output
            while True:
                if self.process.stdout:
                    output = self.process.stdout.readline()
                    if output == "" and self.process.poll() is not None:
                        break
                    if output:
                        log.write(output.rstrip())

            return_code = self.process.poll()

            if return_code == 0:
                log.write("[bold green]✅ Command completed successfully[/bold green]")
            else:
                log.write(f"[bold red]❌ Command failed with exit code {return_code}[/bold red]")

        except Exception as e:
            log.write(f"[bold red]❌ Error executing command: {e}[/bold red]")
        finally:
            # Enable close button
            self.query_one("#close-btn", Button).disabled = False
            self.query_one("#cancel-btn", Button).disabled = True

    @on(Button.Pressed, "#cancel-btn")
    async def on_cancel_pressed(self) -> None:
        """Cancel the running command."""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            log = self.query_one("#output", RichLog)
            log.write("[bold yellow]⚠️ Command cancelled by user[/bold yellow]")

    @on(Button.Pressed, "#close-btn")
    def on_close_pressed(self) -> None:
        """Close the command screen."""
        self.app.pop_screen()

    def action_close(self) -> None:
        """Close the screen."""
        self.app.pop_screen()

    def action_cancel(self) -> None:
        """Cancel the command."""
        if self.process and self.process.poll() is None:
            self.process.terminate()


class Bash2GitlabTUI(App):
    """Main TUI application for bash2gitlab."""

    CSS = """
    .form-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin: 1;
    }

    .label {
        width: 20;
        text-align: right;
        margin-right: 1;
    }

    .warning {
        color: $warning;
        text-style: italic;
        margin: 1;
    }

    .command-title {
        text-align: center;
        text-style: bold;
        margin: 1;
    }

    TabbedContent {
        height: 1fr;
    }

    TabPane {
        padding: 1;
    }

    Button {
        margin: 1;
    }

    Horizontal {
        height: auto;
        margin: 1 0;
    }

    Input {
        width: 1fr;
    }

    Checkbox, Switch {
        margin-right: 2;
    }
    """

    TITLE = f"bash2gitlab TUI v{__about__.__version__}"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("ctrl+h", "help", "Help"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()

        with TabbedContent(initial="compile"):
            with TabPane("Compile", id="compile"):
                yield CompileForm("compile")

            with TabPane("Decompile", id="decompile"):
                yield DecompileForm("decompile")

            with TabPane("Lint", id="lint"):
                yield LintForm("lint")

            with TabPane("Clean", id="clean"):
                yield CleanForm("clean")

            with TabPane("Init", id="init"):
                yield InitForm("init")

            with TabPane("Copy2Local", id="copy2local"):
                yield Copy2LocalForm("copy2local")

            with TabPane("Map Deploy", id="map-deploy"):
                yield MapDeployForm("map-deploy")

            with TabPane("Commit Map", id="commit-map"):
                yield CommitMapForm("commit-map")

            with TabPane("Precommit", id="precommit"):
                yield PrecommitForm("precommit")

            with TabPane("Utilities", id="utilities"):
                yield UtilityForm("utilities")

        yield Footer()

    @on(Button.Pressed, "#execute-btn")
    async def on_execute_button_pressed(self, event: Button.Pressed) -> None:
        """Handle execute button presses from forms."""
        # Find the parent form and execute its command
        form = event.button.parent
        while form and not isinstance(form, CommandForm):
            form = form.parent

        if form:
            await form.execute_command()  # type: ignore[attr-defined]

    @on(ExecuteCommand)
    async def on_execute_command(self, message: ExecuteCommand) -> None:
        """Handle command execution requests."""
        # Push a new screen to show command execution
        screen = CommandScreen(message.args)
        await self.push_screen(screen)

    def action_help(self) -> None:
        """Show help information."""
        help_text = f"""
# bash2gitlab TUI v{__about__.__version__}

## Navigation
- Use Tab/Shift+Tab to navigate between form fields
- Use arrow keys to navigate in option lists
- Press Enter to activate buttons and checkboxes
- Use Ctrl+Q to quit the application

## Commands

### Compile
Compile uncompiled GitLab CI directory structure into standard format.
- **Input Directory**: Path to directory containing uncompiled .gitlab-ci.yml
- **Output Directory**: Where compiled files will be written
- **Parallelism**: Number of files to process simultaneously
- **Watch**: Monitor source files for changes and auto-recompile

### Decompile
Extract inline scripts from GitLab CI YAML files into separate .sh files.
- **Mode**: Choose between single file or folder tree processing
- **Input File/Folder**: Source YAML file or directory
- **Output Directory**: Where decompiled files will be written

### Lint
Validate compiled GitLab CI YAML against a GitLab instance.
- **GitLab URL**: Base URL of GitLab instance (e.g., https://gitlab.com)
- **Token**: Private token or CI job token for authentication
- **Project ID**: Optional project ID for project-scoped linting
- **Include Merged YAML**: Return complete merged YAML (slower)

### Clean
Remove unmodified files that bash2gitlab previously generated.
- **Output Directory**: Directory to clean

### Init  
Initialize a new bash2gitlab project with interactive configuration.
- **Directory**: Project directory to initialize

### Copy2Local
Copy directories from remote repositories to local filesystem.
- **Repository URL**: Git repository URL (HTTP/HTTPS/SSH)
- **Branch**: Branch to copy from
- **Source Directory**: Directory within repo to copy
- **Destination**: Local destination directory

### Map Deploy/Commit Map
Deploy/commit files based on mapping configuration in pyproject.toml.
- **PyProject Path**: Path to pyproject.toml with mapping config
- **Force**: Overwrite files even if they've been modified

### Precommit
Install or uninstall Git pre-commit hooks for bash2gitlab.
- **Repository Root**: Git repository root directory
- **Force**: Overwrite existing hooks

### Utilities
- **Doctor**: Run system health checks
- **Show Config**: Display current configuration
- **Generate Graph**: Create dependency graph (DOT format)  
- **Detect Drift**: Check for manual edits to generated files

## Common Options
- **Dry Run**: Simulate command without making changes
- **Verbose**: Enable detailed logging output
- **Quiet**: Suppress output messages

Press Escape to close this help.
        """

        class HelpScreen(Screen):
            BINDINGS = [("escape", "close", "Close")]

            def compose(self) -> ComposeResult:
                yield Header()
                with VerticalScroll():
                    yield Static(help_text, id="help-text")
                yield Footer()

            def action_close(self) -> None:
                self.app.pop_screen()

        self.push_screen(HelpScreen())

    async def action_quit(self) -> None:
        """Quit the application."""
        self.exit()


def main() -> None:
    """Main entry point for the TUI."""
    # Setup logging
    if config:
        log_level = "INFO" if not config.verbose else "DEBUG"
        if config.quiet:
            log_level = "CRITICAL"
    else:
        log_level = "INFO"

    try:
        logging.config.dictConfig(generate_config(level=log_level))
    except:
        # Fallback logging setup
        logging.basicConfig(level=getattr(logging, log_level))

    app = Bash2GitlabTUI()
    app.run()


if __name__ == "__main__":
    main()
