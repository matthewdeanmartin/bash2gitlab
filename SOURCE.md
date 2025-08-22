## Tree for bash2gitlab
```
├── builtin_plugins.py
├── commands/
│   ├── best_effort_runner.py
│   ├── clean_all.py
│   ├── clone2local.py
│   ├── compile_all.py
│   ├── compile_bash_reader.py
│   ├── compile_detct_last_change.py
│   ├── compile_not_bash.py
│   ├── decompile_all.py
│   ├── detect_drift.py
│   ├── doctor.py
│   ├── graph_all.py
│   ├── init_project.py
│   ├── input_change_detector.py
│   ├── lint_all.py
│   ├── map_commit.py
│   ├── map_deploy.py
│   ├── precommit.py
│   └── show_config.py
├── config.py
├── gui.py
├── hookspecs.py
├── install_help.py
├── interactive.py
├── plugins.py
├── py.typed
├── schemas/
│   └── gitlab_ci_schema.json
├── tui.py
├── utils/
│   ├── check_interactive.py
│   ├── cli_suggestions.py
│   ├── dotenv.py
│   ├── logging_config.py
│   ├── mock_ci_vars.py
│   ├── parse_bash.py
│   ├── pathlib_polyfills.py
│   ├── temp_env.py
│   ├── terminal_colors.py
│   ├── update_checker.py
│   ├── utils.py
│   ├── validate_pipeline.py
│   ├── yaml_factory.py
│   └── yaml_file_same.py
├── watch_files.py
├── __about__.py
└── __main__.py
```

