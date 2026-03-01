import base64
from pathlib import Path
from unittest.mock import patch

import pytest
import ruamel.yaml
from ruamel.yaml import CommentedSeq
from ruamel.yaml.scalarstring import LiteralScalarString

from bash2gitlab.commands.compile_all import (
    as_items,
    compact_runs_to_literal,
    compile_single_file,
    get_banner,
    has_must_inline_pragma,
    infer_cli,
    inline_gitlab_scripts,
    process_job,
    process_script_list,
    rebuild_seq_like,
    run_compile_all,
    write_compiled_file,
    write_yaml_and_hash,
)
from bash2gitlab.errors.exceptions import Bash2GitlabError, ValidationFailed
from bash2gitlab.utils.temp_env import temporary_env_var


@pytest.fixture
def mock_config():
    with patch("bash2gitlab.commands.compile_all.config") as mock_config:
        mock_config.custom_header = None
        yield mock_config


@pytest.fixture
def mock_logger():
    with patch("bash2gitlab.commands.compile_all.logger") as mock_logger:
        yield mock_logger


@pytest.fixture
def yaml_instance():
    yaml = ruamel.yaml.YAML()
    yaml.preserve_quotes = True
    return yaml


def test_infer_cli():
    input_dir = Path("/path/to/input")
    output_path = Path("/path/to/output")

    # Test without optional params
    result = infer_cli(input_dir, output_path)
    assert "bash2gitlab compile" in result
    for part in ["--in", "path", "to", "input"]:
        assert part in result

    for part in ["--out", "path", "to", "output"]:
        assert part in result

    # Test with dry_run
    result = infer_cli(input_dir, output_path, dry_run=True)
    assert " --dry-run" in result

    # Test with parallelism
    result = infer_cli(input_dir, output_path, parallelism=4)
    assert " --parallelism 4" in result


def test_get_banner(mock_config):
    mock_config.custom_header = None
    inferred_cli = "bash2gitlab compile --in test --out test"

    result = get_banner(inferred_cli)
    assert "DO NOT EDIT" in result
    assert "bash2gitlab" in result
    assert inferred_cli in result

    # Test with custom header
    mock_config.custom_header = "Custom Header\nLine 2"
    result = get_banner(inferred_cli)
    assert result == "Custom Header\nLine 2\n"


def test_as_items():
    # Test with string
    items, was_commented, orig_seq = as_items("test string")
    assert items == ["test string"]
    assert was_commented is False
    assert orig_seq is None

    # Test with list
    test_list = ["item1", "item2"]
    items, was_commented, orig_seq = as_items(test_list)
    assert items == test_list
    assert was_commented is False
    assert orig_seq is None

    # Test with CommentedSeq
    seq = CommentedSeq(["item1", "item2"])
    items, was_commented, orig_seq = as_items(seq)
    assert items == ["item1", "item2"]
    assert was_commented is True
    assert orig_seq == seq


def test_rebuild_seq_like():
    processed = ["item1", "item2"]

    # Test with non-commented seq
    result = rebuild_seq_like(processed, False, None)
    assert result == processed

    # Test with commented seq
    orig_seq = CommentedSeq(["old1", "old2"])
    result = rebuild_seq_like(processed, True, orig_seq)
    assert isinstance(result, CommentedSeq)
    assert list(result) == processed


def test_compact_runs_to_literal():
    # Test with consecutive strings
    items = ["line1", "line2", "line3"]
    result = compact_runs_to_literal(items)
    assert len(result) == 1
    assert isinstance(result[0], LiteralScalarString)
    assert str(result[0]) == "line1\nline2\nline3"

    # Test with PlainScalarString (subclass of str but not TaggedScalar)
    # PlainScalarString is treated as a plain string and merged with neighbors
    tagged_scalar = ruamel.yaml.scalarstring.PlainScalarString("tagged")
    items = ["line1", tagged_scalar, "line2"]
    result = compact_runs_to_literal(items)
    assert len(result) == 1
    assert isinstance(result[0], LiteralScalarString)
    assert str(result[0]) == "line1\ntagged\nline2"


def test_process_script_list_basic(mock_logger, tmp_path):
    # Test with simple string
    result = process_script_list("echo hello", tmp_path)
    assert result == ["echo hello"]

    # Test with list
    script_list = ["echo hello", "echo world"]
    result = process_script_list(script_list, tmp_path)
    assert isinstance(result, LiteralScalarString)
    assert str(result) == "echo hello\necho world"


