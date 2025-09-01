# Example usage and tests
import os
import re
import tempfile
from pathlib import Path

from bash2gitlab.utils.dotenv import (
    env_vars_to_simple_dict,
    parse_env_file,
    parse_env_file_with_descriptions,
    set_environment_variables,
    write_env_file,
)


def test_basic_parsing():
    """Test basic key=value parsing"""
    content = "KEY=value\nANOTHER=test"
    result = parse_env_file(content)
    assert result == {"KEY": "value", "ANOTHER": "test"}


def test_export_parsing():
    """Test export KEY=value parsing"""
    content = "export KEY=value\nexport ANOTHER=test"
    result = parse_env_file(content)
    assert result == {"KEY": "value", "ANOTHER": "test"}


def test_mixed_parsing():
    """Test mixed export and regular variables"""
    content = "KEY=value\nexport ANOTHER=test"
    result = parse_env_file(content)
    assert result == {"KEY": "value", "ANOTHER": "test"}


def test_quoted_values():
    """Test quoted values are properly unquoted"""
    content = "KEY=\"quoted value\"\nANOTHER='single quoted'"
    result = parse_env_file(content)
    assert result == {"KEY": "quoted value", "ANOTHER": "single quoted"}


def test_comments_ignored():
    """Test comments are ignored in legacy mode"""
    content = "# This is a comment\nKEY=value\n# Another comment"
    result = parse_env_file(content)
    assert result == {"KEY": "value"}


def test_empty_lines_ignored():
    """Test empty lines are ignored"""
    content = "\n\nKEY=value\n\nANOTHER=test\n\n"
    result = parse_env_file(content)
    assert result == {"KEY": "value", "ANOTHER": "test"}


def test_descriptions_parsing():
    """Test parsing with descriptions"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write("# The name of the tox executable\nTOX_EXE=tox\nNO_DESC=blah\n# Has description\nexport FOO=bar")
        temp_path = Path(f.name)

    try:
        result = parse_env_file_with_descriptions(temp_path)
        expected = {
            "TOX_EXE": {"value": "tox", "description": "The name of the tox executable"},
            "NO_DESC": {"value": "blah", "description": None},
            "FOO": {"value": "bar", "description": "Has description"},
        }
        assert result == expected
    finally:
        temp_path.unlink(missing_ok=True)


def test_env_vars_to_simple_dict():
    """Test conversion to simple dict"""
    env_vars = {
        "KEY1": {"value": "value1", "description": "A description"},
        "KEY2": {"value": "value2", "description": None},
    }
    result = env_vars_to_simple_dict(env_vars)
    assert result == {"KEY1": "value1", "KEY2": "value2"}


def test_write_and_read_round_trip():
    """Test writing and reading back produces same result"""
    original_vars = {
        "KEY1": {"value": "value1", "description": "A description"},
        "KEY2": {"value": "value2", "description": None},
        "QUOTED": {"value": "value with spaces", "description": "Needs quotes"},
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        temp_path = Path(f.name)

    try:
        write_env_file(original_vars, temp_path)
        result = parse_env_file_with_descriptions(temp_path)

        # Values should match
        for key in original_vars:
            assert result[key]["value"] == original_vars[key]["value"]
            assert result[key]["description"] == original_vars[key]["description"]
    finally:
        temp_path.unlink(missing_ok=True)


def test_set_environment_variables(monkeypatch):
    """Test setting environment variables"""
    env_vars = {
        "TEST_VAR1": {"value": "test_value1", "description": None},
        "TEST_VAR2": {"value": "test_value2", "description": "A test var"},
    }

    set_environment_variables(env_vars)
    assert os.environ.get("TEST_VAR1") == "test_value1"
    assert os.environ.get("TEST_VAR2") == "test_value2"


# 10 Regex pattern tests
def test_regex_patterns():
    """Test the regex pattern against various inputs"""
    pattern = r"^(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$"

    # Test cases: (input, should_match, expected_key, expected_value)
    test_cases = [
        ("KEY=value", True, "KEY", "value"),
        ("export KEY=value", True, "KEY", "value"),
        ("SNAKE_CASE=test", True, "SNAKE_CASE", "test"),
        ("_UNDERSCORE=start", True, "_UNDERSCORE", "start"),
        ("KEY123=numeric", True, "KEY123", "numeric"),
        ("export  SPACED=value", True, "SPACED", "value"),  # Multiple spaces after export
        ("KEY=", True, "KEY", ""),  # Empty value
        ("KEY=value=with=equals", True, "KEY", "value=with=equals"),  # Value with equals
        ("123INVALID=value", False, None, None),  # Key starting with number
        ("SPACES IN KEY=value", False, None, None),  # Invalid key with spaces
    ]

    for i, (test_input, should_match, expected_key, expected_value) in enumerate(test_cases):
        match = re.match(pattern, test_input)
        if should_match:
            assert match is not None, f"Test {i + 1}: '{test_input}' should match but didn't"
            assert match.group("key") == expected_key, f"Test {i + 1}: Expected key '{expected_key}', got '{match.group('key')}'"
            assert match.group("value") == expected_value, f"Test {i + 1}: Expected value '{expected_value}', got '{match.group('value')}'"
        else:
            assert match is None, f"Test {i + 1}: '{test_input}' should not match but did"