## File: builtin_plugins.py
```python
from __future__ import annotations

from pathlib import Path

from pluggy import HookimplMarker

from bash2gitlab.commands.compile_not_bash import maybe_inline_interpreter_command
from bash2gitlab.utils.parse_bash import extract_script_path as _extract

hookimpl = HookimplMarker("bash2gitlab")


class Defaults:
    @hookimpl(tryfirst=True)  # firstresult=True
    def extract_script_path(self, line: str) -> str | None:
        return _extract(line)

    @hookimpl(tryfirst=True)  # firstresult=True
    def inline_command(self, line: str, scripts_root: Path) -> tuple[list[str], Path] | tuple[None, None]:
        return maybe_inline_interpreter_command(line, scripts_root)
```
## File: config.py
```python
from __future__ import annotations

import logging
import os
import sys
from collections.abc import Collection
from pathlib import Path
from typing import Any, TypeVar

from bash2gitlab.utils.utils import short_path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

logger = logging.getLogger(__name__)

T = TypeVar("T")


class _Config:
    """
    Manages configuration for bash2gitlab, loading from files and environment variables.

    Configuration is loaded with the following priority:
    1. Environment variables (e.g., BASH2GITLAB_LINT_GITLAB_URL)
    2. Command-specific sections in the config file (e.g., [lint])
    3. Top-level settings in the config file (e.g., output_dir)
    4. Hardcoded defaults (implicitly, where applicable)
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
        self.config_path_override = config_path_override
        self.file_config: dict[str, Any] = self.load_file_config()
        self.env_config: dict[str, str] = self.load_env_config()

    def find_config_file(self) -> Path | None:
        """Searches for a configuration file in the current directory and its parents."""
        current_dir = Path.cwd()
        for directory in [current_dir, *current_dir.parents]:
            for filename in self._CONFIG_FILES:
                config_path = directory / filename
                if config_path.is_file():
                    logger.debug(f"Found configuration file: {config_path}")
                    return config_path
        return None

    def load_file_config(self) -> dict[str, Any]:
        """Loads configuration from bash2gitlab.toml or pyproject.toml."""
        config_path = self.config_path_override or self.find_config_file()
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

            logger.info(f"Loaded configuration from {short_path(config_path)}")
            return file_config

        except tomllib.TOMLDecodeError as e:
            logger.error(f"Error decoding TOML file {short_path(config_path)}: {e}")
            return {}
        except OSError as e:
            logger.error(f"Error reading file {short_path(config_path)}: {e}")
            return {}

    def load_env_config(self) -> dict[str, str]:
        """Loads configuration from environment variables."""
        env_config = {}
        for key, value in os.environ.items():
            if key.startswith(self._ENV_VAR_PREFIX):
                # Converts BASH2GITLAB_SECTION_KEY to section_key
                config_key = key[len(self._ENV_VAR_PREFIX) :].lower()
                env_config[config_key] = value
                logger.debug(f"Loaded from environment: {config_key}")
        return env_config

    def _get_value(self, key: str, section: str | None = None) -> tuple[Any, str]:
        """Internal helper to get a value and its source."""
        # Check environment variables first
        env_key = f"{section}_{key}" if section else key
        value = self.env_config.get(env_key)
        if value is not None:
            return value, "env"

        # Check config file (section-specific, then top-level)
        if section:
            config_section = self.file_config.get(section, {})
            if isinstance(config_section, dict):
                value = config_section.get(key)
                if value is not None:
                    return value, "file"

        value = self.file_config.get(key)
        if value is not None:
            return value, "file"

        return None, "none"

    def _coerce_type(self, value: Any, target_type: type[T], key: str) -> T | None:
        """Coerces a value to the target type, logging warnings on failure."""
        if value is None:
            return None
        try:
            if target_type is bool and isinstance(value, str):
                return value.lower() in ("true", "1", "t", "y", "yes")  # type: ignore[return-value]
            return target_type(value)  # type: ignore[return-value,call-arg]
        except (ValueError, TypeError):
            logger.warning(f"Config value for '{key}' is not a valid {target_type.__name__}. Ignoring.")
            return None

    def get_str(self, key: str, section: str | None = None) -> str | None:
        value, _ = self._get_value(key, section)
        return str(value) if value is not None else None

    def get_bool(self, key: str, section: str | None = None) -> bool | None:
        value, _ = self._get_value(key, section)
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        return self._coerce_type(value, bool, key)

    def get_int(self, key: str, section: str | None = None) -> int | None:
        value, _ = self._get_value(key, section)
        return self._coerce_type(value, int, key)

    def get_float(self, key: str, section: str | None = None) -> float | None:
        value, _ = self._get_value(key, section)
        return self._coerce_type(value, float, key)

    def get_dict(self, key: str, section: str | None = None) -> dict[str, str]:
        value, _ = self._get_value(key, section)
        if isinstance(value, dict):
            copy_dict = {}
            for the_key, the_value in value.items():
                copy_dict[str(the_key)] = str(the_value)
            return copy_dict
        return {}

    def get_dict_of_list(self, key: str, section: str | None = None) -> dict[str, list[str] | Collection[str]]:
        value, _ = self._get_value(key, section)
        if isinstance(value, dict):
            copy_dict = {}
            for the_key, the_value in value.items():
                copy_dict[str(the_key)] = the_value
            return copy_dict
        return {}

    # --- General Properties ---
    @property
    def input_dir(self) -> str | None:
        return self.get_str("input_dir")

    @property
    def output_dir(self) -> str | None:
        return self.get_str("output_dir")

    @property
    def parallelism(self) -> int | None:
        return self.get_int("parallelism")

    @property
    def dry_run(self) -> bool | None:
        return self.get_bool("dry_run")

    @property
    def verbose(self) -> bool | None:
        return self.get_bool("verbose")

    @property
    def quiet(self) -> bool | None:
        return self.get_bool("quiet")

    @property
    def custom_header(self) -> str | None:
        return self.get_str("custom_header")

    # --- Custom Shebangs ---
    @property
    def custom_shebangs(self) -> dict[str, str] | None:
        return self.get_dict("shebangs")

    # --- `compile` Command Properties ---
    @property
    def compile_input_dir(self) -> str | None:
        return self.get_str("input_dir", section="compile") or self.input_dir

    @property
    def compile_output_dir(self) -> str | None:
        return self.get_str("output_dir", section="compile") or self.output_dir

    @property
    def compile_parallelism(self) -> int | None:
        return self.get_int("parallelism", section="compile") or self.parallelism

    @property
    def compile_watch(self) -> bool | None:
        return self.get_bool("watch", section="compile")

    # --- `decompile` Command Properties ---
    @property
    def decompile_input_file(self) -> str | None:
        return self.get_str("input_file", section="decompile")

    @property
    def decompile_input_folder(self) -> str | None:
        return self.get_str("input_folder", section="decompile")

    @property
    def decompile_output_dir(self) -> str | None:
        return self.get_str("output_dir", section="decompile") or self.output_dir

    # --- `lint` Command Properties ---
    @property
    def lint_output_dir(self) -> str | None:
        return self.get_str("output_dir", section="lint") or self.output_dir

    @property
    def lint_gitlab_url(self) -> str | None:
        return self.get_str("gitlab_url", section="lint")

    @property
    def lint_project_id(self) -> int | None:
        return self.get_int("project_id", section="lint")

    @property
    def lint_ref(self) -> str | None:
        return self.get_str("ref", section="lint")

    @property
    def lint_include_merged_yaml(self) -> bool | None:
        return self.get_bool("include_merged_yaml", section="lint")

    @property
    def lint_parallelism(self) -> int | None:
        return self.get_int("parallelism", section="lint") or self.parallelism

    @property
    def lint_timeout(self) -> float | None:
        return self.get_float("timeout", section="lint")

    # --- `copy2local` Command Properties ---
    @property
    def copy2local_repo_url(self) -> str | None:
        return self.get_str("repo_url", section="copy2local")

    @property
    def copy2local_branch(self) -> str | None:
        return self.get_str("branch", section="copy2local")

    @property
    def copy2local_source_dir(self) -> str | None:
        return self.get_str("source_dir", section="copy2local")

    @property
    def copy2local_copy_dir(self) -> str | None:
        return self.get_str("copy_dir", section="copy2local")

    # --- `map-deploy` / `commit-map` Properties ---
    @property
    def map_folders(self) -> dict[str, list[str] | Collection[str]]:
        return self.get_dict_of_list("map", section="map")  # type: ignore[return=value]

    @property
    def map_force(self) -> bool | None:
        return self.get_bool("force", section="map")


config = _Config()


def reset_for_testing(config_path_override: Path | None = None) -> _Config:
    """
    Resets the singleton config instance. For testing purposes only.
    Allows specifying a direct path to a config file.
    """
    # pylint: disable=global-statement
    global config
    config = _Config(config_path_override=config_path_override)
    return config
```
## File: gui.py
```python
#!/usr/bin/env python3
"""
GUI interface for bash2gitlab CLI tool.

This module provides a Tkinter-based graphical interface for all bash2gitlab
commands, making it easier to use without memorizing CLI arguments.
"""

from __future__ import annotations

import logging
import os
import subprocess  # nosec
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Any, Callable


class LogHandler(logging.Handler):
    """Custom logging handler that writes to a Tkinter text widget."""

    def __init__(self, text_widget: tk.Text) -> None:
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to the text widget."""
        msg = self.format(record)
        # Thread-safe GUI update
        self.text_widget.after(0, lambda: self._append_to_widget(msg))

    def _append_to_widget(self, msg: str) -> None:
        """Append message to text widget (must be called from main thread)."""
        self.text_widget.insert(tk.END, msg + "\n")
        self.text_widget.see(tk.END)
        self.text_widget.update_idletasks()


class CommandRunner:
    """Handles running bash2gitlab commands in a separate thread."""

    def __init__(self, output_widget: tk.Text, notebook: ttk.Notebook, output_frame: tk.ttk.Frame) -> None:
        self.output_widget = output_widget
        self.current_process: subprocess.Popen | None = None
        self.is_running = False
        self.notebook = notebook
        self.output_frame = output_frame

    def run_command(self, cmd: list[str], callback: Callable[[int], None] | None = None) -> None:
        """Run a command in a separate thread."""
        if self.is_running:
            messagebox.showwarning("Warning", "A command is already running!")
            return

        self.is_running = True
        thread = threading.Thread(target=self._execute_command, args=(cmd, callback))
        thread.daemon = True
        thread.start()

    def _execute_command(self, cmd: list[str], callback: Callable[[int], None] | None) -> None:
        """Execute the command (runs in separate thread)."""
        try:
            # Clear output
            self.output_widget.after(0, lambda: self.output_widget.delete(1.0, tk.END))

            # Show command being executed
            self.output_widget.after(0, lambda: self.output_widget.insert(tk.END, f"Running: {' '.join(cmd)}\n\n"))

            self.notebook.select(self.output_frame)

            # Start process
            env = {}
            for key, value in os.environ.items():
                env[key] = value
            env["NO_COLOR"] = "1"
            self.current_process = subprocess.Popen(  # nosec
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                encoding="utf-8",
                bufsize=1,
                env=env,
            )

            # Read output line by line
            if self.current_process.stdout:
                for line in iter(self.current_process.stdout.readline, ""):
                    if not line:
                        break
                    self.output_widget.after(
                        0,
                        lambda insert_line=line: self.output_widget.insert(tk.END, insert_line),  # type: ignore
                    )
                    self.output_widget.after(0, lambda: self.output_widget.see(tk.END))  # type: ignore

            # Wait for completion
            return_code = self.current_process.wait()

            # Show completion status
            status_msg = f"\n{'=' * 50}\nCommand completed with exit code: {return_code}\n"
            self.output_widget.after(0, lambda: self.output_widget.insert(tk.END, status_msg))

            # Call callback if provided
            if callback:
                callback(return_code)

        except Exception as e:
            error_msg = f"Error running command: {str(e)}\n"
            self.output_widget.after(0, lambda: self.output_widget.insert(tk.END, error_msg))
        finally:
            self.is_running = False
            self.current_process = None

    def stop_command(self) -> None:
        """Stop the currently running command."""
        if self.current_process:
            try:
                self.current_process.terminate()
                self.output_widget.insert(tk.END, "\n\nCommand terminated by user.\n")
            except Exception as e:
                self.output_widget.insert(tk.END, f"\nError terminating command: {e}\n")


class Bash2GitlabGUI:
    """Main GUI application class."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("bash2gitlab GUI")
        self.root.geometry("1000x700")

        # Command runner
        self.command_runner: CommandRunner | None = None

        # Variables for form fields
        self.vars: dict[str, tk.Variable] = {}

        self.setup_gui()

    def setup_gui(self) -> None:
        """Set up the main GUI layout."""
        # Create notebook for tabs
        notebook = ttk.Notebook(self.root)
        self.notebook = notebook
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create tabs for different command categories
        self.create_compile_tab(notebook)
        self.create_decompile_tab(notebook)
        self.create_utilities_tab(notebook)
        self.create_lint_tab(notebook)
        self.create_git_tab(notebook)
        self.create_output_tab(notebook)

    def create_compile_tab(self, parent: ttk.Notebook) -> None:
        """Create the compile commands tab."""
        frame = ttk.Frame(parent)
        parent.add(frame, text="Compile & Clean")

        # Compile section
        compile_frame = ttk.LabelFrame(frame, text="Compile Project", padding=10)
        compile_frame.pack(fill=tk.X, padx=5, pady=5)

        # Input directory
        ttk.Label(compile_frame, text="Input Directory:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.vars["compile_input"] = tk.StringVar()
        input_entry = ttk.Entry(compile_frame, textvariable=self.vars["compile_input"], width=50)
        input_entry.grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(
            compile_frame, text="Browse", command=lambda: self.browse_directory(self.vars["compile_input"])
        ).grid(row=0, column=2, padx=5)

        # Output directory
        ttk.Label(compile_frame, text="Output Directory:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.vars["compile_output"] = tk.StringVar()
        output_entry = ttk.Entry(compile_frame, textvariable=self.vars["compile_output"], width=50)
        output_entry.grid(row=1, column=1, padx=5, pady=2)
        ttk.Button(
            compile_frame, text="Browse", command=lambda: self.browse_directory(self.vars["compile_output"])
        ).grid(row=1, column=2, padx=5)

        # Options
        options_frame = ttk.Frame(compile_frame)
        options_frame.grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=10)

        self.vars["compile_dry_run"] = tk.BooleanVar()
        ttk.Checkbutton(options_frame, text="Dry Run", variable=self.vars["compile_dry_run"]).pack(side=tk.LEFT, padx=5)

        self.vars["compile_watch"] = tk.BooleanVar()
        ttk.Checkbutton(options_frame, text="Watch Mode", variable=self.vars["compile_watch"]).pack(
            side=tk.LEFT, padx=5
        )

        self.vars["compile_verbose"] = tk.BooleanVar()
        ttk.Checkbutton(options_frame, text="Verbose", variable=self.vars["compile_verbose"]).pack(side=tk.LEFT, padx=5)

        # Parallelism
        ttk.Label(options_frame, text="Parallelism:").pack(side=tk.LEFT, padx=(20, 5))
        self.vars["compile_parallelism"] = tk.StringVar(value="4")
        ttk.Spinbox(options_frame, from_=1, to=16, width=5, textvariable=self.vars["compile_parallelism"]).pack(
            side=tk.LEFT
        )

        # Buttons
        button_frame = ttk.Frame(compile_frame)
        button_frame.grid(row=3, column=0, columnspan=3, pady=10)

        ttk.Button(button_frame, text="Compile", command=self.run_compile).pack(side=tk.LEFT, padx=5)

        # Clean section
        clean_frame = ttk.LabelFrame(frame, text="Clean Output", padding=10)
        clean_frame.pack(fill=tk.X, padx=5, pady=5)

        # Clean output directory
        ttk.Label(clean_frame, text="Output Directory:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.vars["clean_output"] = tk.StringVar()
        clean_entry = ttk.Entry(clean_frame, textvariable=self.vars["clean_output"], width=50)
        clean_entry.grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(clean_frame, text="Browse", command=lambda: self.browse_directory(self.vars["clean_output"])).grid(
            row=0, column=2, padx=5
        )

        # Clean options
        clean_options = ttk.Frame(clean_frame)
        clean_options.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=10)

        self.vars["clean_dry_run"] = tk.BooleanVar()
        ttk.Checkbutton(clean_options, text="Dry Run", variable=self.vars["clean_dry_run"]).pack(side=tk.LEFT, padx=5)

        ttk.Button(clean_options, text="Clean", command=self.run_clean).pack(side=tk.LEFT, padx=20)

    def create_decompile_tab(self, parent: ttk.Notebook) -> None:
        """Create the decompile commands tab."""
        frame = ttk.Frame(parent)
        parent.add(frame, text="Decompile")

        decompile_frame = ttk.LabelFrame(frame, text="Decompile GitLab CI YAML", padding=10)
        decompile_frame.pack(fill=tk.X, padx=5, pady=5)

        # Input type selection
        self.vars["decompile_input_type"] = tk.StringVar(value="file")

        input_type_frame = ttk.Frame(decompile_frame)
        input_type_frame.grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=5)

        ttk.Radiobutton(
            input_type_frame,
            text="Single File",
            variable=self.vars["decompile_input_type"],
            value="file",
            command=self.update_decompile_inputs,
        ).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(
            input_type_frame,
            text="Folder",
            variable=self.vars["decompile_input_type"],
            value="folder",
            command=self.update_decompile_inputs,
        ).pack(side=tk.LEFT, padx=5)

        # Input file
        ttk.Label(decompile_frame, text="Input File:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.vars["decompile_input_file"] = tk.StringVar()
        self.decompile_file_entry = ttk.Entry(decompile_frame, textvariable=self.vars["decompile_input_file"], width=50)
        self.decompile_file_entry.grid(row=1, column=1, padx=5, pady=2)
        self.decompile_file_btn = ttk.Button(
            decompile_frame, text="Browse", command=lambda: self.browse_file(self.vars["decompile_input_file"])
        )
        self.decompile_file_btn.grid(row=1, column=2, padx=5)

        # Input folder
        ttk.Label(decompile_frame, text="Input Folder:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.vars["decompile_input_folder"] = tk.StringVar()
        self.decompile_folder_entry = ttk.Entry(
            decompile_frame, textvariable=self.vars["decompile_input_folder"], width=50, state=tk.DISABLED
        )
        self.decompile_folder_entry.grid(row=2, column=1, padx=5, pady=2)
        self.decompile_folder_btn = ttk.Button(
            decompile_frame,
            text="Browse",
            state=tk.DISABLED,
            command=lambda: self.browse_directory(self.vars["decompile_input_folder"]),
        )
        self.decompile_folder_btn.grid(row=2, column=2, padx=5)

        # Output directory
        ttk.Label(decompile_frame, text="Output Directory:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.vars["decompile_output"] = tk.StringVar()
        ttk.Entry(decompile_frame, textvariable=self.vars["decompile_output"], width=50).grid(
            row=3, column=1, padx=5, pady=2
        )
        ttk.Button(
            decompile_frame, text="Browse", command=lambda: self.browse_directory(self.vars["decompile_output"])
        ).grid(row=3, column=2, padx=5)

        # Options
        decompile_options = ttk.Frame(decompile_frame)
        decompile_options.grid(row=4, column=0, columnspan=3, sticky=tk.W, pady=10)

        self.vars["decompile_dry_run"] = tk.BooleanVar()
        ttk.Checkbutton(decompile_options, text="Dry Run", variable=self.vars["decompile_dry_run"]).pack(
            side=tk.LEFT, padx=5
        )

        self.vars["decompile_verbose"] = tk.BooleanVar()
        ttk.Checkbutton(decompile_options, text="Verbose", variable=self.vars["decompile_verbose"]).pack(
            side=tk.LEFT, padx=5
        )

        ttk.Button(decompile_options, text="Decompile", command=self.run_decompile).pack(side=tk.LEFT, padx=20)

    def create_utilities_tab(self, parent: ttk.Notebook) -> None:
        """Create the utilities tab."""
        frame = ttk.Frame(parent)
        parent.add(frame, text="Utilities")

        # Init section
        init_frame = ttk.LabelFrame(frame, text="Initialize Project", padding=10)
        init_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(init_frame, text="Directory:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.vars["init_directory"] = tk.StringVar(value=".")
        ttk.Entry(init_frame, textvariable=self.vars["init_directory"], width=50).grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(init_frame, text="Browse", command=lambda: self.browse_directory(self.vars["init_directory"])).grid(
            row=0, column=2, padx=5
        )

        init_options = ttk.Frame(init_frame)
        init_options.grid(row=1, column=0, columnspan=3, pady=10)

        self.vars["init_dry_run"] = tk.BooleanVar()
        ttk.Checkbutton(init_options, text="Dry Run", variable=self.vars["init_dry_run"]).pack(side=tk.LEFT, padx=5)

        ttk.Button(init_options, text="Initialize", command=self.run_init).pack(side=tk.LEFT, padx=20)

        # Copy2Local section
        copy_frame = ttk.LabelFrame(frame, text="Copy Repository to Local", padding=10)
        copy_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(copy_frame, text="Repository URL:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.vars["copy_repo_url"] = tk.StringVar()
        ttk.Entry(copy_frame, textvariable=self.vars["copy_repo_url"], width=60).grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(copy_frame, text="Branch:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.vars["copy_branch"] = tk.StringVar(value="main")
        ttk.Entry(copy_frame, textvariable=self.vars["copy_branch"], width=60).grid(row=1, column=1, padx=5, pady=2)

        ttk.Label(copy_frame, text="Source Directory:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.vars["copy_source_dir"] = tk.StringVar()
        ttk.Entry(copy_frame, textvariable=self.vars["copy_source_dir"], width=60).grid(row=2, column=1, padx=5, pady=2)

        ttk.Label(copy_frame, text="Copy Directory:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.vars["copy_copy_dir"] = tk.StringVar()
        ttk.Entry(copy_frame, textvariable=self.vars["copy_copy_dir"], width=50).grid(row=3, column=1, padx=5, pady=2)
        ttk.Button(copy_frame, text="Browse", command=lambda: self.browse_directory(self.vars["copy_copy_dir"])).grid(
            row=3, column=2, padx=5
        )

        copy_options = ttk.Frame(copy_frame)
        copy_options.grid(row=4, column=0, columnspan=3, pady=10)

        self.vars["copy_dry_run"] = tk.BooleanVar()
        ttk.Checkbutton(copy_options, text="Dry Run", variable=self.vars["copy_dry_run"]).pack(side=tk.LEFT, padx=5)

        ttk.Button(copy_options, text="Copy to Local", command=self.run_copy2local).pack(side=tk.LEFT, padx=20)

        # Detect Drift section
        drift_frame = ttk.LabelFrame(frame, text="Detect Drift", padding=10)
        drift_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(drift_frame, text="Output Directory:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.vars["drift_output"] = tk.StringVar()
        ttk.Entry(drift_frame, textvariable=self.vars["drift_output"], width=50).grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(drift_frame, text="Browse", command=lambda: self.browse_directory(self.vars["drift_output"])).grid(
            row=0, column=2, padx=5
        )

        ttk.Button(drift_frame, text="Detect Drift", command=self.run_detect_drift).grid(
            row=1, column=0, columnspan=3, pady=10
        )

    def create_lint_tab(self, parent: ttk.Notebook) -> None:
        """Create the lint tab."""
        frame = ttk.Frame(parent)
        parent.add(frame, text="Lint")

        lint_frame = ttk.LabelFrame(frame, text="GitLab CI Lint", padding=10)
        lint_frame.pack(fill=tk.X, padx=5, pady=5)

        # Output directory
        ttk.Label(lint_frame, text="Output Directory:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.vars["lint_output"] = tk.StringVar()
        ttk.Entry(lint_frame, textvariable=self.vars["lint_output"], width=50).grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(lint_frame, text="Browse", command=lambda: self.browse_directory(self.vars["lint_output"])).grid(
            row=0, column=2, padx=5
        )

        # GitLab URL
        ttk.Label(lint_frame, text="GitLab URL:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.vars["lint_gitlab_url"] = tk.StringVar(value="https://gitlab.com")
        ttk.Entry(lint_frame, textvariable=self.vars["lint_gitlab_url"], width=50).grid(row=1, column=1, padx=5, pady=2)

        # Token
        ttk.Label(lint_frame, text="Token:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.vars["lint_token"] = tk.StringVar()
        token_entry = ttk.Entry(lint_frame, textvariable=self.vars["lint_token"], width=50, show="*")
        token_entry.grid(row=2, column=1, padx=5, pady=2)

        # Project ID
        ttk.Label(lint_frame, text="Project ID:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.vars["lint_project_id"] = tk.StringVar()
        ttk.Entry(lint_frame, textvariable=self.vars["lint_project_id"], width=50).grid(row=3, column=1, padx=5, pady=2)

        # Ref
        ttk.Label(lint_frame, text="Git Ref:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.vars["lint_ref"] = tk.StringVar(value="main")
        ttk.Entry(lint_frame, textvariable=self.vars["lint_ref"], width=50).grid(row=4, column=1, padx=5, pady=2)

        # Options
        lint_options_frame = ttk.Frame(lint_frame)
        lint_options_frame.grid(row=5, column=0, columnspan=3, sticky=tk.W, pady=10)

        self.vars["lint_include_merged"] = tk.BooleanVar()
        ttk.Checkbutton(lint_options_frame, text="Include Merged YAML", variable=self.vars["lint_include_merged"]).pack(
            side=tk.LEFT, padx=5
        )

        self.vars["lint_verbose"] = tk.BooleanVar()
        ttk.Checkbutton(lint_options_frame, text="Verbose", variable=self.vars["lint_verbose"]).pack(
            side=tk.LEFT, padx=5
        )

        # Parallelism and timeout
        params_frame = ttk.Frame(lint_frame)
        params_frame.grid(row=6, column=0, columnspan=3, sticky=tk.W, pady=5)

        ttk.Label(params_frame, text="Parallelism:").pack(side=tk.LEFT, padx=5)
        self.vars["lint_parallelism"] = tk.StringVar(value="4")
        ttk.Spinbox(params_frame, from_=1, to=16, width=5, textvariable=self.vars["lint_parallelism"]).pack(
            side=tk.LEFT, padx=5
        )

        ttk.Label(params_frame, text="Timeout (s):").pack(side=tk.LEFT, padx=(20, 5))
        self.vars["lint_timeout"] = tk.StringVar(value="20")
        ttk.Entry(params_frame, textvariable=self.vars["lint_timeout"], width=8).pack(side=tk.LEFT, padx=5)

        ttk.Button(lint_frame, text="Lint", command=self.run_lint).grid(row=7, column=0, columnspan=3, pady=10)

    def create_git_tab(self, parent: ttk.Notebook) -> None:
        """Create the Git hooks tab."""
        frame = ttk.Frame(parent)
        parent.add(frame, text="Git Hooks")

        # Pre-commit hooks section
        precommit_frame = ttk.LabelFrame(frame, text="Pre-commit Hooks", padding=10)
        precommit_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(precommit_frame, text="Repository Root:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.vars["git_repo_root"] = tk.StringVar(value=".")
        ttk.Entry(precommit_frame, textvariable=self.vars["git_repo_root"], width=50).grid(
            row=0, column=1, padx=5, pady=2
        )
        ttk.Button(
            precommit_frame, text="Browse", command=lambda: self.browse_directory(self.vars["git_repo_root"])
        ).grid(row=0, column=2, padx=5)

        git_options = ttk.Frame(precommit_frame)
        git_options.grid(row=1, column=0, columnspan=3, pady=10)

        self.vars["git_force"] = tk.BooleanVar()
        ttk.Checkbutton(git_options, text="Force", variable=self.vars["git_force"]).pack(side=tk.LEFT, padx=5)

        ttk.Button(git_options, text="Install Pre-commit Hook", command=self.run_install_precommit).pack(
            side=tk.LEFT, padx=10
        )
        ttk.Button(git_options, text="Uninstall Pre-commit Hook", command=self.run_uninstall_precommit).pack(
            side=tk.LEFT, padx=10
        )

        # Map commands section
        map_frame = ttk.LabelFrame(frame, text="Directory Mapping", padding=10)
        map_frame.pack(fill=tk.X, padx=5, pady=5)

        map_options = ttk.Frame(map_frame)
        map_options.grid(row=0, column=0, columnspan=3, pady=10)

        self.vars["map_force"] = tk.BooleanVar()
        ttk.Checkbutton(map_options, text="Force", variable=self.vars["map_force"]).pack(side=tk.LEFT, padx=5)

        self.vars["map_dry_run"] = tk.BooleanVar()
        ttk.Checkbutton(map_options, text="Dry Run", variable=self.vars["map_dry_run"]).pack(side=tk.LEFT, padx=5)

        ttk.Button(map_options, text="Deploy Mapping", command=self.run_map_deploy).pack(side=tk.LEFT, padx=10)
        ttk.Button(map_options, text="Commit Mapping", command=self.run_commit_map).pack(side=tk.LEFT, padx=10)

        # Other utilities
        other_frame = ttk.LabelFrame(frame, text="Other Commands", padding=10)
        other_frame.pack(fill=tk.X, padx=5, pady=5)

        other_buttons = ttk.Frame(other_frame)
        other_buttons.pack(pady=10)

        ttk.Button(other_buttons, text="Doctor (Health Check)", command=self.run_doctor).pack(side=tk.LEFT, padx=10)
        ttk.Button(other_buttons, text="Show Config", command=self.run_show_config).pack(side=tk.LEFT, padx=10)

    def create_output_tab(self, parent: ttk.Notebook) -> None:
        """Create the output/console tab."""
        self.output_frame = ttk.Frame(parent)
        parent.add(self.output_frame, text="Console Output")

        # Output area
        output_frame = ttk.LabelFrame(self.output_frame, text="Command Output", padding=5)
        output_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.output_text = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD, height=25, font=("Courier", 10))
        self.output_text.pack(fill=tk.BOTH, expand=True)

        # Control buttons
        control_frame = ttk.Frame(self.output_frame)
        control_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(control_frame, text="Clear Output", command=self.clear_output).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Stop Command", command=self.stop_command).pack(side=tk.LEFT, padx=5)

        # Initialize command runner
        self.command_runner = CommandRunner(self.output_text, self.notebook, self.output_frame)

    def update_decompile_inputs(self) -> None:
        """Update decompile input fields based on selection."""
        input_type = self.vars["decompile_input_type"].get()

        if input_type == "file":
            self.decompile_file_entry.config(state=tk.NORMAL)
            self.decompile_file_btn.config(state=tk.NORMAL)
            self.decompile_folder_entry.config(state=tk.DISABLED)
            self.decompile_folder_btn.config(state=tk.DISABLED)
        else:
            self.decompile_file_entry.config(state=tk.DISABLED)
            self.decompile_file_btn.config(state=tk.DISABLED)
            self.decompile_folder_entry.config(state=tk.NORMAL)
            self.decompile_folder_btn.config(state=tk.NORMAL)

    def browse_directory(self, var: tk.StringVar | tk.Variable) -> None:
        """Browse for a directory and set the variable."""
        directory = filedialog.askdirectory()
        if directory:
            var.set(directory)

    def browse_file(self, var: tk.StringVar | tk.Variable, filetypes: list[tuple[str, str]] | None = None) -> None:
        """Browse for a file and set the variable."""
        if filetypes is None:
            filetypes = [("YAML files", "*.yml *.yaml"), ("All files", "*.*")]

        filename = filedialog.askopenfilename(filetypes=filetypes)
        if filename:
            var.set(filename)

    def clear_output(self) -> None:
        """Clear the output text area."""
        self.output_text.delete(1.0, tk.END)

    def stop_command(self) -> None:
        """Stop the currently running command."""
        if self.command_runner:
            self.command_runner.stop_command()

    def build_command(self, base_cmd: str, options: dict[str, Any]) -> list[str]:
        """Build a bash2gitlab command with the given options."""
        cmd = ["bash2gitlab", base_cmd]

        for key, value in options.items():
            if key.startswith("_"):  # Skip internal variables
                continue

            if isinstance(value, bool):
                if value:
                    cmd.append(f"--{key.replace('_', '-')}")
            elif isinstance(value, str) and value.strip():
                cmd.extend([f"--{key.replace('_', '-')}", value.strip()])
            elif isinstance(value, (int, float)) and value != 0:
                cmd.extend([f"--{key.replace('_', '-')}", str(value)])

        return cmd

    def run_compile(self) -> None:
        """Run the compile command."""
        if not self.command_runner:
            messagebox.showerror("Error", "Command runner not initialized!")
            return

        options = {
            "in": self.vars["compile_input"].get(),
            "out": self.vars["compile_output"].get(),
            "parallelism": self.vars["compile_parallelism"].get(),
            "dry_run": self.vars["compile_dry_run"].get(),
            "watch": self.vars["compile_watch"].get(),
            "verbose": self.vars["compile_verbose"].get(),
        }

        # Validate required fields
        if not options["in"]:
            messagebox.showerror("Error", "Input directory is required!")
            return
        if not options["out"]:
            messagebox.showerror("Error", "Output directory is required!")
            return

        cmd = self.build_command("compile", options)
        self.command_runner.run_command(cmd)

    def run_clean(self) -> None:
        """Run the clean command."""
        if not self.command_runner:
            return

        options = {
            "out": self.vars["clean_output"].get(),
            "dry_run": self.vars["clean_dry_run"].get(),
        }

        if not options["out"]:
            messagebox.showerror("Error", "Output directory is required!")
            return

        cmd = self.build_command("clean", options)
        self.command_runner.run_command(cmd)

    def run_decompile(self) -> None:
        """Run the decompile command."""
        if not self.command_runner:
            return

        input_type = self.vars["decompile_input_type"].get()

        options = {
            "out": self.vars["decompile_output"].get(),
            "dry_run": self.vars["decompile_dry_run"].get(),
            "verbose": self.vars["decompile_verbose"].get(),
        }

        if input_type == "file":
            options["in_file"] = self.vars["decompile_input_file"].get()
            if not options["in_file"]:
                messagebox.showerror("Error", "Input file is required!")
                return
        else:
            options["in_folder"] = self.vars["decompile_input_folder"].get()
            if not options["in_folder"]:
                messagebox.showerror("Error", "Input folder is required!")
                return

        if not options["out"]:
            messagebox.showerror("Error", "Output directory is required!")
            return

        cmd = self.build_command("decompile", options)
        self.command_runner.run_command(cmd)

    def run_init(self) -> None:
        """Run the init command."""
        if not self.command_runner:
            return

        directory = self.vars["init_directory"].get() or "."
        cmd = ["bash2gitlab", "init", directory]

        if self.vars["init_dry_run"].get():
            cmd.append("--dry-run")

        self.command_runner.run_command(cmd)

    def run_copy2local(self) -> None:
        """Run the copy2local command."""
        if not self.command_runner:
            return

        options = {
            "repo_url": self.vars["copy_repo_url"].get(),
            "branch": self.vars["copy_branch"].get(),
            "source_dir": self.vars["copy_source_dir"].get(),
            "copy_dir": self.vars["copy_copy_dir"].get(),
            "dry_run": self.vars["copy_dry_run"].get(),
        }

        # Validate required fields
        required_fields = ["repo_url", "branch", "source_dir", "copy_dir"]
        for field in required_fields:
            if not options[field]:
                messagebox.showerror("Error", f"{field.replace('_', ' ').title()} is required!")
                return

        cmd = self.build_command("copy2local", options)
        self.command_runner.run_command(cmd)

    def run_detect_drift(self) -> None:
        """Run the detect-drift command."""
        if not self.command_runner:
            return

        output_dir = self.vars["drift_output"].get()
        if not output_dir:
            messagebox.showerror("Error", "Output directory is required!")
            return

        cmd = ["bash2gitlab", "detect-drift", "--out", output_dir]
        self.command_runner.run_command(cmd)

    def run_lint(self) -> None:
        """Run the lint command."""
        if not self.command_runner:
            return

        options = {
            "out": self.vars["lint_output"].get(),
            "gitlab_url": self.vars["lint_gitlab_url"].get(),
            "token": self.vars["lint_token"].get(),
            "project_id": self.vars["lint_project_id"].get(),
            "ref": self.vars["lint_ref"].get(),
            "include_merged_yaml": self.vars["lint_include_merged"].get(),
            "parallelism": self.vars["lint_parallelism"].get(),
            "timeout": self.vars["lint_timeout"].get(),
            "verbose": self.vars["lint_verbose"].get(),
        }

        # Validate required fields
        if not options["out"]:
            messagebox.showerror("Error", "Output directory is required!")
            return
        if not options["gitlab_url"]:
            messagebox.showerror("Error", "GitLab URL is required!")
            return

        cmd = self.build_command("lint", options)
        self.command_runner.run_command(cmd)

    def run_install_precommit(self) -> None:
        """Run the install-precommit command."""
        if not self.command_runner:
            return

        options = {
            "repo_root": self.vars["git_repo_root"].get(),
            "force": self.vars["git_force"].get(),
        }

        cmd = self.build_command("install-precommit", options)
        self.command_runner.run_command(cmd)

    def run_uninstall_precommit(self) -> None:
        """Run the uninstall-precommit command."""
        if not self.command_runner:
            return

        options = {
            "repo_root": self.vars["git_repo_root"].get(),
            "force": self.vars["git_force"].get(),
        }

        cmd = self.build_command("uninstall-precommit", options)
        self.command_runner.run_command(cmd)

    def run_map_deploy(self) -> None:
        """Run the map-deploy command."""
        if not self.command_runner:
            return

        options = {
            "force": self.vars["map_force"].get(),
            "dry_run": self.vars["map_dry_run"].get(),
        }

        cmd = self.build_command("map-deploy", options)
        self.command_runner.run_command(cmd)

    def run_commit_map(self) -> None:
        """Run the commit-map command."""
        if not self.command_runner:
            return

        options = {
            "force": self.vars["map_force"].get(),
            "dry_run": self.vars["map_dry_run"].get(),
        }

        cmd = self.build_command("commit-map", options)
        self.command_runner.run_command(cmd)

    def run_doctor(self) -> None:
        """Run the doctor command."""
        if not self.command_runner:
            return

        cmd = ["bash2gitlab", "doctor"]
        self.command_runner.run_command(cmd)

    def run_show_config(self) -> None:
        """Run the show-config command."""
        if not self.command_runner:
            return

        cmd = ["bash2gitlab", "show-config"]
        self.command_runner.run_command(cmd)


def main() -> None:
    """Main entry point for the GUI application."""
    # Create the main window
    root = tk.Tk()

    # Configure the application
    Bash2GitlabGUI(root)

    # Set up logging to show errors in console
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    try:
        # Start the main loop
        root.mainloop()
    except KeyboardInterrupt:
        logging.info("Application interrupted by user")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        messagebox.showerror("Fatal Error", f"An unexpected error occurred:\n{e}")


if __name__ == "__main__":
    main()
```
## File: hookspecs.py
```python
"""
Hooks, mainly with an eye to allowing supporting inlining other scripting languages.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pluggy

hookspec = pluggy.HookspecMarker("bash2gitlab")


@hookspec(firstresult=True)
def extract_script_path(line: str) -> str | None:
    """Return a path-like string if this line is a ‘run this script’ line."""


@hookspec(firstresult=True)
def inline_command(line: str, scripts_root: Path) -> list[str] | None:
    """Return a list of lines to inline in place of this command, or None."""


@hookspec
def yaml_before_dump(doc: Any, *, path: Path | None = None) -> Any:
    """Given a YAML doc right before dump, return replacement or None."""


@hookspec
def watch_file_extensions() -> Iterable[str]:
    return []


@hookspec
def register_cli(subparsers, config) -> None: ...


@hookspec
def before_command(args: argparse.Namespace) -> None:
    """
    Called right before dispatching a subcommand.
    May mutate `args` (e.g., add defaults), but must not return anything.
    """


@hookspec
def after_command(result: int, args: argparse.Namespace) -> None:
    """
    Called after the command handler returns. Read-only by convention.
    Use for logging/metrics/teardown. No return.
    """
```
## File: install_help.py
```python
from bash2gitlab import __about__
from bash2gitlab.utils.check_interactive import detect_environment

APP = __about__.__title__
HELP = f"""
To unlock the *full* experience of this {APP}, you should install the [all] extra.
By default, `pip install {APP}` only gives you the minimal core.

Here are the most common ways to install `{APP}[all]`:

─────────────────────────────
Command line (pip):
─────────────────────────────
    pip install "{APP}[all]"
    pip install "{APP}[all]" --upgrade
    python -m pip install "{APP}[all]"

─────────────────────────────
Command line (uv / pipx / poetry run):
─────────────────────────────
    uv pip install "{APP}[all]"
    pipx install "{APP}[all]"
    pipx install {APP} --pip-args='.[all]'
    poetry run pip install "{APP}[all]"

─────────────────────────────
requirements.txt:
─────────────────────────────
Add one of these lines:
    {APP}[all]
    {APP}[all]==1.2.3        # pin a version
    {APP}[all]>=1.2.0,<2.0   # version range

─────────────────────────────
pyproject.toml (PEP 621 / Poetry / Hatch / uv):
─────────────────────────────
[tool.poetry.dependencies]
{APP} = {{ version = "1.2.3", extras = ["all"] }}

# or for PEP 621 (uv, hatchling, setuptools):
[project]
dependencies = [
    "{APP}[all]>=1.2.3",
]

─────────────────────────────
setup.cfg (setuptools):
─────────────────────────────
[options]
install_requires =
    {APP}[all]

─────────────────────────────
environment.yml (conda/mamba):
─────────────────────────────
dependencies:
  - pip
  - pip:
      - {APP}[all]

─────────────────────────────
Other notes:
─────────────────────────────
- Quoting is sometimes required: "{APP}[all]"
- If you already installed core, run: pip install --upgrade "{APP}[all]"
- Wheels/conda may not provide all extras; fall back to pip if needed.

Summary:
▶ Default install = minimal.
▶ `{APP}[all]` = full, recommended.
"""


def print_install_help():
    if detect_environment() == "interactive":
        print(HELP)
```
## File: interactive.py
```python
"""
Rich-based interactive Q&A interface for bash2gitlab.

This module provides an interactive command-line interface using Rich library
for a more user-friendly experience with bash2gitlab commands.
"""

from __future__ import annotations

import sys
from typing import Any

from rich import box
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
            clone2local_handler,
            commit_map_handler,
            compile_handler,
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
            "copy2local": clone2local_handler,
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
```
## File: plugins.py
```python
import os

import pluggy

from bash2gitlab import hookspecs

_pm = None


def get_pm() -> pluggy.PluginManager:
    global _pm
    if _pm is None:
        _pm = pluggy.PluginManager("bash2gitlab")
        _pm.add_hookspecs(hookspecs)
        # Builtins keep current behavior:
        from bash2gitlab.builtin_plugins import Defaults

        _pm.register(Defaults())
        # Third-party:
        if not os.environ.get("BASH2GITLAB_NO_PLUGINS"):
            _pm.load_setuptools_entrypoints("bash2gitlab")
    return _pm


def call_seq(func_name: str, value, **kwargs):
    """Apply all hook returns in sequence (for yaml_*)."""
    pm = get_pm()
    results = getattr(pm.hook, func_name)(value, **kwargs)
    for r in results:
        if r is not None:
            value = r
    return value
```
## File: py.typed
```
# when type checking dependents, tell type checkers to use this package's types
```
## File: tui.py
```python
#!/usr/bin/env python3
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

from textual import on, work
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
from bash2gitlab.plugins import get_pm

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
        exts = {".yml", ".yaml", ".sh", ".bash"}
        for extra in get_pm().hook.watch_file_extensions():
            if extra:
                exts.update(extra)
        if not event.src_path.endswith(tuple(exts)):  # type: ignore[arg-type]
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
__version__ = "0.9.0"
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
                   {compile,decompile,detect-drift,copy2local,init,map-deploy,commit-map,clean,lint,install-precommit,uninstall-precommit}
                   ...

A tool for making development of centralized yaml gitlab templates more pleasant.

positional arguments:
  {compile,decompile,detect-drift,copy2local,init,map-deploy,commit-map,clean,lint,install-precommit,uninstall-precommit}
    compile               Compile an uncompiled directory into a standard GitLab CI structure.
    decompile                 Decompile a GitLab CI file, extracting inline scripts into separate .sh files.
    detect-drift          Detect if generated files have been edited and display what the edits are.
    copy2local            Copy folder(s) from a repo to local, for testing bash in the dependent repo
    init                  Initialize a new bash2gitlab project and config file.
    map-deploy            Deploy files from source to target directories based on a mapping in pyproject.toml.
    commit-map            Copy changed files from deployed directories back to their source locations based on a mapping in pyproject.toml.
    clean                 Clean output folder, removing only unmodified files previously written by bash2gitlab.
    lint                  Validate compiled GitLab CI YAML against a GitLab instance (global or project-scoped CI Lint).
    install-precommit     Install a Git pre-commit hook that runs `bash2gitlab compile` (honors core.hooksPath/worktrees).
    uninstall-precommit   Remove the bash2gitlab pre-commit hook.

options:
  -h, --help              show this help message and exit
  --version               show program's version number and exit
"""

from __future__ import annotations

import argparse
import logging
import logging.config
import os
import sys
from pathlib import Path
from urllib import error as _urlerror

from bash2gitlab.commands.best_effort_runner import best_efforts_run
from bash2gitlab.install_help import print_install_help
from bash2gitlab.utils.check_interactive import detect_environment

try:
    import argcomplete
except ModuleNotFoundError:
    argcomplete = None  # type: ignore[assignment]

from bash2gitlab import __about__
from bash2gitlab import __doc__ as root_doc
from bash2gitlab.commands.clean_all import clean_targets
from bash2gitlab.commands.clone2local import clone_repository_ssh, fetch_repository_archive
from bash2gitlab.commands.compile_all import run_compile_all
from bash2gitlab.commands.decompile_all import run_decompile_gitlab_file, run_decompile_gitlab_tree
from bash2gitlab.commands.detect_drift import run_detect_drift
from bash2gitlab.commands.doctor import run_doctor
from bash2gitlab.commands.graph_all import generate_dependency_graph
from bash2gitlab.commands.init_project import run_init
from bash2gitlab.commands.lint_all import lint_output_folder, summarize_results
from bash2gitlab.commands.map_commit import run_commit_map
from bash2gitlab.commands.map_deploy import run_map_deploy
from bash2gitlab.commands.precommit import PrecommitHookError, install, uninstall
from bash2gitlab.commands.show_config import run_show_config
from bash2gitlab.config import config
from bash2gitlab.plugins import get_pm
from bash2gitlab.utils.cli_suggestions import SmartParser
from bash2gitlab.utils.logging_config import generate_config
from bash2gitlab.utils.update_checker import check_for_updates
from bash2gitlab.watch_files import start_watch

# emoji support
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

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

    _ok, fail = summarize_results(results)
    return 0 if fail == 0 else 2


def init_handler(args: argparse.Namespace) -> int:
    """Handles the `init` command logic."""
    logger.info("Starting interactive project initializer...")
    directory = args.directory
    force = args.force
    try:
        run_init(directory, force)
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
    force = bool(args.force)
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
            uncompiled_path=in_dir, output_path=out_dir, dry_run=dry_run, parallelism=parallelism, force=force
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
    """Handler for the 'detect-drift' command."""
    run_detect_drift(Path(args.out))
    return 0


def decompile_handler(args: argparse.Namespace) -> int:
    """Handler for the 'decompile' command (file *or* folder)."""
    logger.info("Starting bash2gitlab decompiler...")

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)  # force folder semantics

    dry_run = bool(args.dry_run)

    try:
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
    except FileNotFoundError as e:
        logger.error("❌ An error occurred: %s", e)
        return 10


def commit_map_handler(args: argparse.Namespace) -> int:
    """Handler for the 'commit-map' command."""
    try:
        mapping = config.map_folders
    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        return 10
    except KeyError as ke:
        logger.error(f"❌ {ke}")
        return 11

    run_commit_map(mapping, dry_run=args.dry_run, force=args.force)
    return 0


def map_deploy_handler(args: argparse.Namespace) -> int:
    """Handler for the 'map-deploy' command."""
    try:
        mapping = config.map_folders
    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        return 10
    except KeyError as ke:
        logger.error(f"❌ {ke}")
        return 11

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
        return 199


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
        return 200


def doctor_handler(args: argparse.Namespace) -> int:
    """Handler for the 'doctor' command."""
    # The run_doctor function already prints messages and returns an exit code.
    return run_doctor()


def graph_handler(args: argparse.Namespace) -> int:
    """Handler for the 'graph' command."""
    in_dir = Path(args.input_dir).resolve()
    if not in_dir.is_dir():
        logger.error(f"Input directory does not exist or is not a directory: {in_dir}")
        return 10

    dot_output = generate_dependency_graph(in_dir)
    if dot_output:
        print(dot_output)
        return 0
    else:
        logger.warning("No graph data generated. Check input directory and file structure.")
        return 1


def show_config_handler(args: argparse.Namespace) -> int:
    """Handler for the 'show-config' command."""
    # The run_show_config function already prints messages and returns an exit code.
    return run_show_config()


def best_efforts_run_handler(args: argparse.Namespace) -> int:
    """Handler for the 'run' command."""

    return best_efforts_run(Path(args.in_file))


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Add shared CLI flags to a subparser."""
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the command without filesystem changes.",
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose (DEBUG) logging output.")
    parser.add_argument("-q", "--quiet", action="store_true", help="Disable output.")


def main() -> int:
    """Main CLI entry point."""
    if (
        argcomplete is None
        and detect_environment == "interactive"
        and not os.environ.get("BASH2GITLAB_HIDE_CORE_ALL_HELP")
    ):
        print_install_help()

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
    parser.add_argument("--force", action="store_true", help="Force compilation even if no input changes detected")
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
        required=not bool(config.compile_output_dir),
        help="Output directory for the compiled GitLab CI files.",
    )
    add_common_arguments(clean_parser)
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

    decompile_parser.set_defaults(func=decompile_handler)

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
    copy2local_parser.set_defaults(func=clone2local_handler)

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
    run_parser.set_defaults(func=best_efforts_run_handler)

    get_pm().hook.register_cli(subparsers=subparsers, config=config)

    if argcomplete:
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
    elif args.command == "graph":
        # Only merge --out from config; GitLab connection is explicit via CLI
        args.input_dir = args.input_dir or config.input_dir
        if not args.input_dir:
            lint_parser.error("argument --in is required")
    # install-precommit / uninstall-precommit / doctor / graph / show-config do not merge config

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

    for _ in get_pm().hook.before_command(args=args):
        pass
    # Execute the appropriate handler
    rc = args.func(args)
    for _ in get_pm().hook.after_command(result=rc, args=args):
        pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
```
## File: commands\best_effort_runner.py
```python
"""
Super limited local pipeline runner.
"""

from __future__ import annotations

import os
import re
import subprocess  # nosec
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union

from ruamel.yaml import YAML

BASE_ENV = os.environ.copy()


def merge_env(env=None):
    """
    Merge os.environ and an env dict into a new dict.
    Values from env override os.environ on conflict.

    Args:
        env: Optional dict of environment variables.

    Returns:
        A merged dict suitable for subprocess calls.
    """
    if env:
        return {**BASE_ENV, **env}
    return BASE_ENV


# ANSI color codes
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

# Disable colors if NO_COLOR is set
if os.getenv("NO_COLOR"):
    GREEN = RED = RESET = ""


def run_colored(script: str, env=None, cwd=None) -> int:
    env = merge_env(env)

    # Disable colors if NO_COLOR is set
    if os.getenv("NO_COLOR"):
        g, r, reset = "", "", ""
    else:
        g, r, reset = GREEN, RED, RESET
    if os.name == "nt":
        bash = r"C:\Program Files\Git\bin\bash.exe"
    else:
        bash = "bash"
    process = subprocess.Popen(  # nosec
        # , "-l"  # -l loads .bashrc and make it really, really slow.
        [bash],  # bash reads script from stdin
        env=env,
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,  # to prevent \r
        bufsize=1,  # line-buffered
    )

    def stream(pipe, color, target):
        for line in iter(pipe.readline, ""):  # text mode here, so sentinel is ""
            if not line:
                break
            target.write(f"{color}{line}{reset}")
            target.flush()
        pipe.close()

    # Start threads to stream stdout and stderr in parallel
    threads = [
        threading.Thread(target=stream, args=(process.stdout, g, sys.stdout)),
        threading.Thread(target=stream, args=(process.stderr, r, sys.stderr)),
    ]
    for t in threads:
        t.start()

    # Feed the script and close stdin

    if os.name == "nt":
        script = script.replace("\r\n", "\n")

    if process.stdin:
        process.stdin.write(script)
        process.stdin.close()

    # Wait for process to finish
    process.wait()
    for t in threads:
        t.join()

    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, script)

    return process.returncode


@dataclass
class JobConfig:
    """Configuration for a single job."""

    name: str
    stage: str = "test"
    script: list[str] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)
    before_script: list[str] = field(default_factory=list)
    after_script: list[str] = field(default_factory=list)


@dataclass
class DefaultConfig:
    """Default configuration that can be inherited by jobs."""

    before_script: list[str] = field(default_factory=list)
    after_script: list[str] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)


@dataclass
class PipelineConfig:
    """Complete pipeline configuration."""

    stages: list[str] = field(default_factory=lambda: ["test"])
    variables: dict[str, str] = field(default_factory=dict)
    default: DefaultConfig = field(default_factory=DefaultConfig)
    jobs: list[JobConfig] = field(default_factory=list)


class GitLabCIError(Exception):
    """Base exception for GitLab CI runner errors."""


class JobExecutionError(GitLabCIError):
    """Raised when a job fails to execute successfully."""


class ConfigurationLoader:
    """Loads and processes GitLab CI configuration files."""

    def __init__(self, base_path: Path | None = None):
        if not base_path:
            self.base_path = Path.cwd()
        else:
            self.base_path = base_path
        self.yaml = YAML(typ="safe")

    def load_config(self, config_path: Path | None = None) -> dict[str, Any]:
        """Load the main configuration file and process includes."""
        if config_path is None:
            config_path = self.base_path / ".gitlab-ci.yml"

        if not config_path.exists():
            raise GitLabCIError(f"Configuration file not found: {config_path}")

        config = self._load_yaml_file(config_path)
        config = self._process_includes(config, config_path.parent)

        return config

    def _load_yaml_file(self, file_path: Path) -> dict[str, Any]:
        """Load a single YAML file."""
        try:
            with open(file_path) as f:
                return self.yaml.load(f) or {}
        except Exception as e:
            raise GitLabCIError(f"Failed to load YAML file {file_path}: {e}") from e

    def _process_includes(self, config: dict[str, Any], base_dir: Path) -> dict[str, Any]:
        """Process include directives for local files only."""
        includes = config.pop("include", [])
        if not includes:
            return config

        if isinstance(includes, (str, dict)):
            includes = [includes]

        for include_item in includes:
            if isinstance(include_item, str):
                # Simple local file include
                include_path = base_dir / include_item
                included_config = self._load_yaml_file(include_path)
                config = self._merge_configs(config, included_config)
            elif isinstance(include_item, dict) and "local" in include_item:
                # Local file with explicit local key
                include_path = base_dir / include_item["local"]
                included_config = self._load_yaml_file(include_path)
                config = self._merge_configs(config, included_config)

        return config

    def _merge_configs(self, base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
        """Merge two configuration dictionaries."""
        result = base.copy()
        for key, value in overlay.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        return result


class PipelineProcessor:
    """Processes raw configuration into structured pipeline configuration."""

    RESERVED_KEYWORDS = {
        "stages",
        "variables",
        "default",
        "include",
        "image",
        "services",
        "before_script",
        "after_script",
        "cache",
        "artifacts",
    }

    def process_config(self, raw_config: dict[str, Any]) -> PipelineConfig:
        """Process raw configuration into structured pipeline config."""
        # Extract global configuration
        stages = raw_config.get("stages", ["test"])
        global_variables = raw_config.get("variables", {})
        default_config = self._process_default_config(raw_config.get("default", {}))

        # Process jobs
        jobs = []
        for name, job_data in raw_config.items():
            if name not in self.RESERVED_KEYWORDS and isinstance(job_data, dict):
                job = self._process_job(name, job_data, default_config, global_variables)
                jobs.append(job)

        return PipelineConfig(stages=stages, variables=global_variables, default=default_config, jobs=jobs)

    def _process_default_config(self, default_data: dict[str, Any]) -> DefaultConfig:
        """Process default configuration block."""
        return DefaultConfig(
            before_script=self._ensure_list(default_data.get("before_script", [])),
            after_script=self._ensure_list(default_data.get("after_script", [])),
            variables=default_data.get("variables", {}),
        )

    def _process_job(
        self, name: str, job_data: dict[str, Any], default: DefaultConfig, global_vars: dict[str, str]
    ) -> JobConfig:
        """Process a single job configuration."""
        # Merge variables with precedence: job > global > default
        variables = {}
        variables.update(default.variables)
        variables.update(global_vars)
        variables.update(job_data.get("variables", {}))

        # Merge scripts with default
        before_script = default.before_script + self._ensure_list(job_data.get("before_script", []))
        after_script = self._ensure_list(job_data.get("after_script", [])) + default.after_script

        return JobConfig(
            name=name,
            stage=job_data.get("stage", "test"),
            script=self._ensure_list(job_data.get("script", [])),
            variables=variables,
            before_script=before_script,
            after_script=after_script,
        )

    def _ensure_list(self, value: Union[str, list[str]]) -> list[str]:
        """Ensure a value is a list of strings."""
        if isinstance(value, str):
            return [value]
        elif isinstance(value, list):
            return value
        return []


class VariableManager:
    """Manages variable substitution and environment preparation."""

    def __init__(self, base_variables: dict[str, str] | None = None):
        self.base_variables = base_variables or {}
        self.gitlab_ci_vars = self._get_gitlab_ci_variables()

    def _get_gitlab_ci_variables(self) -> dict[str, str]:
        """Get GitLab CI built-in variables that we can simulate."""
        return {
            "CI": "true",
            "CI_PROJECT_DIR": str(Path.cwd()),
            "CI_PROJECT_NAME": Path.cwd().name,
            "CI_JOB_STAGE": "",  # Will be set per job
        }

    def prepare_environment(self, job: JobConfig) -> dict[str, str]:
        """Prepare environment variables for job execution."""
        env = os.environ.copy()

        # Apply variables in order: built-in -> base -> job
        env.update(self.gitlab_ci_vars)
        env.update(self.base_variables)
        env.update(job.variables)

        # Set job-specific variables
        env["CI_JOB_STAGE"] = job.stage
        env["CI_JOB_NAME"] = job.name

        return env

    def substitute_variables(self, text: str, variables: dict[str, str]) -> str:
        """Perform basic variable substitution in text."""
        # Simple substitution - replace $VAR and ${VAR} patterns

        def replace_var(match):
            var_name = match.group(1) or match.group(2)
            return variables.get(var_name, match.group(0))

        # Match $VAR or ${VAR}
        pattern = r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)"
        return re.sub(pattern, replace_var, text)


class JobExecutor:
    """Executes individual jobs."""

    def __init__(self, variable_manager: VariableManager):
        self.variable_manager = variable_manager

    def execute_job(self, job: JobConfig) -> None:
        """Execute a single job."""
        print(f"🔧 Running job: {job.name} (stage: {job.stage})")

        env = self.variable_manager.prepare_environment(job)

        try:
            # Execute before_script
            if job.before_script:
                print("  📋 Running before_script...")
                self._execute_scripts(job.before_script, env)

            # Execute main script
            if job.script:
                print("  🚀 Running script...")
                self._execute_scripts(job.script, env)

            # Execute after_script
            if job.after_script:
                print("  📋 Running after_script...")
                self._execute_scripts(job.after_script, env)

            print(f"✅ Job {job.name} completed successfully")

        except subprocess.CalledProcessError as e:
            raise JobExecutionError(f"Job {job.name} failed with exit code {e.returncode}") from e

    def _execute_scripts(self, scripts: list[str], env: dict[str, str]) -> None:
        """Execute a list of script commands."""
        for script in scripts:
            if not isinstance(script, str):
                raise Exception(f"{script} is not a string")
            if not script.strip():
                continue

            # Substitute variables in the script
            script = self.variable_manager.substitute_variables(script, env)

            print(f"    $ {script}")

            # Execute using bash
            # command = ['"/c/Program Files/Git/bin/bash.exe"', '-c', shlex.quote(script).strip('\'')]
            # command = shlex.split(script)

            returncode = run_colored(
                script,
                env=env,
                cwd=Path.cwd(),
            )

            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, script)


class StageOrchestrator:
    """Orchestrates job execution by stages."""

    def __init__(self, job_executor: JobExecutor):
        self.job_executor = job_executor

    def execute_pipeline(self, pipeline: PipelineConfig) -> None:
        """Execute all jobs in the pipeline, organized by stages."""
        print("🚀 Starting GitLab CI pipeline execution")
        print(f"📋 Stages: {', '.join(pipeline.stages)}")

        jobs_by_stage = self._organize_jobs_by_stage(pipeline)

        for stage in pipeline.stages:
            stage_jobs = jobs_by_stage.get(stage, [])
            if not stage_jobs:
                print(f"⏭️  Skipping empty stage: {stage}")
                continue

            print(f"\n🎯 Executing stage: {stage}")

            for job in stage_jobs:
                self.job_executor.execute_job(job)

        print("\n🎉 Pipeline completed successfully!")

    def _organize_jobs_by_stage(self, pipeline: PipelineConfig) -> dict[str, list[JobConfig]]:
        """Organize jobs by their stages."""
        jobs_by_stage: dict[str, Any] = {}

        for job in pipeline.jobs:
            stage = job.stage
            if stage not in jobs_by_stage:
                jobs_by_stage[stage] = []
            jobs_by_stage[stage].append(job)

        return jobs_by_stage


class LocalGitLabRunner:
    """Main runner class that orchestrates the entire pipeline execution."""

    def __init__(self, base_path: Path | None = None):
        if not base_path:
            self.base_path = Path.cwd()
        else:
            self.base_path = base_path
        self.loader = ConfigurationLoader(base_path)
        self.processor = PipelineProcessor()

    def run_pipeline(self, config_path: Path | None = None) -> int:
        """Run the complete pipeline."""
        try:
            # Load and process configuration
            raw_config = self.loader.load_config(config_path)
            pipeline = self.processor.process_config(raw_config)

            # Set up execution components
            variable_manager = VariableManager(pipeline.variables)
            job_executor = JobExecutor(variable_manager)
            orchestrator = StageOrchestrator(job_executor)

            # Execute pipeline
            orchestrator.execute_pipeline(pipeline)

        except GitLabCIError as e:
            print(f"❌ GitLab CI Error: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            sys.exit(1)
        return 0


def best_efforts_run(config_path: Path) -> int:
    """Main entry point for the best-efforts-run command."""
    runner = LocalGitLabRunner()
    return runner.run_pipeline(config_path)


if __name__ == "__main__":

    def run() -> None:
        print(sys.argv)
        config = str(sys.argv[-1:][0])
        print(f"Running {config} ...")
        best_efforts_run(Path(config))

    run()
```
## File: commands\clean_all.py
```python
from __future__ import annotations

import base64
import logging
from collections.abc import Iterator
from pathlib import Path

from bash2gitlab.utils.utils import short_path

logger = logging.getLogger(__name__)

# --- Helpers -----------------------------------------------------------------


def partner_hash_file(base_file: Path) -> Path:
    """Return the expected .hash file for a target file.

    Example: foo/bar.yml -> foo/bar.yml.hash
    """
    return base_file.with_suffix(base_file.suffix + ".hash")


def base_from_hash(hash_file: Path) -> Path:
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
            base = base_from_hash(p)
            if base.exists() and base.is_file():
                yield (base, p)
        else:
            hashf = partner_hash_file(p)
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
            base = base_from_hash(p)
            if base.exists():
                paired_bases.add(base)
                paired_hashes.add(p)
            else:
                strays.append(p)
        else:
            hashf = partner_hash_file(p)
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


def read_current_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_hash_text(hash_file: Path) -> str | None:
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
    expected = read_hash_text(hash_file)
    if expected is None:
        return None
    current = read_current_text(base_file)
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
        base_file = base_from_hash(p)
        if not base_file.exists() or not base_file.is_file():
            # Stray .hash; leave it
            continue
        seen_pairs.add((base_file, p))

    if not seen_pairs:
        logger.info("No target pairs found under %s", short_path(root))
        return (0, 0, 0)

    for base_file, hash_file in sorted(seen_pairs):
        status = is_target_unchanged(base_file, hash_file)
        if status is None:
            logger.warning(
                "Refusing to remove %s (invalid/corrupt hash at %s)", short_path(base_file), short_path(hash_file)
            )
            skipped_invalid += 1
            continue
        if not status:
            skipped_changed += 1
            logger.warning("Refusing to remove %s (content has changed since last write)", short_path(base_file))
            continue

        # status is True: safe to delete
        if dry_run:
            logger.info("[DRY RUN] Would delete %s and %s", short_path(base_file), short_path(hash_file))
        else:
            try:
                base_file.unlink(missing_ok=False)
                hash_file.unlink(missing_ok=True)
                logger.info("Deleted %s and %s", short_path(base_file), short_path(hash_file))
            # narrow surface area; logs any fs issues
            except Exception as e:  # nosec
                logger.error("Failed to delete %s / %s: %s", short_path(base_file), short_path(hash_file), e)
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

    logger.debug("Target report for %s", short_path(root))
    logger.debug("Pairs found: %d", len(pairs))
    for bash_file, hash_file in pairs:
        status = is_target_unchanged(bash_file, hash_file)
        if status:
            logger.debug("OK: %s (hash matches)", short_path(bash_file))
        elif status is False:
            logger.warning("CHANGED: %s (hash mismatch)", short_path(bash_file))
        else:
            logger.warning("INVALID HASH: %s (cannot decode %s)", short_path(bash_file), short_path(hash_file))

    logger.debug("Strays: %d", len(strays))
    for s in strays:
        logger.debug("Stray: %s", short_path(s))
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

from bash2gitlab.utils.utils import short_path

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
                    f"Could not find archive for branch '{branch}' at '{archive_url}'. Please check the repository URL and branch name. (HTTP Status: {e.code})"
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

    logger.info("Successfully cloned directories into %s", short_path(clone_path))
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

from bash2gitlab.commands.clean_all import report_targets
from bash2gitlab.commands.compile_bash_reader import read_bash_script
from bash2gitlab.commands.compile_not_bash import maybe_inline_interpreter_command
from bash2gitlab.commands.input_change_detector import mark_compilation_complete, needs_compilation
from bash2gitlab.config import config
from bash2gitlab.plugins import get_pm
from bash2gitlab.utils.dotenv import parse_env_file
from bash2gitlab.utils.parse_bash import extract_script_path
from bash2gitlab.utils.utils import remove_leading_blank_lines, short_path
from bash2gitlab.utils.validate_pipeline import GitLabCIValidator
from bash2gitlab.utils.yaml_factory import get_yaml
from bash2gitlab.utils.yaml_file_same import normalize_for_compare, yaml_is_same

logger = logging.getLogger(__name__)

__all__ = ["run_compile_all"]


def infer_cli(
    uncompiled_path: Path,
    output_path: Path,
    dry_run: bool = False,
    parallelism: int | None = None,
) -> str:
    command = f"bash2gitlab compile --in {short_path(uncompiled_path)} --out {short_path(output_path)}"
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
                raise Exception(f"Could not inline script '{script_path_str}': {e}. Preserving original line.") from e
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

    validator = GitLabCIValidator()
    ok, problems = validator.validate_ci_config(new_content)
    if not ok:
        raise Exception(problems)
    output_file.write_text(new_content, encoding="utf-8")

    # Store a base64 encoded copy of the exact content we just wrote.
    encoded_content = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
    hash_file.write_text(encoded_content, encoding="utf-8")
    logger.debug(f"Updated hash file: {short_path(hash_file)}")


def unified_diff(old: str, new: str, path: Path, from_label: str = "current", to_label: str = "new") -> str:
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


def diff_stats(diff_text: str) -> tuple[int, int, int]:
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
            diff_text = unified_diff(
                normalize_for_compare(current_content), normalize_for_compare(new_content), output_file
            )
            changed, ins, rem = diff_stats(diff_text)
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
        error_message = f"ERROR: Destination file '{short_path(output_file)}' exists but its .hash file is missing. Aborting to prevent data loss. If you want to regenerate this file, please remove it and run the script again."
        logger.error(error_message)
        raise SystemExit(1)

    # Decode the last known content from the hash file
    last_known_base64 = hash_file.read_text(encoding="utf-8").strip()
    try:
        last_known_content = base64.b64decode(last_known_base64).decode("utf-8")
    except (ValueError, TypeError) as e:
        error_message = f"ERROR: Could not decode the .hash file for '{short_path(output_file)}'. It may be corrupted.\nError: {e}\nAborting to prevent data loss. Please remove the file and its .hash file to regenerate."
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
        diff_text = unified_diff(
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
        # We use sys.exit to print the message directly and exit with an error code.
        sys.exit(error_message)

    # If we reach here, the current file is valid (or just reformatted).
    # Now, we check if the *newly generated* content is different from the current content.
    if not yaml_is_same(current_content, new_content):
        # NEW: log diff + counts before writing
        diff_text = unified_diff(
            normalize_for_compare(current_content), normalize_for_compare(new_content), output_file
        )
        changed, ins, rem = diff_stats(diff_text)
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


def compile_single_file(
    source_path: Path,
    output_file: Path,
    scripts_path: Path,
    variables: dict[str, str],
    uncompiled_path: Path,
    dry_run: bool,
    inferred_cli_command: str,
) -> tuple[int, int]:
    """Compile a single YAML file and write the result.

    Returns a tuple of the number of inlined sections and whether a file was written (0 or 1).
    """
    logger.debug(f"Processing template: {short_path(source_path)}")
    raw_text = source_path.read_text(encoding="utf-8")
    inlined_for_file, compiled_text = inline_gitlab_scripts(raw_text, scripts_path, variables, uncompiled_path)
    final_content = (get_banner(inferred_cli_command) + compiled_text) if inlined_for_file > 0 else raw_text
    written = write_compiled_file(output_file, final_content, dry_run)
    return inlined_for_file, int(written)


def run_compile_all(
    uncompiled_path: Path,
    output_path: Path,
    dry_run: bool = False,
    parallelism: int | None = None,
    force: bool = False,
) -> int:
    """
    Main function to process a directory of uncompiled GitLab CI files.
    This version safely writes files by checking hashes to avoid overwriting manual changes.

    Args:
        uncompiled_path (Path): Path to the input .gitlab-ci.yml, other yaml and bash files.
        output_path (Path): Path to write the .gitlab-ci.yml file and other yaml.
        dry_run (bool): If True, simulate the process without writing any files.
        parallelism (int | None): Maximum number of processes to use for parallel compilation.
        force (bool): If True, compile even if it appears to not be need because nothing changed.

    Returns:
        The total number of inlined sections across all files.
    """
    # Check if compilation is needed (unless forced)
    if not force:
        if not needs_compilation(uncompiled_path):
            logger.info("No input changes detected since last compilation. Skipping compilation.")
            logger.info("Use --force to compile anyway, or modify input files to trigger compilation.")
            return 0
        logger.info("Input changes detected, proceeding with compilation...")

    inferred_cli_command = infer_cli(uncompiled_path, output_path, dry_run, parallelism)
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

    files_to_process: list[tuple[Path, Path, dict[str, str]]] = []

    if uncompiled_path.is_dir():
        template_files = list(uncompiled_path.rglob("*.yml")) + list(uncompiled_path.rglob("*.yaml"))
        if not template_files:
            logger.warning(f"No template YAML files found in {uncompiled_path}")

        for template_path in template_files:
            relative_path = template_path.relative_to(uncompiled_path)
            output_file = output_path / relative_path
            files_to_process.append((template_path, output_file, {}))

    total_files = len(files_to_process)
    max_workers = multiprocessing.cpu_count()
    if parallelism and parallelism > 0:
        max_workers = min(parallelism, max_workers)

    if total_files >= 5 and max_workers > 1 and parallelism:
        args_list = [
            (src, out, uncompiled_path, variables, uncompiled_path, dry_run, inferred_cli_command)
            for src, out, variables in files_to_process
        ]
        with multiprocessing.Pool(processes=max_workers) as pool:
            results = pool.starmap(compile_single_file, args_list)
        total_inlined_count += sum(inlined for inlined, _ in results)
        written_files_count += sum(written for _, written in results)
    else:
        for src, out, variables in files_to_process:
            inlined_for_file, wrote = compile_single_file(
                src, out, uncompiled_path, variables, uncompiled_path, dry_run, inferred_cli_command
            )
            total_inlined_count += inlined_for_file
            written_files_count += wrote

    # After successful compilation, mark as complete
    if not dry_run and (total_inlined_count > 0 or written_files_count > 0):
        try:
            mark_compilation_complete(uncompiled_path)
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
```
## File: commands\compile_bash_reader.py
```python
"""Read a bash script and inline any `source script.sh` patterns."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from bash2gitlab.utils.pathlib_polyfills import is_relative_to
from bash2gitlab.utils.utils import short_path

__all__ = ["read_bash_script"]

# Set up a logger for this module
logger = logging.getLogger(__name__)

# Regex to match 'source file.sh' or '. file.sh'
# It ensures the line contains nothing else but the sourcing command, except a comment.
# - ^\s* - Start of the line with optional whitespace.
# - (?:source|\.) - Non-capturing group for 'source' or '.'.
# - \s+         - At least one whitespace character.
# - (?P<path>[\w./\\-]+) - Captures the file path.
# - \s*$        - Optional whitespace until the end of the line.
# SOURCE_COMMAND_REGEX = re.compile(r"^\s*(?:source|\.)\s+(?P<path>[\w./\\-]+)\s*$")
# Handle optional comment.
SOURCE_COMMAND_REGEX = re.compile(r"^\s*(?:source|\.)\s+(?P<path>[\w./\\-]+)\s*(?:#.*)?$")

# Regex to match pragmas like '# Pragma: do-not-inline'
# It is case-insensitive to 'Pragma' and captures the command.
PRAGMA_REGEX = re.compile(
    r"#\s*Pragma:\s*(?P<command>do-not-inline(?:-next-line)?|start-do-not-inline|end-do-not-inline|allow-outside-root)",
    re.IGNORECASE,
)


class SourceSecurityError(RuntimeError):
    pass


class PragmaError(ValueError):
    """Custom exception for pragma parsing errors."""


def secure_join(
    base_dir: Path,
    user_path: str,
    allowed_root: Path,
    *,
    bypass_security_check: bool = False,
) -> Path:
    """
    Resolve 'user_path' (which may contain ../ and symlinks) against base_dir,
    then ensure the final real path is inside allowed_root.

    Args:
        base_dir: The directory of the script doing the sourcing.
        user_path: The path string from the source command.
        allowed_root: The root directory that sourced files cannot escape.
        bypass_security_check: If True, skips the check against allowed_root.
    """
    # Normalize separators and strip quotes/whitespace
    user_path = user_path.strip().strip('"').strip("'").replace("\\", "/")

    # Resolve relative to the including script's directory
    candidate = (base_dir / user_path).resolve(strict=True)

    # Ensure the real path (after following symlinks) is within allowed_root
    allowed_root = allowed_root.resolve(strict=True)

    if not os.environ.get("BASH2GITLAB_SKIP_ROOT_CHECKS") and not bypass_security_check:
        if not is_relative_to(candidate, allowed_root):
            raise SourceSecurityError(f"Refusing to source '{candidate}': escapes allowed root '{allowed_root}'.")
    elif bypass_security_check:
        logger.warning(
            "Security check explicitly bypassed for path '%s' due to 'allow-outside-root' pragma.",
            candidate,
        )

    return candidate


def read_bash_script(path: Path) -> str:
    """
    Reads a bash script and inlines any sourced files.
    This is the main entry point.
    """
    logger.debug(f"Reading and inlining script from: {path}")

    # Use the recursive inliner to do all the work, including shebang handling.
    content = inline_bash_source(path)

    if not content.strip():
        raise ValueError(f"Script is empty or only contains whitespace: {path}")

    # The returned content is now final.
    return content


def inline_bash_source(
    main_script_path: Path,
    processed_files: set[Path] | None = None,
    *,
    allowed_root: Path | None = None,
    max_depth: int = 64,
    _depth: int = 0,
) -> str:
    """
    Reads a bash script and recursively inlines content from sourced files,
    honoring pragmas to prevent inlining or bypass security.

    This function processes a bash script, identifies any 'source' or '.' commands,
    and replaces them with the content of the specified script. It handles
    nested sourcing, prevents infinite loops, and respects the following pragmas:
    - `# Pragma: do-not-inline`: Prevents inlining on the current line.
    - `# Pragma: do-not-inline-next-line`: Prevents inlining on the next line.
    - `# Pragma: start-do-not-inline`: Starts a block where no inlining occurs.
    - `# Pragma: end-do-not-inline`: Ends the block.
    - `# Pragma: allow-outside-root`: Bypasses the directory traversal security check.
    - `# Pragma: must-inline`: Force an inline in an anchored "job"

    Args:
        main_script_path: The absolute path to the main bash script to process.
        processed_files: A set used internally to track already processed files.
        allowed_root: Root to prevent parent traversal.
        max_depth: Maximum recursion depth for sourcing.
        _depth: Current recursion depth (used internally).

    Returns:
        A string containing the script content with all sourced files inlined.

    Raises:
        FileNotFoundError: If the main_script_path or any sourced script does not exist.
        PragmaError: If start/end pragmas are mismatched.
        RecursionError: If max_depth is exceeded.
    """
    if processed_files is None:
        processed_files = set()

    if allowed_root is None:
        allowed_root = Path.cwd()

    # Normalize and security-check the entry script itself
    try:
        main_script_path = secure_join(
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
    in_do_not_inline_block = False
    skip_next_line = False

    try:
        with main_script_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()

            # --- (FIX) SHEBANG HANDLING MOVED HERE ---
            # Only strip the shebang if this is the top-level script (_depth == 0).
            # This respects pragmas because the logic now happens *before* line-by-line processing.
            if _depth == 0 and lines and lines[0].startswith("#!"):
                logger.debug(f"Stripping shebang from main script: {lines[0].strip()}")
                lines = lines[1:]

            for line_num, line in enumerate(lines, 1):
                source_match = SOURCE_COMMAND_REGEX.match(line)
                pragma_match = PRAGMA_REGEX.search(line)
                pragma_command = pragma_match.group("command").lower() if pragma_match else None

                # --- (FIX) Phase 1: State Management & Strippable Pragmas ---
                # These pragmas are control directives and should be stripped from the output.
                if pragma_command == "start-do-not-inline":
                    if in_do_not_inline_block:
                        raise PragmaError(f"Cannot nest 'start-do-not-inline' at {main_script_path}:{line_num}")
                    in_do_not_inline_block = True
                    continue  # Strip the pragma line itself

                if pragma_command == "end-do-not-inline":
                    if not in_do_not_inline_block:
                        raise PragmaError(f"Found 'end-do-not-inline' without 'start' at {main_script_path}:{line_num}")
                    in_do_not_inline_block = False
                    continue  # Strip the pragma line itself

                if pragma_command == "do-not-inline-next-line":
                    skip_next_line = True
                    continue  # Strip the pragma line itself

                # Any line with a 'do-not-inline' pragma is now stripped.
                if pragma_command == "do-not-inline":
                    continue

                # --- (FIX) Phase 2: Content Filtering ---
                # If we are inside a do-not-inline block, strip this line of content.
                if in_do_not_inline_block:
                    continue

                # --- Phase 3: Line-by-line Processing (for lines we intend to keep) ---
                should_inline = source_match is not None
                reason_to_skip = ""

                if skip_next_line:
                    reason_to_skip = "previous line had 'do-not-inline-next-line' pragma"
                    should_inline = False
                    skip_next_line = False  # Consume the flag
                    continue
                # elif in_do_not_inline_block:
                #     reason_to_skip = "currently in 'do-not-inline' block"
                #     should_inline = False
                elif pragma_command == "do-not-inline":
                    reason_to_skip = "line contains 'do-not-inline' pragma"
                    should_inline = False
                    # Line is kept, just not inlined. Warning for non-sourcing lines.
                    if not source_match:
                        logger.warning(
                            "Pragma 'do-not-inline' on non-sourcing line at %s:%d has no effect.",
                            main_script_path,
                            line_num,
                        )

                if pragma_command == "allow-outside-root" and not source_match:
                    logger.warning(
                        "Pragma 'allow-outside-root' on non-sourcing line at %s:%d has no effect.",
                        main_script_path,
                        line_num,
                    )

                # --- Perform Action: Inline or Append ---
                if should_inline and source_match:
                    sourced_script_name = source_match.group("path")
                    bypass_security = pragma_command == "allow-outside-root"
                    try:
                        sourced_script_path = secure_join(
                            base_dir=main_script_path.parent,
                            user_path=sourced_script_name,
                            allowed_root=allowed_root,
                            bypass_security_check=bypass_security,
                        )
                    except (FileNotFoundError, SourceSecurityError) as e:
                        logger.error(
                            "Blocked/missing source '%s' from '%s': %s", sourced_script_name, main_script_path, e
                        )
                        raise

                    logger.info("Inlining sourced file: %s -> %s", sourced_script_name, short_path(sourced_script_path))
                    inlined = inline_bash_source(
                        sourced_script_path,
                        processed_files,
                        allowed_root=allowed_root,
                        max_depth=max_depth,
                        _depth=_depth + 1,
                    )
                    final_content_lines.append(inlined)
                else:
                    if source_match and reason_to_skip:
                        logger.info(
                            "Skipping inline of '%s' at %s:%d because %s.",
                            source_match.group("path"),
                            main_script_path,
                            line_num,
                            reason_to_skip,
                        )
                    final_content_lines.append(line)

        if in_do_not_inline_block:
            raise PragmaError(f"Unclosed 'start-do-not-inline' pragma in file: {main_script_path}")

    except Exception:
        # Propagate after logging context
        logger.exception("Failed to read or process %s", main_script_path)
        raise

    final = "".join(final_content_lines)
    if not final.endswith("\n"):
        return final + "\n"
    return final
```
## File: commands\compile_detct_last_change.py
```python
# """Example integration of InputChangeDetector with run_compile_all function."""
#
# from pathlib import Path
# import logging
# from bash2gitlab.commands.input_change_detector import InputChangeDetector, needs_compilation, mark_compilation_complete
#
# logger = logging.getLogger(__name__)


# # Command line integration example
# def add_change_detection_args(parser):
#     """Add change detection arguments to argument parser."""
#     parser.add_argument(
#         '--force',
#         action='store_true',
#         help='Force compilation even if no input changes detected'
#     )
#     parser.add_argument(
#         '--check-only',
#         action='store_true',
#         help='Only check if compilation is needed, do not compile'
#     )
#     parser.add_argument(
#         '--list-changed',
#         action='store_true',
#         help='List files that have changed since last compilation'
#     )
#
#
# def handle_change_detection_commands(args, uncompiled_path: Path) -> bool:
#     """Handle change detection specific commands. Returns True if command was handled."""
#
#     if args.check_only:
#         if needs_compilation(uncompiled_path):
#             print("Compilation needed: input files have changed")
#             return True
#         else:
#             print("No compilation needed: no input changes detected")
#             return True
#
#     if args.list_changed:
#         from bash2gitlab.commands.input_change_detector import get_changed_files
#         changed = get_changed_files(uncompiled_path)
#         if changed:
#             print("Changed files since last compilation:")
#             for file_path in changed:
#                 print(f"  {file_path}")
#         else:
#             print("No files have changed since last compilation")
#         return True
#
#     return False
```
## File: commands\compile_not_bash.py
```python
"""Support for inlining many types of scripts.

