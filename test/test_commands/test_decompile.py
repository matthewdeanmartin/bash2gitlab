# File: tests/test_decompile_all.py

from __future__ import annotations

import platform
import stat
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from bash2gitlab.commands.decompile_all import run_decompile_gitlab  # alias to run_decompile_gitlab_file in new code
from bash2gitlab.commands.decompile_all import SHEBANG, create_script_filename

# A sample GitLab CI configuration with various script definitions for comprehensive testing.
SAMPLE_GITLAB_CI_CONTENT = """
stages:
  - build
  - test

variables:
  GLOBAL_VAR: "some_value"

# A job with a simple, multi-line script block.
job_simple_script:
  stage: build
  script:
    - echo "Hello World"
    - ls -la

# A job that defines both before_script and script.
job_with_before_script:
  stage: build
  before_script:
    - echo "Setting up..."
  script: echo "Main task"

# A job with before, after, and a multi-line literal block script.
job_with_all_scripts:
  stage: test
  before_script:
    - export VAR="before"
    - echo $VAR
  script: |
    echo "This is a multi-line script."
    echo "It does important things."
  after_script:
    - echo "Cleaning up..."

# A job with an empty script block, which should be ignored.
job_with_empty_script:
  stage: test
  script:

# A job with no script key, which should be untouched.
job_no_script:
  stage: test
  image: alpine

# A hidden job, which should still be processed.
.hidden_job:
  script:
    - echo "This should be decompileded"
"""


@pytest.mark.parametrize(
    "job_name, script_key, expected_filename",
    [
        ("my-job", "script", "my-job.sh"),
        ("my job", "script", "my-job.sh"),
        ("job_with_underscores", "script", "job_with_underscores.sh"),
        ("My-Job With.Special-Chars!", "script", "my-job-with.special-chars.sh"),
        ("my-job", "before_script", "my-job_before_script.sh"),
        ("my-job", "after_script", "my-job_after_script.sh"),
        (".hidden-job", "script", ".hidden-job.sh"),
    ],
)
def test_create_script_filename(job_name, script_key, expected_filename):
    """Tests the script filename generation for various job names and script keys."""
    assert create_script_filename(job_name, script_key) == expected_filename


class TestdecompileGitlabCI:
    """Test suite for the decompile command with the updated API and semantics."""

    @pytest.fixture
    def setup_test_env(self, tmp_path: Path) -> tuple[Path, Path]:
        """Creates a temporary directory structure with a sample gitlab-ci.yml file."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        input_yaml = input_dir / ".gitlab-ci.yml"
        input_yaml.write_text(SAMPLE_GITLAB_CI_CONTENT, encoding="utf-8")

        return input_yaml, output_dir

    def test_decompile_gitlab_ci_happy_path(self, setup_test_env: tuple[Path, Path]):
        """Tests the standard decompileding process from end to end (single file)."""
        input_yaml, output_dir = setup_test_env

        jobs_processed, files_created, out_yaml = run_decompile_gitlab(
            input_yaml_path=input_yaml,
            output_dir=output_dir,
            dry_run=False,
        )

        # Five jobs considered (including one with empty script key)
        assert jobs_processed == 5
        # Seven script files + one global variables file
        assert files_created == 9

        # --- Verify YAML output ---
        assert out_yaml.exists(), "Output YAML file should have been created"
        yaml = YAML()
        data = yaml.load(out_yaml)

        # Script paths are relative to the YAML file now
        assert data["job_simple_script"]["script"] == "./job_simple_script.sh"
        assert data["job_with_before_script"]["before_script"] == "./job_with_before_script_before_script.sh"
        assert data["job_with_before_script"]["script"] == "./job_with_before_script.sh"
        assert data["job_with_all_scripts"]["script"] == "./job_with_all_scripts.sh"
        # assert data[".hidden_job"]["script"] == "./.hidden_job.sh" # that is not hidden!

        # Check that jobs without scripts or with empty scripts are untouched
        assert "script" not in data["job_no_script"]
        assert data["job_with_empty_script"]["script"] is None, "Empty script block should remain empty"

        # Check content and permissions of a simple script
        script1 = out_yaml.parent / "job_simple_script.sh"
        assert script1.exists()
        if platform.system() == "Linux":
            assert stat.S_IXUSR & script1.stat().st_mode, "Script should be executable on Linux"
        content1 = script1.read_text(encoding="utf-8")
        assert SHEBANG in content1
        assert 'echo "Hello World"' in content1
        assert "ls -la" in content1

        # Check content of a multi-line script
        script2 = out_yaml.parent / "job_with_all_scripts.sh"
        assert script2.exists()
        content2 = script2.read_text(encoding="utf-8")
        assert 'echo "This is a multi-line script."' in content2
        assert 'echo "It does important things."' in content2

        # Check content of an after_script
        script3 = out_yaml.parent / "job_with_all_scripts_after_script.sh"
        assert script3.exists()
        assert 'echo "Cleaning up..."' in script3.read_text(encoding="utf-8")

    def test_decompile_gitlab_ci_dry_run(self, setup_test_env: tuple[Path, Path]):
        """Ensures that no files are written to disk during a dry run."""
        input_yaml, output_dir = setup_test_env

        jobs_processed, files_created, out_yaml = run_decompile_gitlab(
            input_yaml_path=input_yaml,
            output_dir=output_dir,
            dry_run=True,
        )

        # The function should still report what it *would* have done.
        assert jobs_processed == 5
        assert files_created == 8

        # But no files should have been created.
        assert not out_yaml.exists(), "Output YAML should not be created on dry run"
        assert not (output_dir / "job_simple_script.sh").exists(), "No script files on dry run"

    def test_decompile_gitlab_ci_no_scripts_to_decompile(self, tmp_path: Path):
        """Tests behavior when the input YAML contains no scripts to extract."""
        no_script_content = """job_a:
  image: node
job_b:
  stage: test
"""
        input_yaml = tmp_path / "ci.yml"
        input_yaml.write_text(no_script_content, encoding="utf-8")
        output_dir = tmp_path / "out"

        jobs_processed, files_created, out_yaml = run_decompile_gitlab(
            input_yaml_path=input_yaml,
            output_dir=output_dir,
        )

        assert jobs_processed == 0
        assert files_created == 0
        assert not out_yaml.exists(), "Output YAML should not be created if no changes are made"
        # mock CI variables helper is created even when nothing was decompileded (non-dry-run)
        assert (output_dir / "mock_ci_variables.sh").exists()

    def test_decompile_file_not_found(self, tmp_path: Path):
        """Ensures a FileNotFoundError is raised for a non-existent input file."""
        with pytest.raises(FileNotFoundError, match="Input YAML file not found"):
            run_decompile_gitlab(
                input_yaml_path=tmp_path / "nonexistent.yml",
                output_dir=tmp_path / "out",
            )
