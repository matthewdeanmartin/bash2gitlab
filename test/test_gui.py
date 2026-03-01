"""
Unit tests for bash2gitlab/gui.py

Tests demonstrate that gui.py components are fully testable by mocking Tkinter,
threading, and subprocess calls to run headless without requiring a display.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_tk():
    """Mock Tkinter to avoid GUI display."""
    with patch("bash2gitlab.gui.tk") as mock:
        # Mock common tk types
        mock.Tk = MagicMock
        mock.Text = MagicMock
        mock.StringVar = MagicMock
        mock.BooleanVar = MagicMock
        mock.Variable = MagicMock
        mock.END = "end"
        mock.NORMAL = "normal"
        mock.DISABLED = "disabled"
        mock.W = "w"
        mock.X = "x"
        mock.BOTH = "both"
        mock.LEFT = "left"
        mock.WORD = "word"
        yield mock


@pytest.fixture
def mock_ttk():
    """Mock ttk widgets."""
    with patch("bash2gitlab.gui.ttk") as mock:
        mock.Notebook = MagicMock
        mock.Frame = MagicMock
        mock.LabelFrame = MagicMock
        mock.Entry = MagicMock
        mock.Button = MagicMock
        mock.Checkbutton = MagicMock
        mock.Spinbox = MagicMock
        mock.Label = MagicMock
        mock.Radiobutton = MagicMock
        yield mock


@pytest.fixture
def mock_filedialog():
    """Mock file dialogs."""
    with patch("bash2gitlab.gui.filedialog") as mock:
        yield mock


@pytest.fixture
def mock_messagebox():
    """Mock message boxes."""
    with patch("bash2gitlab.gui.messagebox") as mock:
        yield mock


@pytest.fixture
def mock_scrolledtext():
    """Mock scrolledtext widget."""
    with patch("bash2gitlab.gui.scrolledtext") as mock:
        mock.ScrolledText = MagicMock
        yield mock


@pytest.fixture
def mock_text_widget():
    """Create a mock text widget for testing."""
    widget = MagicMock()
    widget.insert = MagicMock()
    widget.delete = MagicMock()
    widget.see = MagicMock()
    widget.update_idletasks = MagicMock()
    widget.after = MagicMock(side_effect=lambda delay, func: func())
    return widget


class TestLogHandler:
    """Test the LogHandler class."""

    def test_loghandler_initialization(self, mock_text_widget):
        """Test LogHandler can be initialized with a text widget."""
        from bash2gitlab.gui import LogHandler

        handler = LogHandler(mock_text_widget)
        assert handler.text_widget is mock_text_widget
        assert isinstance(handler, logging.Handler)

    def test_loghandler_emit_writes_to_widget(self, mock_text_widget):
        """Test that emit() writes formatted log messages to text widget."""
        from bash2gitlab.gui import LogHandler

        handler = LogHandler(mock_text_widget)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        # Create a log record
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Emit the record
        handler.emit(record)

        # Verify text widget was updated
        assert mock_text_widget.after.called

    def test_loghandler_append_to_widget(self, mock_text_widget):
        """Test _append_to_widget inserts text correctly."""
        from bash2gitlab.gui import LogHandler

        handler = LogHandler(mock_text_widget)
        # Call directly (normally called via after())
        handler._append_to_widget("Test log line")

        # Verify widget operations
        mock_text_widget.insert.assert_called_once()
        mock_text_widget.see.assert_called_once()
        mock_text_widget.update_idletasks.assert_called_once()

    def test_loghandler_multiple_emits(self, mock_text_widget):
        """Test multiple log emissions."""
        from bash2gitlab.gui import LogHandler

        handler = LogHandler(mock_text_widget)
        handler.setFormatter(logging.Formatter("%(message)s"))

        for i in range(3):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=i,
                msg=f"Message {i}",
                args=(),
                exc_info=None,
            )
            handler.emit(record)

        # Verify after was called for each emit
        assert mock_text_widget.after.call_count == 3


class TestCommandRunner:
    """Test the CommandRunner class."""

    @pytest.fixture
    def mock_notebook(self):
        """Mock notebook widget."""
        notebook = MagicMock()
        notebook.select = MagicMock()
        return notebook

    @pytest.fixture
    def command_runner(self, mock_text_widget, mock_notebook):
        """Create CommandRunner instance with mocked dependencies."""
        from bash2gitlab.gui import CommandRunner

        output_frame = MagicMock()
        return CommandRunner(mock_text_widget, mock_notebook, output_frame)

    def test_commandrunner_initialization(self, mock_text_widget, mock_notebook, command_runner):
        """Test CommandRunner initialization."""
        assert command_runner.output_widget is mock_text_widget
        assert command_runner.notebook is mock_notebook
        assert command_runner.current_process is None
        assert command_runner.is_running is False

    def test_run_command_starts_thread(self, command_runner, mock_text_widget, mock_messagebox):
        """Test that run_command starts a thread."""
        with patch("bash2gitlab.gui.threading.Thread") as mock_thread:
            mock_thread_instance = MagicMock()
            mock_thread.return_value = mock_thread_instance

            cmd = ["bash2gitlab", "doctor"]
            command_runner.run_command(cmd)

            # Verify thread was created and started
            mock_thread.assert_called_once()
            mock_thread_instance.start.assert_called_once()
            assert command_runner.is_running is True

    def test_run_command_prevents_concurrent_execution(self, command_runner, mock_messagebox):
        """Test that run_command prevents running multiple commands."""
        command_runner.is_running = True

        with patch("bash2gitlab.gui.threading.Thread") as mock_thread:
            cmd = ["bash2gitlab", "doctor"]
            command_runner.run_command(cmd)

            # Thread should not be started
            mock_thread.assert_not_called()
            # Warning should be shown
            mock_messagebox.showwarning.assert_called_once()

    def test_execute_command_success(self, command_runner, mock_text_widget):
        """Test successful command execution."""
        mock_process = MagicMock()
        # Mock stdout.readline to return lines then empty string
        mock_process.stdout.readline.side_effect = ["Line 1\n", "Line 2\n", ""]
        mock_process.wait.return_value = 0

        with patch("bash2gitlab.gui.subprocess.Popen", return_value=mock_process):
            cmd = ["bash2gitlab", "doctor"]
            callback = MagicMock()

            # Execute in the same thread for testing
            command_runner._execute_command(cmd, callback)

            # Verify process was created
            assert mock_text_widget.after.called
            # Verify callback was called with exit code
            callback.assert_called_once_with(0)
            # Verify is_running is reset
            assert command_runner.is_running is False

    def test_execute_command_with_output(self, command_runner, mock_text_widget):
        """Test command execution captures output."""
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ["Output line 1\n", "Output line 2\n", ""]
        mock_process.wait.return_value = 0

        with patch("bash2gitlab.gui.subprocess.Popen", return_value=mock_process):
            cmd = ["bash2gitlab", "doctor"]
            command_runner._execute_command(cmd, None)

            # Verify output was written to widget (via after calls)
            assert mock_text_widget.after.call_count > 0

    def test_execute_command_nonzero_exit(self, command_runner, mock_text_widget):
        """Test command execution with non-zero exit code."""
        mock_process = MagicMock()
        mock_process.stdout.readline.return_value = ""
        mock_process.wait.return_value = 1

        with patch("bash2gitlab.gui.subprocess.Popen", return_value=mock_process):
            cmd = ["bash2gitlab", "invalid-command"]
            callback = MagicMock()

            command_runner._execute_command(cmd, callback)

            # Callback should receive exit code 1
            callback.assert_called_once_with(1)

    def test_execute_command_exception_handling(self, command_runner, mock_text_widget):
        """Test command execution handles exceptions."""
        with patch(
            "bash2gitlab.gui.subprocess.Popen",
            side_effect=Exception("Command failed"),
        ):
            cmd = ["bash2gitlab", "doctor"]

            # Should not raise, but handle gracefully
            command_runner._execute_command(cmd, None)

            # Verify is_running is reset
            assert command_runner.is_running is False

    def test_execute_command_sets_no_color_env(self, command_runner, mock_text_widget):
        """Test that NO_COLOR environment variable is set."""
        mock_process = MagicMock()
        mock_process.stdout.readline.return_value = ""
        mock_process.wait.return_value = 0

        with patch("bash2gitlab.gui.subprocess.Popen", return_value=mock_process) as mock_popen:
            with patch("bash2gitlab.gui.os.environ", {"PATH": "/usr/bin"}):
                cmd = ["bash2gitlab", "doctor"]
                command_runner._execute_command(cmd, None)

                # Check that NO_COLOR was set in environment
                call_kwargs = mock_popen.call_args[1]
                assert "env" in call_kwargs
                assert call_kwargs["env"]["NO_COLOR"] == "1"

    def test_stop_command_terminates_process(self, command_runner, mock_text_widget):
        """Test stop_command terminates the running process."""
        mock_process = MagicMock()
        command_runner.current_process = mock_process

        command_runner.stop_command()

        mock_process.terminate.assert_called_once()
        mock_text_widget.insert.assert_called()

    def test_stop_command_handles_no_process(self, command_runner, mock_text_widget):
        """Test stop_command when no process is running."""
        command_runner.current_process = None

        # Should not raise
        command_runner.stop_command()

        # No insert should happen
        mock_text_widget.insert.assert_not_called()

    def test_stop_command_handles_exception(self, command_runner, mock_text_widget):
        """Test stop_command handles termination exceptions."""
        mock_process = MagicMock()
        mock_process.terminate.side_effect = Exception("Cannot terminate")
        command_runner.current_process = mock_process

        # Should not raise
        command_runner.stop_command()

        # Error should be written to widget
        mock_text_widget.insert.assert_called()


class TestBash2GitlabGUI:
    """Test the Bash2GitlabGUI class."""

    @pytest.fixture
    def mock_root(self, mock_tk):
        """Create mock root window."""
        root = MagicMock()
        root.title = MagicMock()
        root.geometry = MagicMock()
        return root

    @pytest.fixture
    def gui_instance(self, mock_root, mock_tk, mock_ttk, mock_scrolledtext, mock_filedialog, mock_messagebox):
        """Create GUI instance with all mocks."""
        from bash2gitlab.gui import Bash2GitlabGUI

        with patch.object(Bash2GitlabGUI, "setup_gui"):
            gui = Bash2GitlabGUI(mock_root)
            # Manually set up minimal state
            gui.vars = {}
            gui.command_runner = MagicMock()
            gui.output_text = MagicMock()
            return gui

    def test_gui_initialization(self, mock_root, mock_tk, mock_ttk, mock_scrolledtext):
        """Test GUI initialization sets up window."""
        from bash2gitlab.gui import Bash2GitlabGUI

        with patch.object(Bash2GitlabGUI, "setup_gui"):
            _gui = Bash2GitlabGUI(mock_root)  # is this necessary?

            mock_root.title.assert_called_once_with("bash2gitlab GUI")
            mock_root.geometry.assert_called_once_with("1000x700")

    def test_browse_directory(self, gui_instance, mock_filedialog):
        """Test browse_directory sets variable."""
        mock_filedialog.askdirectory.return_value = "/path/to/directory"
        mock_var = MagicMock()

        gui_instance.browse_directory(mock_var)

        mock_filedialog.askdirectory.assert_called_once()
        mock_var.set.assert_called_once_with("/path/to/directory")

    def test_browse_directory_cancel(self, gui_instance, mock_filedialog):
        """Test browse_directory when user cancels."""
        mock_filedialog.askdirectory.return_value = ""
        mock_var = MagicMock()

        gui_instance.browse_directory(mock_var)

        # Variable should not be set when empty
        mock_var.set.assert_not_called()

    def test_browse_file(self, gui_instance, mock_filedialog):
        """Test browse_file sets variable."""
        mock_filedialog.askopenfilename.return_value = "/path/to/file.yml"
        mock_var = MagicMock()

        gui_instance.browse_file(mock_var)

        mock_filedialog.askopenfilename.assert_called_once()
        mock_var.set.assert_called_once_with("/path/to/file.yml")

    def test_browse_file_with_filetypes(self, gui_instance, mock_filedialog):
        """Test browse_file with custom filetypes."""
        mock_filedialog.askopenfilename.return_value = "/path/to/script.sh"
        mock_var = MagicMock()
        filetypes = [("Shell files", "*.sh"), ("All files", "*.*")]

        gui_instance.browse_file(mock_var, filetypes=filetypes)

        call_args = mock_filedialog.askopenfilename.call_args[1]
        assert call_args["filetypes"] == filetypes

    def test_clear_output(self, gui_instance):
        """Test clear_output clears the text widget."""
        gui_instance.clear_output()

        gui_instance.output_text.delete.assert_called_once()

    def test_stop_command(self, gui_instance):
        """Test stop_command delegates to command_runner."""
        gui_instance.stop_command()

        gui_instance.command_runner.stop_command.assert_called_once()

    def test_build_command_basic(self, gui_instance):
        """Test build_command creates correct command list."""
        options = {
            "in": "/input/path",
            "out": "/output/path",
        }

        cmd = gui_instance.build_command("compile", options)

        assert cmd == [
            "bash2gitlab",
            "compile",
            "--in",
            "/input/path",
            "--out",
            "/output/path",
        ]

    def test_build_command_with_boolean_flags(self, gui_instance):
        """Test build_command handles boolean flags."""
        options = {
            "dry_run": True,
            "verbose": False,
            "force": True,
        }

        cmd = gui_instance.build_command("compile", options)

        assert "bash2gitlab" in cmd
        assert "compile" in cmd
        assert "--dry-run" in cmd
        assert "--force" in cmd
        assert "--verbose" not in cmd

    def test_build_command_with_integers(self, gui_instance):
        """Test build_command handles integer parameters."""
        options = {
            "parallelism": 8,
            "timeout": 30,
        }

        cmd = gui_instance.build_command("lint", options)

        assert "--parallelism" in cmd
        assert "8" in cmd
        assert "--timeout" in cmd
        assert "30" in cmd

    def test_build_command_skips_empty_strings(self, gui_instance):
        """Test build_command skips empty string values."""
        options = {
            "in": "/path",
            "token": "",
            "ref": "   ",
        }

        cmd = gui_instance.build_command("lint", options)

        assert "--in" in cmd
        assert "--token" not in cmd
        assert "--ref" not in cmd

    def test_build_command_skips_internal_vars(self, gui_instance):
        """Test build_command skips internal variables."""
        options = {
            "_internal": "value",
            "public": "value",
        }

        cmd = gui_instance.build_command("compile", options)

        assert "--internal" not in cmd
        assert "--public" in cmd

    def test_build_command_converts_underscores(self, gui_instance):
        """Test build_command converts underscores to hyphens."""
        options = {
            "dry_run": True,
            "include_merged_yaml": True,
        }

        cmd = gui_instance.build_command("lint", options)

        assert "--dry-run" in cmd
        assert "--include-merged-yaml" in cmd

    def test_update_decompile_inputs_file_mode(self, gui_instance):
        """Test update_decompile_inputs enables file input in file mode."""
        # Setup mock UI elements
        gui_instance.decompile_file_entry = MagicMock()
        gui_instance.decompile_file_btn = MagicMock()
        gui_instance.decompile_folder_entry = MagicMock()
        gui_instance.decompile_folder_btn = MagicMock()
        gui_instance.vars["decompile_input_type"] = MagicMock()
        gui_instance.vars["decompile_input_type"].get.return_value = "file"

        gui_instance.update_decompile_inputs()

        # File controls should be enabled
        gui_instance.decompile_file_entry.config.assert_called()
        gui_instance.decompile_file_btn.config.assert_called()

    def test_update_decompile_inputs_folder_mode(self, gui_instance):
        """Test update_decompile_inputs enables folder input in folder mode."""
        # Setup mock UI elements
        gui_instance.decompile_file_entry = MagicMock()
        gui_instance.decompile_file_btn = MagicMock()
        gui_instance.decompile_folder_entry = MagicMock()
        gui_instance.decompile_folder_btn = MagicMock()
        gui_instance.vars["decompile_input_type"] = MagicMock()
        gui_instance.vars["decompile_input_type"].get.return_value = "folder"

        gui_instance.update_decompile_inputs()

        # Folder controls should be enabled
        gui_instance.decompile_folder_entry.config.assert_called()
        gui_instance.decompile_folder_btn.config.assert_called()


class TestCommandMethods:
    """Test specific command execution methods."""

    @pytest.fixture
    def setup_gui(self, mock_tk, mock_ttk, mock_scrolledtext, mock_filedialog, mock_messagebox):
        """Setup GUI with mocked variables."""
        from bash2gitlab.gui import Bash2GitlabGUI

        root = MagicMock()
        with patch.object(Bash2GitlabGUI, "setup_gui"):
            gui = Bash2GitlabGUI(root)
            gui.command_runner = MagicMock()
            gui.output_text = MagicMock()

            # Initialize all vars as StringVar or BooleanVar mocks
            var_names = [
                "compile_input",
                "compile_output",
                "compile_parallelism",
                "compile_dry_run",
                "compile_watch",
                "compile_verbose",
                "compile_force",
                "compile_autogit",
                "clean_output",
                "clean_dry_run",
                "clean_autogit",
                "init_directory",
                "init_dry_run",
                "lint_output",
                "lint_gitlab_url",
                "lint_token",
                "lint_project_id",
                "lint_ref",
                "lint_include_merged",
                "lint_parallelism",
                "lint_timeout",
                "lint_verbose",
            ]

            for var_name in var_names:
                mock_var = MagicMock()
                mock_var.get.return_value = ""
                gui.vars[var_name] = mock_var

            return gui

    def test_run_compile_success(self, setup_gui, mock_messagebox):
        """Test run_compile with valid inputs."""
        gui = setup_gui
        gui.vars["compile_input"].get.return_value = "/input"
        gui.vars["compile_output"].get.return_value = "/output"
        gui.vars["compile_parallelism"].get.return_value = "4"
        gui.vars["compile_dry_run"].get.return_value = False
        gui.vars["compile_watch"].get.return_value = False
        gui.vars["compile_verbose"].get.return_value = False
        gui.vars["compile_force"].get.return_value = False
        gui.vars["compile_autogit"].get.return_value = False

        gui.run_compile()

        # Command runner should be called
        gui.command_runner.run_command.assert_called_once()
        cmd = gui.command_runner.run_command.call_args[0][0]
        assert "bash2gitlab" in cmd
        assert "compile" in cmd
        assert "--in" in cmd
        assert "/input" in cmd

    def test_run_compile_missing_input(self, setup_gui, mock_messagebox):
        """Test run_compile shows error when input is missing."""
        gui = setup_gui
        gui.vars["compile_input"].get.return_value = ""
        gui.vars["compile_output"].get.return_value = "/output"

        gui.run_compile()

        # Error should be shown
        mock_messagebox.showerror.assert_called_once()
        # Command should not run
        gui.command_runner.run_command.assert_not_called()

    def test_run_compile_missing_output(self, setup_gui, mock_messagebox):
        """Test run_compile shows error when output is missing."""
        gui = setup_gui
        gui.vars["compile_input"].get.return_value = "/input"
        gui.vars["compile_output"].get.return_value = ""

        gui.run_compile()

        # Error should be shown
        mock_messagebox.showerror.assert_called_once()
        # Command should not run
        gui.command_runner.run_command.assert_not_called()

    def test_run_clean_success(self, setup_gui, mock_messagebox):
        """Test run_clean with valid inputs."""
        gui = setup_gui
        gui.vars["clean_output"].get.return_value = "/output"
        gui.vars["clean_dry_run"].get.return_value = True
        gui.vars["clean_autogit"].get.return_value = False

        gui.run_clean()

        gui.command_runner.run_command.assert_called_once()
        cmd = gui.command_runner.run_command.call_args[0][0]
        assert "clean" in cmd
        assert "--dry-run" in cmd

    def test_run_clean_missing_output(self, setup_gui, mock_messagebox):
        """Test run_clean shows error when output is missing."""
        gui = setup_gui
        gui.vars["clean_output"].get.return_value = ""

        gui.run_clean()

        mock_messagebox.showerror.assert_called_once()
        gui.command_runner.run_command.assert_not_called()

    def test_run_init(self, setup_gui):
        """Test run_init command."""
        gui = setup_gui
        gui.vars["init_directory"].get.return_value = "."
        gui.vars["init_dry_run"].get.return_value = False

        gui.run_init()

        gui.command_runner.run_command.assert_called_once()
        cmd = gui.command_runner.run_command.call_args[0][0]
        assert "bash2gitlab" in cmd
        assert "init" in cmd
        assert "." in cmd

    def test_run_init_with_dry_run(self, setup_gui):
        """Test run_init with dry run flag."""
        gui = setup_gui
        gui.vars["init_directory"].get.return_value = "/project"
        gui.vars["init_dry_run"].get.return_value = True

        gui.run_init()

        cmd = gui.command_runner.run_command.call_args[0][0]
        assert "--dry-run" in cmd

    def test_run_doctor(self, setup_gui):
        """Test run_doctor command."""
        gui = setup_gui

        gui.run_doctor()

        gui.command_runner.run_command.assert_called_once()
        cmd = gui.command_runner.run_command.call_args[0][0]
        assert cmd == ["bash2gitlab", "doctor"]

    def test_run_show_config(self, setup_gui):
        """Test run_show_config command."""
        gui = setup_gui

        gui.run_show_config()

        gui.command_runner.run_command.assert_called_once()
        cmd = gui.command_runner.run_command.call_args[0][0]
        assert cmd == ["bash2gitlab", "show-config"]

    def test_run_lint_success(self, setup_gui, mock_messagebox):
        """Test run_lint with valid inputs."""
        gui = setup_gui
        gui.vars["lint_output"].get.return_value = "/output"
        gui.vars["lint_gitlab_url"].get.return_value = "https://gitlab.com"
        gui.vars["lint_token"].get.return_value = "token"
        gui.vars["lint_project_id"].get.return_value = "123"
        gui.vars["lint_ref"].get.return_value = "main"
        gui.vars["lint_include_merged"].get.return_value = True
        gui.vars["lint_parallelism"].get.return_value = "4"
        gui.vars["lint_timeout"].get.return_value = "20"
        gui.vars["lint_verbose"].get.return_value = False

        gui.run_lint()

        gui.command_runner.run_command.assert_called_once()
        cmd = gui.command_runner.run_command.call_args[0][0]
        assert "lint" in cmd
        assert "--gitlab-url" in cmd
        assert "--include-merged-yaml" in cmd

    def test_run_lint_missing_output(self, setup_gui, mock_messagebox):
        """Test run_lint shows error when output is missing."""
        gui = setup_gui
        gui.vars["lint_output"].get.return_value = ""
        gui.vars["lint_gitlab_url"].get.return_value = "https://gitlab.com"

        gui.run_lint()

        mock_messagebox.showerror.assert_called_once()
        gui.command_runner.run_command.assert_not_called()

    def test_run_lint_missing_gitlab_url(self, setup_gui, mock_messagebox):
        """Test run_lint shows error when GitLab URL is missing."""
        gui = setup_gui
        gui.vars["lint_output"].get.return_value = "/output"
        gui.vars["lint_gitlab_url"].get.return_value = ""

        gui.run_lint()

        mock_messagebox.showerror.assert_called_once()
        gui.command_runner.run_command.assert_not_called()


class TestMainFunction:
    """Test the main() function."""

    def test_main_creates_window(self):
        """Test main() creates and runs the GUI."""
        from bash2gitlab.gui import main

        mock_root = MagicMock()
        mock_root.mainloop.side_effect = KeyboardInterrupt()

        with patch("bash2gitlab.gui.tk.Tk", return_value=mock_root) as mock_tk_class:
            with patch("bash2gitlab.gui.Bash2GitlabGUI"):
                with patch("bash2gitlab.gui.logging.basicConfig"):
                    main()

                    # Verify window was created
                    mock_tk_class.assert_called_once()
                    # Verify mainloop was started
                    mock_root.mainloop.assert_called_once()

    def test_main_handles_exception(self):
        """Test main() handles unexpected exceptions."""
        from bash2gitlab.gui import main

        mock_root = MagicMock()
        mock_root.mainloop.side_effect = Exception("Test error")

        with patch("bash2gitlab.gui.tk.Tk", return_value=mock_root):
            with patch("bash2gitlab.gui.Bash2GitlabGUI"):
                with patch("bash2gitlab.gui.logging.basicConfig"):
                    with patch("bash2gitlab.gui.messagebox.showerror") as mock_showerror:
                        main()

                        # Error dialog should be shown
                        mock_showerror.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