Turns invocations like `python -m pkg.tool`, `node scripts/foo.js`, `awk -f prog.awk data.txt`
into a single interpreter call that evaluates the file contents inline, e.g.:

    # >>> BEGIN inline: python -m pkg.tool
    python -c '...file contents...'
    # <<< END inline

If a line doesn't match a supported pattern, returns None.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

__all__ = ["maybe_inline_interpreter_command"]

logger = logging.getLogger(__name__)

# Maximum *quoted* payload length to inline. Large payloads risk hitting ARG_MAX
# limits on various platforms/runners. Choose a conservative default.
MAX_INLINE_LEN = int(os.getenv("BASH2GITLAB_MAX_INLINE_LEN", "16000"))

# Env toggles
ALLOW_ANY_EXT = os.getenv("BASH2GITLAB_ALLOW_ANY_EXT") == "1"

# Interpreters → flag that accepts a *single* string of code.
# Empty string means the code is the first positional argument (awk/jq).
_INTERPRETER_FLAGS: dict[str, str | None] = {
    # existing
    "python": "-c",
    "node": "-e",
    "ruby": "-e",
    "php": "-r",
    "fish": "-c",
    # shells
    "bash": "-c",
    "sh": "-c",
    "zsh": "-c",
    "ksh": "-c",
    "pwsh": "-Command",
    "powershell": "-Command",
    # scripting languages
    "perl": "-e",
    "lua": "-e",
    "elixir": "-e",
    "raku": "-e",
    "julia": "-e",
    "groovy": "-e",
    "scala": "-e",  # may depend on launcher availability
    "clojure": "-e",
    "bb": "-e",  # babashka
    "erl": "-eval",  # special-cased with -noshell -s init stop
    "R": "-e",
    "Rscript": "-e",
    # JS runtimes
    "deno": "eval",  # map `deno run` to `deno eval`
    "bun": "eval",  # map `bun run` to `bun eval` (verify version)
    # mini-languages / filters
    "awk": "",  # program as first arg
    "sed": "-e",
    "jq": "",  # filter as first arg
}

# Interpreter → expected extensions for sanity checking. Permissive by default.
_INTERPRETER_EXTS: dict[str, tuple[str, ...]] = {
    "python": (".py",),
    "node": (".js", ".mjs", ".cjs"),
    "ruby": (".rb",),
    "php": (".php",),
    "fish": (".fish", ".sh"),
    # shells
    "bash": (".sh",),
    "sh": (".sh",),
    "zsh": (".zsh", ".sh"),
    "ksh": (".ksh", ".sh"),
    "pwsh": (".ps1",),
    "powershell": (".ps1",),
    # scripting languages
    "perl": (".pl", ".pm"),
    "lua": (".lua",),
    "elixir": (".exs",),
    "raku": (".raku", ".p6"),
    "julia": (".jl",),
    "groovy": (".groovy",),
    "scala": (".scala",),
    "clojure": (".clj",),
    "bb": (".clj",),
    "erl": (".erl",),
    "R": (".R", ".r"),
    "Rscript": (".R", ".r"),
    # JS runtimes
    "deno": (".ts", ".tsx", ".js", ".mjs"),
    "bun": (".ts", ".tsx", ".js"),
    # mini-languages
    "awk": (".awk", ".txt"),
    "sed": (".sed", ".txt"),
    "jq": (".jq", ".txt"),
}

# Match common interpreter invocations. Supports python -m, deno/bun run, and tail args.
# BUG: might not handle script files with spaces in the name. Maybe use shlex.split().
_INTERP_LINE = re.compile(
    r"""
    ^\s*
    (?P<interp>
        python(?:\d+(?:\.\d+)?)? | node | deno | bun |
        ruby | php | fish |
        bash | sh | zsh | ksh |
        pwsh | powershell |
        perl | lua | elixir | raku | julia | groovy | scala | clojure | bb | erl | Rscript | R |
        awk | sed | jq
    )
    (?:\s+run)?              # handle `deno run`, `bun run`
    \s+
    (?:
        -m\s+(?P<module>[A-Za-z0-9_\.]+)  # python -m package.module
        |
        (?P<path>\.?/?[^\s]+)             # or a script path
    )
    (?P<rest>\s+.*)?              # preserve trailing args/files
    \s*$
    """,
    re.VERBOSE,
)


def shell_single_quote(s: str) -> str:
    """Safely single-quote *s* for POSIX shell.
    Turns: abc'def  ->  'abc'"'"'def'
    """
    return "'" + s.replace("'", "'\"'\"'") + "'"


def normalize_interp(interp: str) -> str:
    """Map interpreter aliases to their base key for look-ups.
    e.g., python3.12 → python.
    """
    if interp.startswith("python"):
        return "python"
    return interp


def resolve_interpreter_target(
    interp: str, module: str | None, path_str: str | None, scripts_root: Path
) -> tuple[Path, str]:
    """Resolve the target file and a display label from either a module or a path.
    For python -m, map "a.b.c" -> a/b/c.py
    """
    if module:
        if normalize_interp(interp) != "python":
            raise ValueError(f"-m is only supported for python, got: {interp}")
        rel = Path(module.replace(".", "/") + ".py")
        return scripts_root / rel, f"python -m {module}"
    if path_str:
        rel_str = Path(path_str.strip()).as_posix().lstrip("./")
        shown = f"{interp} {Path(rel_str).as_posix()}"
        return scripts_root / rel_str, shown
    raise ValueError("Neither module nor path provided.")


def is_reasonable_ext(interp: str, file: Path) -> bool:
    if ALLOW_ANY_EXT:
        return True
    base = normalize_interp(interp)
    exts = _INTERPRETER_EXTS.get(base)
    if not exts:
        return True
    return file.suffix.lower() in exts


def read_script_bytes(p: Path) -> str | None:
    try:
        text = p.read_text(encoding="utf-8")
    # reading local workspace file
    except Exception as e:  # nosec
        logger.warning("Could not read %s: %s; preserving original.", p, e)
        return None
    # Strip UTF-8 BOM if present
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    # Strip shebang
    if text.startswith("#!"):
        lines = text.splitlines()
        text = "\n".join(lines[1:])
    return text


def build_eval_command(interp: str, flag: str | None, quoted: str, rest: str | None) -> str | None:
    if flag is None:
        return None
    r = rest or ""
    # erl needs some boilerplate to run and exit non-interactively
    if interp == "erl":
        return f"erl -noshell -eval {quoted} -s init stop{r}"
    if flag == "":  # awk / jq (no flag; program/filter is first positional)
        return f"{interp} {quoted}{r}"
    return f"{interp} {flag} {quoted}{r}"


def maybe_inline_interpreter_command(line: str, scripts_root: Path) -> tuple[list[str], Path] | tuple[None, None]:
    """If *line* looks like an interpreter execution we can inline, return:
    [BEGIN_MARK, <interpreter -flag 'code'>, END_MARK]. Otherwise, return None.
    """
    m = _INTERP_LINE.match(line)
    if not m:
        return None, None

    interp_raw = m.group("interp")
    interp = normalize_interp(interp_raw)
    module = m.group("module")
    path_str = m.group("path")
    rest = m.group("rest") or ""

    try:
        target_file, shown = resolve_interpreter_target(interp_raw, module, path_str, scripts_root)
    except ValueError as e:
        logger.debug("Interpreter inline skip: %s", e)
        return None, None

    if not target_file.is_file():
        logger.warning("Could not inline %s: file not found at %s; preserving original.", shown, target_file)
        return None, None

    if not is_reasonable_ext(interp, target_file):
        logger.debug("Interpreter inline skip: extension %s not expected for %s", target_file.suffix, interp)
        return None, None

    code = read_script_bytes(target_file)
    if code is None:
        return None, None

    quoted = shell_single_quote(code)

    # size guard
    if len(quoted) > MAX_INLINE_LEN:
        logger.warning(
            "Skipping inline for %s: payload %d chars exceeds MAX_INLINE_LEN=%d.",
            shown,
            len(quoted),
            MAX_INLINE_LEN,
        )
        return None, None

    flag = _INTERPRETER_FLAGS.get(interp)
    if flag is None:
        logger.debug("Interpreter inline skip: no eval flag known for %s", interp)
        return None, None

    inlined_cmd = build_eval_command(interp, flag, quoted, rest)
    if inlined_cmd is None:
        return None, None

    begin_marker = f"# >>> BEGIN inline: {shown}"
    end_marker = "# <<< END inline"
    logger.debug("Inlining interpreter command '%s' (%d chars).", shown, len(code))
    return [begin_marker, inlined_cmd, end_marker], target_file
```
## File: commands\decompile_all.py
```python
"""
Take a gitlab template with inline yaml and split it up into yaml and shell
commands. Useful for project initialization.

Fixes:
 - Support decompiling a *file* or an entire *folder* tree
 - Force --out to be a *directory* (scripts live next to output YAML)
 - Script refs are made *relative to the YAML file* (e.g., "./script.sh")
 - Any YAML ``!reference [...]`` items in scripts are emitted as *bash comments*
 - Logging prints *paths relative to CWD* to reduce noise
 - Generate Makefile with proper dependency patterns for before_/after_ scripts
"""

from __future__ import annotations

import io
import logging
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import TaggedScalar
from ruamel.yaml.scalarstring import FoldedScalarString

from bash2gitlab.config import config
from bash2gitlab.utils.mock_ci_vars import generate_mock_ci_variables_script
from bash2gitlab.utils.pathlib_polyfills import is_relative_to
from bash2gitlab.utils.utils import short_path
from bash2gitlab.utils.validate_pipeline import GitLabCIValidator
from bash2gitlab.utils.yaml_factory import get_yaml

logger = logging.getLogger(__name__)

SHEBANG = "#!/bin/bash"

__all__ = [
    "run_decompile_gitlab_file",
    "run_decompile_gitlab_tree",
]


# --- helpers -----------------------------------------------------------------


def dump_inline_no_doc_markers(yaml: YAML, node: Any) -> str:
    buf = io.StringIO()
    prev_start, prev_end = yaml.explicit_start, yaml.explicit_end
    try:
        yaml.explicit_start = False
        yaml.explicit_end = False
        yaml.dump(node, buf)
    finally:
        yaml.explicit_start, yaml.explicit_end = prev_start, prev_end
    return buf.getvalue().rstrip("\n")


def create_script_filename(job_name: str, script_key: str) -> str:
    """Create a standardized, safe filename for a script.

    For the main 'script' key, just use the job name. For others, append the key.
    """
    sanitized_job_name = re.sub(r"[^\w.-]", "-", job_name.lower())
    sanitized_job_name = re.sub(r"-+", "-", sanitized_job_name).strip("-")
    return f"{sanitized_job_name}.sh" if script_key == "script" else f"{sanitized_job_name}_{script_key}.sh"


def bashify_script_items(script_content: list[str | Any] | str, yaml: YAML) -> list[str]:
    """Convert YAML items from a script block into bash lines.

    - Strings are kept as-is.
    - Other YAML nodes are dumped to text with no doc markers.
    - ``!reference [...]`` turns into a bash comment line so the intent isn't lost.
    - Empty/whitespace lines are dropped.
    """
    raw_lines: list[str] = []

    if isinstance(script_content, str):
        raw_lines.extend(script_content.splitlines())
    else:
        for item in script_content:  # ruamel CommentedSeq-like or list
            if isinstance(item, str):
                raw_lines.append(item)
            elif isinstance(item, TaggedScalar) and str(item.tag).endswith("reference"):
                dumped = dump_inline_no_doc_markers(yaml, item)
                raw_lines.append(f"# {dumped}")
            elif item is not None:
                dumped = dump_inline_no_doc_markers(yaml, item)
                # If the dump still contains an explicit !reference tag, comment it out
                if dumped.lstrip().startswith("!reference"):
                    raw_lines.append(f"# {dumped}")
                else:
                    raw_lines.append(dumped)

    # Filter empties
    # return [ln for ln in (ln if isinstance(ln, str) else str(ln) for ln in raw_lines) if ln and ln.strip()]

    # Make sure line continuations (`\`) get their own newline
    normalized = []
    for ln in raw_lines:
        normalized.append(ln.rstrip())
    return [ln for ln in normalized if ln and ln.strip()]


def generate_makefile(jobs_info: dict[str, dict[str, str]], output_dir: Path, dry_run: bool = False) -> None:
    """Generate a Makefile with proper dependency patterns for GitLab CI jobs.

    Args:
        jobs_info: Dict mapping job names to their script info
        output_dir: Directory where Makefile should be created
        dry_run: Whether to actually write the file
    """
    makefile_lines: list[str] = [
        "# Auto-generated Makefile for GitLab CI jobs",
        "# Use 'make <job_name>' to run a job with proper before/after script handling",
        "",
        ".PHONY: help",
        "",
    ]

    # Collect all job names for help target
    job_names = list(jobs_info.keys())

    # Help target
    makefile_lines.extend(
        [
            "help:",
            "\t@echo 'Available jobs:'",
        ]
    )
    for job_name in sorted(job_names):
        makefile_lines.append(f"\t@echo '  {job_name}'")
    makefile_lines.extend(
        [
            "\t@echo ''",
            "\t@echo 'Use: make <job_name> to run a job'",
            "",
        ]
    )

    # Generate rules for each job
    for job_name, scripts in jobs_info.items():
        sanitized_name = re.sub(r"[^\w.-]", "-", job_name.lower())
        sanitized_name = re.sub(r"-+", "-", sanitized_name).strip("-")

        # Determine dependencies and targets
        dependencies: list[str] = []
        targets_after_main: list[str] = []

        # Before script dependency
        if "before_script" in scripts:
            before_target = f"{sanitized_name}_before_script"
            dependencies.append(before_target)

        # After script runs after main job
        if "after_script" in scripts:
            after_target = f"{sanitized_name}_after_script"
            targets_after_main.append(after_target)

        # Main job rule
        makefile_lines.append(f".PHONY: {sanitized_name}")
        if dependencies:
            makefile_lines.append(f"{sanitized_name}: {' '.join(dependencies)}")
        else:
            makefile_lines.append(f"{sanitized_name}:")

        # Execute the main script
        if "script" in scripts:
            makefile_lines.append(f"\t@echo 'Running {job_name} main script...'")
            makefile_lines.append(f"\t@./{scripts['script']}")
        else:
            makefile_lines.append(f"\t@echo 'No main script for {job_name}'")

        # Execute after scripts if they exist
        for after_target in targets_after_main:
            makefile_lines.append(f"\t@$(MAKE) {after_target}")

        makefile_lines.append("")

        # Before script rule
        if "before_script" in scripts:
            before_target = f"{sanitized_name}_before_script"
            makefile_lines.extend(
                [
                    f".PHONY: {before_target}",
                    f"{before_target}:",
                    f"\t@echo 'Running {job_name} before script...'",
                    f"\t@./{scripts['before_script']}",
                    "",
                ]
            )

        # After script rule
        if "after_script" in scripts:
            after_target = f"{sanitized_name}_after_script"
            makefile_lines.extend(
                [
                    f".PHONY: {after_target}",
                    f"{after_target}:",
                    f"\t@echo 'Running {job_name} after script...'",
                    f"\t@./{scripts['after_script']}",
                    "",
                ]
            )

        # Pre-get-sources script rule (standalone)
        if "pre_get_sources_script" in scripts:
            pre_target = f"{sanitized_name}_pre_get_sources_script"
            makefile_lines.extend(
                [
                    f".PHONY: {pre_target}",
                    f"{pre_target}:",
                    f"\t@echo 'Running {job_name} pre-get-sources script...'",
                    f"\t@./{scripts['pre_get_sources_script']}",
                    "",
                ]
            )

    # Add a rule to run all jobs
    if job_names:
        makefile_lines.extend(
            [
                ".PHONY: all",
                f"all: {' '.join(sorted(job_names))}",
                "",
            ]
        )

    makefile_content = "\n".join(makefile_lines)
    makefile_path = output_dir / "Makefile"

    logger.info("Generating Makefile at: %s", short_path(makefile_path))

    if not dry_run:
        makefile_path.write_text(makefile_content, encoding="utf-8")


