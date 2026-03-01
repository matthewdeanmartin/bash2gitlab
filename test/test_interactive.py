"""
Unit tests for bash2gitlab/interactive.py

Tests demonstrate that interactive.py is fully testable by mocking Rich prompts
and verifying that each handler method properly collects and structures parameters.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from argparse import Namespace

import pytest


@pytest.fixture
def mock_console():
    """Mock Rich Console to avoid actual terminal output."""
    with patch("bash2gitlab.interactive.Console") as mock:
        yield mock.return_value


@pytest.fixture
def mock_prompt():
    """Mock Rich Prompt.ask to simulate user input."""
    with patch("bash2gitlab.interactive.Prompt") as mock:
        yield mock


@pytest.fixture
def mock_confirm():
    """Mock Rich Confirm.ask to simulate yes/no questions."""
    with patch("bash2gitlab.interactive.Confirm") as mock:
        yield mock


@pytest.fixture
def mock_int_prompt():
    """Mock Rich IntPrompt.ask to simulate integer input."""
    with patch("bash2gitlab.interactive.IntPrompt") as mock:
        yield mock


@pytest.fixture
def interface(mock_console):
    """Create InteractiveInterface instance with mocked console."""
    from bash2gitlab.interactive import InteractiveInterface

    return InteractiveInterface()


class TestCompileHandler:
    """Test the compile command handler."""

    def test_handle_compile_command_returns_correct_structure(
        self, interface, mock_prompt, mock_confirm, mock_int_prompt
    ):
        """Verify compile handler returns all required parameters."""
        # Arrange: Set up mock responses
        mock_prompt.ask.side_effect = ["./input", "./output"]
        mock_int_prompt.ask.return_value = 4
        mock_confirm.ask.side_effect = [
            False,  # watch
            False,  # force
            False,  # dry_run
            False,  # verbose
            False,  # quiet
        ]

        # Act: Call the handler
        params = interface.handle_compile_command()

        # Assert: Verify structure
        assert params["input_dir"] == "./input"
        assert params["output_dir"] == "./output"
        assert params["parallelism"] == 4
        assert params["watch"] is False
        assert params["force"] is False
        assert params["dry_run"] is False
        assert params["verbose"] is False
        assert params["quiet"] is False

    def test_handle_compile_with_watch_enabled(
        self, interface, mock_prompt, mock_confirm, mock_int_prompt
    ):
        """Test compile handler when watch mode is enabled."""
        # Arrange
        mock_prompt.ask.side_effect = ["./src", "./build"]
        mock_int_prompt.ask.return_value = 8
        mock_confirm.ask.side_effect = [
            True,  # watch
            True,  # force
            True,  # dry_run
            True,  # verbose
            False,  # quiet
        ]

        # Act
        params = interface.handle_compile_command()

        # Assert
        assert params["watch"] is True
        assert params["force"] is True
        assert params["parallelism"] == 8


class TestValidateHandler:
    """Test the validate command handler."""

    def test_handle_validate_command_basic(
        self, interface, mock_prompt, mock_confirm, mock_int_prompt
    ):
        """Test validate handler with basic inputs."""
        # Arrange
        mock_prompt.ask.side_effect = ["./source", "./output"]
        mock_int_prompt.ask.return_value = 2
        mock_confirm.ask.side_effect = [False, False, False]  # dry_run, verbose, quiet

        # Act
        params = interface.handle_validate_command()

        # Assert
        assert params["input_dir"] == "./source"
        assert params["output_dir"] == "./output"
        assert params["parallelism"] == 2


class TestCheckPinsHandler:
    """Test the check-pins command handler."""

    def test_handle_check_pins_with_token(
        self, interface, mock_prompt, mock_confirm
    ):
        """Test check-pins handler with authentication token."""
        # Arrange
        mock_prompt.ask.side_effect = [
            ".gitlab-ci.yml",  # file
            "https://gitlab.example.com",  # gitlab_url
            "glpat-xxx",  # token
            "",  # oauth_token (empty)
        ]
        mock_confirm.ask.side_effect = [
            True,  # pin_tags_only
            False,  # json output
            False,  # dry_run
            False,  # verbose
            False,  # quiet
        ]

        # Act
        params = interface.handle_check_pins_command()

        # Assert
        assert params["file"] == ".gitlab-ci.yml"
        assert params["gitlab_url"] == "https://gitlab.example.com"
        assert params["token"] == "glpat-xxx"
        assert params["oauth_token"] is None
        assert params["pin_tags_only"] is True
        assert params["json"] is False


class TestTriggerPipelinesHandler:
    """Test the trigger-pipelines command handler."""

    def test_handle_trigger_pipelines_single_project(
        self, interface, mock_prompt, mock_confirm
    ):
        """Test trigger-pipelines with one project and no variables."""
        # Arrange
        mock_prompt.ask.side_effect = [
            "https://gitlab.com",  # gitlab_url
            "glpat-token",  # token
            "123:main",  # first project
            "",  # end projects
            "",  # end variables
        ]
        mock_confirm.ask.side_effect = [
            False,  # wait
            False,  # dry_run
            False,  # verbose
            False,  # quiet
        ]

        # Act
        params = interface.handle_trigger_pipelines_command()

        # Assert
        assert params["gitlab_url"] == "https://gitlab.com"
        assert params["token"] == "glpat-token"
        assert params["project"] == ["123:main"]
        assert "variable" not in params
        assert params["wait"] is False

    def test_handle_trigger_pipelines_with_wait_and_variables(
        self, interface, mock_prompt, mock_confirm
    ):
        """Test trigger-pipelines with wait enabled and variables."""
        # Arrange
        mock_prompt.ask.side_effect = [
            "https://gitlab.internal",  # gitlab_url
            "token123",  # token
            "456:dev",  # first project
            "789:staging",  # second project
            "",  # end projects
            "ENV=prod",  # first variable
            "DEBUG=true",  # second variable
            "",  # end variables
            "3600",  # timeout
            "60",  # poll_interval
        ]
        mock_confirm.ask.side_effect = [
            True,  # wait
            False,  # dry_run
            False,  # verbose
            False,  # quiet
        ]

        # Act
        params = interface.handle_trigger_pipelines_command()

        # Assert
        assert params["project"] == ["456:dev", "789:staging"]
        assert params["variable"] == ["ENV=prod", "DEBUG=true"]
        assert params["wait"] is True
        assert params["timeout"] == 3600
        assert params["poll_interval"] == 60


class TestRunHandler:
    """Test the run command handler."""

    def test_handle_run_command_default(self, interface, mock_prompt, mock_confirm):
        """Test run handler with default file."""
        # Arrange
        mock_prompt.ask.side_effect = [".gitlab-ci.yml"]
        mock_confirm.ask.side_effect = [False, False, False]  # dry_run, verbose, quiet

        # Act
        params = interface.handle_run_command()

        # Assert
        assert params["input_file"] == ".gitlab-ci.yml"


class TestAutogitHandler:
    """Test the autogit command handler."""

    def test_handle_autogit_with_message(self, interface, mock_prompt, mock_confirm):
        """Test autogit handler with custom commit message."""
        # Arrange
        mock_prompt.ask.side_effect = ["feat: add new feature"]
        mock_confirm.ask.side_effect = [False, False, False]

        # Act
        params = interface.handle_autogit_command()

        # Assert
        assert params["message"] == "feat: add new feature"

    def test_handle_autogit_without_message(
        self, interface, mock_prompt, mock_confirm
    ):
        """Test autogit handler without custom message."""
        # Arrange
        mock_prompt.ask.side_effect = [""]  # empty message
        mock_confirm.ask.side_effect = [False, False, False]

        # Act
        params = interface.handle_autogit_command()

        # Assert
        assert params["message"] is None


class TestDetectUncompiledHandler:
    """Test the detect-uncompiled command handler."""

    def test_handle_detect_uncompiled_check_only(
        self, interface, mock_prompt, mock_confirm
    ):
        """Test detect-uncompiled with check-only mode."""
        # Arrange
        mock_prompt.ask.side_effect = ["./project"]
        mock_confirm.ask.side_effect = [
            True,  # check_only
            False,  # dry_run
            False,  # verbose
            False,  # quiet
        ]

        # Act
        params = interface.handle_detect_uncompiled_command()

        # Assert
        assert params["input_dir"] == "./project"
        assert params["check_only"] is True
        assert params["list_changed"] is False

    def test_handle_detect_uncompiled_list_changed(
        self, interface, mock_prompt, mock_confirm
    ):
        """Test detect-uncompiled with list-changed mode."""
        # Arrange
        mock_prompt.ask.side_effect = ["./src"]
        mock_confirm.ask.side_effect = [
            False,  # check_only
            True,  # list_changed
            False,  # dry_run
            False,  # verbose
            False,  # quiet
        ]

        # Act
        params = interface.handle_detect_uncompiled_command()

        # Assert
        assert params["check_only"] is False
        assert params["list_changed"] is True


class TestExecuteCommand:
    """Test the execute_command method."""

    def test_execute_command_calls_handler(self, interface, mock_console):
        """Test that execute_command properly dispatches to handlers."""
        # Arrange: Mock the compile_handler (imported inside execute_command)
        with patch("bash2gitlab.__main__.compile_handler") as mock_handler:
            mock_handler.return_value = 0  # success exit code

            params = {
                "input_dir": "./in",
                "output_dir": "./out",
                "parallelism": 4,
                "dry_run": False,
                "verbose": False,
                "quiet": False,
                "watch": False,
                "force": False,
            }

            # Act
            interface.execute_command("compile", params)

            # Assert: Handler was called with correct arguments
            mock_handler.assert_called_once()
            args = mock_handler.call_args[0][0]  # Get the Namespace object
            assert isinstance(args, Namespace)
            assert args.input_dir == "./in"
            assert args.output_dir == "./out"

    def test_execute_command_handles_unknown_command(self, interface, mock_console):
        """Test that execute_command handles unknown commands gracefully."""
        # Act
        interface.execute_command("nonexistent-command", {})

        # Assert: Console should print error message
        # (We can't easily assert the exact message without more mocking,
        #  but the method should not raise an exception)


class TestDisplayCommandSummary:
    """Test the display_command_summary method."""

    def test_display_command_summary_user_confirms(
        self, interface, mock_confirm, mock_console
    ):
        """Test summary display when user confirms execution."""
        # Arrange
        mock_confirm.ask.return_value = True
        params = {"input_dir": "./src", "output_dir": "./build"}

        # Act
        result = interface.display_command_summary("compile", params)

        # Assert
        assert result is True
        mock_confirm.ask.assert_called_once()

    def test_display_command_summary_user_cancels(
        self, interface, mock_confirm, mock_console
    ):
        """Test summary display when user cancels execution."""
        # Arrange
        mock_confirm.ask.return_value = False
        params = {"input_dir": "./src"}

        # Act
        result = interface.display_command_summary("validate", params)

        # Assert
        assert result is False


class TestMainMenu:
    """Test the main menu display."""

    def test_show_main_menu_returns_choice(self, interface, mock_prompt):
        """Test that show_main_menu returns user's choice."""
        # Arrange
        mock_prompt.ask.return_value = "1"

        # Act
        choice = interface.show_main_menu()

        # Assert
        assert choice == "1"
        mock_prompt.ask.assert_called_once()

    def test_show_main_menu_quit_option(self, interface, mock_prompt):
        """Test that quit option works."""
        # Arrange
        mock_prompt.ask.return_value = "q"

        # Act
        choice = interface.show_main_menu()

        # Assert
        assert choice == "q"


# Integration-style test showing full flow
class TestIntegrationFlow:
    """Integration tests showing complete user flows."""

    def test_complete_compile_flow(
        self, interface, mock_prompt, mock_confirm, mock_int_prompt, mock_console
    ):
        """Test complete flow: menu -> compile -> execute."""
        with patch("bash2gitlab.__main__.compile_handler") as mock_handler:
            mock_handler.return_value = 0

            # Simulate menu selection
            mock_prompt.ask.side_effect = [
                "./input",  # input_dir
                "./output",  # output_dir
            ]
            mock_int_prompt.ask.return_value = 4  # parallelism
            mock_confirm.ask.side_effect = [
                False,  # watch
                False,  # force
                False,  # dry_run
                False,  # verbose
                False,  # quiet
                True,  # confirm execution
            ]

            # Get params from handler
            params = interface.handle_compile_command()

            # Display summary and confirm
            confirmed = interface.display_command_summary("compile", params)
            assert confirmed is True

            # Execute
            interface.execute_command("compile", params)

            # Verify handler was called
            mock_handler.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
