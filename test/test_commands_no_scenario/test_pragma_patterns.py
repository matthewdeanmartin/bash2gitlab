import re

import pytest

# The regular expression being tested
PRAGMA_REGEX = re.compile(
    r"#\s*Pragma:\s*(?P<command>do-not-inline(?:-next-line)?|start-do-not-inline|end-do-not-inline|allow-outside-root)",
    re.IGNORECASE,
)


# --- Test cases for successful matches ---


@pytest.mark.parametrize(
    "input_line, expected_command",
    [
        pytest.param("echo 'hello world' # Pragma: do-not-inline", "do-not-inline", id="basic_do-not-inline"),
        pytest.param("ls # Pragma: do-not-inline", "do-not-inline", id="basic_do-not-inline"),
        # Category 1: Basic Happy Path for each command
        pytest.param("# Pragma: do-not-inline", "do-not-inline", id="basic_do-not-inline"),
        pytest.param(
            "# Pragma: do-not-inline-next-line",
            "do-not-inline-next-line",
            id="basic_do-not-inline-next-line",
        ),
        pytest.param(
            "# Pragma: start-do-not-inline",
            "start-do-not-inline",
            id="basic_start-do-not-inline",
        ),
        pytest.param(
            "# Pragma: end-do-not-inline",
            "end-do-not-inline",
            id="basic_end-do-not-inline",
        ),
        pytest.param(
            "# Pragma: allow-outside-root",
            "allow-outside-root",
            id="basic_allow-outside-root",
        ),
        # Category 2: Whitespace Variations
        pytest.param("#Pragma:do-not-inline", "do-not-inline", id="whitespace_no_spaces"),
        pytest.param(
            "#  Pragma:  start-do-not-inline",
            "start-do-not-inline",
            id="whitespace_multiple_spaces",
        ),
        pytest.param(
            "#\tPragma:\tallow-outside-root",
            "allow-outside-root",
            id="whitespace_tabs",
        ),
        pytest.param(
            "# Pragma: end-do-not-inline   ",
            "end-do-not-inline",
            id="whitespace_trailing_spaces",
        ),
        # Category 3: Case-Insensitivity
        pytest.param("# pragma: do-not-inline", "do-not-inline", id="case_lowercase_pragma"),
        pytest.param(
            "# PRAGMA: start-do-not-inline",
            "start-do-not-inline",
            id="case_uppercase_pragma",
        ),
        pytest.param(
            "# pRaGmA: allow-outside-root",
            "allow-outside-root",
            id="case_mixed_case_pragma",
        ),
        # Category 4: On lines with other content
        pytest.param("source ./lib.sh # Pragma: do-not-inline", "do-not-inline", id="on_line_with_command"),
        pytest.param("    # Pragma: start-do-not-inline", "start-do-not-inline", id="on_line_with_leading_indent"),
        pytest.param(
            "# Pragma: end-do-not-inline # with extra comment", "end-do-not-inline", id="on_line_with_trailing_comment"
        ),
    ],
)
def test_pragma_regex_positive_matches(input_line, expected_command):
    """
    Tests that the PRAGMA_REGEX correctly finds and captures valid pragma commands.
    """
    match = PRAGMA_REGEX.search(input_line)
    assert match is not None
    assert match.group("command") == expected_command


# --- Test cases for strings that should NOT match ---


@pytest.mark.parametrize(
    "input_line",
    [
        pytest.param("Pragma: do-not-inline", id="negative_missing_hash"),
        pytest.param("# Pragma do-not-inline", id="negative_missing_colon"),
        pytest.param("# Pragmas: do-not-inline", id="negative_misspelled_pragma"),
        pytest.param("# Pragma: do-not-in-line", id="negative_misspelled_command"),
        # pytest.param("# Pragma: do-not-inline-now", id="negative_extra_suffix_on_command"),
        pytest.param("# Pragma: stop-do-not-inline", id="negative_invalid_command_prefix"),
        pytest.param("# Pragma:", id="negative_empty_command"),
        # pytest.param("echo '# Pragma: do-not-inline'", id="negative_inside_quotes"),
        pytest.param("This is not a Pragma: it is a comment", id="negative_prose_not_a_match"),
        pytest.param("just a normal line of code", id="negative_unrelated_code"),
        pytest.param("# just a normal comment", id="negative_unrelated_comment"),
    ],
)
def test_pragma_regex_negative_matches(input_line):
    """
    Tests that the PRAGMA_REGEX does not match invalid or unrelated strings.
    """
    match = PRAGMA_REGEX.search(input_line)
    assert match is None