# --- decompilers ---------------------------------------------------------------


def decompile_variables_block(
    variables_data: dict,
    base_name: str,
    scripts_output_path: Path,
    *,
    dry_run: bool = False,
) -> str | None:
    """Extract variables dict into a ``.sh`` file of ``export`` statements.

    Returns the filename (not full path) of the created variables script, or ``None``.
    """
    if not variables_data or not isinstance(variables_data, dict):
        return None

    variable_lines: list[str] = []
    for key, value in variables_data.items():
        value_str = str(value).replace('"', '\\"')
        variable_lines.append(f'export {key}="{value_str}"')

    if not variable_lines:
        return None

    script_filename = f"{base_name}_variables.sh"
    script_filepath = scripts_output_path / script_filename
    full_script_content = "\n".join(variable_lines) + "\n"

    logger.info("Decompileding variables for '%s' to '%s'", base_name, short_path(script_filepath))

    if not dry_run:
        script_filepath.parent.mkdir(parents=True, exist_ok=True)
        script_filepath.write_text(full_script_content, encoding="utf-8")
        script_filepath.chmod(0o755)

    return script_filename


def decompile_script_block(
    *,
    script_content: list[str | Any] | str,
    job_name: str,
    script_key: str,
    scripts_output_path: Path,
    yaml_dir: Path,
    dry_run: bool = False,
    global_vars_filename: str | None = None,
    job_vars_filename: str | None = None,
    minimum_lines: int = 1,
) -> tuple[str | None, str | None]:
    """Extract a script block into a ``.sh`` file and return (script_path, bash_command).

    The generated bash command will reference the script *relative to the YAML file*.
    """
    if not script_content:
        return None, None

    yaml = get_yaml()

    script_lines = bashify_script_items(script_content, yaml)
    if not script_lines:
        logger.debug("Skipping empty script block in job '%s' for key '%s'.", job_name, script_key)
        return None, None

    # Check if the script meets the minimum lines requirement
    if len(script_lines) < minimum_lines:
        logger.debug(
            "Skipping script block in job '%s' for key '%s' - only %d lines (minimum: %d)",
            job_name,
            script_key,
            len(script_lines),
            minimum_lines,
        )
        return None, None

    script_filename = create_script_filename(job_name, script_key)
    script_filepath = scripts_output_path / script_filename

    # Build header with conditional sourcing for local execution
    script_filename_path = Path(create_script_filename(job_name, script_key))
    file_ext = script_filename_path.suffix.lstrip(".")

    custom_shebangs = config.custom_shebangs or {"sh": "#!/bin/bash"}
    shebang = custom_shebangs.get(file_ext, SHEBANG)  # SHEBANG is the '#!/bin/bash' default

    header_parts: list[str] = [shebang]
    sourcing_block: list[str] = []
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

    logger.info("Decompileded script from '%s:%s' to '%s'", job_name, script_key, short_path(script_filepath))

    if not dry_run:
        script_filepath.parent.mkdir(parents=True, exist_ok=True)
        script_filepath.write_text(full_script_content, encoding="utf-8")
        script_filepath.chmod(0o755)

    # Compute bash command relative to YAML
    base = yaml_dir.resolve()
    target = script_filepath.resolve()
    relative_path = target.relative_to(base) if is_relative_to(target, base) else Path(script_filename)

    # Normalize to posix for YAML
    rel_str = str(relative_path).replace("\\", "/")
    if not rel_str.startswith(".") and "/" not in rel_str:
        rel_str = f"./{rel_str}"
    elif not rel_str.startswith("."):
        rel_str = "./" + rel_str

    return str(script_filepath), rel_str


def process_decompile_job(
    *,
    job_name: str,
    job_data: dict,
    scripts_output_path: Path,
    yaml_dir: Path,
    dry_run: bool = False,
    global_vars_filename: str | None = None,
    minimum_lines: int = 1,
) -> tuple[int, dict[str, str]]:
    """Process a single job definition to decompile its script and variables blocks.

    Returns (decompiled_count, scripts_info) where scripts_info maps script_key to filename.
    """
    decompiled_count = 0
    scripts_info: dict[str, str] = {}

    # Job-specific variables first
    job_vars_filename: str | None = None
    if isinstance(job_data.get("variables"), dict):
        sanitized_job_name = re.sub(r"[^\w.-]", "-", job_name.lower())
        sanitized_job_name = re.sub(r"-+", "-", sanitized_job_name).strip("-")
        job_vars_filename = decompile_variables_block(
            job_data["variables"], sanitized_job_name, scripts_output_path, dry_run=dry_run
        )
        if job_vars_filename:
            decompiled_count += 1

    # Script-like keys to decompile
    for key in ("script", "before_script", "after_script", "pre_get_sources_script"):
        if key in job_data and job_data[key]:
            _, command = decompile_script_block(
                script_content=job_data[key],
                job_name=job_name,
                script_key=key,
                scripts_output_path=scripts_output_path,
                yaml_dir=yaml_dir,
                dry_run=dry_run,
                global_vars_filename=global_vars_filename,
                job_vars_filename=job_vars_filename,
                minimum_lines=minimum_lines,
            )
            if command:
                job_data[key] = FoldedScalarString(command.replace("\\", "/"))
                decompiled_count += 1
                # Store just the filename for Makefile generation
                scripts_info[key] = command.lstrip("./")

    return decompiled_count, scripts_info


# --- public entry points -----------------------------------------------------


def iterate_yaml_files(root: Path) -> Iterable[Path]:
    yield from root.rglob("*.yml")
    yield from root.rglob("*.yaml")


def run_decompile_gitlab_file(
    *, input_yaml_path: Path, output_dir: Path, dry_run: bool = False, minimum_lines: int = 1
) -> tuple[int, int, Path]:
    """Decompile a *single* GitLab CI YAML file into scripts + modified YAML in *output_dir*.

    Returns (jobs_processed, total_files_created, output_yaml_path).
    """
    if not input_yaml_path.is_file():
        raise FileNotFoundError(f"Input YAML file not found: {input_yaml_path}")

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)  # force directory

    yaml = get_yaml()
    yaml.indent(mapping=2, sequence=4, offset=2)

    logger.info("Loading GitLab CI configuration from: %s", short_path(input_yaml_path))
    data = yaml.load(input_yaml_path)

    # Layout: write YAML and scripts side-by-side under output_dir[/subdirs]
    output_yaml_path = output_dir / input_yaml_path.name
    scripts_dir = output_yaml_path.parent
    yaml_dir = output_yaml_path.parent

    jobs_processed = 0
    total_files_created = 0
    jobs_info: dict[str, dict[str, str]] = {}

    # Top-level variables -> global_variables.sh next to YAML
    global_vars_filename: str | None = None
    if isinstance(data.get("variables"), dict):
        logger.info("Processing global variables block.")
        global_vars_filename = decompile_variables_block(data["variables"], "global", scripts_dir, dry_run=dry_run)
        if global_vars_filename:
            total_files_created += 1

    # Jobs
    for key, value in data.items():
        if isinstance(value, dict) and "script" in value:
            logger.debug("Processing job: %s", key)
            jobs_processed += 1
            decompiled_count, scripts_info = process_decompile_job(
                job_name=key,
                job_data=value,
                scripts_output_path=scripts_dir,
                yaml_dir=yaml_dir,
                dry_run=dry_run,
                global_vars_filename=global_vars_filename,
                minimum_lines=minimum_lines,
            )
            total_files_created += decompiled_count
            if scripts_info:
                jobs_info[key] = scripts_info

    if total_files_created > 0:
        logger.info("Decompileded %s file(s) from %s job(s).", total_files_created, jobs_processed)
        if not dry_run:
            logger.info("Writing modified YAML to: %s", short_path(output_yaml_path))
            output_yaml_path.parent.mkdir(parents=True, exist_ok=True)
            with output_yaml_path.open("w", encoding="utf-8") as f:
                yaml.dump(data, f)
            with output_yaml_path.open() as f:
                new_content = f.read()
                validator = GitLabCIValidator()
                ok, problems = validator.validate_ci_config(new_content)
                if not ok:
                    raise Exception(problems)
    else:
        logger.info("No script or variable blocks found to decompile.")

    # Generate Makefile if we have jobs
    if jobs_info:
        generate_makefile(jobs_info, output_dir, dry_run=dry_run)
        if not dry_run:
            total_files_created += 1  # Count the Makefile

    if not dry_run:
        output_yaml_path.parent.mkdir(exist_ok=True)
        generate_mock_ci_variables_script(str(output_yaml_path.parent / "mock_ci_variables.sh"))

    return jobs_processed, total_files_created, output_yaml_path


def run_decompile_gitlab_tree(
    *, input_root: Path, output_dir: Path, dry_run: bool = False, minimum_lines: int = 1
) -> tuple[int, int, int]:
    """Decompile *all* ``*.yml`` / ``*.yaml`` under ``input_root`` into ``output_dir``.

    The relative directory structure under ``input_root`` is preserved in ``output_dir``.

    Returns (yaml_files_processed, total_jobs_processed, total_files_created).
    """
    if not input_root.is_dir():
        raise FileNotFoundError(f"Input folder not found: {input_root}")

    yaml_files_processed = 0
    total_jobs = 0
    total_created = 0

    for in_file in iterate_yaml_files(input_root):
        rel_dir = in_file.parent.relative_to(input_root)
        out_subdir = (output_dir / rel_dir).resolve()
        jobs, created, _ = run_decompile_gitlab_file(
            input_yaml_path=in_file, output_dir=out_subdir, dry_run=dry_run, minimum_lines=minimum_lines
        )
        yaml_files_processed += 1
        total_jobs += jobs
        total_created += created

    return yaml_files_processed, total_jobs, total_created
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
from collections.abc import Generator
from pathlib import Path

__all__ = ["run_detect_drift"]

from bash2gitlab.utils.terminal_colors import Colors
from bash2gitlab.utils.utils import short_path

# Setting up a logger for this module. The calling application can configure the handler.
logger = logging.getLogger(__name__)


def decode_hash_content(hash_file: Path) -> str | None:
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


def get_source_file_from_hash(hash_file: Path) -> Path:
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


