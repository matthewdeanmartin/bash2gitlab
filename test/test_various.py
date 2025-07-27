from __future__ import annotations

from pathlib import Path

import pytest
from ruamel.yaml.scalarstring import LiteralScalarString

import bash2gitlab.compile_all as compile_all

# --- Fixtures ---


@pytest.fixture
def script_sources_fixture():
    """Provides a sample dictionary of script sources for testing."""
    return {
        "scripts/short_script.sh": "echo 'hello world'",
        "scripts/multiline_short.sh": "echo 'line 1'\necho 'line 2'\necho 'line 3'",
        "scripts/long_script.sh": "echo 'line 1'\necho 'line 2'\necho 'line 3'\necho 'line 4'",
        "scripts/empty.sh": "",
    }


# --- Unit Tests for Core Logic Functions ---


@pytest.mark.parametrize(
    "file_content, expected",
    [
        ("KEY=VALUE", {"KEY": "VALUE"}),
        ("export KEY=VALUE", {"KEY": "VALUE"}),
        ('KEY="A value with spaces"', {"KEY": "A value with spaces"}),
        ("KEY='Another value'", {"KEY": "Another value"}),
        ("  KEY=VALUE  ", {"KEY": "VALUE"}),
        ("# This is a comment\nKEY=VALUE", {"KEY": "VALUE"}),
        ("INVALID-KEY=value", {}),
        ("_KEY=valid", {"_KEY": "valid"}),
        ("KEY=value # inline comment", {"KEY": "value # inline comment"}),  # shlex behavior
        ("export KEY_1=one\nKEY_2=two", {"KEY_1": "one", "KEY_2": "two"}),
        ("", {}),
    ],
)
def test_parse_env_file(file_content, expected):
    """Tests parsing of .env-style variable files."""
    assert compile_all.parse_env_file(file_content) == expected


@pytest.mark.parametrize(
    "command_line, expected",
    [
        ("./scripts/run.sh --arg1", None),
        ("bash ./scripts/run.sh", "scripts/run.sh"),
        ("  source   scripts/run.sh  ", "scripts/run.sh"),
        ("sh scripts/run.sh", "scripts/run.sh"),
        ("echo 'not a script'", None),
        ("python run_script.py", None),
        ("malformed ' command", None),
        ("scripts/run.sh", "scripts/run.sh"),  # without executor
        ("do_something && ./my.sh", None),  # shlex will split this
    ],
)
def test_extract_script_path(command_line, expected):
    """Tests the extraction of script paths from command lines."""
    assert compile_all.extract_script_path(command_line) == expected


def test_read_bash_script_not_found(script_sources_fixture):
    """Tests that FileNotFoundError is raised for a missing script."""
    with pytest.raises(FileNotFoundError):
        compile_all.read_bash_script(Path("nonexistent.sh"), script_sources_fixture)


def test_process_script_list_no_scripts():
    """Tests a list with no scripts to ensure it remains unchanged."""
    script_list = ["echo 'hello'", "ls -la"]
    result = compile_all.process_script_list(script_list, Path("."), {})
    assert result == script_list


def test_process_script_list_already_literal():
    """Tests that a pre-existing LiteralScalarString is passed through."""
    literal = LiteralScalarString("some existing script")
    result = compile_all.process_script_list(literal, Path("."), {})
    assert result == [literal]


def test_collect_script_sources(tmp_path: Path):
    """Tests the recursive collection of script sources."""
    scripts_dir = tmp_path / "scripts"
    (scripts_dir / "subdir").mkdir(parents=True)
    (scripts_dir / "script1.sh").write_text("content1")
    (scripts_dir / "subdir" / "script2.sh").write_text("content2")
    (scripts_dir / "empty.sh").write_text("  ")  # whitespace only
    (scripts_dir / "not_a_script.txt").write_text("ignore me")

    sources = compile_all.collect_script_sources(scripts_dir)
    assert str(scripts_dir / "script1.sh") in sources
    assert str(scripts_dir / "subdir" / "script2.sh") in sources
    assert sources[str(scripts_dir / "script1.sh")] == "content1"
    assert sources[str(scripts_dir / "subdir" / "script2.sh")] == "content2"
    assert len(sources) == 2  # empty.sh should be ignored


def test_collect_script_sources_not_found():
    """Tests error handling when the scripts directory doesn't exist."""
    with pytest.raises(FileNotFoundError):
        compile_all.collect_script_sources(Path("nonexistent/dir"))