def test_process_script_list_with_script_file(mock_logger, tmp_path):
    with temporary_env_var("BASH2GITLAB_SKIP_ROOT_CHECKS", "1"):
        # Create a test script file
        script_file = tmp_path / "test.sh"
        script_file.write_text("echo 'test script'\necho 'second line'")

        # Test script reference
        script_list = [f"./{script_file.name}"]
        result = process_script_list(script_list, tmp_path)

        assert isinstance(result, str)
        assert "BEGIN inline" in result
        assert "test script" in result


def test_process_job(tmp_path):
    with temporary_env_var("BASH2GITLAB_SKIP_ROOT_CHECKS", "1"):
        job_data = {
            "script": ["echo hello", "echo world"],
            "before_script": ["setup.sh"],
            "after_script": ["cleanup.sh"],
        }

        # Create mock script files
        (tmp_path / "setup.sh").write_text("echo setting up")
        (tmp_path / "cleanup.sh").write_text("echo cleaning up")

        found = process_job(job_data, tmp_path)
        assert found > 0
        assert "BEGIN inline" in str(job_data["before_script"])
        assert "BEGIN inline" in str(job_data["after_script"])


def test_has_must_inline_pragma():
    # Test with list containing pragma
    assert has_must_inline_pragma(["# pragma must-inline"])
    assert has_must_inline_pragma(["some content", "# pragma MUST-INLINE"])

    # Test with string containing pragma
    assert has_must_inline_pragma("# pragma must-inline content")

    # Test without pragma
    assert not has_must_inline_pragma(["regular content"])
    assert not has_must_inline_pragma("regular string")


def test_inline_gitlab_scripts_basic(tmp_path):
    yaml_content = """
test-job:
  script:
    - echo hello
    - echo world
"""

    inlined_count, result = inline_gitlab_scripts(yaml_content, tmp_path, {}, tmp_path)
    # assert inlined_count == 0
    assert "test-job" in result
    assert "echo hello" in result


def test_inline_gitlab_scripts_with_global_vars(tmp_path):
    """Test that global variables are merged with YAML-defined variables.

    Precedence: YAML-defined variables override global variables with the same name.
    """
    yaml_content = """
variables:
  EXISTING_VAR: existing

test-job:
  script:
    - echo hello
"""

    global_vars = {"GLOBAL_VAR": "value", "EXISTING_VAR": "overridden"}
    inlined_count, result = inline_gitlab_scripts(yaml_content, tmp_path, global_vars, tmp_path)

    assert inlined_count == 0
    # Global var should be added
    assert "GLOBAL_VAR: value" in result
    # YAML-defined variable should win over global (per code at compile_all.py:336-339)
    assert "EXISTING_VAR: existing" in result
    assert "EXISTING_VAR: overridden" not in result


def test_write_yaml_and_hash(tmp_path, mock_logger):
    output_file = tmp_path / "test.yml"
    hash_file = tmp_path / "test.yml.hash"
    content = "test: value\n"

    with patch("bash2gitlab.commands.compile_all.GitLabCIValidator") as mock_validator:
        mock_instance = mock_validator.return_value
        mock_instance.validate_ci_config.return_value = (True, [])

        write_yaml_and_hash(output_file, content, hash_file)

        assert output_file.exists()
        assert hash_file.exists()
        assert output_file.read_text().strip(" \n") == content.strip(" \n")

        # Verify hash content
        encoded = base64.b64encode(content.strip(" \n").encode()).decode()
        assert hash_file.read_text() == encoded


def test_write_yaml_and_hash_validation_failed(tmp_path):
    output_file = tmp_path / "test.yml"
    hash_file = tmp_path / "test.yml.hash"
    content = "invalid: yaml\n"

    with patch("bash2gitlab.commands.compile_all.GitLabCIValidator") as mock_validator:
        mock_instance = mock_validator.return_value
        mock_instance.validate_ci_config.return_value = (False, ["validation error"])

        with pytest.raises(ValidationFailed):
            write_yaml_and_hash(output_file, content, hash_file)

        assert not output_file.exists()
        assert not hash_file.exists()


def test_write_compiled_file_new_file(tmp_path, mock_logger):
    output_file = tmp_path / "test.yml"
    content = "test: content\n"

    with patch("bash2gitlab.commands.compile_all.GitLabCIValidator") as mock_validator:
        mock_instance = mock_validator.return_value
        mock_instance.validate_ci_config.return_value = (True, [])

        result = write_compiled_file(output_file, content, dry_run=False)
        assert result is True
        assert output_file.exists()


def test_write_compiled_file_dry_run(tmp_path, mock_logger):
    output_file = tmp_path / "test.yml"
    content = "test: content\n"

    result = write_compiled_file(output_file, content, dry_run=True)
    assert result is True
    assert not output_file.exists()