def generate_pretty_diff(source_content: str, decoded_content: str, source_file_path: Path) -> str:
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
        logger.info(f"Searching for .hash files in: {short_path(search_path)}")
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
        source_file = get_source_file_from_hash(hash_file)

        if not source_file.exists():
            logger.error(f"Drift check failed: Source file '{source_file}' is missing for hash file '{hash_file}'.")
            error_count += 1
            continue

        decoded_content = decode_hash_content(hash_file)
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
            diff_text = generate_pretty_diff(current_content, decoded_content, source_file)

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
## File: commands\doctor.py
```python
from __future__ import annotations

import logging
import re
import shutil
import subprocess  # nosec
from pathlib import Path

from bash2gitlab.commands.clean_all import list_stray_files as list_stray_output_files
from bash2gitlab.commands.graph_all import find_script_references_in_node
from bash2gitlab.config import config
from bash2gitlab.utils.terminal_colors import Colors
from bash2gitlab.utils.yaml_factory import get_yaml

logger = logging.getLogger(__name__)

__all__ = ["run_doctor"]


def check(message: str, success: bool) -> bool:
    """Prints a formatted check message and returns the success status."""
    status = f"{Colors.OKGREEN}✔ OK{Colors.ENDC}" if success else f"{Colors.FAIL}✖ FAILED{Colors.ENDC}"
    print(f"  [{status}] {message}")
    return success


def get_command_version(cmd: str) -> str:
    """Gets the version of a command-line tool."""
    if not shutil.which(cmd):
        return f"{Colors.WARNING}not found{Colors.ENDC}"
    try:
        result = subprocess.run(  # nosec
            [cmd, "--version"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        # Get the first line of output and strip whitespace
        return result.stdout.splitlines()[0].strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.debug(f"Could not get version for {cmd}: {e}")
        return f"{Colors.FAIL}Error checking version{Colors.ENDC}"


def find_unreferenced_source_files(uncompiled_path: Path) -> set[Path]:
    """Finds script files in the source directory that are not referenced by any YAML."""
    root_path = uncompiled_path.resolve()
    all_scripts = set(root_path.rglob("*.sh")) | set(root_path.rglob("*.py"))
    referenced_scripts: set[Path] = set()
    # processed_scripts: set[Path] = set()  # To avoid cycles in script parsing

    yaml_parser = get_yaml()
    template_files = list(root_path.rglob("*.yml")) + list(root_path.rglob("*.yaml"))

    # Build a set of all referenced scripts by adapting graph logic
    for yaml_path in template_files:
        try:
            content = yaml_path.read_text("utf-8")
            yaml_data = yaml_parser.load(content)
            if yaml_data:
                # Dummy graph, we only care about the side effect on referenced_scripts
                dummy_graph: dict[Path, set[Path]] = {}
                find_script_references_in_node(
                    yaml_data, yaml_path, root_path, dummy_graph, processed_scripts=referenced_scripts
                )

        except Exception:  # nosec
            # Ignore parsing errors, focus is on finding valid references
            pass

    # The above only adds the top-level scripts. Now, find sourced scripts.
    scripts_to_scan = list(referenced_scripts)
    scanned_for_source: set[Path] = set()

    while scripts_to_scan:
        script = scripts_to_scan.pop(0)
        if script in scanned_for_source or not script.is_file():
            continue
        scanned_for_source.add(script)
        try:
            content = script.read_text("utf-8")
            for line in content.splitlines():
                match = re.search(r"^\s*(?:source|\.)\s+([\w./\\-]+)", line)
                if match:
                    sourced_path = (script.parent / match.group(1)).resolve()
                    if sourced_path.is_file() and sourced_path not in referenced_scripts:
                        referenced_scripts.add(sourced_path)
                        scripts_to_scan.append(sourced_path)

        except Exception:  # nosec
            pass

    return all_scripts - referenced_scripts


def run_doctor() -> int:
    """Runs a series of health checks on the project and environment."""
    print(f"{Colors.BOLD}🩺 Running bash2gitlab doctor...{Colors.ENDC}\n")
    issues_found = 0

    # --- Configuration Checks ---
    print(f"{Colors.BOLD}Configuration:{Colors.ENDC}")
    input_dir_str = config.input_dir
    output_dir_str = config.output_dir

    if check("Input directory is configured", bool(input_dir_str)):
        input_dir = Path(input_dir_str or "")
        if not check(f"Input directory exists: '{input_dir}'", input_dir.is_dir()):
            issues_found += 1
    else:
        issues_found += 1

    if check("Output directory is configured", bool(output_dir_str)):
        output_dir = Path(output_dir_str or "")
        if not check(f"Output directory exists: '{output_dir}'", output_dir.is_dir()):
            print(f"  {Colors.WARNING}  -> Note: This is not an error if you haven't compiled yet.{Colors.ENDC}")
    else:
        issues_found += 1

    # --- External Dependencies ---
    print(f"\n{Colors.BOLD}External Dependencies:{Colors.ENDC}")
    print(f"  - Bash version: {get_command_version('bash')}")
    print(f"  - Git version:  {get_command_version('git')}")
    print(f"  - PowerShell:   {get_command_version('pwsh')}")

    # --- Project Health ---
    print(f"\n{Colors.BOLD}Project Health:{Colors.ENDC}")
    if input_dir_str and Path(input_dir_str).is_dir():
        unreferenced_files = find_unreferenced_source_files(Path(input_dir_str))
        if unreferenced_files:
            issues_found += 1
            check("No unreferenced script files in source directory", False)
            for f in sorted(unreferenced_files):
                print(f"    {Colors.WARNING}  -> Stray source file: {f.relative_to(input_dir_str)}{Colors.ENDC}")
        else:
            check("No unreferenced script files in source directory", True)

    if output_dir_str and Path(output_dir_str).is_dir():
        stray_files = list_stray_output_files(Path(output_dir_str))
        if stray_files:
            issues_found += 1
            check("No unhashed/stray files in output directory", False)
            for f in sorted(stray_files):
                print(f"    {Colors.WARNING}  -> Stray output file: {f.relative_to(output_dir_str)}{Colors.ENDC}")
        else:
            check("No unhashed/stray files in output directory", True)

    # --- Summary ---
    print("-" * 40)
    if issues_found == 0:
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}✅ All checks passed. Your project looks healthy!{Colors.ENDC}")
        return 0

    print(
        f"\n{Colors.FAIL}{Colors.BOLD}✖ Doctor found {issues_found} issue(s). Please review the output above.{Colors.ENDC}"
    )
    return 1
```
## File: commands\graph_all.py
```python
from __future__ import annotations

import logging
import os
import webbrowser
from pathlib import Path
from typing import Any, Literal

try:
    import matplotlib.pyplot as plt
    import networkx as nx
    from graphviz import Source
    from pyvis.network import Network
except ModuleNotFoundError:
    pass
from ruamel.yaml.error import YAMLError

from bash2gitlab.commands.compile_bash_reader import SOURCE_COMMAND_REGEX
from bash2gitlab.utils.parse_bash import extract_script_path
from bash2gitlab.utils.pathlib_polyfills import is_relative_to
from bash2gitlab.utils.temp_env import temporary_env_var
from bash2gitlab.utils.utils import short_path
from bash2gitlab.utils.yaml_factory import get_yaml

logger = logging.getLogger(__name__)

__all__ = ["generate_dependency_graph", "find_script_references_in_node"]


def format_dot_output(graph: dict[Path, set[Path]], root_path: Path) -> str:
    """Formats the dependency graph into the DOT language."""
    dot_lines = [
        "digraph bash2gitlab {",
        "    rankdir=LR;",
        "    node [shape=box, style=rounded];",
        "    graph [bgcolor=transparent];",
        '    edge [color="#cccccc"];',
        '    node [fontname="Inter", fontsize=10];',
        "    subgraph cluster_yaml {",
        '        label="YAML Sources";',
        '        style="rounded";',
        '        color="#0066cc";',
        '        node [style="filled,rounded", fillcolor="#e6f0fa", color="#0066cc"];',
    ]

    # YAML nodes
    yaml_files = {n for n in graph if n.suffix.lower() in (".yml", ".yaml")}
    for f in sorted(yaml_files):
        rel = f.relative_to(root_path)
        dot_lines.append(f'        "{rel}" [label="{rel}"];')
    dot_lines.append("    }")

    # Script nodes
    dot_lines.append("    subgraph cluster_scripts {")
    dot_lines.append('        label="Scripts";')
    dot_lines.append('        style="rounded";')
    dot_lines.append('        color="#22863a";')
    dot_lines.append('        node [style="filled,rounded", fillcolor="#e9f3ea", color="#22863a"];')

    script_files = {n for n in graph if n not in yaml_files}
    for deps in graph.values():
        script_files.update(d for d in deps if d not in yaml_files)

    for f in sorted(script_files):
        rel = f.relative_to(root_path)
        dot_lines.append(f'        "{rel}" [label="{rel}"];')
    dot_lines.append("    }")

    # Edges
    for src, deps in sorted(graph.items()):
        s_rel = src.relative_to(root_path)
        for dep in sorted(deps):
            d_rel = dep.relative_to(root_path)
            dot_lines.append(f'    "{s_rel}" -> "{d_rel}";')

    dot_lines.append("}")
    return "\n".join(dot_lines)


def parse_shell_script_dependencies(
    script_path: Path,
    root_path: Path,
    graph: dict[Path, set[Path]],
    processed_files: set[Path],
) -> None:
    """Recursively parses a shell script to find `source` dependencies."""
    if script_path in processed_files:
        return
    processed_files.add(script_path)

    if not script_path.is_file():
        logger.warning(f"Dependency not found and will be skipped: {script_path}")
        return

    graph.setdefault(script_path, set())

    try:
        content = script_path.read_text("utf-8")
        for line in content.splitlines():
            match = SOURCE_COMMAND_REGEX.match(line)
            if match:
                sourced_script_name = match.group("path")
                sourced_path = (script_path.parent / sourced_script_name).resolve()

                if not is_relative_to(sourced_path, root_path):
                    logger.error(f"Refusing to trace source '{sourced_path}': escapes allowed root '{root_path}'.")
                    continue

                graph[script_path].add(sourced_path)
                parse_shell_script_dependencies(sourced_path, root_path, graph, processed_files)
    except Exception as e:
        logger.error(f"Failed to read or parse script {script_path}: {e}")


def find_script_references_in_node(
    node: Any,
    yaml_path: Path,
    root_path: Path,
    graph: dict[Path, set[Path]],
    processed_scripts: set[Path],
) -> None:
    """Recursively traverses the YAML data structure to find script references."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("script", "before_script", "after_script"):
                find_script_references_in_node(value, yaml_path, root_path, graph, processed_scripts)
            else:
                find_script_references_in_node(value, yaml_path, root_path, graph, processed_scripts)
    elif isinstance(node, list):
        for item in node:
            find_script_references_in_node(item, yaml_path, root_path, graph, processed_scripts)
    elif isinstance(node, str):
        script_path_str = extract_script_path(node)
        if script_path_str:
            script_path = (yaml_path.parent / script_path_str).resolve()
            if not is_relative_to(script_path, root_path):
                logger.error(f"Refusing to trace script '{script_path}': escapes allowed root '{root_path}'.")
                return
            graph.setdefault(yaml_path, set()).add(script_path)
            parse_shell_script_dependencies(script_path, root_path, graph, processed_scripts)


def _render_with_graphviz(dot_output: str, filename_base: str) -> Path:
    src = Source(dot_output)
    out_file = src.render(
        filename=filename_base,
        directory=str(Path.cwd()),
        format="svg",
        cleanup=True,
    )
    return Path(out_file)


def _render_with_pyvis(graph: dict[Path, set[Path]], root_path: Path, filename_base: str) -> Path:
    # Pure-Python interactive HTML (vis.js)

    html_path = Path.cwd() / f"{filename_base}.html"
    net = Network(height="750px", width="100%", directed=True, cdn_resources="in_line")

    yaml_nodes = {n for n in graph if n.suffix.lower() in (".yml", ".yaml")}
    script_nodes = set()
    for deps in graph.values():
        script_nodes.update(deps)
    script_nodes |= {n for n in graph if n not in yaml_nodes}

    # Add nodes with lightweight styling
    for n in sorted(yaml_nodes):
        rel = str(n.relative_to(root_path))
        net.add_node(rel, label=rel, title=rel, shape="box", color="#e6f0fa")
    for n in sorted(script_nodes):
        rel = str(n.relative_to(root_path))
        net.add_node(rel, label=rel, title=rel, shape="box", color="#e9f3ea")

    # Add edges
    for src, deps in graph.items():
        s_rel = str(src.relative_to(root_path))
        for dep in deps:
            d_rel = str(dep.relative_to(root_path))
            net.add_edge(s_rel, d_rel, arrows="to")

    # Write once; don't auto-open here (caller decides)
    net.write_html(str(html_path), open_browser=False)
    return html_path


def _render_with_networkx(graph: dict[Path, set[Path]], root_path: Path, filename_base: str) -> Path:
    out_path = Path.cwd() / f"{filename_base}.svg"
    G = nx.DiGraph()

    yaml_nodes = {n for n in graph if n.suffix.lower() in (".yml", ".yaml")}
    script_nodes = set()
    for deps in graph.values():
        script_nodes.update(deps)
    script_nodes |= {n for n in graph if n not in yaml_nodes}

    def rel(p: Path) -> str:
        return str(p.relative_to(root_path))

    # Build graph
    for n in yaml_nodes | script_nodes:
        G.add_node(rel(n))
    for src, deps in graph.items():
        for dep in deps:
            G.add_edge(rel(src), rel(dep))

    # Layout & draw
    pos = nx.spring_layout(G, seed=42)
    plt.figure(figsize=(12, 6))
    nx.draw_networkx_nodes(G, pos, nodelist=[rel(n) for n in yaml_nodes])
    nx.draw_networkx_nodes(G, pos, nodelist=[rel(n) for n in script_nodes])
    nx.draw_networkx_edges(G, pos, arrows=True)
    nx.draw_networkx_labels(G, pos, font_size=8)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(out_path, format="svg")
    plt.close()
    return out_path


def generate_dependency_graph(
    uncompiled_path: Path,
    *,
    open_graph_in_browser: bool = True,
    renderer: Literal["auto", "graphviz", "pyvis", "networkx"] = "auto",
    attempts: int = 0,
    renderers_attempted: set[str] | None = None,
) -> str:
    """
    Analyze YAML + scripts to build a dependency graph.

    Args:
        uncompiled_path: Root directory of the uncompiled source files.
        open_graph_in_browser: If True, write a graph file to CWD and open it.
        renderer: "graphviz", "pyvis", "networkx", or "auto" (try in that order).
        attempts: how many renderers attempted
        renderers_attempted: which were tried

    Returns:
        DOT graph as a string (stdout responsibility is left to the caller).
    """
    auto_mode = renderer == "auto"
    graph: dict[Path, set[Path]] = {}
    processed_scripts: set[Path] = set()
    yaml_parser = get_yaml()
    root_path = uncompiled_path.resolve()

    logger.info(f"Starting dependency graph generation in: {short_path(root_path)}")

    template_files = list(root_path.rglob("*.yml")) + list(root_path.rglob("*.yaml"))
    if not template_files:
        logger.warning(f"No YAML files found in {root_path}")
        return ""

    for yaml_path in template_files:
        logger.debug(f"Parsing YAML file: {yaml_path}")
        graph.setdefault(yaml_path, set())
        try:
            content = yaml_path.read_text("utf-8")
            yaml_data = yaml_parser.load(content)
            if yaml_data:
                find_script_references_in_node(yaml_data, yaml_path, root_path, graph, processed_scripts)
        except YAMLError as e:
            logger.error(f"Failed to parse YAML file {yaml_path}: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred with {yaml_path}: {e}")

    logger.info(f"Found {len(graph)} source files and traced {len(processed_scripts)} script dependencies.")

    dot_output = format_dot_output(graph, root_path)
    logger.info("Successfully generated DOT graph output.")

    if open_graph_in_browser:
        filename_base = f"dependency-graph-{root_path.name}".replace(" ", "_")

        def _auto_pick() -> str:
            try:
                import graphviz  # noqa: F401

                return "graphviz"
            except Exception:
                try:
                    import pyvis  # noqa: F401

                    return "pyvis"
                except Exception:
                    try:
                        import matplotlib  # noqa: F401
                        import networkx  # noqa: F401

                        return "networkx"
                    except Exception:
                        return "none"

        chosen = _auto_pick() if renderer == "auto" else renderer

        try:
            # pyvis needs utf-8 but doesn't explicitly set it so it fails on Windows.
            with temporary_env_var("PYTHONUTF8", "1"):
                if chosen == "graphviz":
                    # best, but requires additional installation
                    out_path = _render_with_graphviz(dot_output, filename_base)
                elif chosen == "pyvis":
                    # not at godo as graphviz
                    out_path = _render_with_pyvis(graph, root_path, filename_base)
                elif chosen == "networkx":
                    # can be a messy diagram
                    out_path = _render_with_networkx(graph, root_path, filename_base)
                else:
                    raise RuntimeError(
                        "No suitable renderer available. Install one of: graphviz, pyvis, networkx+matplotlib."
                    )

            logger.info("Wrote graph to %s", short_path(out_path))
            if not os.environ.get("CI"):
                webbrowser.open(out_path.as_uri())
        except Exception as e:  # pragma: no cover - env dependent
            logger.error("Failed to render or open the graph: %s", e)
            if (1 < attempts < 4 and len(renderers_attempted or {}) < 3) or auto_mode:
                if not renderers_attempted:
                    renderers_attempted = set()
                renderers_attempted.add(renderer)
                attempts += 1
                return generate_dependency_graph(
                    uncompiled_path,
                    open_graph_in_browser=open_graph_in_browser,
                    attempts=attempts,
                    renderers_attempted=renderers_attempted,
                )

    return dot_output
```
## File: commands\init_project.py
```python
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
```
## File: commands\input_change_detector.py
```python
"""Input change detection for bash2gitlab compilation.

This module provides functionality to detect if input files have changed since
the last compilation, allowing for efficient incremental builds.
"""

from __future__ import annotations

import hashlib
import logging
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML

from bash2gitlab.utils.yaml_factory import get_yaml

logger = logging.getLogger(__name__)


def normalize_yaml_content(content: str) -> str:
    """Normalize YAML content by loading and dumping to remove formatting differences."""
    try:
        yaml = get_yaml()
        data = yaml.load(content)
        # Use a clean YAML dumper for normalization

        norm_yaml = YAML()
        norm_yaml.preserve_quotes = False
        norm_yaml.default_flow_style = False

        output = StringIO()
        norm_yaml.dump(data, output)
        return output.getvalue()
    except Exception as e:
        logger.warning(f"Failed to normalize YAML content: {e}. Using original content.")
        return content


def normalize_text_content(content: str) -> str:
    """Normalize text content by removing all whitespace."""
    return "".join(content.split())


def compute_content_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of file content, normalized appropriately."""
    content = file_path.read_text(encoding="utf-8")

    # Normalize based on file type
    if file_path.suffix.lower() in {".yml", ".yaml"}:
        normalized_content = normalize_yaml_content(content)
    else:
        normalized_content = normalize_text_content(content)

    return hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()


def _read_stored_hash(hash_file: Path) -> str | None:
    """Read stored hash from hash file."""
    try:
        if hash_file.exists():
            return hash_file.read_text(encoding="utf-8").strip()
    except Exception as e:
        logger.warning(f"Failed to read hash file {hash_file}: {e}")
    return None


def _write_hash(hash_file: Path, content_hash: str) -> None:
    """Write hash to hash file."""
    try:
        hash_file.parent.mkdir(parents=True, exist_ok=True)
        hash_file.write_text(content_hash, encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to write hash file {hash_file}: {e}")


class InputChangeDetector:
    """Detects changes in input files since last compilation."""

    def __init__(self, base_path: Path, hash_dir_name: str = ".bash2gitlab"):
        """Initialize change detector.

        Args:
            base_path: Base directory for the project
            hash_dir_name: Name of directory to store hash files
        """
        self.base_path = base_path
        self.hash_dir = base_path / hash_dir_name / "input_hashes"

    def _get_hash_file_path(self, input_file: Path) -> Path:
        """Get the hash file path for an input file."""
        # Create a mirror directory structure in the hash directory
        try:
            rel_path = input_file.relative_to(self.base_path)
        except ValueError:
            # If input_file is not relative to base_path, use absolute path conversion
            rel_path = Path(str(input_file).lstrip("/\\").replace(":", "_"))

        hash_file = self.hash_dir / rel_path.with_suffix(rel_path.suffix + ".hash")
        return hash_file

    def has_file_changed(self, file_path: Path) -> bool:
        """Check if a single file has changed since last compilation.

        Args:
            file_path: Path to the input file to check

        Returns:
            True if file has changed or no previous hash exists, False otherwise
        """
        if not file_path.exists():
            logger.warning(f"Input file does not exist: {file_path}")
            return True

        hash_file = self._get_hash_file_path(file_path)
        stored_hash = _read_stored_hash(hash_file)

        if stored_hash is None:
            logger.debug(f"No previous hash for {file_path}, considering changed")
            return True

        current_hash = compute_content_hash(file_path)
        changed = current_hash != stored_hash

        if changed:
            logger.debug(f"File changed: {file_path}")
        else:
            logger.debug(f"File unchanged: {file_path}")

        return changed

    def needs_compilation(self, input_dir: Path) -> bool:
        """Check if any input file in the directory has changed.

        Args:
            input_dir: Directory containing input files

        Returns:
            True if any file has changed, False if all files are unchanged
        """
        if not input_dir.exists():
            logger.warning(f"Input directory does not exist: {input_dir}")
            return True

        # Get all relevant input files
        input_files: list[Path] = []
        for pattern in ["*.yml", "*.yaml", "*.sh", "*.py", "*.js", "*.rb", "*.php", "*.fish"]:
            input_files.extend(input_dir.rglob(pattern))

        if not input_files:
            logger.info(f"No input files found in {input_dir}")
            return False

        # Check if any file has changed
        for file_path in input_files:
            if self.has_file_changed(file_path):
                logger.info(f"Compilation needed: {file_path} has changed")
                return True

        logger.info("No input files have changed, compilation not needed")
        return False

    def get_changed_files(self, input_dir: Path) -> list[Path]:
        """Get list of files that have changed since last compilation.

        Args:
            input_dir: Directory containing input files

        Returns:
            List of paths to files that have changed
        """
        if not input_dir.exists():
            return []

        changed_files = []

        # Get all relevant input files
        input_files: list[Path] = []
        for pattern in ["*.yml", "*.yaml", "*.sh", "*.py", "*.js", "*.rb", "*.php", "*.fish"]:
            input_files.extend(input_dir.rglob(pattern))

        for file_path in input_files:
            if self.has_file_changed(file_path):
                changed_files.append(file_path)

        return changed_files

    def mark_compiled(self, input_dir: Path) -> None:
        """Mark all input files as compiled by updating their hashes.

        Args:
            input_dir: Directory containing input files that were compiled
        """
        if not input_dir.exists():
            logger.warning(f"Input directory does not exist: {input_dir}")
            return

        # Get all relevant input files
        input_files: list[Path] = []
        for pattern in ["*.yml", "*.yaml", "*.sh", "*.py", "*.js", "*.rb", "*.php", "*.fish"]:
            input_files.extend(input_dir.rglob(pattern))

        for file_path in input_files:
            try:
                current_hash = compute_content_hash(file_path)
                hash_file = self._get_hash_file_path(file_path)
                _write_hash(hash_file, current_hash)
                logger.debug(f"Updated hash for {file_path}")
            except Exception as e:
                logger.warning(f"Failed to update hash for {file_path}: {e}")

    def cleanup_stale_hashes(self, input_dir: Path) -> None:
        """Remove hash files for input files that no longer exist.

        Args:
            input_dir: Directory containing current input files
        """
        if not self.hash_dir.exists():
            return

        # Get current input files
        current_files: set[Path] = set()
        if input_dir.exists():
            for pattern in ["*.yml", "*.yaml", "*.sh", "*.py", "*.js", "*.rb", "*.php", "*.fish"]:
                current_files.update(input_dir.rglob(pattern))

        # Find and remove stale hash files
        removed_count = 0
        for hash_file in self.hash_dir.rglob("*.hash"):
            # Reconstruct the original file path
            try:
                rel_path = hash_file.relative_to(self.hash_dir)
                original_path = self.base_path / rel_path.with_suffix(rel_path.suffixes[0])  # Remove .hash

                if original_path not in current_files:
                    hash_file.unlink()
                    removed_count += 1
                    logger.debug(f"Removed stale hash file: {hash_file}")
            except Exception as e:
                logger.warning(f"Error processing hash file {hash_file}: {e}")

        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} stale hash files")


# Convenience functions for drop-in replacement
def needs_compilation(input_dir: Path, base_path: Path | None = None) -> bool:
    """Check if compilation is needed for input directory.

    Args:
        input_dir: Directory containing input files
        base_path: Base path for hash storage (defaults to input_dir)

    Returns:
        True if compilation is needed, False otherwise
    """
    if base_path is None:
        base_path = input_dir

    detector = InputChangeDetector(base_path)
    return detector.needs_compilation(input_dir)


def mark_compilation_complete(input_dir: Path, base_path: Path | None = None) -> None:
    """Mark compilation as complete for input directory.

    Args:
        input_dir: Directory containing input files that were compiled
        base_path: Base path for hash storage (defaults to input_dir)
    """
    if base_path is None:
        base_path = input_dir

    detector = InputChangeDetector(base_path)
    detector.mark_compiled(input_dir)


def get_changed_files(input_dir: Path, base_path: Path | None = None) -> list[Path]:
    """Get list of changed files in input directory.

    Args:
        input_dir: Directory containing input files
        base_path: Base path for hash storage (defaults to input_dir)

    Returns:
        List of paths to files that have changed
    """
    if base_path is None:
        base_path = input_dir

    detector = InputChangeDetector(base_path)
    return detector.get_changed_files(input_dir)
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
from functools import partial
from pathlib import Path
from urllib import error, request

from bash2gitlab.utils.utils import short_path

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


def api_url(
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


def post_json(
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
    url = api_url(gitlab_url, project_id)

    payload: dict = {"content": content}

    # Project-scoped knobs
    if project_id is not None and ref is not None:
        payload["ref"] = ref
    if project_id is not None and include_merged_yaml:
        payload["include_merged_yaml"] = True

    resp = post_json(url, payload, private_token=private_token, timeout=timeout)

    # GitLab returns varying shapes across versions. Normalize defensively.
    status = str(resp.get("status") or ("valid" if resp.get("valid") else "invalid"))
    valid = bool(resp.get("valid", status == "valid"))

    def collect(kind: str) -> list[LintIssue]:
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

    errors = collect("errors")
    warnings = collect("warnings")
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


def discover_yaml_files(root: Path) -> list[Path]:
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
    files = discover_yaml_files(output_root)
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
            logger.info("OK: %s", short_path(r.path))
            if r.warnings:
                for w in r.warnings:
                    logger.warning("%s: %s", short_path(r.path), w.message)
        else:
            logger.error("INVALID: %s (status=%s)", short_path(r.path), r.status)
            for e in r.errors:
                if e.line is not None:
                    logger.error("%s:%s: %s", short_path(r.path), e.line, e.message)
                else:
                    logger.error("%s: %s", short_path(r.path), e.message)

    logger.info("Lint summary: %d ok, %d failed", ok, fail)
    return ok, fail
```
## File: commands\map_commit.py
```python
"""
Syncs changes from multiple target folders back to a single source folder.
This is intended to be fed by a TOML configuration file where users can easily
map one source directory to a list of target/deployed directories.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from collections.abc import Collection
from pathlib import Path

from bash2gitlab.commands.compile_not_bash import _INTERPRETER_EXTS

__all__ = ["run_commit_map"]


_VALID_SUFFIXES = {".sh", ".ps1", ".yml", ".yaml", ".bash"}

for _key, value in _INTERPRETER_EXTS.items():
    _VALID_SUFFIXES.update(value)

_CHUNK_SIZE = 65536  # 64kb

logger = logging.getLogger(__name__)


def _calculate_file_hash(file_path: Path) -> str | None:
    """Calculates the SHA256 hash of a file, returning None if it doesn't exist."""
    if not file_path.is_file():
        return None

    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(_CHUNK_SIZE):
            sha256.update(chunk)
    return sha256.hexdigest()


def _sync_single_target_to_source(
    source_base_path: Path,
    target_base_path: Path,
    dry_run: bool,
    force: bool,
) -> None:
    """Helper to sync one target directory back to the source."""
    if not target_base_path.is_dir():
        print(f"Warning: Target directory '{target_base_path}' does not exist. Skipping.")
        return

    print(f"\nProcessing sync: '{target_base_path}' -> '{source_base_path}'")

    for target_file_path in target_base_path.rglob("*"):
        # Skip directories and non-file types
        if not target_file_path.is_file():
            continue

        # Skip ignored files
        if (
            target_file_path.name == ".gitignore"
            or target_file_path.suffix == ".hash"
            or target_file_path.suffix.lower() not in _VALID_SUFFIXES
        ):
            continue

        relative_path = target_file_path.relative_to(target_base_path)
        source_file_path = source_base_path / relative_path
        hash_file_path = target_file_path.with_suffix(target_file_path.suffix + ".hash")

        target_hash = _calculate_file_hash(target_file_path)
        stored_hash = hash_file_path.read_text().strip() if hash_file_path.exists() else None

        # Case 1: File is unchanged since last deployment/sync.
        if stored_hash and target_hash == stored_hash:
            # Using logger.debug for unchanged files to reduce noise
            logger.debug(f"Unchanged: '{target_file_path}'")
            continue

        # Case 2: Source file was modified locally since deployment.
        source_hash = _calculate_file_hash(source_file_path)
        if stored_hash and source_hash and source_hash != stored_hash and not force:
            print(f"Warning: Source file '{source_file_path}' was modified locally.")
            print("         Skipping sync. Use --force to overwrite.")
            continue

        # Case 3: File in target has changed, proceed with sync.
        action = "Creating" if not source_file_path.exists() else "Updating"
        print(f"{action}: '{source_file_path}' (from '{target_file_path}')")

        if not dry_run:
            # Ensure the destination directory exists
            source_file_path.parent.mkdir(parents=True, exist_ok=True)
            # Copy file and its metadata
            shutil.copy2(target_file_path, source_file_path)
            # Update the hash file in the target directory to reflect the new state
            hash_file_path.write_text(target_hash or "")


def run_commit_map(
    deployment_map: dict[str, list[str] | Collection[str]],
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """
    Syncs modified files from target directories back to their source directory.

    For each source directory, this function iterates through its corresponding
    list of target (deployed) directories. It detects changes in the target
    files by comparing their current content hash against a stored hash in a
    parallel '.hash' file.

    If a file has changed in the target, it is copied back to the source,
    overwriting the original.

    Args:
        deployment_map: A mapping where each key is a source directory and the
            value is a list of target directories where the source content
            was deployed.
        dry_run: If ``True``, simulates the sync and prints actions without
            modifying any files.
        force: If ``True``, a source file will be overwritten even if it was
            modified locally since the last deployment.
    """
    for source_base, target_bases in deployment_map.items():
        source_base_path = Path(source_base).resolve()

        if not isinstance(target_bases, (list, tuple, set)):
            logger.error(f"Invalid format for '{source_base}'. Targets must be a list. Skipping.")
            continue

        for target_base in target_bases:
            target_base_path = Path(target_base).resolve()
            _sync_single_target_to_source(source_base_path, target_base_path, dry_run, force)
```
## File: commands\map_deploy.py
```python
"""
Deploys scripts from a central source directory to multiple target directories.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from collections.abc import Collection
from pathlib import Path

from bash2gitlab.commands.compile_not_bash import _INTERPRETER_EXTS

__all__ = ["run_map_deploy"]

from bash2gitlab.utils.utils import short_path

_VALID_SUFFIXES = {".sh", ".ps1", ".yml", ".yaml", ".bash"}

for _key, value in _INTERPRETER_EXTS.items():
    _VALID_SUFFIXES.update(value)

_CHUNK_SIZE = 65536  # 64kb

logger = logging.getLogger(__name__)


def calculate_file_hash(file_path: Path) -> str | None:
    """Calculates the SHA256 hash of a file, returning None if it doesn't exist."""
    if not file_path.is_file():
        return None

    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in chunks to handle large files efficiently
        while chunk := f.read(_CHUNK_SIZE):
            sha256.update(chunk)
    return sha256.hexdigest()


def deploy_to_single_target(
    source_base_path: Path,
    target_base_path: Path,
    dry_run: bool,
    force: bool,
) -> None:
    """
    Helper function to handle the deployment logic for one source-to-target pair.
    """
    logger.info(f"\nProcessing deployment: '{short_path(source_base_path)}' -> '{short_path(target_base_path)}'")

    # Create target directory and .gitignore if they don't exist
    if not dry_run:
        target_base_path.mkdir(parents=True, exist_ok=True)
        gitignore_path = target_base_path / ".gitignore"
        if not gitignore_path.exists():
            logger.info(f"Creating .gitignore in '{short_path(target_base_path)}'")
            gitignore_path.write_text("*\n")
    else:
        if not target_base_path.exists():
            logger.info(f"DRY RUN: Would create directory '{short_path(target_base_path)}'")
        if not (target_base_path / ".gitignore").exists():
            logger.info(f"DRY RUN: Would create .gitignore in '{short_path(target_base_path)}'")

    # Use rglob for efficient recursive file searching
    for source_file_path in source_base_path.rglob("*"):
        if not source_file_path.is_file() or source_file_path.suffix.lower() not in _VALID_SUFFIXES:
            continue

        relative_path = source_file_path.relative_to(source_base_path)
        target_file_path = target_base_path / relative_path
        hash_file_path = target_file_path.with_suffix(target_file_path.suffix + ".hash")

        source_hash = calculate_file_hash(source_file_path)

        # Check for modifications at the destination if the file exists
        if target_file_path.exists():
            target_hash = calculate_file_hash(target_file_path)
            stored_hash = hash_file_path.read_text().strip() if hash_file_path.exists() else None

            # Case 1: Target file was modified locally since last deployment.
            if stored_hash and target_hash != stored_hash:
                logger.warning(f"Warning: Target '{short_path(target_file_path)}' was modified locally.")
                if not force:
                    logger.warning("         Skipping copy. Use --force to overwrite.")
                    continue
                logger.warning("         Forcing overwrite.")

            # Case 2: Target file is identical to the source file.
            if source_hash == target_hash:
                logger.debug(f"Unchanged: '{short_path(target_file_path)}'")
                continue

        # If we reach here, we need to copy/update the file.
        action = "Deploying" if not target_file_path.exists() else "Updating"
        logger.info(f"{action}: '{short_path(source_file_path)}' -> '{short_path(target_file_path)}'")

        if not dry_run:
            target_file_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file_path, target_file_path)
            hash_file_path.write_text(source_hash or "")


def run_map_deploy(
    deployment_map: dict[str, list[str] | Collection[str]],
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """
    Deploys files from source directories to their corresponding target directories.

    This function iterates through a map where each source directory is associated
    with a list of target directories. It copies valid files and creates a '.hash'
    file alongside each deployed file to track its state.

    Args:
        deployment_map: A dictionary where keys are source paths and values are
                        a list or collection of target paths.
        dry_run: If True, simulates the deployment without making changes.
        force: If True, overwrites target files even if they have been modified
               locally since the last deployment.
    """
    if len(deployment_map):
        logger.info(f"Preparing to deploy {len(deployment_map)} items")
    else:
        logger.warning(
            """No items in map config section. Map deploy requires pyproject.toml to have something like
        [tool.bash2gitlab.map.map]
        "out/python" =["my_microservice/gitlab-scripts", "my_other/gitlab-scripts"]"""
        )

    # bash2gitlab.toml
    for source_base, target_bases in deployment_map.items():
        logger.info(f"Deploying {short_path(Path(source_base))} to {len(target_bases)} destinations")
        source_base_path = Path(source_base).resolve()

        if not source_base_path.is_dir():
            logger.warning(f"Warning: Source directory '{short_path(source_base_path)}' does not exist. Skipping.")
            continue

        if not isinstance(target_bases, (list, tuple, set)):
            logger.error(f"Invalid format for '{source_base}'. Targets must be a list. Skipping.")
            continue
        if not len(target_bases):
            logger.warning("Source folder but no destinations!")

        for target_base in target_bases:
            target_base_path = Path(target_base).resolve()
            deploy_to_single_target(source_base_path, target_base_path, dry_run, force)
```
## File: commands\precommit.py
```python
#!/usr/bin/env python3
"""Precommit handler.

Installs and removes a Git `pre-commit` hook that runs `bash2gitlab compile`.
Respects environment/TOML config, Git worktrees, and `core.hooksPath`.
"""

from __future__ import annotations

import configparser
import hashlib
import logging
import os
import stat
from pathlib import Path

from bash2gitlab.config import config

logger = logging.getLogger(__name__)

__all__ = ["install", "uninstall", "PrecommitHookError", "hook_hash", "hook_path"]


class PrecommitHookError(Exception):
    """Raised when pre-commit hook installation or removal fails."""


HOOK_NAME = "pre-commit"

# POSIX sh (not bash). Avoid `pipefail` and bashisms.
# We do not use `set -e` because we intentionally fall through runners.
HOOK_CONTENT = """#!/bin/sh
# Auto-generated by bash2gitlab: run `bash2gitlab compile` before committing.
set -u

say() { printf '%s\\n' "$*"; }

say "[pre-commit] Running bash2gitlab compile..."

try_run() {
  # $* is the command string
  if sh -c "$*"; then
    say "[pre-commit] OK: $*"
    exit 0
  fi
  return 1
}

# 1) direct
if command -v bash2gitlab >/dev/null 2>&1; then
  try_run "bash2gitlab compile"
fi

# 2) common project runners
for tool in uv poetry pipenv pdm hatch rye; do
  if command -v "$tool" >/dev/null 2>&1; then
    case "$tool" in
      hatch) try_run "hatch run bash2gitlab compile" || true ;;
      *)     try_run "$tool run bash2gitlab compile" || true ;;
    esac
  fi
done

# 3) python module fallback
if command -v python >/dev/null 2>&1; then
  try_run "python -m bash2gitlab compile" || true
fi

say "[pre-commit] ERROR: could not run bash2gitlab. Install it or use uv/poetry/pipenv/pdm/hatch/rye."
exit 1
"""

CONFIG_SECTION = "tool.bash2gitlab"
REQUIRED_ENV_VARS = {"BASH2GITLAB_INPUT_DIR", "BASH2GITLAB_OUTPUT_DIR"}


def hook_hash(content: str) -> str:
    """Return a stable hash of hook content for conflict detection.

    Args:
        content: Hook script content.

    Returns:
        Hex digest string (sha256).
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def resolve_git_dir(repo_root: Path) -> Path:
    """Resolve the actual .git directory, supporting worktrees (gitdir file).

    Args:
        repo_root: Candidate repo root.

    Returns:
        Path to the real .git directory.

    Raises:
        PrecommitHookError: If a git directory cannot be located.
    """
    git_path = repo_root / ".git"
    if git_path.is_dir():
        return git_path
    if git_path.is_file():
        try:
            data = git_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise PrecommitHookError(f"Unable to read {git_path}: {exc}") from exc
        if data.lower().startswith("gitdir:"):
            target = data.split(":", 1)[1].strip()
            return (repo_root / target).resolve()
    raise PrecommitHookError(f"Not inside a Git repository: {repo_root}")


def read_hooks_path(git_dir: Path, repo_root: Path) -> Path | None:
    """Read core.hooksPath from .git/config, if present.

    Args:
        git_dir: Path to .git directory (resolved).
        repo_root: Repo root.

    Returns:
        Path to hooks dir or None if not configured.
    """
    cfg = configparser.ConfigParser()
    cfg_path = git_dir / "config"
    if not cfg_path.is_file():
        return None
    try:
        cfg.read(cfg_path, encoding="utf-8")
    except Exception:  # best-effort
        return None
    if cfg.has_section("core") and cfg.has_option("core", "hooksPath"):
        hooks_path = Path(cfg.get("core", "hooksPath"))
        if not hooks_path.is_absolute():
            hooks_path = (repo_root / hooks_path).resolve()
        return hooks_path
    return None


def hooks_dir(repo_root: Path) -> Path:
    """Compute the correct hooks directory, honoring `core.hooksPath`."""
    git_dir = resolve_git_dir(repo_root)
    alt = read_hooks_path(git_dir, repo_root)
    return alt if alt else (git_dir / "hooks")


def hook_path(repo_root: Path) -> Path:
    """Return full path to the pre-commit hook file."""
    return hooks_dir(repo_root) / HOOK_NAME


def has_required_config() -> bool:
    """Check whether compile input/output are configured via env or TOML.

    Returns:
        True if `input_dir` and `output_dir` are present; otherwise False.
    """
    # Env wins
    if REQUIRED_ENV_VARS.issubset(os.environ):
        return True

    # TOML via singleton config
    if config.input_dir and config.output_dir:
        return True

    return False


def install(repo_root: Path | None = None, *, force: bool = False) -> None:
    """Install the bash2gitlab `pre-commit` hook.

    The hook will try multiple runners (direct, uv, poetry, pipenv, pdm, hatch, rye,
    then `python -m`) to invoke `bash2gitlab compile`.

    Args:
        repo_root: Directory considered as the repository root (defaults to CWD).
        force: Overwrite an existing non-matching hook if True.

    Raises:
        PrecommitHookError: If outside a Git repo, config missing, or conflict.
    """
    repo_root = repo_root or Path.cwd()

    # Validate repo and config
    _git_dir = resolve_git_dir(repo_root)  # raises if not a repo
    if not has_required_config():
        raise PrecommitHookError(
            "Missing bash2gitlab input/output configuration. Run `bash2gitlab init` to create TOML, or set BASH2GITLAB_INPUT_DIR and BASH2GITLAB_OUTPUT_DIR."
        )

    # Ensure hooks dir exists
    hdir = hooks_dir(repo_root)
    hdir.mkdir(parents=True, exist_ok=True)

    dest = hdir / HOOK_NAME
    new_hash = hook_hash(HOOK_CONTENT)

    if dest.exists():
        existing = dest.read_text(encoding="utf-8")
        if hook_hash(existing) == new_hash and not force:
            logger.info("Pre-commit hook is already up to date at %s", dest.relative_to(repo_root))
            return
        if hook_hash(existing) != new_hash and not force:
            raise PrecommitHookError(f"A different pre-commit hook exists at {dest}. Use force=True to overwrite.")

    dest.write_text(HOOK_CONTENT, encoding="utf-8")

    # Executable on POSIX; Git for Windows runs sh hooks regardless of mode.
    if os.name == "posix":
        st_mode = dest.stat().st_mode
        dest.chmod(st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    logger.info("Installed pre-commit hook at %s", dest.relative_to(repo_root))


def uninstall(repo_root: Path | None = None, *, force: bool = False) -> None:
    """Remove the bash2gitlab `pre-commit` hook.

    Args:
        repo_root: Directory considered as the repository root (defaults to CWD).
        force: Remove even if the hook content does not match our generated one.

    Raises:
        PrecommitHookError: If outside a Git repo or conflict without `force`.
    """
    repo_root = repo_root or Path.cwd()
    _git_dir = resolve_git_dir(repo_root)  # raises if not a repo

    dest = hook_path(repo_root)
    if not dest.exists():
        logger.warning("No pre-commit hook to uninstall at %s", dest)
        return

    content = dest.read_text(encoding="utf-8")
    if hook_hash(content) != hook_hash(HOOK_CONTENT) and not force:
        raise PrecommitHookError(
            f"Pre-commit hook at {dest} does not match bash2gitlab's. Use force=True to remove anyway."
        )

    dest.unlink()
    logger.info("Removed pre-commit hook at %s", dest.relative_to(repo_root))
```
## File: commands\show_config.py
```python
from __future__ import annotations

import logging
import os
from typing import Any

from bash2gitlab.config import _Config, config
from bash2gitlab.utils.terminal_colors import Colors
from bash2gitlab.utils.utils import short_path

logger = logging.getLogger(__name__)

__all__ = ["run_show_config"]

# Defines the structure of the output.
# Maps section titles to a list of tuples: (display_key, config_property_name)
CONFIG_STRUCTURE = {
    "General Settings": [
        ("input_dir", "input_dir"),
        ("output_dir", "output_dir"),
        ("parallelism", "parallelism"),
        ("dry_run", "dry_run"),
        ("verbose", "verbose"),
        ("quiet", "quiet"),
        ("custom_header", "custom_header"),
    ],
    "Custom Shebangs (`[shebangs]`)": [("shebangs", "custom_shebangs")],
    "Compile Command (`[compile]`)": [
        ("input_dir", "compile_input_dir"),
        ("output_dir", "compile_output_dir"),
        ("parallelism", "compile_parallelism"),
        ("watch", "compile_watch"),
    ],
    "Decompile Command (`[decompile]`)": [
        ("input_file", "decompile_input_file"),
        ("input_folder", "decompile_input_folder"),
        ("output_dir", "decompile_output_dir"),
    ],
    "Lint Command (`[lint]`)": [
        ("output_dir", "lint_output_dir"),
        ("gitlab_url", "lint_gitlab_url"),
        ("token", "lint_token"),
        ("project_id", "lint_project_id"),
        ("ref", "lint_ref"),
        ("include_merged_yaml", "lint_include_merged_yaml"),
        ("parallelism", "lint_parallelism"),
        ("timeout", "lint_timeout"),
    ],
    "Copy2Local Command (`[copy2local]`)": [
        ("repo_url", "copy2local_repo_url"),
        ("branch", "copy2local_branch"),
        ("source_dir", "copy2local_source_dir"),
        ("copy_dir", "copy2local_copy_dir"),
    ],
    "Map Commands (`[map]`)": [
        ("pyproject_path", "map_pyproject_path"),
        ("force", "map_force"),
    ],
}

# Known sections used for parsing property names
_SECTIONS = {"compile", "decompile", "lint", "copy2local", "map"}


def _parse_prop_name(prop_name: str) -> tuple[str, str | None]:
    """Parses a config property name into its key and section."""
    parts = prop_name.split("_", 1)
    if parts[0] in _SECTIONS:
        # e.g., "lint_gitlab_url" -> ("gitlab_url", "lint")
        return (parts[1], parts[0])
    if prop_name == "custom_shebangs":
        # e.g. "custom_shebangs" -> ("shebangs", None) but it is a section-like table
        return ("shebangs", None)
    # e.g., "input_dir" -> ("input_dir", None)
    return (prop_name, None)


def get_value_and_source_details(prop_name: str, config_instance: _Config) -> tuple[Any, str, str | None]:
    """
    Determines the final value and the specific source of a configuration property.

    Returns:
        A tuple of (value, source_type, source_detail).
    """
    # 1. Get the final, resolved value from the config property.
    #    This correctly handles fallbacks (e.g., `lint_output_dir` -> `output_dir`).
    value = getattr(config_instance, prop_name, None)

    # 2. Determine the original source of the value.
    key, section = _parse_prop_name(prop_name)
    key_for_file = "shebangs" if prop_name == "custom_shebangs" else key

    # Check Environment Variable
    env_key = f"{section}_{key}" if section else key
    env_var_name = config_instance._ENV_VAR_PREFIX + env_key.upper()
    if env_var_name in os.environ:
        return value, "Environment Variable", env_var_name

    # Check Configuration File ([section])
    if section:
        config_section = config_instance.file_config.get(section, {})
        if isinstance(config_section, dict) and key in config_section:
            config_path = config_instance.config_path_override or config_instance.find_config_file()
            detail = f"[{section}] in {short_path(config_path)}" if config_path else f"in section [{section}]"
            return value, "Configuration File", detail

    # Check Configuration File (top-level)
    if key_for_file in config_instance.file_config:
        config_path = config_instance.config_path_override or config_instance.find_config_file()
        detail = f"in {short_path(config_path)}" if config_path else "in config file"
        return value, "Configuration File", detail

    # Check if the value came from a fallback to a general property
    if section and value is not None:
        # Check if the fallback general property has a source
        general_value, general_source, general_detail = get_value_and_source_details(key, config_instance)
        if general_value == value and general_source != "Default":
            return value, general_source, f"{general_detail} (fallback)"

    return value, "Default", None


def run_show_config() -> int:
    """
    Displays the resolved configuration values, grouped by section, and their sources.
    """
    print(f"{Colors.BOLD}bash2gitlab Configuration:{Colors.ENDC}")

    config_file_path = config.config_path_override or config.find_config_file()
    if config_file_path:
        print(f"Loaded from: {Colors.OKCYAN}{short_path(config_file_path)}{Colors.ENDC}")
    else:
        print(f"{Colors.WARNING}Note: No 'bash2gitlab.toml' or 'pyproject.toml' config file found.{Colors.ENDC}")

    max_key_len = max(len(k) for section in CONFIG_STRUCTURE.values() for k, _ in section)

    for section_title, keys in CONFIG_STRUCTURE.items():
        # Check if any value in the section is set to avoid printing empty sections
        has_values = any(getattr(config, prop_name, None) is not None for _, prop_name in keys)
        if not has_values:
            continue

        print(f"\n{Colors.BOLD}{section_title}{Colors.ENDC}")
        for display_key, prop_name in keys:
            value, source_type, source_detail = get_value_and_source_details(prop_name, config)

            if source_type == "Environment Variable":
                source_color = Colors.OKCYAN
            elif source_type == "Configuration File":
                source_color = Colors.OKGREEN
            else:
                source_color = Colors.WARNING

            key_padded = display_key.ljust(max_key_len)

            if isinstance(value, dict):
                value_str = (
                    f"\n{Colors.BOLD}"
                    + "\n".join(f"{' ' * (max_key_len + 5)}- {k}: {v}" for k, v in value.items())
                    + f"{Colors.ENDC}"
                )
            elif value is not None:
                value_str = f"{Colors.BOLD}{value}{Colors.ENDC}"
            else:
                value_str = f"{Colors.FAIL}Not Set{Colors.ENDC}"

            source_str = f"{source_color}({source_type}{Colors.ENDC}"
            if source_detail:
                source_str += f": {source_detail}"
            source_str += ")"

            # Don't show source for unset defaults
            if source_type == "Default" and value is None:
                source_str = ""

            print(f"  {key_padded} = {value_str} {source_str}")

    return 0
```
## File: schemas\gitlab_ci_schema.json
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://gitlab.com/.gitlab-ci.yml",
  "markdownDescription": "GitLab has a built-in solution for doing CI called GitLab CI. It is configured by supplying a file called `.gitlab-ci.yml`, which will list all the jobs that are going to run for the project. A full list of all options can be found [here](https://docs.gitlab.com/ci/yaml/). [Learn More](https://docs.gitlab.com/ci/).",
  "type": "object",
  "properties": {
    "$schema": {
      "type": "string",
      "format": "uri"
    },
    "spec": {
      "type": "object",
      "markdownDescription": "Specification for pipeline configuration. Must be declared at the top of a configuration file, in a header section separated from the rest of the configuration with `---`. [Learn More](https://docs.gitlab.com/ci/yaml/#spec).",
      "properties": {
        "inputs": {
          "$ref": "#/definitions/inputParameters"
        }
      },
      "additionalProperties": false
    },
    "image": {
      "$ref": "#/definitions/image",
      "markdownDescription": "Defining `image` globally is deprecated. Use [`default`](https://docs.gitlab.com/ci/yaml/#default) instead. [Learn more](https://docs.gitlab.com/ci/yaml/#globally-defined-image-services-cache-before_script-after_script)."
    },
    "services": {
      "$ref": "#/definitions/services",
      "markdownDescription": "Defining `services` globally is deprecated. Use [`default`](https://docs.gitlab.com/ci/yaml/#default) instead. [Learn more](https://docs.gitlab.com/ci/yaml/#globally-defined-image-services-cache-before_script-after_script)."
    },
    "before_script": {
      "$ref": "#/definitions/before_script",
      "markdownDescription": "Defining `before_script` globally is deprecated. Use [`default`](https://docs.gitlab.com/ci/yaml/#default) instead. [Learn more](https://docs.gitlab.com/ci/yaml/#globally-defined-image-services-cache-before_script-after_script)."
    },
    "after_script": {
      "$ref": "#/definitions/after_script",
      "markdownDescription": "Defining `after_script` globally is deprecated. Use [`default`](https://docs.gitlab.com/ci/yaml/#default) instead. [Learn more](https://docs.gitlab.com/ci/yaml/#globally-defined-image-services-cache-before_script-after_script)."
    },
    "variables": {
      "$ref": "#/definitions/globalVariables"
    },
    "cache": {
      "$ref": "#/definitions/cache",
      "markdownDescription": "Defining `cache` globally is deprecated. Use [`default`](https://docs.gitlab.com/ci/yaml/#default) instead. [Learn more](https://docs.gitlab.com/ci/yaml/#globally-defined-image-services-cache-before_script-after_script)."
    },
    "!reference": {
      "$ref": "#/definitions/!reference"
    },
    "default": {
      "type": "object",
      "properties": {
        "after_script": {
          "$ref": "#/definitions/after_script"
        },
        "artifacts": {
          "$ref": "#/definitions/artifacts"
        },
        "before_script": {
          "$ref": "#/definitions/before_script"
        },
        "hooks": {
          "$ref": "#/definitions/hooks"
        },
        "cache": {
          "$ref": "#/definitions/cache"
        },
        "image": {
          "$ref": "#/definitions/image"
        },
        "interruptible": {
          "$ref": "#/definitions/interruptible"
        },
        "id_tokens": {
          "$ref": "#/definitions/id_tokens"
        },
        "identity": {
          "$ref": "#/definitions/identity"
        },
        "retry": {
          "$ref": "#/definitions/retry"
        },
        "services": {
          "$ref": "#/definitions/services"
        },
        "tags": {
          "$ref": "#/definitions/tags"
        },
        "timeout": {
          "$ref": "#/definitions/timeout"
        },
        "!reference": {
          "$ref": "#/definitions/!reference"
        }
      },
      "additionalProperties": false
    },
    "stages": {
      "type": "array",
      "markdownDescription": "Groups jobs into stages. All jobs in one stage must complete before next stage is executed. Defaults to ['build', 'test', 'deploy']. [Learn More](https://docs.gitlab.com/ci/yaml/#stages).",
      "default": [
        "build",
        "test",
        "deploy"
      ],
      "items": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "array",
            "items": {
              "type": "string"
            }
          }
        ]
      },
      "uniqueItems": true,
      "minItems": 1
    },
    "include": {
      "markdownDescription": "Can be `IncludeItem` or `IncludeItem[]`. Each `IncludeItem` will be a string, or an object with properties for the method if including external YAML file. The external content will be fetched, included and evaluated along the `.gitlab-ci.yml`. [Learn More](https://docs.gitlab.com/ci/yaml/#include).",
      "oneOf": [
        {
          "$ref": "#/definitions/include_item"
        },
        {
          "type": "array",
          "items": {
            "$ref": "#/definitions/include_item"
          }
        }
      ]
    },
    "pages": {
      "$ref": "#/definitions/job",
      "markdownDescription": "A special job used to upload static sites to GitLab pages. Requires a `public/` directory with `artifacts.path` pointing to it. [Learn More](https://docs.gitlab.com/ci/yaml/#pages)."
    },
    "workflow": {
      "type": "object",
      "properties": {
        "name": {
          "$ref": "#/definitions/workflowName"
        },
        "auto_cancel": {
          "$ref": "#/definitions/workflowAutoCancel"
        },
        "rules": {
          "type": "array",
          "items": {
            "anyOf": [
              {
                "type": "object"
              },
              {
                "type": "array",
                "minItems": 1,
                "items": {
                  "type": "string"
                }
              }
            ],
            "properties": {
              "if": {
                "$ref": "#/definitions/if"
              },
              "changes": {
                "$ref": "#/definitions/changes"
              },
              "exists": {
                "$ref": "#/definitions/exists"
              },
              "variables": {
                "$ref": "#/definitions/rulesVariables"
              },
              "when": {
                "type": "string",
                "enum": [
                  "always",
                  "never"
                ]
              },
              "auto_cancel": {
                "$ref": "#/definitions/workflowAutoCancel"
              }
            },
            "additionalProperties": false
          }
        }
      }
    }
  },
  "patternProperties": {
    "^[.]": {
      "description": "Hidden keys.",
      "anyOf": [
        {
          "$ref": "#/definitions/job_template"
        },
        {
          "description": "Arbitrary YAML anchor."
        }
      ]
    }
  },
  "additionalProperties": {
    "$ref": "#/definitions/job"
  },
  "definitions": {
    "artifacts": {
      "type": [
        "object",
        "null"
      ],
      "markdownDescription": "Used to specify a list of files and directories that should be attached to the job if it succeeds. Artifacts are sent to GitLab where they can be downloaded. [Learn More](https://docs.gitlab.com/ci/yaml/#artifacts).",
      "additionalProperties": false,
      "properties": {
        "paths": {
          "type": "array",
          "markdownDescription": "A list of paths to files/folders that should be included in the artifact. [Learn More](https://docs.gitlab.com/ci/yaml/#artifactspaths).",
          "items": {
            "type": "string"
          },
          "minItems": 1
        },
        "exclude": {
          "type": "array",
          "markdownDescription": "A list of paths to files/folders that should be excluded in the artifact. [Learn More](https://docs.gitlab.com/ci/yaml/#artifactsexclude).",
          "items": {
            "type": "string"
          },
          "minItems": 1
        },
        "expose_as": {
          "type": "string",
          "markdownDescription": "Can be used to expose job artifacts in the merge request UI. GitLab will add a link <expose_as> to the relevant merge request that points to the artifact. [Learn More](https://docs.gitlab.com/ci/yaml/#artifactsexpose_as)."
        },
        "name": {
          "type": "string",
          "markdownDescription": "Name for the archive created on job success. Can use variables in the name, e.g. '$CI_JOB_NAME' [Learn More](https://docs.gitlab.com/ci/yaml/#artifactsname)."
        },
        "untracked": {
          "type": "boolean",
          "markdownDescription": "Whether to add all untracked files (along with 'artifacts.paths') to the artifact. [Learn More](https://docs.gitlab.com/ci/yaml/#artifactsuntracked).",
          "default": false
        },
        "when": {
          "markdownDescription": "Configure when artifacts are uploaded depended on job status. [Learn More](https://docs.gitlab.com/ci/yaml/#artifactswhen).",
          "default": "on_success",
          "type": "string",
          "enum": [
            "on_success",
            "on_failure",
            "always"
          ]
        },
        "access": {
          "markdownDescription": "Configure who can access the artifacts. [Learn More](https://docs.gitlab.com/ci/yaml/#artifactsaccess).",
          "default": "all",
          "type": "string",
          "enum": [
            "none",
            "developer",
            "all"
          ]
        },
        "expire_in": {
          "type": "string",
          "markdownDescription": "How long artifacts should be kept. They are saved 30 days by default. Artifacts that have expired are removed periodically via cron job. Supports a wide variety of formats, e.g. '1 week', '3 mins 4 sec', '2 hrs 20 min', '2h20min', '6 mos 1 day', '47 yrs 6 mos and 4d', '3 weeks and 2 days'. [Learn More](https://docs.gitlab.com/ci/yaml/#artifactsexpire_in).",
          "default": "30 days"
        },
        "reports": {
          "type": "object",
          "markdownDescription": "Reports will be uploaded as artifacts, and often displayed in the GitLab UI, such as in merge requests. [Learn More](https://docs.gitlab.com/ci/yaml/#artifactsreports).",
          "additionalProperties": false,
          "properties": {
            "accessibility": {
              "type": "string",
              "description": "Path to JSON file with accessibility report."
            },
            "annotations": {
              "type": "string",
              "description": "Path to JSON file with annotations report."
            },
            "junit": {
              "description": "Path for file(s) that should be parsed as JUnit XML result",
              "oneOf": [
                {
                  "type": "string",
                  "description": "Path to a single XML file"
                },
                {
                  "type": "array",
                  "description": "A list of paths to XML files that will automatically be concatenated into a single file",
                  "items": {
                    "type": "string"
                  },
                  "minItems": 1
                }
              ]
            },
            "browser_performance": {
              "type": "string",
              "description": "Path to a single file with browser performance metric report(s)."
            },
            "coverage_report": {
              "type": [
                "object",
                "null"
              ],
              "description": "Used to collect coverage reports from the job.",
              "properties": {
                "coverage_format": {
                  "description": "Code coverage format used by the test framework.",
                  "enum": [
                    "cobertura",
                    "jacoco"
                  ]
                },
                "path": {
                  "description": "Path to the coverage report file that should be parsed.",
                  "type": "string",
                  "minLength": 1
                }
              }
            },
            "codequality": {
              "$ref": "#/definitions/string_file_list",
              "description": "Path to file or list of files with code quality report(s) (such as Code Climate)."
            },
            "dotenv": {
              "$ref": "#/definitions/string_file_list",
              "description": "Path to file or list of files containing runtime-created variables for this job."
            },
            "lsif": {
              "$ref": "#/definitions/string_file_list",
              "description": "Path to file or list of files containing code intelligence (Language Server Index Format)."
            },
            "sast": {
              "$ref": "#/definitions/string_file_list",
              "description": "Path to file or list of files with SAST vulnerabilities report(s)."
            },
            "dependency_scanning": {
              "$ref": "#/definitions/string_file_list",
              "description": "Path to file or list of files with Dependency scanning vulnerabilities report(s)."
            },
            "container_scanning": {
              "$ref": "#/definitions/string_file_list",
              "description": "Path to file or list of files with Container scanning vulnerabilities report(s)."
            },
            "dast": {
              "$ref": "#/definitions/string_file_list",
              "description": "Path to file or list of files with DAST vulnerabilities report(s)."
            },
            "license_management": {
              "$ref": "#/definitions/string_file_list",
              "description": "Deprecated in 12.8: Path to file or list of files with license report(s)."
            },
            "license_scanning": {
              "$ref": "#/definitions/string_file_list",
              "description": "Path to file or list of files with license report(s)."
            },
            "requirements": {
              "$ref": "#/definitions/string_file_list",
              "description": "Path to file or list of files with requirements report(s)."
            },
            "secret_detection": {
              "$ref": "#/definitions/string_file_list",
              "description": "Path to file or list of files with secret detection report(s)."
            },
            "metrics": {
              "$ref": "#/definitions/string_file_list",
              "description": "Path to file or list of files with custom metrics report(s)."
            },
            "terraform": {
              "$ref": "#/definitions/string_file_list",
              "description": "Path to file or list of files with terraform plan(s)."
            },
            "cyclonedx": {
              "$ref": "#/definitions/string_file_list",
              "markdownDescription": "Path to file or list of files with cyclonedx report(s). [Learn More](https://docs.gitlab.com/ci/yaml/artifacts_reports/#artifactsreportscyclonedx)."
            },
            "load_performance": {
              "$ref": "#/definitions/string_file_list",
              "markdownDescription": "Path to file or list of files with load performance testing report(s). [Learn More](https://docs.gitlab.com/ci/yaml/artifacts_reports/#artifactsreportsload_performance)."
            },
            "repository_xray": {
              "$ref": "#/definitions/string_file_list",
              "description": "Path to file or list of files with Repository X-Ray report(s)."
            }
          }
        }
      }
    },
    "string_file_list": {
      "oneOf": [
        {
          "type": "string"
        },
        {
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      ]
    },
    "inputParameters": {
      "type": "object",
      "markdownDescription": "Define parameters that can be populated in reusable CI/CD configuration files when added to a pipeline. [Learn More](https://docs.gitlab.com/ci/inputs/).",
      "patternProperties": {
        ".*": {
          "markdownDescription": "**Input Configuration**\n\nAvailable properties:\n- `type`: string (default), array, boolean, or number\n- `description`: Human-readable explanation of the parameter (supports Markdown)\n- `options`: List of allowed values\n- `default`: Value to use when not specified (makes input optional)\n- `regex`: Pattern that string values must match",
          "oneOf": [
            {
              "type": "object",
              "properties": {
                "type": {
                  "type": "string",
                  "markdownDescription": "Force a specific input type. Defaults to 'string' when not specified. [Learn More](https://docs.gitlab.com/ci/inputs/#input-types).",
                  "enum": [
                    "array",
                    "boolean",
                    "number",
                    "string"
                  ],
                  "default": "string"
                },
                "description": {
                  "type": "string",
                  "markdownDescription": "Give a description to a specific input. The description does not affect the input, but can help people understand the input details or expected values. Supports markdown.",
                  "maxLength": 1024
                },
                "options": {
                  "type": "array",
                  "markdownDescription": "Specify a list of allowed values for an input.",
                  "items": {
                    "oneOf": [
                      {
                        "type": "string"
                      },
                      {
                        "type": "number"
                      },
                      {
                        "type": "boolean"
                      }
                    ]
                  }
                },
                "regex": {
                  "type": "string",
                  "markdownDescription": "Specify a regular expression that the input must match. Only impacts inputs with a `type` of `string`."
                },
                "default": {
                  "markdownDescription": "Define default values for inputs when not specified. When you specify a default, the inputs are no longer mandatory."
                }
              },
              "allOf": [
                {
                  "if": {
                    "properties": {
                      "type": {
                        "enum": [
                          "string"
                        ]
                      }
                    }
                  },
                  "then": {
                    "properties": {
                      "default": {
                        "type": [
                          "string",
                          "null"
                        ]
                      }
                    }
                  }
                },
                {
                  "if": {
                    "properties": {
                      "type": {
                        "enum": [
                          "number"
                        ]
                      }
                    }
                  },
                  "then": {
                    "properties": {
                      "default": {
                        "type": [
                          "number",
                          "null"
                        ]
                      }
                    }
                  }
                },
                {
                  "if": {
                    "properties": {
                      "type": {
                        "enum": [
                          "boolean"
                        ]
                      }
                    }
                  },
                  "then": {
                    "properties": {
                      "default": {
                        "type": [
                          "boolean",
                          "null"
                        ]
                      }
                    }
                  }
                },
                {
                  "if": {
                    "properties": {
                      "type": {
                        "enum": [
                          "array"
                        ]
                      }
                    }
                  },
                  "then": {
                    "properties": {
                      "default": {
                        "oneOf": [
                          {
                            "type": "array"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      }
                    }
                  }
                }
              ],
              "additionalProperties": false
            },
            {
              "type": "null"
            }
          ]
        }
      }
    },
    "include_item": {
      "oneOf": [
        {
          "description": "Will infer the method based on the value. E.g. `https://...` strings will be of type `include:remote`, and `/templates/...` or `templates/...` will be of type `include:local`.",
          "type": "string",
          "format": "uri-reference",
          "pattern": "\\w\\.ya?ml$",
          "anyOf": [
            {
              "pattern": "^https?://"
            },
            {
              "not": {
                "pattern": "^\\w+://"
              }
            }
          ]
        },
        {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "local": {
              "description": "Relative path from local repository root (`/`) to the `yaml`/`yml` file template. The file must be on the same branch, and does not work across git submodules.",
              "type": "string",
              "format": "uri-reference",
              "pattern": "\\.ya?ml$"
            },
            "rules": {
              "$ref": "#/definitions/includeRules"
            },
            "inputs": {
              "$ref": "#/definitions/inputs"
            }
          },
          "required": [
            "local"
          ]
        },
        {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "project": {
              "description": "Path to the project, e.g. `group/project`, or `group/sub-group/project` [Learn more](https://docs.gitlab.com/ci/yaml/#includeproject).",
              "type": "string",
              "pattern": "(?:\\S/\\S|\\$\\S+)"
            },
            "ref": {
              "description": "Branch/Tag/Commit-hash for the target project.",
              "type": "string"
            },
            "file": {
              "oneOf": [
                {
                  "description": "Relative path from project root (`/`) to the `yaml`/`yml` file template.",
                  "type": "string",
                  "pattern": "\\.ya?ml$"
                },
                {
                  "description": "List of files by relative path from project root (`/`) to the `yaml`/`yml` file template.",
                  "type": "array",
                  "items": {
                    "type": "string",
                    "pattern": "\\.ya?ml$"
                  }
                }
              ]
            },
            "rules": {
              "$ref": "#/definitions/includeRules"
            },
            "inputs": {
              "$ref": "#/definitions/inputs"
            }
          },
          "required": [
            "project",
            "file"
          ]
        },
        {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "template": {
              "description": "Use a `.gitlab-ci.yml` template as a base, e.g. `Nodejs.gitlab-ci.yml`.",
              "type": "string",
              "format": "uri-reference",
              "pattern": "\\.ya?ml$"
            },
            "rules": {
              "$ref": "#/definitions/includeRules"
            },
            "inputs": {
              "$ref": "#/definitions/inputs"
            }
          },
          "required": [
            "template"
          ]
        },
        {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "component": {
              "description": "Local path to component directory or full path to external component directory.",
              "type": "string",
              "format": "uri-reference"
            },
            "rules": {
              "$ref": "#/definitions/includeRules"
            },
            "inputs": {
              "$ref": "#/definitions/inputs"
            }
          },
          "required": [
            "component"
          ]
        },
        {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "remote": {
              "description": "URL to a `yaml`/`yml` template file using HTTP/HTTPS.",
              "type": "string",
              "format": "uri-reference",
              "pattern": "^https?://.+\\.ya?ml$"
            },
            "integrity": {
              "description": "SHA256 integrity hash of the remote file content.",
              "type": "string",
              "pattern": "^sha256-[A-Za-z0-9+/]{43}=$"
            },
            "rules": {
              "$ref": "#/definitions/includeRules"
            },
            "inputs": {
              "$ref": "#/definitions/inputs"
            }
          },
          "required": [
            "remote"
          ]
        }
      ]
    },
    "!reference": {
      "type": "array",
      "items": {
        "type": "string",
        "minLength": 1
      }
    },
    "image": {
      "oneOf": [
        {
          "type": "string",
          "minLength": 1,
          "description": "Full name of the image that should be used. It should contain the Registry part if needed."
        },
        {
          "type": "object",
          "description": "Specifies the docker image to use for the job or globally for all jobs. Job configuration takes precedence over global setting. Requires a certain kind of GitLab runner executor.",
          "additionalProperties": false,
          "properties": {
            "name": {
              "type": "string",
              "minLength": 1,
              "description": "Full name of the image that should be used. It should contain the Registry part if needed."
            },
            "entrypoint": {
              "type": "array",
              "description": "Command or script that should be executed as the container's entrypoint. It will be translated to Docker's --entrypoint option while creating the container. The syntax is similar to Dockerfile's ENTRYPOINT directive, where each shell token is a separate string in the array.",
              "minItems": 1
            },
            "docker": {
              "type": "object",
              "markdownDescription": "Options to pass to Runners Docker Executor. [Learn More](https://docs.gitlab.com/ci/yaml/#imagedocker)",
              "additionalProperties": false,
              "properties": {
                "platform": {
                  "type": "string",
                  "minLength": 1,
                  "description": "Image architecture to pull."
                },
                "user": {
                  "type": "string",
                  "minLength": 1,
                  "maxLength": 255,
                  "description": "Username or UID to use for the container."
                }
              }
            },
            "kubernetes": {
              "type": "object",
              "markdownDescription": "Options to pass to Runners Kubernetes Executor. [Learn More](https://docs.gitlab.com/ci/yaml/#imagekubernetes)",
              "additionalProperties": false,
              "properties": {
                "user": {
                  "type": [
                    "string",
                    "integer"
                  ],
                  "minLength": 1,
                  "maxLength": 255,
                  "description": "Username or UID to use for the container. It also supports the UID:GID format."
                }
              }
            },
            "pull_policy": {
              "markdownDescription": "Specifies how to pull the image in Runner. It can be one of `always`, `never` or `if-not-present`. The default value is `always`. [Learn more](https://docs.gitlab.com/ci/yaml/#imagepull_policy).",
              "default": "always",
              "oneOf": [
                {
                  "type": "string",
                  "enum": [
                    "always",
                    "never",
                    "if-not-present"
                  ]
                },
                {
                  "type": "array",
                  "items": {
                    "type": "string",
                    "enum": [
                      "always",
                      "never",
                      "if-not-present"
                    ]
                  },
                  "minItems": 1,
                  "uniqueItems": true
                }
              ]
            }
          },
          "required": [
            "name"
          ]
        }
      ],
      "markdownDescription": "Specifies the docker image to use for the job or globally for all jobs. Job configuration takes precedence over global setting. Requires a certain kind of GitLab runner executor. [Learn More](https://docs.gitlab.com/ci/yaml/#image)."
    },
    "services": {
      "type": "array",
      "markdownDescription": "Similar to `image` property, but will link the specified services to the `image` container. [Learn More](https://docs.gitlab.com/ci/yaml/#services).",
      "items": {
        "oneOf": [
          {
            "type": "string",
            "minLength": 1,
            "description": "Full name of the image that should be used. It should contain the Registry part if needed."
          },
          {
            "type": "object",
            "description": "",
            "additionalProperties": false,
            "properties": {
              "name": {
                "type": "string",
                "description": "Full name of the image that should be used. It should contain the Registry part if needed.",
                "minLength": 1
              },
              "entrypoint": {
                "type": "array",
                "markdownDescription": "Command or script that should be executed as the container's entrypoint. It will be translated to Docker's --entrypoint option while creating the container. The syntax is similar to Dockerfile's ENTRYPOINT directive, where each shell token is a separate string in the array. [Learn More](https://docs.gitlab.com/ci/services/#available-settings-for-services)",
                "minItems": 1,
                "items": {
                  "type": "string"
                }
              },
              "docker": {
                "type": "object",
                "markdownDescription": "Options to pass to Runners Docker Executor. [Learn More](https://docs.gitlab.com/ci/yaml/#servicesdocker)",
                "additionalProperties": false,
                "properties": {
                  "platform": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Image architecture to pull."
                  },
                  "user": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 255,
                    "description": "Username or UID to use for the container."
                  }
                }
              },
              "kubernetes": {
                "type": "object",
                "markdownDescription": "Options to pass to Runners Kubernetes Executor. [Learn More](https://docs.gitlab.com/ci/yaml/#imagekubernetes)",
                "additionalProperties": false,
                "properties": {
                  "user": {
                    "type": [
                      "string",
                      "integer"
                    ],
                    "minLength": 1,
                    "maxLength": 255,
                    "description": "Username or UID to use for the container. It also supports the UID:GID format."
                  }
                }
              },
              "pull_policy": {
                "markdownDescription": "Specifies how to pull the image in Runner. It can be one of `always`, `never` or `if-not-present`. The default value is `always`. [Learn more](https://docs.gitlab.com/ci/yaml/#servicespull_policy).",
                "default": "always",
                "oneOf": [
                  {
                    "type": "string",
                    "enum": [
                      "always",
                      "never",
                      "if-not-present"
                    ]
                  },
                  {
                    "type": "array",
                    "items": {
                      "type": "string",
                      "enum": [
                        "always",
                        "never",
                        "if-not-present"
                      ]
                    },
                    "minItems": 1,
                    "uniqueItems": true
                  }
                ]
              },
              "command": {
                "type": "array",
                "markdownDescription": "Command or script that should be used as the container's command. It will be translated to arguments passed to Docker after the image's name. The syntax is similar to Dockerfile's CMD directive, where each shell token is a separate string in the array. [Learn More](https://docs.gitlab.com/ci/services/#available-settings-for-services)",
                "minItems": 1,
                "items": {
                  "type": "string"
                }
              },
              "alias": {
                "type": "string",
                "markdownDescription": "Additional alias that can be used to access the service from the job's container. Read Accessing the services for more information. [Learn More](https://docs.gitlab.com/ci/services/#available-settings-for-services)",
                "minLength": 1
              },
              "variables": {
                "$ref": "#/definitions/jobVariables",
                "markdownDescription": "Additional environment variables that are passed exclusively to the service. Service variables cannot reference themselves. [Learn More](https://docs.gitlab.com/ci/services/#available-settings-for-services)"
              }
            },
            "required": [
              "name"
            ]
          }
        ]
      }
    },
    "id_tokens": {
      "type": "object",
      "markdownDescription": "Defines JWTs to be injected as environment variables.",
      "patternProperties": {
        ".*": {
          "type": "object",
          "properties": {
            "aud": {
              "oneOf": [
                {
                  "type": "string"
                },
                {
                  "type": "array",
                  "items": {
                    "type": "string"
                  },
                  "minItems": 1,
                  "uniqueItems": true
                }
              ]
            }
          },
          "required": [
            "aud"
          ],
          "additionalProperties": false
        }
      }
    },
    "identity": {
      "type": "string",
      "markdownDescription": "Sets a workload identity (experimental), allowing automatic authentication with the external system. [Learn More](https://docs.gitlab.com/ci/yaml/#identity).",
      "enum": [
        "google_cloud"
      ]
    },
    "secrets": {
      "type": "object",
      "markdownDescription": "Defines secrets to be injected as environment variables. [Learn More](https://docs.gitlab.com/ci/yaml/#secrets).",
      "patternProperties": {
        ".*": {
          "type": "object",
          "properties": {
            "vault": {
              "oneOf": [
                {
                  "type": "string",
                  "markdownDescription": "The secret to be fetched from Vault (e.g. 'production/db/password@ops' translates to secret 'ops/data/production/db', field `password`). [Learn More](https://docs.gitlab.com/ci/yaml/#secretsvault)"
                },
                {
                  "type": "object",
                  "properties": {
                    "engine": {
                      "type": "object",
                      "properties": {
                        "name": {
                          "type": "string"
                        },
                        "path": {
                          "type": "string"
                        }
                      },
                      "required": [
                        "name",
                        "path"
                      ]
                    },
                    "path": {
                      "type": "string"
                    },
                    "field": {
                      "type": "string"
                    }
                  },
                  "required": [
                    "engine",
                    "path",
                    "field"
                  ],
                  "additionalProperties": false
                }
              ]
            },
            "gcp_secret_manager": {
              "type": "object",
              "markdownDescription": "Defines the secret version to be fetched from GCP Secret Manager. Name refers to the secret name in GCP secret manager. Version refers to the desired secret version (defaults to 'latest').",
              "properties": {
                "name": {
                  "type": "string"
                },
                "version": {
                  "oneOf": [
                    {
                      "type": "string"
                    },
                    {
                      "type": "integer"
                    }
                  ],
                  "default": "version"
                }
              },
              "required": [
                "name"
              ],
              "additionalProperties": false
            },
            "azure_key_vault": {
              "type": "object",
              "properties": {
                "name": {
                  "type": "string"
                },
                "version": {
                  "type": "string"
                }
              },
              "required": [
                "name"
              ],
              "additionalProperties": false
            },
            "aws_secrets_manager": {
              "oneOf": [
                {
                  "type": "string",
                  "description": "The ARN or name of the secret to retrieve. To retrieve a secret from another account, you must use an ARN."
                },
                {
                  "type": "object",
                  "markdownDescription": "Defines the secret to be fetched from AWS Secrets Manager. The secret_id refers to the ARN or name of the secret in AWS Secrets Manager. Version_id and version_stage are optional parameters that can be used to specify a specific version of the secret, else AWSCURRENT version will be returned.",
                  "properties": {
                    "secret_id": {
                      "type": "string",
                      "description": "The ARN or name of the secret to retrieve. To retrieve a secret from another account, you must use an ARN."
                    },
                    "version_id": {
                      "type": "string",
                      "description": "The unique identifier of the version of the secret to retrieve. If you include both this parameter and VersionStage, the two parameters must refer to the same secret version. If you don't specify either a VersionStage or VersionId, Secrets Manager returns the AWSCURRENT version."
                    },
                    "version_stage": {
                      "type": "string",
                      "description": "The staging label of the version of the secret to retrieve. If you include both this parameter and VersionStage, the two parameters must refer to the same secret version. If you don't specify either a VersionStage or VersionId, Secrets Manager returns the AWSCURRENT version."
                    },
                    "region": {
                      "type": "string",
                      "description": "The AWS region where the secret is stored. Use this to override the region for a specific secret. Defaults to AWS_REGION variable."
                    },
                    "role_arn": {
                      "type": "string",
                      "description": "The ARN of the IAM role to assume before retrieving the secret. Use this to override the ARN. Defaults to AWS_ROLE_ARN variable."
                    },
                    "role_session_name": {
                      "type": "string",
                      "description": "The name of the session to use when assuming the role. Use this to override the session name. Defaults to AWS_ROLE_SESSION_NAME variable."
                    },
                    "field": {
                      "type": "string",
                      "description": "The name of the field to retrieve from the secret. If not specified, the entire secret is retrieved."
                    }
                  },
                  "required": [
                    "secret_id"
                  ],
                  "additionalProperties": false
                }
              ]
            },
            "file": {
              "type": "boolean",
              "default": true,
              "markdownDescription": "Configures the secret to be stored as either a file or variable type CI/CD variable. [Learn More](https://docs.gitlab.com/ci/yaml/#secretsfile)"
            },
            "token": {
              "type": "string",
              "description": "Specifies the JWT variable that should be used to authenticate with the secret provider."
            }
          },
          "anyOf": [
            {
              "required": [
                "vault"
              ]
            },
            {
              "required": [
                "azure_key_vault"
              ]
            },
            {
              "required": [
                "gcp_secret_manager"
              ]
            },
            {
              "required": [
                "aws_secrets_manager"
              ]
            }
          ],
          "dependencies": {
            "gcp_secret_manager": [
              "token"
            ]
          },
          "additionalProperties": false
        }
      }
    },
    "script": {
      "oneOf": [
        {
          "type": "string",
          "minLength": 1
        },
        {
          "type": "array",
          "items": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "array",
                "items": {
                  "type": "string"
                }
              }
            ]
          },
          "minItems": 1
        }
      ]
    },
    "steps": {
      "type": "array",
      "items": {
        "$ref": "#/definitions/step"
      }
    },
    "optional_script": {
      "oneOf": [
        {
          "type": "string"
        },
        {
          "type": "array",
          "items": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "array",
                "items": {
                  "type": "string"
                }
              }
            ]
          }
        }
      ]
    },
    "before_script": {
      "$ref": "#/definitions/optional_script",
      "markdownDescription": "Defines scripts that should run *before* the job. Can be set globally or per job. [Learn More](https://docs.gitlab.com/ci/yaml/#before_script)."
    },
    "after_script": {
      "$ref": "#/definitions/optional_script",
      "markdownDescription": "Defines scripts that should run *after* the job. Can be set globally or per job. [Learn More](https://docs.gitlab.com/ci/yaml/#after_script)."
    },
    "rules": {
      "type": [
        "array",
        "null"
      ],
      "markdownDescription": "Rules allows for an array of individual rule objects to be evaluated in order, until one matches and dynamically provides attributes to the job. [Learn More](https://docs.gitlab.com/ci/yaml/#rules).",
      "items": {
        "anyOf": [
          {
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "if": {
                "$ref": "#/definitions/if"
              },
              "changes": {
                "$ref": "#/definitions/changes"
              },
              "exists": {
                "$ref": "#/definitions/exists"
              },
              "variables": {
                "$ref": "#/definitions/rulesVariables"
              },
              "when": {
                "$ref": "#/definitions/when"
              },
              "start_in": {
                "$ref": "#/definitions/start_in"
              },
              "allow_failure": {
                "$ref": "#/definitions/allow_failure"
              },
              "needs": {
                "$ref": "#/definitions/rulesNeeds"
              },
              "interruptible": {
                "$ref": "#/definitions/interruptible"
              }
            }
          },
          {
            "type": "string",
            "minLength": 1
          },
          {
            "type": "array",
            "minItems": 1,
            "items": {
              "type": "string"
            }
          }
        ]
      }
    },
    "includeRules": {
      "type": [
        "array",
        "null"
      ],
      "markdownDescription": "You can use rules to conditionally include other configuration files. [Learn More](https://docs.gitlab.com/ci/yaml/includes/#use-rules-with-include).",
      "items": {
        "anyOf": [
          {
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "if": {
                "$ref": "#/definitions/if"
              },
              "changes": {
                "$ref": "#/definitions/changes"
              },
              "exists": {
                "$ref": "#/definitions/exists"
              },
              "when": {
                "markdownDescription": "Use `when: never` to exclude the configuration file if the condition matches. [Learn More](https://docs.gitlab.com/ci/yaml/includes/#include-with-rulesif).",
                "oneOf": [
                  {
                    "type": "string",
                    "enum": [
                      "never",
                      "always"
                    ]
                  },
                  {
                    "type": "null"
                  }
                ]
              }
            }
          },
          {
            "type": "string",
            "minLength": 1
          },
          {
            "type": "array",
            "minItems": 1,
            "items": {
              "type": "string"
            }
          }
        ]
      }
    },
    "workflowName": {
      "type": "string",
      "markdownDescription": "Defines the pipeline name. [Learn More](https://docs.gitlab.com/ci/yaml/#workflowname).",
      "minLength": 1,
      "maxLength": 255
    },
    "workflowAutoCancel": {
      "type": "object",
      "description": "Define the rules for when pipeline should be automatically cancelled.",
      "additionalProperties": false,
      "properties": {
        "on_job_failure": {
          "markdownDescription": "Define which jobs to stop after a job fails.",
          "default": "none",
          "type": "string",
          "enum": [
            "none",
            "all"
          ]
        },
        "on_new_commit": {
          "markdownDescription": "Configure the behavior of the auto-cancel redundant pipelines feature. [Learn More](https://docs.gitlab.com/ci/yaml/#workflowauto_cancelon_new_commit)",
          "type": "string",
          "enum": [
            "conservative",
            "interruptible",
            "none"
          ]
        }
      }
    },
    "globalVariables": {
      "markdownDescription": "Defines default variables for all jobs. Job level property overrides global variables. [Learn More](https://docs.gitlab.com/ci/yaml/#variables).",
      "type": "object",
      "patternProperties": {
        ".*": {
          "oneOf": [
            {
              "type": [
                "boolean",
                "number",
                "string"
              ]
            },
            {
              "type": "object",
              "properties": {
                "value": {
                  "type": "string",
                  "markdownDescription": "Default value of the variable. If used with `options`, `value` must be included in the array. [Learn More](https://docs.gitlab.com/ci/yaml/#variablesvalue)"
                },
                "options": {
                  "type": "array",
                  "items": {
                    "type": "string"
                  },
                  "minItems": 1,
                  "uniqueItems": true,
                  "markdownDescription": "A list of predefined values that users can select from in the **Run pipeline** page when running a pipeline manually. [Learn More](https://docs.gitlab.com/ci/yaml/#variablesoptions)"
                },
                "description": {
                  "type": "string",
                  "markdownDescription": "Explains what the variable is used for, what the acceptable values are. Variables with `description` are prefilled when running a pipeline manually. [Learn More](https://docs.gitlab.com/ci/yaml/#variablesdescription)."
                },
                "expand": {
                  "type": "boolean",
                  "markdownDescription": "If the variable is expandable or not. [Learn More](https://docs.gitlab.com/ci/yaml/#variablesexpand)."
                }
              },
              "additionalProperties": false
            }
          ]
        }
      }
    },
    "jobVariables": {
      "markdownDescription": "Defines variables for a job. [Learn More](https://docs.gitlab.com/ci/yaml/#variables).",
      "type": "object",
      "patternProperties": {
        ".*": {
          "oneOf": [
            {
              "type": [
                "boolean",
                "number",
                "string"
              ]
            },
            {
              "type": "object",
              "properties": {
                "value": {
                  "type": "string"
                },
                "expand": {
                  "type": "boolean",
                  "markdownDescription": "Defines if the variable is expandable or not. [Learn More](https://docs.gitlab.com/ci/yaml/#variablesexpand)."
                }
              },
              "additionalProperties": false
            }
          ]
        }
      }
    },
    "rulesVariables": {
      "markdownDescription": "Defines variables for a rule result. [Learn More](https://docs.gitlab.com/ci/yaml/#rulesvariables).",
      "type": "object",
      "patternProperties": {
        ".*": {
          "type": [
            "boolean",
            "number",
            "string"
          ]
        }
      }
    },
    "if": {
      "type": "string",
      "markdownDescription": "Expression to evaluate whether additional attributes should be provided to the job. [Learn More](https://docs.gitlab.com/ci/yaml/#rulesif)."
    },
    "changes": {
      "markdownDescription": "Additional attributes will be provided to job if any of the provided paths matches a modified file. [Learn More](https://docs.gitlab.com/ci/yaml/#ruleschanges).",
      "anyOf": [
        {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "paths"
          ],
          "properties": {
            "paths": {
              "type": "array",
              "description": "List of file paths.",
              "items": {
                "type": "string"
              }
            },
            "compare_to": {
              "type": "string",
              "description": "Ref for comparing changes."
            }
          }
        },
        {
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      ]
    },
    "exists": {
      "markdownDescription": "Additional attributes will be provided to job if any of the provided paths matches an existing file in the repository. [Learn More](https://docs.gitlab.com/ci/yaml/#rulesexists).",
      "anyOf": [
        {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "paths"
          ],
          "properties": {
            "paths": {
              "type": "array",
              "description": "List of file paths.",
              "items": {
                "type": "string"
              }
            },
            "project": {
              "type": "string",
              "description": "Path of the project to search in."
            }
          }
        },
        {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "paths",
            "project"
          ],
          "properties": {
            "paths": {
              "type": "array",
              "description": "List of file paths.",
              "items": {
                "type": "string"
              }
            },
            "project": {
              "type": "string",
              "description": "Path of the project to search in."
            },
            "ref": {
              "type": "string",
              "description": "Ref of the project to search in."
            }
          }
        }
      ]
    },
    "timeout": {
      "type": "string",
      "markdownDescription": "Allows you to configure a timeout for a specific job (e.g. `1 minute`, `1h 30m 12s`). [Learn More](https://docs.gitlab.com/ci/yaml/#timeout).",
      "minLength": 1
    },
    "start_in": {
      "type": "string",
      "markdownDescription": "Used in conjunction with 'when: delayed' to set how long to delay before starting a job. e.g. '5', 5 seconds, 30 minutes, 1 week, etc. [Learn More](https://docs.gitlab.com/ci/jobs/job_control/#run-a-job-after-a-delay).",
      "minLength": 1
    },
    "rulesNeeds": {
      "markdownDescription": "Use needs in rules to update job needs for specific conditions. When a condition matches a rule, the job's needs configuration is completely replaced with the needs in the rule. [Learn More](https://docs.gitlab.com/ci/yaml/#rulesneeds).",
      "type": "array",
      "items": {
        "oneOf": [
          {
            "type": "string"
          },
          {
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "job": {
                "type": "string",
                "minLength": 1,
                "description": "Name of a job that is defined in the pipeline."
              },
              "artifacts": {
                "type": "boolean",
                "description": "Download artifacts of the job in needs."
              },
              "optional": {
                "type": "boolean",
                "description": "Whether the job needs to be present in the pipeline to run ahead of the current job."
              }
            },
            "required": [
              "job"
            ]
          }
        ]
      }
    },
    "allow_failure": {
      "markdownDescription": "Allow job to fail. A failed job does not cause the pipeline to fail. [Learn More](https://docs.gitlab.com/ci/yaml/#allow_failure).",
      "oneOf": [
        {
          "description": "Setting this option to true will allow the job to fail while still letting the pipeline pass.",
          "type": "boolean",
          "default": false
        },
        {
          "description": "Exit code that are not considered failure. The job fails for any other exit code.",
          "type": "object",
          "additionalProperties": false,
          "required": [
            "exit_codes"
          ],
          "properties": {
            "exit_codes": {
              "type": "integer"
            }
          }
        },
        {
          "description": "You can list which exit codes are not considered failures. The job fails for any other exit code.",
          "type": "object",
          "additionalProperties": false,
          "required": [
            "exit_codes"
          ],
          "properties": {
            "exit_codes": {
              "type": "array",
              "minItems": 1,
              "uniqueItems": true,
              "items": {
                "type": "integer"
              }
            }
          }
        }
      ]
    },
    "parallel": {
      "description": "Splits up a single job into multiple that run in parallel. Provides `CI_NODE_INDEX` and `CI_NODE_TOTAL` environment variables to the jobs.",
      "oneOf": [
        {
          "type": "integer",
          "description": "Creates N instances of the job that run in parallel.",
          "default": 0,
          "minimum": 1,
          "maximum": 200
        },
        {
          "type": "object",
          "properties": {
            "matrix": {
              "type": "array",
              "description": "Defines different variables for jobs that are running in parallel.",
              "items": {
                "type": "object",
                "description": "Defines the variables for a specific job.",
                "additionalProperties": {
                  "type": [
                    "string",
                    "number",
                    "array"
                  ]
                }
              },
              "maxItems": 200
            }
          },
          "additionalProperties": false,
          "required": [
            "matrix"
          ]
        }
      ]
    },
    "parallel_matrix": {
      "description": "Use the `needs:parallel:matrix` keyword to specify parallelized jobs needed to be completed for the job to run. [Learn More](https://docs.gitlab.com/ci/yaml/#needsparallelmatrix)",
      "oneOf": [
        {
          "type": "object",
          "properties": {
            "matrix": {
              "type": "array",
              "description": "Defines different variables for jobs that are running in parallel.",
              "items": {
                "type": "object",
                "description": "Defines the variables for a specific job.",
                "additionalProperties": {
                  "type": [
                    "string",
                    "number",
                    "array"
                  ]
                }
              },
              "maxItems": 200
            }
          },
          "additionalProperties": false,
          "required": [
            "matrix"
          ]
        }
      ]
    },
    "when": {
      "markdownDescription": "Describes the conditions for when to run the job. Defaults to 'on_success'. [Learn More](https://docs.gitlab.com/ci/yaml/#when).",
      "default": "on_success",
      "type": "string",
      "enum": [
        "on_success",
        "on_failure",
        "always",
        "never",
        "manual",
        "delayed"
      ]
    },
    "cache": {
      "markdownDescription": "Use `cache` to specify a list of files and directories to cache between jobs. You can only use paths that are in the local working copy. [Learn More](https://docs.gitlab.com/ci/yaml/#cache)",
      "oneOf": [
        {
          "$ref": "#/definitions/cache_item"
        },
        {
          "type": "array",
          "items": {
            "$ref": "#/definitions/cache_item"
          }
        }
      ]
    },
    "cache_item": {
      "type": "object",
      "properties": {
        "key": {
          "markdownDescription": "Use the `cache:key` keyword to give each cache a unique identifying key. All jobs that use the same cache key use the same cache, including in different pipelines. Must be used with `cache:path`, or nothing is cached. [Learn More](https://docs.gitlab.com/ci/yaml/#cachekey).",
          "oneOf": [
            {
              "type": "string",
              "pattern": "^[^/]*[^./][^/]*$"
            },
            {
              "type": "object",
              "properties": {
                "files": {
                  "markdownDescription": "Use the `cache:key:files` keyword to generate a new key when one or two specific files change. [Learn More](https://docs.gitlab.com/ci/yaml/#cachekeyfiles)",
                  "type": "array",
                  "items": {
                    "type": "string"
                  },
                  "minItems": 1,
                  "maxItems": 2
                },
                "prefix": {
                  "markdownDescription": "Use `cache:key:prefix` to combine a prefix with the SHA computed for `cache:key:files`. [Learn More](https://docs.gitlab.com/ci/yaml/#cachekeyprefix)",
                  "type": "string"
                }
              }
            }
          ]
        },
        "paths": {
          "type": "array",
          "markdownDescription": "Use the `cache:paths` keyword to choose which files or directories to cache. [Learn More](https://docs.gitlab.com/ci/yaml/#cachepaths)",
          "items": {
            "type": "string"
          }
        },
        "policy": {
          "type": "string",
          "markdownDescription": "Determines the strategy for downloading and updating the cache. [Learn More](https://docs.gitlab.com/ci/yaml/#cachepolicy)",
          "default": "pull-push",
          "pattern": "pull-push|pull|push|\\$\\w{1,255}"
        },
        "unprotect": {
          "type": "boolean",
          "markdownDescription": "Use `unprotect: true` to set a cache to be shared between protected and unprotected branches.",
          "default": false
        },
        "untracked": {
          "type": "boolean",
          "markdownDescription": "Use `untracked: true` to cache all files that are untracked in your Git repository. [Learn More](https://docs.gitlab.com/ci/yaml/#cacheuntracked)",
          "default": false
        },
        "when": {
          "type": "string",
          "markdownDescription": "Defines when to save the cache, based on the status of the job. [Learn More](https://docs.gitlab.com/ci/yaml/#cachewhen).",
          "default": "on_success",
          "enum": [
            "on_success",
            "on_failure",
            "always"
          ]
        },
        "fallback_keys": {
          "type": "array",
          "markdownDescription": "List of keys to download cache from if no cache hit occurred for key",
          "items": {
            "type": "string"
          },
          "maxItems": 5
        }
      }
    },
    "filter_refs": {
      "type": "array",
      "description": "Filter job by different keywords that determine origin or state, or by supplying string/regex to check against branch/tag names.",
      "items": {
        "anyOf": [
          {
            "oneOf": [
              {
                "enum": [
                  "branches"
                ],
                "description": "When a branch is pushed."
              },
              {
                "enum": [
                  "tags"
                ],
                "description": "When a tag is pushed."
              },
              {
                "enum": [
                  "api"
                ],
                "description": "When a pipeline has been triggered by a second pipelines API (not triggers API)."
              },
              {
                "enum": [
                  "external"
                ],
                "description": "When using CI services other than GitLab"
              },
              {
                "enum": [
                  "pipelines"
                ],
                "description": "For multi-project triggers, created using the API with 'CI_JOB_TOKEN'."
              },
              {
                "enum": [
                  "pushes"
                ],
                "description": "Pipeline is triggered by a `git push` by the user"
              },
              {
                "enum": [
                  "schedules"
                ],
                "description": "For scheduled pipelines."
              },
              {
                "enum": [
                  "triggers"
                ],
                "description": "For pipelines created using a trigger token."
              },
              {
                "enum": [
                  "web"
                ],
                "description": "For pipelines created using *Run pipeline* button in GitLab UI (under your project's *Pipelines*)."
              }
            ]
          },
          {
            "type": "string",
            "description": "String or regular expression to match against tag or branch names."
          }
        ]
      }
    },
    "filter": {
      "oneOf": [
        {
          "type": "null"
        },
        {
          "$ref": "#/definitions/filter_refs"
        },
        {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "refs": {
              "$ref": "#/definitions/filter_refs"
            },
            "kubernetes": {
              "enum": [
                "active"
              ],
              "description": "Filter job based on if Kubernetes integration is active."
            },
            "variables": {
              "type": "array",
              "markdownDescription": "Filter job by checking comparing values of CI/CD variables. [Learn More](https://docs.gitlab.com/ci/jobs/job_control/#cicd-variable-expressions).",
              "items": {
                "type": "string"
              }
            },
            "changes": {
              "type": "array",
              "description": "Filter job creation based on files that were modified in a git push.",
              "items": {
                "type": "string"
              }
            }
          }
        }
      ]
    },
    "retry": {
      "markdownDescription": "Retry a job if it fails. Can be a simple integer or object definition. [Learn More](https://docs.gitlab.com/ci/yaml/#retry).",
      "oneOf": [
        {
          "$ref": "#/definitions/retry_max"
        },
        {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "max": {
              "$ref": "#/definitions/retry_max"
            },
            "when": {
              "markdownDescription": "Either a single or array of error types to trigger job retry. [Learn More](https://docs.gitlab.com/ci/yaml/#retrywhen).",
              "oneOf": [
                {
                  "$ref": "#/definitions/retry_errors"
                },
                {
                  "type": "array",
                  "items": {
                    "$ref": "#/definitions/retry_errors"
                  }
                }
              ]
            },
            "exit_codes": {
              "markdownDescription": "Either a single or array of exit codes to trigger job retry on. [Learn More](https://docs.gitlab.com/ci/yaml/#retryexit_codes).",
              "oneOf": [
                {
                  "description": "Retry when the job exit code is included in the array's values.",
                  "type": "array",
                  "minItems": 1,
                  "uniqueItems": true,
                  "items": {
                    "type": "integer"
                  }
                },
                {
                  "description": "Retry when the job exit code is equal to.",
                  "type": "integer"
                }
              ]
            }
          }
        }
      ]
    },
    "retry_max": {
      "type": "integer",
      "description": "The number of times the job will be retried if it fails. Defaults to 0 and can max be retried 2 times (3 times total).",
      "default": 0,
      "minimum": 0,
      "maximum": 2
    },
    "retry_errors": {
      "oneOf": [
        {
          "const": "always",
          "description": "Retry on any failure (default)."
        },
        {
          "const": "unknown_failure",
          "description": "Retry when the failure reason is unknown."
        },
        {
          "const": "script_failure",
          "description": "Retry when the script failed."
        },
        {
          "const": "api_failure",
          "description": "Retry on API failure."
        },
        {
          "const": "stuck_or_timeout_failure",
          "description": "Retry when the job got stuck or timed out."
        },
        {
          "const": "runner_system_failure",
          "description": "Retry if there is a runner system failure (for example, job setup failed)."
        },
        {
          "const": "runner_unsupported",
          "description": "Retry if the runner is unsupported."
        },
        {
          "const": "stale_schedule",
          "description": "Retry if a delayed job could not be executed."
        },
        {
          "const": "job_execution_timeout",
          "description": "Retry if the script exceeded the maximum execution time set for the job."
        },
        {
          "const": "archived_failure",
          "description": "Retry if the job is archived and can’t be run."
        },
        {
          "const": "unmet_prerequisites",
          "description": "Retry if the job failed to complete prerequisite tasks."
        },
        {
          "const": "scheduler_failure",
          "description": "Retry if the scheduler failed to assign the job to a runner."
        },
        {
          "const": "data_integrity_failure",
          "description": "Retry if there is an unknown job problem."
        }
      ]
    },
    "interruptible": {
      "type": "boolean",
      "markdownDescription": "Interruptible is used to indicate that a job should be canceled if made redundant by a newer pipeline run. [Learn More](https://docs.gitlab.com/ci/yaml/#interruptible).",
      "default": false
    },
    "inputs": {
      "markdownDescription": "Used to pass input values to included templates, components, downstream pipelines, or child pipelines. [Learn More](https://docs.gitlab.com/ci/inputs/).",
      "type": "object",
      "patternProperties": {
        "^[a-zA-Z0-9_-]+$": {
          "description": "Input parameter value that matches parameter names defined in spec:inputs of the included configuration.",
          "oneOf": [
            {
              "type": "string",
              "maxLength": 1024
            },
            {
              "type": "number"
            },
            {
              "type": "boolean"
            },
            {
              "type": "array",
              "items": {
                "oneOf": [
                  {
                    "type": "string"
                  },
                  {
                    "type": "number"
                  },
                  {
                    "type": "boolean"
                  },
                  {
                    "type": "object",
                    "additionalProperties": true
                  },
                  {
                    "type": "array",
                    "items": {
                      "additionalProperties": true
                    }
                  }
                ]
              }
            },
            {
              "type": "object",
              "additionalProperties": true
            },
            {
              "type": "null"
            }
          ]
        }
      },
      "additionalProperties": false
    },
    "job": {
      "allOf": [
        {
          "$ref": "#/definitions/job_template"
        }
      ]
    },
    "job_template": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "image": {
          "$ref": "#/definitions/image"
        },
        "services": {
          "$ref": "#/definitions/services"
        },
        "before_script": {
          "$ref": "#/definitions/before_script"
        },
        "after_script": {
          "$ref": "#/definitions/after_script"
        },
        "hooks": {
          "$ref": "#/definitions/hooks"
        },
        "rules": {
          "$ref": "#/definitions/rules"
        },
        "variables": {
          "$ref": "#/definitions/jobVariables"
        },
        "cache": {
          "$ref": "#/definitions/cache"
        },
        "id_tokens": {
          "$ref": "#/definitions/id_tokens"
        },
        "identity": {
          "$ref": "#/definitions/identity"
        },
        "secrets": {
          "$ref": "#/definitions/secrets"
        },
        "script": {
          "$ref": "#/definitions/script",
          "markdownDescription": "Shell scripts executed by the Runner. The only required property of jobs. Be careful with special characters (e.g. `:`, `{`, `}`, `&`) and use single or double quotes to avoid issues. [Learn More](https://docs.gitlab.com/ci/yaml/#script)"
        },
        "run": {
          "$ref": "#/definitions/steps",
          "markdownDescription": "Specifies a list of steps to execute in the job. The `run` keyword is an alternative to `script` and allows for more advanced job configuration. Each step is an object that defines a single task or command. Use either `run` or `script` in a job, but not both, otherwise the pipeline will error out."
        },
        "stage": {
          "description": "Define what stage the job will run in.",
          "anyOf": [
            {
              "type": "string",
              "minLength": 1
            },
            {
              "type": "array",
              "minItems": 1,
              "items": {
                "type": "string"
              }
            }
          ]
        },
        "only": {
          "$ref": "#/definitions/filter",
          "description": "Job will run *only* when these filtering options match."
        },
        "extends": {
          "description": "The name of one or more jobs to inherit configuration from.",
          "oneOf": [
            {
              "type": "string"
            },
            {
              "type": "array",
              "items": {
                "type": "string"
              },
              "minItems": 1
            }
          ]
        },
        "needs": {
          "description": "The list of jobs in previous stages whose sole completion is needed to start the current job.",
          "type": "array",
          "items": {
            "oneOf": [
              {
                "type": "string"
              },
              {
                "type": "object",
                "additionalProperties": false,
                "properties": {
                  "job": {
                    "type": "string"
                  },
                  "artifacts": {
                    "type": "boolean"
                  },
                  "optional": {
                    "type": "boolean"
                  },
                  "parallel": {
                    "$ref": "#/definitions/parallel_matrix"
                  }
                },
                "required": [
                  "job"
                ]
              },
              {
                "type": "object",
                "additionalProperties": false,
                "properties": {
                  "pipeline": {
                    "type": "string"
                  },
                  "job": {
                    "type": "string"
                  },
                  "artifacts": {
                    "type": "boolean"
                  },
                  "parallel": {
                    "$ref": "#/definitions/parallel_matrix"
                  }
                },
                "required": [
                  "job",
                  "pipeline"
                ]
              },
              {
                "type": "object",
                "additionalProperties": false,
                "properties": {
                  "job": {
                    "type": "string"
                  },
                  "project": {
                    "type": "string"
                  },
                  "ref": {
                    "type": "string"
                  },
                  "artifacts": {
                    "type": "boolean"
                  },
                  "parallel": {
                    "$ref": "#/definitions/parallel_matrix"
                  }
                },
                "required": [
                  "job",
                  "project",
                  "ref"
                ]
              },
              {
                "$ref": "#/definitions/!reference"
              }
            ]
          }
        },
        "except": {
          "$ref": "#/definitions/filter",
          "description": "Job will run *except* for when these filtering options match."
        },
        "tags": {
          "$ref": "#/definitions/tags"
        },
        "allow_failure": {
          "$ref": "#/definitions/allow_failure"
        },
        "timeout": {
          "$ref": "#/definitions/timeout"
        },
        "when": {
          "$ref": "#/definitions/when"
        },
        "start_in": {
          "$ref": "#/definitions/start_in"
        },
        "manual_confirmation": {
          "markdownDescription": "Describes the Custom confirmation message for a manual job [Learn More](https://docs.gitlab.com/ci/yaml/#when).",
          "type": "string"
        },
        "dependencies": {
          "type": "array",
          "description": "Specify a list of job names from earlier stages from which artifacts should be loaded. By default, all previous artifacts are passed. Use an empty array to skip downloading artifacts.",
          "items": {
            "type": "string"
          }
        },
        "artifacts": {
          "$ref": "#/definitions/artifacts"
        },
        "environment": {
          "description": "Used to associate environment metadata with a deploy. Environment can have a name and URL attached to it, and will be displayed under /environments under the project.",
          "oneOf": [
            {
              "type": "string"
            },
            {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "name": {
                  "type": "string",
                  "description": "The name of the environment, e.g. 'qa', 'staging', 'production'.",
                  "minLength": 1
                },
                "url": {
                  "type": "string",
                  "description": "When set, this will expose buttons in various places for the current environment in GitLab, that will take you to the defined URL.",
                  "format": "uri",
                  "pattern": "^(https?://.+|\\$[A-Za-z]+)"
                },
                "on_stop": {
                  "type": "string",
                  "description": "The name of a job to execute when the environment is about to be stopped."
                },
                "action": {
                  "enum": [
                    "start",
                    "prepare",
                    "stop",
                    "verify",
                    "access"
                  ],
                  "description": "Specifies what this job will do. 'start' (default) indicates the job will start the deployment. 'prepare'/'verify'/'access' indicates this will not affect the deployment. 'stop' indicates this will stop the deployment.",
                  "default": "start"
                },
                "auto_stop_in": {
                  "type": "string",
                  "description": "The amount of time it should take before GitLab will automatically stop the environment. Supports a wide variety of formats, e.g. '1 week', '3 mins 4 sec', '2 hrs 20 min', '2h20min', '6 mos 1 day', '47 yrs 6 mos and 4d', '3 weeks and 2 days'."
                },
                "kubernetes": {
                  "type": "object",
                  "description": "Used to configure the kubernetes deployment for this environment. This is currently not supported for kubernetes clusters that are managed by GitLab.",
                  "properties": {
                    "namespace": {
                      "type": "string",
                      "description": "The kubernetes namespace where this environment should be deployed to.",
                      "minLength": 1
                    },
                    "agent": {
                      "type": "string",
                      "description": "Specifies the GitLab Agent for Kubernetes. The format is `path/to/agent/project:agent-name`."
                    },
                    "flux_resource_path": {
                      "type": "string",
                      "description": "The Flux resource path to associate with this environment. This must be the full resource path. For example, 'helm.toolkit.fluxcd.io/v2/namespaces/gitlab-agent/helmreleases/gitlab-agent'."
                    }
                  }
                },
                "deployment_tier": {
                  "type": "string",
                  "description": "Explicitly specifies the tier of the deployment environment if non-standard environment name is used.",
                  "enum": [
                    "production",
                    "staging",
                    "testing",
                    "development",
                    "other"
                  ]
                }
              },
              "required": [
                "name"
              ]
            }
          ]
        },
        "release": {
          "type": "object",
          "description": "Indicates that the job creates a Release.",
          "additionalProperties": false,
          "properties": {
            "tag_name": {
              "type": "string",
              "description": "The tag_name must be specified. It can refer to an existing Git tag or can be specified by the user.",
              "minLength": 1
            },
            "tag_message": {
              "type": "string",
              "description": "Message to use if creating a new annotated tag."
            },
            "description": {
              "type": "string",
              "description": "Specifies the longer description of the Release.",
              "minLength": 1
            },
            "name": {
              "type": "string",
              "description": "The Release name. If omitted, it is populated with the value of release: tag_name."
            },
            "ref": {
              "type": "string",
              "description": "If the release: tag_name doesn’t exist yet, the release is created from ref. ref can be a commit SHA, another tag name, or a branch name."
            },
            "milestones": {
              "type": "array",
              "description": "The title of each milestone the release is associated with.",
              "items": {
                "type": "string"
              }
            },
            "released_at": {
              "type": "string",
              "description": "The date and time when the release is ready. Defaults to the current date and time if not defined. Should be enclosed in quotes and expressed in ISO 8601 format.",
              "format": "date-time",
              "pattern": "^(?:[1-9]\\d{3}-(?:(?:0[1-9]|1[0-2])-(?:0[1-9]|1\\d|2[0-8])|(?:0[13-9]|1[0-2])-(?:29|30)|(?:0[13578]|1[02])-31)|(?:[1-9]\\d(?:0[48]|[2468][048]|[13579][26])|(?:[2468][048]|[13579][26])00)-02-29)T(?:[01]\\d|2[0-3]):[0-5]\\d:[0-5]\\d(?:Z|[+-][01]\\d:[0-5]\\d)$"
            },
            "assets": {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "links": {
                  "type": "array",
                  "description": "Include asset links in the release.",
                  "items": {
                    "type": "object",
                    "additionalProperties": false,
                    "properties": {
                      "name": {
                        "type": "string",
                        "description": "The name of the link.",
                        "minLength": 1
                      },
                      "url": {
                        "type": "string",
                        "description": "The URL to download a file.",
                        "minLength": 1
                      },
                      "filepath": {
                        "type": "string",
                        "description": "The redirect link to the url."
                      },
                      "link_type": {
                        "type": "string",
                        "description": "The content kind of what users can download via url.",
                        "enum": [
                          "runbook",
                          "package",
                          "image",
                          "other"
                        ]
                      }
                    },
                    "required": [
                      "name",
                      "url"
                    ]
                  },
                  "minItems": 1
                }
              },
              "required": [
                "links"
              ]
            }
          },
          "required": [
            "tag_name",
            "description"
          ]
        },
        "coverage": {
          "type": "string",
          "description": "Must be a regular expression, optionally but recommended to be quoted, and must be surrounded with '/'. Example: '/Code coverage: \\d+\\.\\d+/'",
          "format": "regex",
          "pattern": "^/.+/$"
        },
        "retry": {
          "$ref": "#/definitions/retry"
        },
        "parallel": {
          "$ref": "#/definitions/parallel"
        },
        "interruptible": {
          "$ref": "#/definitions/interruptible"
        },
        "resource_group": {
          "type": "string",
          "description": "Limit job concurrency. Can be used to ensure that the Runner will not run certain jobs simultaneously."
        },
        "trigger": {
          "markdownDescription": "Trigger allows you to define downstream pipeline trigger. When a job created from trigger definition is started by GitLab, a downstream pipeline gets created. [Learn More](https://docs.gitlab.com/ci/yaml/#trigger).",
          "oneOf": [
            {
              "type": "object",
              "markdownDescription": "Trigger a multi-project pipeline. [Learn More](https://docs.gitlab.com/ci/pipelines/downstream_pipelines/#multi-project-pipelines).",
              "additionalProperties": false,
              "properties": {
                "project": {
                  "description": "Path to the project, e.g. `group/project`, or `group/sub-group/project`.",
                  "type": "string",
                  "pattern": "(?:\\S/\\S|\\$\\S+)"
                },
                "branch": {
                  "description": "The branch name that a downstream pipeline will use",
                  "type": "string"
                },
                "strategy": {
                  "description": "You can mirror or depend on the pipeline status from the triggered pipeline to the source bridge job by using strategy: `depend` or `mirror`",
                  "type": "string",
                  "enum": [
                    "depend",
                    "mirror"
                  ]
                },
                "inputs": {
                  "$ref": "#/definitions/inputs"
                },
                "forward": {
                  "description": "Specify what to forward to the downstream pipeline.",
                  "type": "object",
                  "additionalProperties": false,
                  "properties": {
                    "yaml_variables": {
                      "type": "boolean",
                      "description": "Variables defined in the trigger job are passed to downstream pipelines.",
                      "default": true
                    },
                    "pipeline_variables": {
                      "type": "boolean",
                      "description": "Variables added for manual pipeline runs and scheduled pipelines are passed to downstream pipelines.",
                      "default": false
                    }
                  }
                }
              },
              "required": [
                "project"
              ],
              "dependencies": {
                "branch": [
                  "project"
                ]
              }
            },
            {
              "type": "object",
              "description": "Trigger a child pipeline. [Learn More](https://docs.gitlab.com/ci/pipelines/downstream_pipelines/#parent-child-pipelines).",
              "additionalProperties": false,
              "properties": {
                "include": {
                  "oneOf": [
                    {
                      "description": "Relative path from local repository root (`/`) to the local YAML file to define the pipeline configuration.",
                      "type": "string",
                      "format": "uri-reference",
                      "pattern": "\\.ya?ml$"
                    },
                    {
                      "type": "array",
                      "description": "References a local file or an artifact from another job to define the pipeline configuration.",
                      "maxItems": 3,
                      "items": {
                        "oneOf": [
                          {
                            "type": "object",
                            "additionalProperties": false,
                            "properties": {
                              "local": {
                                "description": "Relative path from local repository root (`/`) to the local YAML file to define the pipeline configuration.",
                                "type": "string",
                                "format": "uri-reference",
                                "pattern": "\\.ya?ml$"
                              },
                              "inputs": {
                                "$ref": "#/definitions/inputs"
                              }
                            },
                            "required": [
                              "local"
                            ]
                          },
                          {
                            "type": "object",
                            "additionalProperties": false,
                            "properties": {
                              "template": {
                                "description": "Name of the template YAML file to use in the pipeline configuration.",
                                "type": "string",
                                "format": "uri-reference",
                                "pattern": "\\.ya?ml$"
                              },
                              "inputs": {
                                "$ref": "#/definitions/inputs"
                              }
                            },
                            "required": [
                              "template"
                            ]
                          },
                          {
                            "type": "object",
                            "additionalProperties": false,
                            "properties": {
                              "artifact": {
                                "description": "Relative path to the generated YAML file which is extracted from the artifacts and used as the configuration for triggering the child pipeline.",
                                "type": "string",
                                "format": "uri-reference",
                                "pattern": "\\.ya?ml$"
                              },
                              "job": {
                                "description": "Job name which generates the artifact",
                                "type": "string"
                              },
                              "inputs": {
                                "$ref": "#/definitions/inputs"
                              }
                            },
                            "required": [
                              "artifact",
                              "job"
                            ]
                          },
                          {
                            "type": "object",
                            "additionalProperties": false,
                            "properties": {
                              "project": {
                                "description": "Path to another private project under the same GitLab instance, like `group/project` or `group/sub-group/project`.",
                                "type": "string",
                                "pattern": "(?:\\S/\\S|\\$\\S+)"
                              },
                              "ref": {
                                "description": "Branch/Tag/Commit hash for the target project.",
                                "minLength": 1,
                                "type": "string"
                              },
                              "file": {
                                "description": "Relative path from repository root (`/`) to the pipeline configuration YAML file.",
                                "type": "string",
                                "format": "uri-reference",
                                "pattern": "\\.ya?ml$"
                              },
                              "inputs": {
                                "$ref": "#/definitions/inputs"
                              }
                            },
                            "required": [
                              "project",
                              "file"
                            ]
                          },
                          {
                            "type": "object",
                            "additionalProperties": false,
                            "properties": {
                              "component": {
                                "description": "Local path to component directory or full path to external component directory.",
                                "type": "string",
                                "format": "uri-reference"
                              },
                              "inputs": {
                                "$ref": "#/definitions/inputs"
                              }
                            },
                            "required": [
                              "component"
                            ]
                          },
                          {
                            "type": "object",
                            "additionalProperties": false,
                            "properties": {
                              "remote": {
                                "description": "URL to a `yaml`/`yml` template file using HTTP/HTTPS.",
                                "type": "string",
                                "format": "uri-reference",
                                "pattern": "^https?://.+\\.ya?ml$"
                              },
                              "inputs": {
                                "$ref": "#/definitions/inputs"
                              }
                            },
                            "required": [
                              "remote"
                            ]
                          }
                        ]
                      }
                    }
                  ]
                },
                "strategy": {
                  "description": "You can mirror or depend on the pipeline status from the triggered pipeline to the source bridge job by using strategy: `depend` or `mirror`",
                  "type": "string",
                  "enum": [
                    "depend",
                    "mirror"
                  ]
                },
                "forward": {
                  "description": "Specify what to forward to the downstream pipeline.",
                  "type": "object",
                  "additionalProperties": false,
                  "properties": {
                    "yaml_variables": {
                      "type": "boolean",
                      "description": "Variables defined in the trigger job are passed to downstream pipelines.",
                      "default": true
                    },
                    "pipeline_variables": {
                      "type": "boolean",
                      "description": "Variables added for manual pipeline runs and scheduled pipelines are passed to downstream pipelines.",
                      "default": false
                    }
                  }
                }
              }
            },
            {
              "markdownDescription": "Path to the project, e.g. `group/project`, or `group/sub-group/project`. [Learn More](https://docs.gitlab.com/ci/yaml/#trigger).",
              "type": "string",
              "pattern": "(?:\\S/\\S|\\$\\S+)"
            }
          ]
        },
        "inherit": {
          "type": "object",
          "markdownDescription": "Controls inheritance of globally-defined defaults and variables. Boolean values control inheritance of all default: or variables: keywords. To inherit only a subset of default: or variables: keywords, specify what you wish to inherit. Anything not listed is not inherited. [Learn More](https://docs.gitlab.com/ci/yaml/#inherit).",
          "properties": {
            "default": {
              "markdownDescription": "Whether to inherit all globally-defined defaults or not. Or subset of inherited defaults. [Learn more](https://docs.gitlab.com/ci/yaml/#inheritdefault).",
              "oneOf": [
                {
                  "type": "boolean"
                },
                {
                  "type": "array",
                  "items": {
                    "type": "string",
                    "enum": [
                      "after_script",
                      "artifacts",
                      "before_script",
                      "cache",
                      "image",
                      "interruptible",
                      "retry",
                      "services",
                      "tags",
                      "timeout"
                    ]
                  }
                }
              ]
            },
            "variables": {
              "markdownDescription": "Whether to inherit all globally-defined variables or not. Or subset of inherited variables. [Learn More](https://docs.gitlab.com/ci/yaml/#inheritvariables).",
              "oneOf": [
                {
                  "type": "boolean"
                },
                {
                  "type": "array",
                  "items": {
                    "type": "string"
                  }
                }
              ]
            }
          },
          "additionalProperties": false
        },
        "publish": {
          "description": "Deprecated. Use `pages.publish` instead. A path to a directory that contains the files to be published with Pages.",
          "type": "string"
        },
        "pages": {
          "oneOf": [
            {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "path_prefix": {
                  "type": "string",
                  "markdownDescription": "The GitLab Pages URL path prefix used in this version of pages. The given value is converted to lowercase, shortened to 63 bytes, and everything except alphanumeric characters is replaced with a hyphen. Leading and trailing hyphens are not permitted."
                },
                "expire_in": {
                  "type": "string",
                  "markdownDescription": "How long the deployment should be active. Deployments that have expired are no longer available on the web. Supports a wide variety of formats, e.g. '1 week', '3 mins 4 sec', '2 hrs 20 min', '2h20min', '6 mos 1 day', '47 yrs 6 mos and 4d', '3 weeks and 2 days'. Set to 'never' to prevent extra deployments from expiring. [Learn More](https://docs.gitlab.com/ci/yaml/#pagesexpire_in)."
                },
                "publish": {
                  "type": "string",
                  "markdownDescription": "A path to a directory that contains the files to be published with Pages."
                }
              }
            },
            {
              "type": "boolean",
              "markdownDescription": "Whether this job should trigger a Pages deploy (Replaces the need to name the job `pages`)",
              "default": false
            }
          ]
        }
      },
      "oneOf": [
        {
          "properties": {
            "when": {
              "enum": [
                "delayed"
              ]
            }
          },
          "required": [
            "when",
            "start_in"
          ]
        },
        {
          "properties": {
            "when": {
              "not": {
                "enum": [
                  "delayed"
                ]
              }
            }
          }
        }
      ]
    },
    "tags": {
      "type": "array",
      "minItems": 1,
      "markdownDescription": "Used to select runners from the list of available runners. A runner must have all tags listed here to run the job. [Learn More](https://docs.gitlab.com/ci/yaml/#tags).",
      "items": {
        "anyOf": [
          {
            "type": "string",
            "minLength": 1
          },
          {
            "type": "array",
            "minItems": 1,
            "items": {
              "type": "string"
            }
          }
        ]
      }
    },
    "hooks": {
      "type": "object",
      "markdownDescription": "Specifies lists of commands to execute on the runner at certain stages of job execution. [Learn More](https://docs.gitlab.com/ci/yaml/#hooks).",
      "properties": {
        "pre_get_sources_script": {
          "$ref": "#/definitions/optional_script",
          "markdownDescription": "Specifies a list of commands to execute on the runner before updating the Git repository and any submodules. [Learn More](https://docs.gitlab.com/ci/yaml/#hookspre_get_sources_script)."
        }
      },
      "additionalProperties": false
    },
    "step": {
      "description": "Any of these step use cases are valid.",
      "oneOf": [
        {
          "description": "Run a referenced step.",
          "type": "object",
          "additionalProperties": false,
          "required": [
            "name",
            "step"
          ],
          "properties": {
            "name": {
              "$ref": "#/definitions/stepName"
            },
            "env": {
              "$ref": "#/definitions/stepNamedStrings"
            },
            "inputs": {
              "$ref": "#/definitions/stepNamedValues"
            },
            "step": {
              "oneOf": [
                {
                  "type": "string"
                },
                {
                  "$ref": "#/definitions/stepGitReference"
                },
                {
                  "$ref": "#/definitions/stepOciReference"
                }
              ]
            }
          }
        },
        {
          "description": "Run a sequence of steps.",
          "oneOf": [
            {
              "type": "object",
              "additionalProperties": false,
              "required": [
                "run"
              ],
              "properties": {
                "env": {
                  "$ref": "#/definitions/stepNamedStrings"
                },
                "run": {
                  "type": "array",
                  "items": {
                    "$ref": "#/definitions/step"
                  }
                },
                "outputs": {
                  "$ref": "#/definitions/stepNamedValues"
                },
                "delegate": {
                  "type": "string"
                }
              }
            }
          ]
        },
        {
          "description": "Run an action.",
          "type": "object",
          "additionalProperties": false,
          "required": [
            "name",
            "action"
          ],
          "properties": {
            "name": {
              "$ref": "#/definitions/stepName"
            },
            "env": {
              "$ref": "#/definitions/stepNamedStrings"
            },
            "inputs": {
              "$ref": "#/definitions/stepNamedValues"
            },
            "action": {
              "type": "string",
              "minLength": 1
            }
          }
        },
        {
          "description": "Run a script.",
          "type": "object",
          "additionalProperties": false,
          "required": [
            "name",
            "script"
          ],
          "properties": {
            "name": {
              "$ref": "#/definitions/stepName"
            },
            "env": {
              "$ref": "#/definitions/stepNamedStrings"
            },
            "script": {
              "type": "string",
              "minLength": 1
            }
          }
        },
        {
          "description": "Exec a binary.",
          "type": "object",
          "additionalProperties": false,
          "required": [
            "exec"
          ],
          "properties": {
            "env": {
              "$ref": "#/definitions/stepNamedStrings"
            },
            "exec": {
              "description": "Exec is a command to run.",
              "$ref": "#/definitions/stepExec"
            }
          }
        }
      ]
    },
    "stepName": {
      "type": "string",
      "pattern": "^[a-zA-Z_][a-zA-Z0-9_]*$"
    },
    "stepNamedStrings": {
      "type": "object",
      "patternProperties": {
        "^[a-zA-Z_][a-zA-Z0-9_]*$": {
          "type": "string"
        }
      },
      "additionalProperties": false
    },
    "stepNamedValues": {
      "type": "object",
      "patternProperties": {
        "^[a-zA-Z_][a-zA-Z0-9_]*$": {
          "type": [
            "string",
            "number",
            "boolean",
            "null",
            "array",
            "object"
          ]
        }
      },
      "additionalProperties": false
    },
    "stepGitReference": {
      "type": "object",
      "description": "GitReference is a reference to a step in a Git repository.",
      "additionalProperties": false,
      "required": [
        "git"
      ],
      "properties": {
        "git": {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "url",
            "rev"
          ],
          "properties": {
            "url": {
              "type": "string"
            },
            "dir": {
              "type": "string"
            },
            "rev": {
              "type": "string"
            },
            "file": {
              "type": "string"
            }
          }
        }
      }
    },
    "stepOciReference": {
      "type": "object",
      "description": "OCIReference is a reference to a step hosted in an OCI repository.",
      "additionalProperties": false,
      "required": [
        "oci"
      ],
      "properties": {
        "oci": {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "registry",
            "repository",
            "tag"
          ],
          "properties": {
            "registry": {
              "type": "string",
              "description": "The <host>[:<port>] of the container registry server.",
              "examples": [
                "registry.gitlab.com"
              ]
            },
            "repository": {
              "type": "string",
              "description": "A path within the registry containing related OCI images. Typically the namespace, project, and image name.",
              "examples": [
                "my_group/my_project/image"
              ]
            },
            "tag": {
              "type": "string",
              "description": "A pointer to the image manifest hosted in the OCI repository.",
              "examples": [
                "latest",
                "1",
                "1.5",
                "1.5.0"
              ]
            },
            "dir": {
              "type": "string",
              "description": "A directory inside the OCI image where the step can be found.",
              "examples": [
                "/my_steps/hello_world"
              ]
            },
            "file": {
              "type": "string",
              "description": "The name of the file that defines the step, defaults to step.yml.",
              "examples": [
                "step.yml"
              ]
            }
          }
        }
      }
    },
    "stepExec": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "command"
      ],
      "properties": {
        "command": {
          "type": "array",
          "description": "Command are the parameters to the system exec API. It does not invoke a shell.",
          "items": {
            "type": "string"
          },
          "minItems": 1
        },
        "work_dir": {
          "type": "string",
          "description": "WorkDir is the working directly in which `command` will be exec'ed."
        }
      }
    }
  }
}
```
## File: utils\check_interactive.py
```python
from __future__ import annotations

