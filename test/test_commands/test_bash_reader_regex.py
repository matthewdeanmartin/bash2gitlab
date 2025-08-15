import pytest

from bash2gitlab.bash_reader import SOURCE_COMMAND_REGEX

# A list of test cases with the line to test and the expected captured path.
# If the expected path is None, the regex should not match the line.
TEST_CASES = [
    # --- Valid Cases ---
    ("source my_script.sh", "my_script.sh"),
    (". my_script.sh", "my_script.sh"),
    ("  source relative/path/to/script.sh", "relative/path/to/script.sh"),
    ("\tsource script-with-hyphens.sh", "script-with-hyphens.sh"),
    ("source ../parent/dir/script.sh", "../parent/dir/script.sh"),
    (". ./script_in_current_dir.sh", "./script_in_current_dir.sh"),
    (r"source windows\style\path.sh", r"windows\style\path.sh"),
    ("source path_with_underscores_and.numbers123", "path_with_underscores_and.numbers123"),
    ("source my_script.sh   ", "my_script.sh"),  # Test with trailing whitespace
    (". my_script.sh\t", "my_script.sh"),  # Test with trailing tab
    ("source my_script.sh # with a comment", "my_script.sh"),  # Should not match if there are trailing characters
    # --- Invalid or Non-Matching Cases ---
    ("# source my_script.sh", None),  # Should not match commented out lines
    ("source", None),  # Should not match without a path
    (". ", None),  # Should not match without a path
    ("echo 'source my_script.sh'", None),  # Should not match if part of another command
    ("export VAR=source", None),  # Should not match variable assignments
    ("source 'quoted/path.sh'", None),  # The current regex does not support quotes
    ('source "double/quoted/path.sh"', None),  # The current regex does not support quotes
    ("anothersource my_script.sh", None),  # 'source' must be at the beginning (after whitespace)
    ("source path/with/invalid$char.sh", None),  # '$' is not a valid character in the regex path
]


@pytest.mark.parametrize("line_to_test, expected_path", TEST_CASES)
def test_source_command_regex(line_to_test, expected_path):
    """
    Tests the SOURCE_COMMAND_REGEX against various valid and invalid lines.

    Args:
        line_to_test: The string representing a line from a bash script.
        expected_path: The expected path to be extracted, or None if no match is expected.
    """
    match = SOURCE_COMMAND_REGEX.match(line_to_test)

    if expected_path is not None:
        assert match is not None, f"Expected to find a match in: '{line_to_test}'"
        assert match.group("path") == expected_path, f"Extracted path does not match for: '{line_to_test}'"
    else:
        assert match is None, f"Expected no match for line: '{line_to_test}'"


# Additional test to make it an even dozen distinct tests
def test_regex_handles_dot_alias_with_whitespace():
    """
    Ensures the dot alias for source is handled correctly with various whitespace.
    """
    line = "   .   ./some/script.sh   "
    match = SOURCE_COMMAND_REGEX.match(line)
    assert match is not None
    assert match.group("path") == "./some/script.sh"


def test_regex_fails_on_multiline():
    """
    Ensures the regex with '$' anchor does not match across newlines.
    """
    line = "source my_script.sh\necho 'hello'"
    match = SOURCE_COMMAND_REGEX.match(line)
    assert match is None