def test_write_compiled_file_existing_no_changes(tmp_path, mock_logger):
    output_file = tmp_path / "test.yml"
    hash_file = tmp_path / "test.yml.hash"
    content = "test: content\n"

    # Create existing files
    output_file.write_text(content)
    encoded = base64.b64encode(content.encode()).decode()
    hash_file.write_text(encoded)

    with patch("bash2gitlab.commands.compile_all.yaml_is_same", return_value=True):
        result = write_compiled_file(output_file, content, dry_run=False)
        assert result is False


def test_compile_single_file(tmp_path, mock_logger):
    source_path = tmp_path / "source.yml"
    output_file = tmp_path / "output.yml"
    scripts_path = tmp_path
    input_dir = tmp_path

    source_content = """
test-job:
  script:
    - echo hello
"""
    source_path.write_text(source_content)

    with patch("bash2gitlab.commands.compile_all.inline_gitlab_scripts") as mock_inline:
        mock_inline.return_value = (1, "compiled content")
        with patch("bash2gitlab.commands.compile_all.write_compiled_file") as mock_write:
            mock_write.return_value = True

            inlined, written = compile_single_file(
                source_path, output_file, scripts_path, {}, input_dir, False, "test command"
            )

            assert inlined == 1
            assert written == 1
            mock_inline.assert_called_once()
            mock_write.assert_called_once()


def test_run_compile_all_no_changes(tmp_path, mock_logger):
    with patch("bash2gitlab.commands.compile_all.needs_compilation") as mock_needs:
        mock_needs.return_value = False

        result = run_compile_all(tmp_path, tmp_path, force=False)
        assert result == 0


def test_run_compile_all_with_force(tmp_path, mock_logger):
    with patch("bash2gitlab.commands.compile_all.needs_compilation") as mock_needs:
        mock_needs.return_value = False
        with patch("bash2gitlab.commands.compile_all.report_targets") as mock_report:
            mock_report.return_value = []
            with patch("bash2gitlab.commands.compile_all.compile_single_file") as mock_compile:
                mock_compile.return_value = (1, 1)

                result = run_compile_all(tmp_path, tmp_path, force=True)
                assert result == 0  # No files to process in empty directory


def test_run_compile_all_with_files(tmp_path, mock_logger):
    # Create test YAML files
    yaml_file = tmp_path / "test.yml"
    yaml_file.write_text("test: content")

    with patch("bash2gitlab.commands.compile_all.needs_compilation") as mock_needs:
        mock_needs.return_value = True
        with patch("bash2gitlab.commands.compile_all.report_targets") as mock_report:
            mock_report.return_value = []
            with patch("bash2gitlab.commands.compile_all.compile_single_file") as mock_compile:
                mock_compile.return_value = (2, 1)
                with patch("bash2gitlab.commands.compile_all.mark_compilation_complete") as mock_mark:
                    result = run_compile_all(tmp_path, tmp_path, force=False)
                    assert result == 2
                    mock_mark.assert_called_once()


def test_process_script_list_error_handling(tmp_path):
    """Test that missing script files raise Bash2GitlabError with appropriate message."""
    script_list = ["./nonexistent.sh"]

    with pytest.raises(Bash2GitlabError) as exc_info:
        process_script_list(script_list, tmp_path)

    # Behavior: exception should contain information about the missing file
    assert "nonexistent.sh" in str(exc_info.value)


def test_inline_gitlab_scripts_job_variables(tmp_path):
    """Test that job-specific variables are loaded from job_name_variables.sh file."""
    # Create job variables file - note: job name "test-job" becomes "test-job_variables.sh"
    job_vars_file = tmp_path / "test-job_variables.sh"
    job_vars_file.write_text("JOB_VAR=job_value\nANOTHER_VAR=another_value")

    yaml_content = """
test-job:
  variables:
    EXISTING_VAR: existing
  script:
    - echo hello
"""

    inlined_count, result = inline_gitlab_scripts(yaml_content, tmp_path, {}, tmp_path)

    # Behavior: job-specific variables should be merged into the job
    assert "JOB_VAR: job_value" in result
    assert "ANOTHER_VAR: another_value" in result
    assert "EXISTING_VAR: existing" in result


def test_compact_runs_to_literal_edge_cases():
    # Test empty list
    assert compact_runs_to_literal([]) == []

    # Test single item
    assert compact_runs_to_literal(["single"]) == ["single"]


def test_as_items_edge_cases():
    # Test empty string
    items, was_commented, orig_seq = as_items("")
    assert items == [""]

    # Test empty list
    items, was_commented, orig_seq = as_items([])
    assert items == []

    # Test empty CommentedSeq
    empty_seq = CommentedSeq([])
    items, was_commented, orig_seq = as_items(empty_seq)
    assert items == []
    assert was_commented is True