import os
import sys
from typing import Literal

EnvType = Literal["interactive", "non-interactive"]


def detect_environment() -> EnvType:
    """
    Detect if the current process is running interactively (likely a user
    on a laptop/terminal) or in a non-interactive context (CI, build server,
    cron, etc.).

    Returns:
        "interactive" or "non-interactive"

    Detection strategy:
    - CI markers: CI=true, GITHUB_ACTIONS, GITLAB_CI, BUILD_ID, etc.
    - Headless signals: DISPLAY unset (on Linux), running as PID 1 in container.
    - Non-TTY stdin/stdout/stderr (not attached to terminal).
    - Fallback: default to "interactive".
    """
    # --- CI / build system markers ---
    ci_env_markers = [
        "CI",
        "BUILD_ID",
        "BUILD_NUMBER",
        "TEAMCITY_VERSION",
        "JENKINS_HOME",
        "GITHUB_ACTIONS",
        "GITLAB_CI",
        "CIRCLECI",
        "TRAVIS",
        "APPVEYOR",
        "AZURE_HTTP_USER_AGENT",
    ]
    for marker in ci_env_markers:
        if os.getenv(marker):
            return "non-interactive"

    # --- Headless signals ---
    if sys.platform.startswith("linux") and not os.getenv("DISPLAY"):
        # But ignore WSL and interactive shells where DISPLAY may not be set
        if "WSL_DISTRO_NAME" not in os.environ and "TERM" not in os.environ:
            return "non-interactive"

    # --- Container heuristics ---
    if os.path.exists("/.dockerenv"):
        return "non-interactive"
    try:
        with open("/proc/1/cgroup") as f:
            if "docker" in f.read() or "kubepods" in f.read():
                return "non-interactive"
    except OSError:
        pass  # not Linux, skip

    # --- TTY checks ---
    if not (sys.stdin.isatty() and sys.stdout.isatty() and sys.stderr.isatty()):
        return "non-interactive"

    # --- Default ---
    return "interactive"
