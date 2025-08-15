from __future__ import annotations

import pytest

from bash2gitlab.commands.compile_all import extract_script_path
from bash2gitlab.utils.dotenv import parse_env_file


class TestHelperFunctions:
    """Tests for the helper functions in compile_all.py"""

    def test_parse_env_file(self):
        """Verify .env file parsing for different formats."""
        content = """
# This is a comment
export VAR1="Hello World"
VAR2=SimpleValue
VAR3='SingleQuoted'

# Empty line above
        """
        expected = {
            "VAR1": "Hello World",
            "VAR2": "SimpleValue",
            "VAR3": "SingleQuoted",
        }
        assert parse_env_file(content) == expected

    @pytest.mark.parametrize(
        "command, expected_path",
        [
            ("bash ./scripts/deploy.sh", "scripts/deploy.sh"),
            ("sh scripts/setup.sh", "scripts/setup.sh"),
            ("./run.sh", "run.sh"),
            ("source /path/to/my.sh", "/path/to/my.sh"),
            ("echo 'running ./run.sh'", None),
            ("do_something && ./run.sh", None),
            ("bash -c 'some command'", None),
            ("npm install", None),
        ],
    )
    def test_extract_script_path(self, command, expected_path):
        """Verify script path extraction from command lines."""
        assert extract_script_path(command) == expected_path
