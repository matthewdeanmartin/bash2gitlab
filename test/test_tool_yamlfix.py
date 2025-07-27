import subprocess
from unittest.mock import Mock, patch

import pytest

from bash2gitlab.tool_yamlfix import run_formatter  # Replace with actual module path


@pytest.fixture
def temp_dirs(tmp_path):
    output = tmp_path / "output"
    templates = tmp_path / "templates"
    output.mkdir()
    templates.mkdir()
    return output, templates


def test_run_formatter_success(temp_dirs):
    output_dir, templates_output_dir = temp_dirs

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stderr=b"")
        run_formatter(output_dir, templates_output_dir)

        # Check both yamlfix version check and format run were called
        assert mock_run.call_count == 2
        mock_run.assert_any_call(["yamlfix", "--version"], check=True, capture_output=True)
        mock_run.assert_any_call(
            ["yamlfix", str(output_dir), str(templates_output_dir)], check=True, capture_output=True
        )


def test_run_formatter_yamlfix_fails(temp_dirs):
    output_dir, templates_output_dir = temp_dirs

    with patch("subprocess.run") as mock_run, patch("sys.exit") as mock_exit:
        # First call (version check) succeeds
        # Second call (formatting) fails
        def side_effect(*args, **kwargs):
            if args[0][:2] == ["yamlfix", "--version"]:
                return Mock(returncode=0, stderr=b"")
            else:
                raise subprocess.CalledProcessError(1, args[0], stderr=b"something went wrong")

        mock_run.side_effect = side_effect
        run_formatter(output_dir, templates_output_dir)
        mock_exit.assert_called_once_with(1)


def test_run_formatter_no_targets(tmp_path):
    # Neither directory exists
    output_dir = tmp_path / "missing_output"
    templates_output_dir = tmp_path / "missing_templates"

    with patch("subprocess.run") as mock_run:
        run_formatter(output_dir, templates_output_dir)
        mock_run.assert_called_once_with(["yamlfix", "--version"], check=True, capture_output=True)