```
## File: utils\cli_suggestions.py
```python
from __future__ import annotations

import argparse
import sys
from difflib import get_close_matches


class SmartParser(argparse.ArgumentParser):
    def error(self, message: str):
        # Detect "invalid choice: 'foo' (choose from ...)"
        if "invalid choice" in message and "choose from" in message:
            bad = message.split("invalid choice:")[1].split("(")[0].strip().strip("'\"")
            choices_str = message.split("choose from")[1]
            choices = [c.strip().strip(",)'") for c in choices_str.split() if c.strip(",)")]

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
""".env file support with descriptions"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)


class EnvVar(TypedDict):
    """Type definition for environment variable with optional description."""

    value: str
    description: str | None


def parse_env_content_with_descriptions(content: str) -> dict[str, EnvVar]:
    """
    Parses .env-style content string into a dictionary with descriptions.
    Handles lines like 'KEY=VALUE' and 'export KEY=VALUE'.
    Associates comments immediately preceding variable definitions as descriptions.

    Args:
        content: The .env file content as a string.

    Returns:
        dict[str, EnvVar]: A dictionary mapping variable names to EnvVar objects
                          containing value and optional description.
    """
    variables: dict[str, EnvVar] = {}
    current_description: str | None = None

    logger.debug("Parsing environment content")

    for line in content.splitlines():
        stripped_line = line.strip()

        # Skip empty lines
        if not stripped_line:
            current_description = None
            continue

        # Handle comments
        if stripped_line.startswith("#"):
            # Extract comment text (remove # and leading/trailing whitespace)
            comment_text = stripped_line[1:].strip()
            if comment_text:  # Only use non-empty comments as descriptions
                current_description = comment_text
            continue

        # Try to match variable assignment
        match = re.match(r"^(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$", stripped_line)
        if match:
            key = match.group("key")
            value = match.group("value").strip()

            # Remove matching quotes from the value
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]

            variables[key] = EnvVar(value=value, description=current_description)
            logger.debug(
                f"Found variable: {key} = {value}"
                + (f" (description: {current_description})" if current_description else "")
            )

            # Reset description after using it
            current_description = None
        else:
            # If line doesn't match variable pattern, reset description
            current_description = None

    return variables


def parse_env_file_with_descriptions(file_path: Path | str) -> dict[str, EnvVar]:
    """
    Parses a .env-style file into a dictionary with descriptions.
    Handles lines like 'KEY=VALUE' and 'export KEY=VALUE'.
    Associates comments immediately preceding variable definitions as descriptions.

    Args:
        file_path: Path to the .env file to parse.

    Returns:
        dict[str, EnvVar]: A dictionary mapping variable names to EnvVar objects
                          containing value and optional description.
    """
    file_path = Path(file_path)

    if not file_path.exists():
        logger.warning(f"Environment file {file_path} does not exist")
        return {}

    content = file_path.read_text(encoding="utf-8")
    logger.debug(f"Parsing environment file: {file_path}")

    return parse_env_content_with_descriptions(content)


def set_environment_variables(env_vars: dict[str, EnvVar]) -> None:
    """
    Sets environment variables from the parsed structure.

    Args:
        env_vars: Dictionary of environment variables with descriptions.
    """
    logger.debug("Setting environment variables")

    for key, env_var in env_vars.items():
        os.environ[key] = env_var["value"]
        logger.debug(f"Set environment variable: {key} = {env_var['value']}")


def write_env_file(env_vars: dict[str, EnvVar], file_path: Path | str, include_export: bool = False) -> None:
    """
    Writes environment variables with descriptions to a .env file.

    Args:
        env_vars: Dictionary of environment variables with descriptions.
        file_path: Path where to write the .env file.
        include_export: Whether to prefix variables with 'export'.
    """
    file_path = Path(file_path)
    logger.debug(f"Writing environment file: {file_path}")

    lines: list[str] = []

    for key, env_var in env_vars.items():
        # Add description as comment if present
        if env_var["description"]:
            lines.append(f"# {env_var['description']}")

        # Format the variable assignment
        prefix = "export " if include_export else ""
        value = env_var["value"]

        # Quote the value if it contains spaces or special characters
        if " " in value or any(char in value for char in "\"'$`\\"):
            value = f'"{value}"'

        lines.append(f"{prefix}{key}={value}")
        lines.append("")  # Add empty line for readability

    # Remove trailing empty line
    if lines and lines[-1] == "":
        lines.pop()

    file_path.write_text("\n".join(lines), encoding="utf-8")
    logger.debug(f"Successfully wrote {len(env_vars)} variables to {file_path}")


def env_vars_to_simple_dict(env_vars: dict[str, EnvVar]) -> dict[str, str]:
    """
    Converts the environment variables structure to a simple key-value dictionary.

    Args:
        env_vars: Dictionary of environment variables with descriptions.

    Returns:
        dict[str, str]: Simple dictionary mapping variable names to values.
    """
    return {key: env_var["value"] for key, env_var in env_vars.items()}


# Legacy function for backwards compatibility
def parse_env_file(file_content: str) -> dict[str, str]:
    """
    Legacy function: Parses a .env-style file content into a simple dictionary.
    This maintains compatibility with existing code by delegating to the new implementation.

    Args:
        file_content: The content of the variables file.

    Returns:
        dict[str, str]: A dictionary of the parsed variables.
    """
    env_vars = parse_env_content_with_descriptions(file_content)
    return env_vars_to_simple_dict(env_vars)
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
_VALID_SUFFIXES = {".sh", ".ps1", ".bash"}
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def split_cmd(cmd_line: str) -> list[str] | None:
    """
    Split *cmd_line* into tokens while preserving backslashes (e.g. '.\\foo.sh').
    Uses POSIX-like rules for quoting/whitespace but disables backslash escaping.
    """
    try:
        lex = shlex.shlex(cmd_line, posix=True)
        lex.whitespace_split = True  # split on whitespace
        # lex.commenters = ""               # don't treat '#' as a comment
        lex.escape = ""  # *** preserve backslashes ***
        return list(lex)
    except ValueError:
        # Unbalanced quotes or similar
        return None


def extract_script_path(cmd_line: str) -> str | None:
    """
    Return a *safe-to-inline* script path or ``None``.
    A path is safe when:

        • there are **no interpreter flags**
        • there are **no extra positional arguments**
        • there are **no leading ENV=val assignments**
    """
    if not isinstance(cmd_line, str):
        raise Exception("Expected string for cmd_line")

    tokens = split_cmd(cmd_line)
    if not tokens:
        return None

    # Disallow leading VAR=val assignments
    if _ENV_ASSIGN_RE.match(tokens[0]):
        return None

    # Case A ─ plain script call
    if len(tokens) == 1 and is_script(tokens[0]):
        return to_posix(tokens[0])

    # Case B ─ executor + script
    if len(tokens) == 2 and is_executor(tokens[0]) and is_script(tokens[1]):
        return to_posix(tokens[1])

    # Case C ─ dot-source
    if len(tokens) == 2 and tokens[0] in _DOT_SOURCE and is_script(tokens[1]):
        return to_posix(tokens[1])

    return None


# ───────────────────────── helper predicates ────────────────────────────────
def is_executor(tok: str) -> bool:
    """True if token is bash/sh/pwsh *without leading dash*."""
    return tok in _EXECUTORS


def is_script(tok: str) -> bool:
    """
    True if token ends with a known script suffix and is not an option flag.

    Handles both POSIX-style (./foo.sh) and Windows-style (.\\foo.sh, C:\\path\\bar.ps1).
    """
    if tok.startswith("-"):
        return False
    normalized = tok.replace("\\", "/")
    return Path(normalized).suffix.lower() in _VALID_SUFFIXES


def to_posix(tok: str) -> str:
    """Return a normalized POSIX-style path for consistent downstream handling."""
    return Path(tok.replace("\\", "/")).as_posix()
```
## File: utils\pathlib_polyfills.py
```python
from __future__ import annotations

import os
from pathlib import Path, PurePath


def is_relative_to(child: Path, parent: Path) -> bool:
    """
    Check if a path is relative to another.

    Uses the native Path.is_relative_to() on Python 3.9+ and falls back
    to a polyfill for older versions.
    """
    try:
        # First, try to use the native implementation (available in Python 3.9+)
        return child.is_relative_to(parent)
    except AttributeError:
        # If the native method doesn't exist, fall back to the shim.
        try:
            # Resolving paths is important to handle symlinks and '..'
            child.resolve().relative_to(parent.resolve())
            return True
        except ValueError:
            # This error is raised by relative_to() if the path is not a subpath
            return False


#


# 3.9+ -> 3.8
def with_stem(p: PurePath, new_stem: str) -> PurePath:
    # Keep all suffixes (e.g., .tar.gz)
    return p.with_name(new_stem + "".join(p.suffixes))


# 3.9+ -> 3.8
def readlink(p: Path) -> Path:
    return Path(os.readlink(p))


# 3.10+ -> 3.8  (mirrors symlink_to API)
def hardlink_to(dst: Path, target: Path) -> None:
    os.link(os.fspath(target), os.fspath(dst))


# 3.12+ -> 3.8  (PurePath.relative_to(..., walk_up=True))
def relative_to_walk_up(path: PurePath, other: PurePath) -> PurePath:
    return Path(os.path.relpath(os.fspath(path), start=os.fspath(other)))


# 3.12+ -> 3.8  (Path.walk)
def path_walk(root: Path, top_down=True, on_error=None, follow_symlinks=False):
    for dirpath, dirnames, filenames in os.walk(root, topdown=top_down, onerror=on_error, followlinks=follow_symlinks):
        base = Path(dirpath)
        yield base, [base / d for d in dirnames], [base / f for f in filenames]


# 3.12+ -> 3.8  (case_sensitive kwarg for glob/rglob/match)
def glob_cs(p: Path, pattern: str, case_sensitive=None):
    # Py3.8: just ignore the flag (you can post-filter if you truly need case control)
    return p.glob(pattern)
```
## File: utils\temp_env.py
```python
import os
from contextlib import contextmanager


@contextmanager
def temporary_env_var(key: str, value: str):
    """
    Temporarily set an environment variable and revert it back after the block of code.

    Args:
        key(str): The environment variable key
        value(str): The value to set for the environment variable
    """
    original_value = os.environ.get(key)
    try:
        os.environ[key] = value
        yield
    finally:
        # Revert the environment variable to its original state
        if original_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original_value
```
## File: utils\terminal_colors.py
```python
import os


class Colors:
    """Simple ANSI color codes for terminal output."""

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

    @classmethod
    def disable(cls):
        """Disable all color output."""
        for attr in dir(cls):
            if isinstance(getattr(cls, attr), str) and getattr(cls, attr).startswith("\033"):
                setattr(cls, attr, "")

    @classmethod
    def enable(cls):
        """Disable all color output."""
        cls.HEADER = "\033[95m"
        cls.OKBLUE = "\033[94m"
        cls.OKCYAN = "\033[96m"
        cls.OKGREEN = "\033[92m"
        cls.WARNING = "\033[93m"
        cls.FAIL = "\033[91m"
        cls.ENDC = "\033[0m"
        cls.BOLD = "\033[1m"

        cls.UNDERLINE = "\033[4m"
        cls.RED_BG = "\033[41m"
        cls.GREEN_BG = "\033[42m"


if os.environ.get("NO_COLOR") or not os.isatty(1):
    Colors.disable()
```
## File: utils\update_checker.py
```python
"""Improved update checker utility for bash2gitlab (standalone module).