def test_collect_script_sources_no_scripts(tmp_path: Path):
    """Tests error handling when no non-empty scripts are found."""
    (tmp_path / "scripts").mkdir()
    with pytest.raises(RuntimeError, match="No non-empty scripts found"):
        compile_all.collect_script_sources(tmp_path / "scripts")


# test_inline_bash_to_yaml.py


# --- Fixtures ---


@pytest.fixture
def sample_gitlab_ci_yaml():
    """Provides a sample GitLab CI YAML content as a string."""
    return """
test_job_short:
  script:
    - echo "Running a short script"
    - ./scripts/short_test.sh
    - echo "Done"

test_job_long:
  script:
    - ./scripts/long_test.sh

job_with_no_script:
  image: alpine

job_with_non_list_script:
  script: "echo 'hello'"

another_job:
  script:
    - ls -la
"""


@pytest.fixture
def script_sources_dict():
    """Provides a dictionary of script paths to contents for mocking."""
    return {
        "./scripts/short_test.sh": "echo 'line 1'\necho 'line 2'",
        "./scripts/long_test.sh": "line 1\nline 2\nline 3\nline 4",
    }


# --- Tests for inline_bash_to_yaml.py ---


# def test_inline_short_script(sample_gitlab_ci_yaml, script_sources_dict):
#     """
#     Tests that a short script (<= 3 lines) is correctly inlined into a list.
#     """
#     result_yaml = inline_bash_to_yaml.inline_gitlab_scripts(sample_gitlab_ci_yaml, script_sources_dict)
#
#     yaml = inline_bash_to_yaml.YAML()
#     data = yaml.load(result_yaml)
#
#     # Check the job with the short script
#     script_content = data["test_job_short"]["script"]
#     expected_script = [
#         'echo "Running a short script"',
#         "echo 'line 1'",
#         "echo 'line 2'",
#         'echo "Done"',
#     ]
#     assert script_content == expected_script
#     # Final check to ensure no file references remain
#     assert not any(".sh" in line for line in script_content)


# def test_no_change_for_unaffected_jobs(sample_gitlab_ci_yaml, script_sources_dict):
#     """
#     Tests that jobs without script references or with non-list scripts are unchanged.
#     """
#     result_yaml = inline_bash_to_yaml.inline_gitlab_scripts(sample_gitlab_ci_yaml, script_sources_dict)
#
#     yaml = inline_bash_to_yaml.YAML()
#     data = yaml.load(result_yaml)
#
#     # This job should be exactly as it was
#     assert data["another_job"]["script"] == ["ls -la"]
#     # This job's script should also be unchanged
#     assert data["job_with_non_list_script"]["script"] == "echo 'hello'"
#     # This job has no script key at all
#     assert "script" not in data["job_with_no_script"]


# def test_read_from_filesystem(tmp_path):
#     """
#     Tests that the script reader can fall back to the filesystem if
#     script_sources is not provided.
#     """
#     # Setup a script file on the temporary filesystem
#     script_dir = tmp_path / "scripts"
#     script_dir.mkdir()
#     script_path = script_dir / "file_script.sh"
#     script_path.write_text("echo 'hello from file'")
#
#     # Create a gitlab-ci.yml that references this file
#     # Note: The path in the YAML must be relative to where the script would run
#     # so we use a relative path. The test will run from tmp_path.
#
#     # We need to create the file in the root of tmp_path for the relative path to work
#     file_script_path_for_yaml = "./file_script.sh"
#     (tmp_path / "file_script.sh").write_text("echo 'hello from file'")
#
#     gitlab_ci_content = f"""
#     file_job:
#       script:
#         - {file_script_path_for_yaml}
#     """
#
#     # Change cwd to tmp_path so the relative file path can be found
#     import os
#
#     original_cwd = os.getcwd()
#     os.chdir(tmp_path)
#
#     try:
#         # Run the inliner without providing script_sources
#         result_yaml = inline_bash_to_yaml.inline_gitlab_scripts(gitlab_ci_content)
#
#         yaml = inline_bash_to_yaml.YAML()
#         data = yaml.load(result_yaml)
#
#         # Check that the script was inlined from the file
#         assert data["file_job"]["script"] == ["echo 'hello from file'"]
#     finally:
#         # IMPORTANT: Change back to the original directory
#         os.chdir(original_cwd)
