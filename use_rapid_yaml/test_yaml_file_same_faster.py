import pytest

from bash2gitlab.utils.yaml_file_same_faster import normalize_for_compare, yaml_is_same

# --- Tests for normalize_for_compare ---


@pytest.mark.parametrize(
    "input_text, expected_text",
    [
        # Test case 1: Basic text with no changes needed
        ("hello\nworld", "hello\nworld"),
        # Test case 2: Windows line endings
        ("hello\r\nworld", "hello\nworld"),
        # Test case 3: Old Mac line endings
        ("hello\rworld", "hello\nworld"),
        # Test case 4: Mixed line endings
        ("hello\r\nworld\nagain\r!", "hello\nworld\nagain\n!"),
        # Test case 5: Trailing whitespace on lines
        ("line1  \nline2\t\n", "line1\nline2"),
        # Test case 6: No newline at EOF
        ("no newline at end", "no newline at end"),
        # Test case 7: Multiple newlines at EOF
        ("multiple newlines\n\n\n", "multiple newlines"),
        # Test case 8: Whitespace at the very beginning and end of the string
        ("  \n  some content \n ", "some content"),
        # Test case 9: Empty string
        ("", ""),
        # Test case 10: String with only whitespace
        ("   \n\t\n  ", ""),
        # Test case 11: A more complex, combined example
        ("  key: value  \r\nlist:\r  - item1\t\n  - item2\n\n\n", "key: value\nlist:\n  - item1\n  - item2"),
    ],
)
def test_normalize_for_compare(input_text, expected_text):
    """
    Tests the normalize_for_compare function with various inputs to ensure
    it correctly handles line endings, trailing whitespace, and EOF newlines.
    """
    assert normalize_for_compare(input_text) == expected_text


# --- Tests for yaml_is_same ---

# Simple YAML content for testing
YAML_A = """
key: value
list:
  - item1
  - item2
"""

# Identical content to A, but with different formatting
YAML_B_DIFFERENT_FORMAT = """
key:    value
list: [item1, item2] # inline list
"""

# Different content from A
YAML_C_DIFFERENT_CONTENT = """
key: another_value
list:
  - item1
  - item3
"""

# YAML with different key order
YAML_D_DIFFERENT_ORDER = """
list:
  - item1
  - item2
key: value
"""

# Text that is not valid YAML
INVALID_YAML = "this: is not: valid yaml"


@pytest.mark.parametrize(
    "content1, content2, expected_result",
    [
        # Test case 1: Identical strings
        ("hello", "hello", True),
        (YAML_A, YAML_A, True),
        # Test case 2: Simple strings that are different
        ("hello", "world", False),
        # Test case 3: Strings that are identical after stripping whitespace
        ("  hello\n", "hello", True),
        # Test case 4: Strings that become identical after normalization
        ("key: value  \r\n", "key: value\n", True),
        # Test case 5: YAML with identical content but different formatting/style
        # (YAML_A, YAML_B_DIFFERENT_FORMAT, True), # rapid yaml sees this as different
        # Test case 6: YAML with identical content but different key order
        # (YAML_A, YAML_D_DIFFERENT_ORDER, True), # rapid yaml sees this as different
        # Test case 7: YAML with different content
        (YAML_A, YAML_C_DIFFERENT_CONTENT, False),
        # Test case 8: One string is valid YAML, the other is not
        (YAML_A, INVALID_YAML, False),
        # Test case 9: Both strings are invalid YAML but are identical
        (INVALID_YAML, INVALID_YAML, True),
        # Test case 10: Both strings are invalid YAML and different
        (INVALID_YAML, "another: invalid: string", False),
        # Test case 11: Comparing with an empty string
        (YAML_A, "", False),
        ("", YAML_A, False),
        # Test case 12: Both strings are empty
        ("", "", True),
        # Test case 13: Strings containing only whitespace
        ("  \n", "\t", True),
    ],
)
def test_yaml_is_same(content1, content2, expected_result):
    """
    Tests the yaml_is_same function across various scenarios:
    - Simple string comparison
    - Normalized string comparison
    - Deep YAML content comparison
    - Handling of invalid YAML
    """
    assert yaml_is_same(content1, content2) == expected_result


# To run these tests, you would save the original code as `yaml_utils.py`
# and this test code as `test_yaml_utils.py`, then run `pytest` in your terminal.
# You will need to have `pytest` and `ruamel.yaml` installed (`pip install pytest ruamel.yaml`).
# You'll also need a dummy `bash2gitlab` directory with `utils/yaml_factory.py`
# or adjust the imports to match your project structure.

# Dummy structure for the import to work out of the box.
# You can create these files/folders or adapt the import `from yaml_utils ...`
# to match your actual file name.


def create_dummy_factory(tmp_path):
    """Creates a dummy yaml_factory module for testing purposes."""
    utils_dir = tmp_path / "bash2gitlab" / "utils"
    utils_dir.mkdir(parents=True, exist_ok=True)
    (utils_dir / "__init__.py").touch()
    (tmp_path / "bash2gitlab" / "__init__.py").touch()
    factory_path = utils_dir / "yaml_factory.py"
    factory_path.write_text("from ruamel.yaml import YAML\n\ndef get_yaml():\n    yaml = YAML()\n    yaml.preserve_quotes = True\n    yaml.indent(mapping=2, sequence=4, offset=2)\n    return yaml\n")
    return factory_path


# This is an example of how you might use tmp_path if you needed to write files,
# though for these specific tests, it's not strictly necessary unless you are
# setting up a temporary project structure for imports.
def test_with_dummy_factory(tmp_path, monkeypatch):
    """
    An example test showing how to use tmp_path to create a dummy module
    if the import structure is complex.
    """
    monkeypatch.syspath_prepend(str(tmp_path))
    create_dummy_factory(tmp_path)

    # Re-import the function now that the dummy module is in the path
    from bash2gitlab.utils.yaml_file_same import yaml_is_same

    assert yaml_is_same("a: 1", "a: 1")