Key improvements over prior version:
- Clear public API with docstrings and type hints
- Robust networking with timeouts, retries, and explicit User-Agent
- Safe, simple JSON cache with TTL to avoid frequent network calls
- Correct prerelease handling using packaging.version
- Yanked version detection with warnings
- Development version detection and reporting
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
    RED: str = "\033[91m"
    BLUE: str = "\033[94m"
    ENDC: str = "\033[0m"


@dataclass(frozen=True)
class VersionInfo:
    """Information about available versions."""

    latest_stable: str | None
    latest_dev: str | None
    current_yanked: bool


def get_logger(user_logger: logging.Logger | None) -> Callable[[str], None]:
    """Get a warning logging function.

    Args:
        user_logger: Logger instance or None.

    Returns:
        Logger warning method or built-in print.
    """
    if isinstance(user_logger, logging.Logger):
        return user_logger.warning
    return print


def can_use_color() -> bool:
    """Determine if color output is allowed.

    Returns:
        True if output can be colorized.
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


def cache_paths(package_name: str) -> tuple[Path, Path]:
    """Compute cache directory and file path for a package.

    Args:
        package_name: Name of the package.

    Returns:
        Cache directory and file path.
    """
    cache_dir = Path(tempfile.gettempdir()) / "python_update_checker"
    cache_file = cache_dir / f"{package_name}_cache.json"
    return cache_dir, cache_file


def is_fresh(cache_file: Path, ttl_seconds: int) -> bool:
    """Check if cache file is fresh.

    Args:
        cache_file: Path to cache file.
        ttl_seconds: TTL in seconds.

    Returns:
        True if cache is within TTL.
    """
    try:
        if cache_file.exists():
            last_check_time = cache_file.stat().st_mtime
            return (time.time() - last_check_time) < ttl_seconds
    except (OSError, PermissionError):
        return False
    return False


def save_cache(cache_dir: Path, cache_file: Path, payload: dict) -> None:
    """Save data to cache.

    Args:
        cache_dir: Cache directory.
        cache_file: Cache file path.
        payload: Data to store.
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
        package_name: Package name to clear from cache.
    """
    _, cache_file = cache_paths(package_name)
    try:
        if cache_file.exists():
            cache_file.unlink(missing_ok=True)
    except (OSError, PermissionError):
        pass


def fetch_pypi_json(url: str, timeout: float) -> dict:
    """Fetch JSON metadata from PyPI.

    Args:
        url: URL to fetch.
        timeout: Timeout in seconds.

    Returns:
        Parsed JSON data.
    """
    req = request.Request(url, headers={"User-Agent": "bash2gitlab-update-checker/2"})
    with request.urlopen(req, timeout=timeout) as resp:  # nosec
        return json.loads(resp.read().decode("utf-8"))


def is_dev_version(version_str: str) -> bool:
    """Check if a version string represents a development version.

    Args:
        version_str: Version string to check.

    Returns:
        True if this is a development version.
    """
    try:
        v = _version.parse(version_str)
        return v.is_devrelease
    except _version.InvalidVersion:
        return False


def is_version_yanked(releases: dict, version_str: str) -> bool:
    """Check if a specific version has been yanked.

    Args:
        releases: PyPI releases data.
        version_str: Version string to check.

    Returns:
        True if the version is yanked.
    """
    version_releases = releases.get(version_str, [])
    if not version_releases:
        return False

    # Check if any release file for this version is yanked
    for release in version_releases:
        if release.get("yanked", False):
            return True
    return False


def get_version_info_from_pypi(
    package_name: str,
    current_version: str,
    *,
    include_prereleases: bool,
    timeout: float = 5.0,
    retries: int = 2,
    backoff: float = 0.5,
) -> VersionInfo:
    """Get version information from PyPI.

    Args:
        package_name: Package name.
        current_version: Current version to check if yanked.
        include_prereleases: Whether to include prereleases.
        timeout: Request timeout.
        retries: Number of retries.
        backoff: Backoff factor between retries.

    Returns:
        Version information including latest stable, dev, and yank status.

    Raises:
        PackageNotFoundError: If the package does not exist.
        NetworkError: If network error occurs after retries.
    """
    url = f"https://pypi.org/pypi/{package_name}/json"
    last_err: Exception | None = None

    for attempt in range(retries + 1):
        try:
            data = fetch_pypi_json(url, timeout)
            releases = data.get("releases", {})

            if not releases:
                info_ver = data.get("info", {}).get("version")
                return VersionInfo(
                    latest_stable=str(info_ver) if info_ver else None, latest_dev=None, current_yanked=False
                )

            # Check if current version is yanked
            current_yanked = is_version_yanked(releases, current_version)

            # Parse all valid versions
            stable_versions: list[_version.Version] = []
            dev_versions: list[_version.Version] = []

            for v_str in releases.keys():
                try:
                    v = _version.parse(v_str)
                except _version.InvalidVersion:
                    continue

                # Skip yanked versions when looking for latest
                if is_version_yanked(releases, v_str):
                    continue

                if v.is_devrelease:
                    dev_versions.append(v)
                elif v.is_prerelease:
                    if include_prereleases:
                        stable_versions.append(v)
                else:
                    stable_versions.append(v)

            latest_stable = str(max(stable_versions)) if stable_versions else None
            latest_dev = str(max(dev_versions)) if dev_versions else None

            return VersionInfo(latest_stable=latest_stable, latest_dev=latest_dev, current_yanked=current_yanked)

        except error.HTTPError as e:
            if e.code == 404:
                raise PackageNotFoundError from e
            last_err = e
        except (error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            last_err = e

        if attempt < retries:
            time.sleep(backoff * (attempt + 1))

    raise NetworkError(str(last_err))


def format_update_message(
    package_name: str,
    current_version_str: str,
    version_info: VersionInfo,
) -> str:
    """Format the update notification message.

    Args:
        package_name: Package name.
        current_version_str: Current version string.
        version_info: Version information from PyPI.

    Returns:
        Formatted update message.
    """
    pypi_url = f"https://pypi.org/project/{package_name}/"
    messages: list[str] = []

    try:
        current = _version.parse(current_version_str)
    except _version.InvalidVersion:
        current = None

    c = _Color() if can_use_color() else None

    # Check if current version is yanked
    if version_info.current_yanked:
        if c:
            yank_msg = f"{c.RED}WARNING: Your current version {current_version_str} of {package_name} has been yanked from PyPI!{c.ENDC}"
        else:
            yank_msg = (
                f"WARNING: Your current version {current_version_str} of {package_name} has been yanked from PyPI!"
            )
        messages.append(yank_msg)

    # Check for stable updates
    if version_info.latest_stable and current:
        try:
            latest_stable = _version.parse(version_info.latest_stable)
            if latest_stable > current:
                if c:
                    stable_msg = f"{c.YELLOW}A new stable version of {package_name} is available: {c.GREEN}{latest_stable}{c.YELLOW} (you are using {current}).{c.ENDC}"
                else:
                    stable_msg = f"A new stable version of {package_name} is available: {latest_stable} (you are using {current})."
                messages.append(stable_msg)
        except _version.InvalidVersion:
            pass

    # Check for dev versions
    if version_info.latest_dev:
        try:
            latest_dev = _version.parse(version_info.latest_dev)
            if current is None or latest_dev > current:
                if c:
                    dev_msg = f"{c.BLUE}Development version available: {c.GREEN}{latest_dev}{c.BLUE} (use at your own risk).{c.ENDC}"
                else:
                    dev_msg = f"Development version available: {latest_dev} (use at your own risk)."
                messages.append(dev_msg)
        except _version.InvalidVersion:
            pass

    if messages:
        upgrade_msg = "Please upgrade using your preferred package manager."
        info_msg = f"More info: {pypi_url}"
        messages.extend([upgrade_msg, info_msg])
        return "\n".join(messages)

    return ""


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
        package_name: The PyPI package name to check.
        current_version: The currently installed version string.
        logger: Optional logger for warnings.
        cache_ttl_seconds: Cache time-to-live in seconds.
        include_prereleases: Whether to consider prereleases newer.

    Returns:
        Formatted update message if update available, else None.
    """
    warn = get_logger(logger)
    cache_dir, cache_file = cache_paths(package_name)

    if is_fresh(cache_file, cache_ttl_seconds):
        return None

    try:
        version_info = get_version_info_from_pypi(
            package_name, current_version, include_prereleases=include_prereleases
        )

        message = format_update_message(package_name, current_version, version_info)

        # Cache the results
        cache_payload = {
            "latest_stable": version_info.latest_stable,
            "latest_dev": version_info.latest_dev,
            "current_yanked": version_info.current_yanked,
        }
        save_cache(cache_dir, cache_file, cache_payload)

        return message if message else None

    except PackageNotFoundError:
        warn(f"Package '{package_name}' not found on PyPI.")
        save_cache(cache_dir, cache_file, {"error": "not_found"})
        return None
    except NetworkError:
        save_cache(cache_dir, cache_file, {"error": "network"})
        return None
    except Exception:
        save_cache(cache_dir, cache_file, {"error": "unknown"})
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

from __future__ import annotations

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
## File: utils\validate_pipeline.py
```python
from __future__ import annotations

import json
import logging
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import jsonschema
import ruamel.yaml

logger = logging.getLogger(__name__)

# Import compatibility for Python 3.8+
if sys.version_info >= (3, 9):  # noqa: UP036
    from importlib.resources import files
else:
    try:
        from importlib_resources import files
    except ImportError:
        files = None


class GitLabCIValidator:
    """Validates GitLab CI YAML files against the official schema."""

    def __init__(self, cache_dir: str | None = None):
        """
        Initialize the validator.

        Args:
            cache_dir: Directory to cache the schema file. If None, uses system temp directory.
        """
        self.schema_url = (
            "https://gitlab.com/gitlab-org/gitlab/-/raw/master/app/assets/javascripts/editor/schema/ci.json"
        )
        self.cache_dir = Path(cache_dir) if cache_dir else Path(tempfile.gettempdir())
        self.cache_file = self.cache_dir / "gitlab_ci_schema.json"
        self.fallback_schema_path = "schemas/gitlab_ci_schema.json"  # Package resource path
        self.yaml = ruamel.yaml.YAML(typ="rt")

    def _fetch_schema_from_url(self) -> dict[str, Any] | None:
        """
        Fetch the schema from GitLab's repository.

        Returns:
            Schema dictionary if successful, None otherwise.
        """
        try:
            with urllib.request.urlopen(self.schema_url, timeout=5) as response:  # nosec
                schema_data = response.read().decode("utf-8")
                return json.loads(schema_data)
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError) as e:
            print(f"Failed to fetch schema from URL: {e}")
            return None

    def _load_schema_from_cache(self) -> dict[str, Any] | None:
        """
        Load the schema from cache file.

        Returns:
            Schema dictionary if successful, None otherwise.
        """
        try:
            if self.cache_file.exists():
                with open(self.cache_file, encoding="utf-8") as f:
                    return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Failed to load schema from cache: {e}")
        return None

    def _save_schema_to_cache(self, schema: dict[str, Any]) -> None:
        """
        Save the schema to cache file.

        Args:
            schema: Schema dictionary to cache.
        """
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(schema, f, indent=2)
        except OSError as e:
            print(f"Failed to save schema to cache: {e}")

    def _load_fallback_schema(self) -> dict[str, Any] | None:
        """
        Load the fallback schema from package resources.

        Returns:
            Schema dictionary if successful, None otherwise.
        """
        try:
            # Try modern importlib.resources approach (Python 3.9+) or importlib_resources backport
            if files is not None:
                try:
                    package_files = files(__package__ or __name__.split(".", maxsplit=1)[0])
                    schema_file = package_files / self.fallback_schema_path
                    if schema_file.is_file():
                        schema_data = schema_file.read_text(encoding="utf-8")
                        return json.loads(schema_data)
                except (FileNotFoundError, AttributeError, TypeError):
                    pass

            # Fallback: try to load from relative path
            try:
                current_dir = Path(__file__).parent if "__file__" in globals() else Path.cwd()
                fallback_file = current_dir / self.fallback_schema_path
                if fallback_file.exists():
                    with open(fallback_file, encoding="utf-8") as f:
                        return json.load(f)
            except (OSError, FileNotFoundError):
                pass

        except (json.JSONDecodeError, Exception) as e:
            print(f"Failed to load fallback schema: {e}")

        return None

    def get_schema(self) -> dict[str, Any]:
        """
        Get the GitLab CI schema, trying URL first, then cache, then fallback.

        Returns:
            Schema dictionary.

        Raises:
            RuntimeError: If no schema could be loaded from any source.
        """
        # Try to fetch from URL first
        schema = self._fetch_schema_from_url()
        if schema:
            self._save_schema_to_cache(schema)
            return schema

        # Fall back to cache
        schema = self._load_schema_from_cache()
        if schema:
            print("Using cached schema (could not fetch from URL)")
            return schema

        # Fall back to package resource
        schema = self._load_fallback_schema()
        if schema:
            print("Using fallback schema from package (could not fetch from URL or cache)")
            return schema

        raise RuntimeError("Could not load schema from URL, cache, or fallback resource")

    def yaml_to_json(self, yaml_content: str) -> dict[str, Any]:
        """
        Convert YAML content to JSON-compatible dictionary.

        Args:
            yaml_content: YAML string content.

        Returns:
            Dictionary representation of the YAML.

        Raises:
            ruamel.yaml.YAMLError: If YAML parsing fails.
        """
        return self.yaml.load(yaml_content)

    def validate_ci_config(self, yaml_content: str) -> tuple[bool, list[str]]:
        """
        Validate GitLab CI YAML configuration against the schema.

        Args:
            yaml_content: YAML configuration as string.

        Returns:
            tuple of (is_valid, list_of_error_messages).
        """
        if "pragma" in yaml_content.lower() and "do-not-validate-schema" in yaml_content.lower():
            logger.debug("Skipping validation found do-not-validate-schema Pragma")
            return True, []

        try:
            # Convert YAML to JSON-compatible dict
            config_dict = self.yaml_to_json(yaml_content)

            # Get the schema
            schema = self.get_schema()

            # Validate against schema
            validator = jsonschema.Draft7Validator(schema)
            errors = []

            for error in validator.iter_errors(config_dict):
                error_path = " -> ".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
                error_msg = f"Path '{error_path}': {error.message}"
                errors.append(error_msg)

            is_valid = len(errors) == 0
            return is_valid, errors

        except ruamel.yaml.YAMLError as e:
            return False, [f"YAML parsing error: {str(e)}"]
        except Exception as e:
            return False, [f"Validation error: {str(e)}"]


def validate_gitlab_ci_yaml(yaml_content: str, cache_dir: str | None = None) -> tuple[bool, list[str]]:
    """
    Convenience function to validate GitLab CI YAML configuration.

    Args:
        yaml_content: YAML configuration as string.
        cache_dir: Optional directory for caching schema.

    Returns:
        tuple of (is_valid, list_of_error_messages).
    """
    validator = GitLabCIValidator(cache_dir=cache_dir)
    return validator.validate_ci_config(yaml_content)
```
## File: utils\yaml_factory.py
```python
"""Cache and centralize the YAML object"""

import functools

from ruamel.yaml import YAML


@functools.lru_cache(maxsize=1)
def get_yaml() -> YAML:
    # https://stackoverflow.com/a/70496481/33264
    y = YAML(typ="rt")  # rt to support !reference tag
    y.width = 4096
    y.preserve_quotes = True  # Want to minimize quotes, but "1.0" -> 1.0 is a type change.
    # maximize quotes
    # y.default_style = '"'  # type: ignore[assignment]
    y.explicit_start = False  # no '---'
    y.explicit_end = False  # no '...'
    return y


#
# @functools.lru_cache(maxsize=1)
# def get_yaml() -> YAML:
#     y = YAML()
#     y.width = 4096
#     y.preserve_quotes = True  # Want to minimize quotes, but "1.0" -> 1.0 is a type change.
#
#     # Don't set default_style for all strings - let LiteralScalarString work naturally
#     # y.default_style = '"'  # COMMENTED OUT - this was preventing | syntax
#
#     # Instead, set up a custom representer that quotes regular strings but not literal blocks
#     def custom_str_representer(dumper, data):
#         if isinstance(data, LiteralScalarString):
#             return dumper.represent_literal_scalar(data)
#         # Force quotes on regular strings to prevent type changes like "1.0" -> 1.0
#         return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')
#
#     y.representer.add_representer(str, custom_str_representer)
#     y.representer.add_representer(LiteralScalarString, y.representer.represent_literal_scalarstring)
#
#     y.explicit_start = False  # no '---'
#     y.explicit_end = False  # no '...'
#     return y
```
## File: utils\yaml_file_same.py
```python
from __future__ import annotations

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
