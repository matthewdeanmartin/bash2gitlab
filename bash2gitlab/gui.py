#!/usr/bin/env python3
"""
GUI interface for bash2gitlab CLI tool.

This module provides a Tkinter-based graphical interface for all bash2gitlab
commands, making it easier to use without memorizing CLI arguments.

Supported commands:
- Compile/Decompile: Convert between inline scripts and separate files
- Clean: Remove generated files
- Lint: Validate YAML against GitLab
- Utilities: Init, copy2local, detect-drift
- Advanced: check-pins, trigger-pipelines, graph, run, detect-uncompiled, validate, autogit
- Git: Pre-commit hooks, directory mapping

Features:
- All commands accessible through tabs
- Form-based input with validation
- Real-time command output
- File/directory browser integration
- Helpful examples and labels for complex inputs
"""

from __future__ import annotations

import logging
import os
import subprocess  # nosec
import sys
import threading

from bash2gitlab.utils.missing_tkinter import check_for_python_3_13_0

try:
    import tkinter as tk
except Exception:
    if check_for_python_3_13_0():
        # python 3.13.
        sys.exit(99)
    raise
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

            # Start process - use sys.executable to ensure we use the correct Python interpreter
            # Replace "bash2gitlab" with module invocation
            if cmd and cmd[0] == "bash2gitlab":
                cmd = [sys.executable, "-m", "bash2gitlab"] + cmd[1:]

            env = {}
            for key, value in os.environ.items():
                env[key] = value
            env["NO_COLOR"] = "1"
            # pylint: disable=consider-using-with
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

        # UI elements (initialized in setup methods)
        self.decompile_file_entry: ttk.Entry | None = None
        self.decompile_file_btn: ttk.Button | None = None
        self.decompile_folder_entry: ttk.Entry | None = None
        self.decompile_folder_btn: ttk.Button | None = None
        self.output_frame: ttk.Frame | None = None
        self.output_text: scrolledtext.ScrolledText | None = None

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
        self.create_advanced_tab(notebook)
        self.create_git_tab(notebook)
        self.create_output_tab(notebook)

    def create_compile_tab(self, parent: ttk.Notebook) -> None:
        """Create the compile commands tab."""
        frame = ttk.Frame(parent)
        parent.add(frame, text="Compile & Clean")

        # Compile section
        compile_frame = ttk.LabelFrame(frame, text="Compile Project - Inline .sh files into .gitlab-ci.yml", padding=10)
        compile_frame.pack(fill=tk.X, padx=5, pady=5)

        # Input directory
        ttk.Label(compile_frame, text="Input Directory:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Label(compile_frame, text="(Source YAML & scripts)", font=("TkDefaultFont", 8), foreground="gray").grid(
            row=0, column=3, sticky=tk.W, padx=5
        )
        self.vars["compile_input"] = tk.StringVar()
        input_entry = ttk.Entry(compile_frame, textvariable=self.vars["compile_input"], width=50)
        input_entry.grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(
            compile_frame, text="Browse", command=lambda: self.browse_directory(self.vars["compile_input"])
        ).grid(row=0, column=2, padx=5)

        # Output directory
        ttk.Label(compile_frame, text="Output Directory:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Label(compile_frame, text="(Final .gitlab-ci.yml)", font=("TkDefaultFont", 8), foreground="gray").grid(
            row=1, column=3, sticky=tk.W, padx=5
        )
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

        self.vars["compile_force"] = tk.BooleanVar()
        ttk.Checkbutton(
            options_frame, text="Force (ignore change detection)", variable=self.vars["compile_force"]
        ).pack(side=tk.LEFT, padx=5)

        self.vars["compile_autogit"] = tk.BooleanVar()
        ttk.Checkbutton(options_frame, text="Auto Git (commit changes)", variable=self.vars["compile_autogit"]).pack(
            side=tk.LEFT, padx=5
        )

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
        clean_frame = ttk.LabelFrame(frame, text="Clean Output - Remove only unmodified generated files", padding=10)
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

        self.vars["clean_autogit"] = tk.BooleanVar()
        ttk.Checkbutton(clean_options, text="Auto Git", variable=self.vars["clean_autogit"]).pack(side=tk.LEFT, padx=5)

        ttk.Button(clean_options, text="Clean", command=self.run_clean).pack(side=tk.LEFT, padx=20)

    def create_decompile_tab(self, parent: ttk.Notebook) -> None:
        """Create the decompile commands tab."""
        frame = ttk.Frame(parent)
        parent.add(frame, text="Decompile")

        decompile_frame = ttk.LabelFrame(
            frame, text="Decompile GitLab CI YAML - Extract inline scripts to .sh files", padding=10
        )
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

        self.vars["decompile_autogit"] = tk.BooleanVar()
        ttk.Checkbutton(decompile_options, text="Auto Git", variable=self.vars["decompile_autogit"]).pack(
            side=tk.LEFT, padx=5
        )

        ttk.Button(decompile_options, text="Decompile", command=self.run_decompile).pack(side=tk.LEFT, padx=20)

    def create_utilities_tab(self, parent: ttk.Notebook) -> None:
        """Create the utilities tab."""
        frame = ttk.Frame(parent)
        parent.add(frame, text="Utilities")

        # Init section
        init_frame = ttk.LabelFrame(
            frame, text="Initialize Project - Create config and directory structure", padding=10
        )
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
        copy_frame = ttk.LabelFrame(
            frame, text="Copy Repository to Local - For testing centralized templates", padding=10
        )
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
        drift_frame = ttk.LabelFrame(frame, text="Detect Drift - Find manual edits to generated files", padding=10)
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

        lint_frame = ttk.LabelFrame(frame, text="GitLab CI Lint - Validate YAML against GitLab API", padding=10)
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

    def create_advanced_tab(self, parent: ttk.Notebook) -> None:
        """Create the advanced commands tab."""
        frame = ttk.Frame(parent)
        parent.add(frame, text="Advanced")

        # Check-pins section
        pins_frame = ttk.LabelFrame(frame, text="Check Include Pins - Suggest pinning includes to tags", padding=10)
        pins_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(pins_frame, text="GitLab CI File:", width=15).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.vars["pins_file"] = tk.StringVar(value=".gitlab-ci.yml")
        ttk.Entry(pins_frame, textvariable=self.vars["pins_file"], width=40).grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(pins_frame, text="Browse", command=lambda: self.browse_file(self.vars["pins_file"])).grid(
            row=0, column=2, padx=5
        )

        ttk.Label(pins_frame, text="GitLab URL:", width=15).grid(row=1, column=0, sticky=tk.W, pady=2)
        self.vars["pins_gitlab_url"] = tk.StringVar(value="https://gitlab.com")
        ttk.Entry(pins_frame, textvariable=self.vars["pins_gitlab_url"], width=40).grid(row=1, column=1, padx=5, pady=2)

        ttk.Label(pins_frame, text="Token:", width=15).grid(row=2, column=0, sticky=tk.W, pady=2)
        self.vars["pins_token"] = tk.StringVar()
        ttk.Entry(pins_frame, textvariable=self.vars["pins_token"], width=40, show="*").grid(
            row=2, column=1, padx=5, pady=2
        )

        pins_opts = ttk.Frame(pins_frame)
        pins_opts.grid(row=3, column=0, columnspan=3, pady=5)
        self.vars["pins_json"] = tk.BooleanVar()
        ttk.Checkbutton(pins_opts, text="JSON output", variable=self.vars["pins_json"]).pack(side=tk.LEFT, padx=5)
        self.vars["pins_pin_all"] = tk.BooleanVar()
        ttk.Checkbutton(pins_opts, text="Pin all (not just tags)", variable=self.vars["pins_pin_all"]).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(pins_opts, text="Check Pins", command=self.run_check_pins).pack(side=tk.LEFT, padx=20)

        # Validate section
        validate_frame = ttk.LabelFrame(
            frame, text="Validate YAML Schema - Check against GitLab JSON schema", padding=10
        )
        validate_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(validate_frame, text="Input Directory:", width=15).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.vars["validate_input"] = tk.StringVar()
        ttk.Entry(validate_frame, textvariable=self.vars["validate_input"], width=40).grid(
            row=0, column=1, padx=5, pady=2
        )
        ttk.Button(
            validate_frame, text="Browse", command=lambda: self.browse_directory(self.vars["validate_input"])
        ).grid(row=0, column=2, padx=5)

        ttk.Label(validate_frame, text="Output Directory:", width=15).grid(row=1, column=0, sticky=tk.W, pady=2)
        self.vars["validate_output"] = tk.StringVar()
        ttk.Entry(validate_frame, textvariable=self.vars["validate_output"], width=40).grid(
            row=1, column=1, padx=5, pady=2
        )
        ttk.Button(
            validate_frame, text="Browse", command=lambda: self.browse_directory(self.vars["validate_output"])
        ).grid(row=1, column=2, padx=5)

        validate_opts = ttk.Frame(validate_frame)
        validate_opts.grid(row=2, column=0, columnspan=3, pady=5)
        ttk.Label(validate_opts, text="Parallelism:").pack(side=tk.LEFT, padx=5)
        self.vars["validate_parallelism"] = tk.StringVar(value="4")
        ttk.Spinbox(validate_opts, from_=1, to=16, width=5, textvariable=self.vars["validate_parallelism"]).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(validate_opts, text="Validate", command=self.run_validate).pack(side=tk.LEFT, padx=20)

        # Graph section
        graph_frame = ttk.LabelFrame(
            frame, text="Generate Dependency Graph - Visualize script relationships", padding=10
        )
        graph_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(graph_frame, text="Input Directory:", width=15).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.vars["graph_input"] = tk.StringVar()
        ttk.Entry(graph_frame, textvariable=self.vars["graph_input"], width=40).grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(graph_frame, text="Browse", command=lambda: self.browse_directory(self.vars["graph_input"])).grid(
            row=0, column=2, padx=5
        )
        ttk.Button(graph_frame, text="Generate Graph (DOT)", command=self.run_graph).grid(
            row=1, column=0, columnspan=3, pady=10
        )

        # Run section
        run_frame = ttk.LabelFrame(frame, text="Run Pipeline Locally - Best effort local execution", padding=10)
        run_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(run_frame, text="GitLab CI File:", width=15).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.vars["run_input"] = tk.StringVar(value=".gitlab-ci.yml")
        ttk.Entry(run_frame, textvariable=self.vars["run_input"], width=40).grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(run_frame, text="Browse", command=lambda: self.browse_file(self.vars["run_input"])).grid(
            row=0, column=2, padx=5
        )
        ttk.Button(run_frame, text="Run Locally", command=self.run_pipeline).grid(
            row=1, column=0, columnspan=3, pady=10
        )

        # Detect uncompiled section
        detect_uncompiled_frame = ttk.LabelFrame(
            frame, text="Detect Uncompiled Changes - Check if recompilation needed", padding=10
        )
        detect_uncompiled_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(detect_uncompiled_frame, text="Input Directory:", width=15).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.vars["uncompiled_input"] = tk.StringVar()
        ttk.Entry(detect_uncompiled_frame, textvariable=self.vars["uncompiled_input"], width=40).grid(
            row=0, column=1, padx=5, pady=2
        )
        ttk.Button(
            detect_uncompiled_frame, text="Browse", command=lambda: self.browse_directory(self.vars["uncompiled_input"])
        ).grid(row=0, column=2, padx=5)

        uncompiled_opts = ttk.Frame(detect_uncompiled_frame)
        uncompiled_opts.grid(row=1, column=0, columnspan=3, pady=5)
        self.vars["uncompiled_check_only"] = tk.BooleanVar(value=True)
        ttk.Checkbutton(uncompiled_opts, text="Check only", variable=self.vars["uncompiled_check_only"]).pack(
            side=tk.LEFT, padx=5
        )
        self.vars["uncompiled_list"] = tk.BooleanVar()
        ttk.Checkbutton(uncompiled_opts, text="List changed files", variable=self.vars["uncompiled_list"]).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(uncompiled_opts, text="Detect Changes", command=self.run_detect_uncompiled).pack(
            side=tk.LEFT, padx=20
        )

        # Trigger pipelines section
        trigger_frame = ttk.LabelFrame(frame, text="Trigger Remote Pipelines - Start pipelines on GitLab", padding=10)
        trigger_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(trigger_frame, text="GitLab URL:", width=15).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.vars["trigger_gitlab_url"] = tk.StringVar(value="https://gitlab.com")
        ttk.Entry(trigger_frame, textvariable=self.vars["trigger_gitlab_url"], width=40).grid(
            row=0, column=1, padx=5, pady=2
        )

        ttk.Label(trigger_frame, text="Token:", width=15).grid(row=1, column=0, sticky=tk.W, pady=2)
        self.vars["trigger_token"] = tk.StringVar()
        ttk.Entry(trigger_frame, textvariable=self.vars["trigger_token"], width=40, show="*").grid(
            row=1, column=1, padx=5, pady=2
        )

        ttk.Label(trigger_frame, text="Projects (ID:REF):", width=15).grid(row=2, column=0, sticky=tk.W, pady=2)
        self.vars["trigger_projects"] = tk.StringVar()
        ttk.Entry(trigger_frame, textvariable=self.vars["trigger_projects"], width=40).grid(
            row=2, column=1, padx=5, pady=2
        )
        ttk.Label(trigger_frame, text="e.g., 123:main,456:develop", font=("TkDefaultFont", 8), foreground="gray").grid(
            row=2, column=2, sticky=tk.W
        )

        ttk.Label(trigger_frame, text="Variables (KEY=VAL):", width=15).grid(row=3, column=0, sticky=tk.W, pady=2)
        self.vars["trigger_variables"] = tk.StringVar()
        ttk.Entry(trigger_frame, textvariable=self.vars["trigger_variables"], width=40).grid(
            row=3, column=1, padx=5, pady=2
        )
        ttk.Label(
            trigger_frame, text="e.g., VAR1=value1,VAR2=value2", font=("TkDefaultFont", 8), foreground="gray"
        ).grid(row=3, column=2, sticky=tk.W)

        trigger_opts = ttk.Frame(trigger_frame)
        trigger_opts.grid(row=4, column=0, columnspan=3, pady=5)
        self.vars["trigger_wait"] = tk.BooleanVar()
        ttk.Checkbutton(trigger_opts, text="Wait for completion", variable=self.vars["trigger_wait"]).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Label(trigger_opts, text="Timeout (s):").pack(side=tk.LEFT, padx=5)
        self.vars["trigger_timeout"] = tk.StringVar(value="1800")
        ttk.Entry(trigger_opts, textvariable=self.vars["trigger_timeout"], width=8).pack(side=tk.LEFT, padx=5)
        ttk.Button(trigger_opts, text="Trigger", command=self.run_trigger_pipelines).pack(side=tk.LEFT, padx=20)

        # Autogit section
        autogit_frame = ttk.LabelFrame(
            frame, text="Auto Git Commit - Automatically stage, commit, and push", padding=10
        )
        autogit_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(autogit_frame, text="Commit Message:", width=15).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.vars["autogit_message"] = tk.StringVar()
        ttk.Entry(autogit_frame, textvariable=self.vars["autogit_message"], width=40).grid(
            row=0, column=1, padx=5, pady=2
        )
        ttk.Button(autogit_frame, text="Run Autogit", command=self.run_autogit).grid(
            row=1, column=0, columnspan=3, pady=10
        )

    def create_git_tab(self, parent: ttk.Notebook) -> None:
        """Create the Git hooks tab."""
        frame = ttk.Frame(parent)
        parent.add(frame, text="Git Hooks")

        # Pre-commit hooks section
        precommit_frame = ttk.LabelFrame(frame, text="Pre-commit Hooks - Auto-compile on git commit", padding=10)
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
        map_frame = ttk.LabelFrame(frame, text="Directory Mapping - Deploy/sync between directories", padding=10)
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
        other_frame = ttk.LabelFrame(frame, text="Diagnostics - Health checks and config display", padding=10)
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
            if self.decompile_file_entry:
                self.decompile_file_entry.config(state=tk.NORMAL)
            if self.decompile_file_btn:
                self.decompile_file_btn.config(state=tk.NORMAL)
            if self.decompile_folder_entry:
                self.decompile_folder_entry.config(state=tk.DISABLED)
            if self.decompile_folder_btn:
                self.decompile_folder_btn.config(state=tk.DISABLED)
        else:
            if self.decompile_file_entry:
                self.decompile_file_entry.config(state=tk.DISABLED)
            if self.decompile_file_btn:
                self.decompile_file_btn.config(state=tk.DISABLED)
            if self.decompile_folder_entry:
                self.decompile_folder_entry.config(state=tk.NORMAL)
            if self.decompile_folder_btn:
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
        if self.output_text:
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
            "force": self.vars["compile_force"].get(),
            "autogit": self.vars["compile_autogit"].get(),
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
            "autogit": self.vars["clean_autogit"].get(),
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
            "autogit": self.vars["decompile_autogit"].get(),
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

    def run_check_pins(self) -> None:
        """Run the check-pins command."""
        if not self.command_runner:
            return

        options = {
            "file": self.vars["pins_file"].get(),
            "gitlab_url": self.vars["pins_gitlab_url"].get(),
            "token": self.vars["pins_token"].get(),
            "json": self.vars["pins_json"].get(),
        }

        # Add --pin-all if checkbox is checked
        if self.vars["pins_pin_all"].get():
            options["pin_all"] = True

        # Validate required fields
        if not options["file"]:
            messagebox.showerror("Error", "GitLab CI file is required!")
            return
        if not options["gitlab_url"]:
            messagebox.showerror("Error", "GitLab URL is required!")
            return

        cmd = self.build_command("check-pins", options)
        self.command_runner.run_command(cmd)

    def run_validate(self) -> None:
        """Run the validate command."""
        if not self.command_runner:
            return

        options = {
            "in": self.vars["validate_input"].get(),
            "out": self.vars["validate_output"].get(),
            "parallelism": self.vars["validate_parallelism"].get(),
        }

        # Validate required fields
        if not options["in"]:
            messagebox.showerror("Error", "Input directory is required!")
            return
        if not options["out"]:
            messagebox.showerror("Error", "Output directory is required!")
            return

        cmd = self.build_command("validate", options)
        self.command_runner.run_command(cmd)

    def run_graph(self) -> None:
        """Run the graph command."""
        if not self.command_runner:
            return

        input_dir = self.vars["graph_input"].get()
        if not input_dir:
            messagebox.showerror("Error", "Input directory is required!")
            return

        cmd = ["bash2gitlab", "graph", "--in", input_dir]
        self.command_runner.run_command(cmd)

    def run_pipeline(self) -> None:
        """Run the run command (execute pipeline locally)."""
        if not self.command_runner:
            return

        input_file = self.vars["run_input"].get()
        if not input_file:
            messagebox.showerror("Error", "GitLab CI file is required!")
            return

        cmd = ["bash2gitlab", "run", "--in-file", input_file]
        self.command_runner.run_command(cmd)

    def run_detect_uncompiled(self) -> None:
        """Run the detect-uncompiled command."""
        if not self.command_runner:
            return

        input_dir = self.vars["uncompiled_input"].get()
        if not input_dir:
            messagebox.showerror("Error", "Input directory is required!")
            return

        cmd = ["bash2gitlab", "detect-uncompiled", "--in", input_dir]

        if self.vars["uncompiled_check_only"].get():
            cmd.append("--check-only")
        if self.vars["uncompiled_list"].get():
            cmd.append("--list-changed")

        self.command_runner.run_command(cmd)

    def run_autogit(self) -> None:
        """Run the autogit command."""
        if not self.command_runner:
            return

        cmd = ["bash2gitlab", "autogit"]

        message = self.vars["autogit_message"].get()
        if message:
            cmd.extend(["-m", message])

        self.command_runner.run_command(cmd)

    def run_trigger_pipelines(self) -> None:
        """Run the trigger-pipelines command."""
        if not self.command_runner:
            return

        gitlab_url = self.vars["trigger_gitlab_url"].get()
        token = self.vars["trigger_token"].get()
        projects_str = self.vars["trigger_projects"].get()

        # Validate required fields
        if not gitlab_url:
            messagebox.showerror("Error", "GitLab URL is required!")
            return
        if not token:
            messagebox.showerror("Error", "Token is required!")
            return
        if not projects_str:
            messagebox.showerror("Error", "At least one project (ID:REF) is required!")
            return

        cmd = ["bash2gitlab", "trigger-pipelines"]
        cmd.extend(["--gitlab-url", gitlab_url])
        cmd.extend(["--token", token])

        # Parse and add projects
        projects = [p.strip() for p in projects_str.split(",") if p.strip()]
        for project in projects:
            cmd.extend(["--project", project])

        # Parse and add variables if present
        variables_str = self.vars["trigger_variables"].get()
        if variables_str:
            variables = [v.strip() for v in variables_str.split(",") if v.strip()]
            for variable in variables:
                cmd.extend(["--variable", variable])

        # Add wait options if checked
        if self.vars["trigger_wait"].get():
            cmd.append("--wait")
            timeout = self.vars["trigger_timeout"].get()
            if timeout:
                cmd.extend(["--timeout", timeout])

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
