from __future__ import annotations

import platform
import stat
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from bash2gitlab.shred_all import SHEBANG, create_script_filename, shred_gitlab_ci

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
    - echo "This should be shredded"
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


class TestShredGitlabCI:
    """Test suite for the main shred_gitlab_ci function."""

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

    def test_shred_gitlab_ci_happy_path(self, setup_test_env: tuple[Path, Path]):
        """Tests the standard shredding process from end to end."""
        input_yaml, output_dir = setup_test_env
        output_yaml = output_dir / ".gitlab-ci.yml"
        scripts_output_path = output_dir / "scripts"

        jobs_processed, scripts_created = shred_gitlab_ci(
            input_yaml_path=input_yaml,
            output_yaml_path=output_yaml,
            scripts_output_path=scripts_output_path,
            dry_run=False,
        )

        # Four jobs have scripts: job_simple_script, job_with_before_script, job_with_all_scripts, .hidden_job
        assert jobs_processed == 5
        # Five script blocks in total should be extracted.
        assert scripts_created == 7

        # --- Verify YAML output ---
        assert output_yaml.exists(), "Output YAML file should have been created"
        yaml = YAML()
        data = yaml.load(output_yaml)

        assert data["job_simple_script"]["script"] == "./scripts/job_simple_script.sh"
        assert data["job_with_before_script"]["before_script"] == "./scripts/job_with_before_script_before_script.sh"
        assert data["job_with_before_script"]["script"] == "./scripts/job_with_before_script.sh"
        assert data["job_with_all_scripts"]["script"] == "./scripts/job_with_all_scripts.sh"
        assert data[".hidden_job"]["script"] == "./scripts/.hidden_job.sh"

        # Check that jobs without scripts or with empty scripts are untouched
        assert "script" not in data["job_no_script"]
        assert data["job_with_empty_script"]["script"] is None, "Empty script block should remain empty"

        # --- Verify script files ---
        assert scripts_output_path.is_dir()

        # Check content and permissions of a simple script
        script1 = scripts_output_path / "job_simple_script.sh"
        assert script1.exists()
        if platform.system() == "Linux":
            assert stat.S_IXUSR & script1.stat().st_mode, "Script should be executable"
        content1 = script1.read_text(encoding="utf-8")
        assert SHEBANG in content1
        assert 'echo "Hello World"' in content1
        assert "ls -la" in content1

        # Check content of a multi-line script
        script2 = scripts_output_path / "job_with_all_scripts.sh"
        assert script2.exists()
        content2 = script2.read_text(encoding="utf-8")
        assert 'echo "This is a multi-line script."' in content2
        assert 'echo "It does important things."' in content2

        # Check content of an after_script
        script3 = scripts_output_path / "job_with_all_scripts_after_script.sh"
        assert script3.exists()
        assert 'echo "Cleaning up..."' in script3.read_text(encoding="utf-8")

    def test_shred_gitlab_ci_dry_run(self, setup_test_env: tuple[Path, Path]):
        """Ensures that no files are written to disk during a dry run."""
        input_yaml, output_dir = setup_test_env
        output_yaml = output_dir / ".gitlab-ci.yml"
        scripts_output_path = output_dir / "scripts"

        jobs_processed, scripts_created = shred_gitlab_ci(
            input_yaml_path=input_yaml,
            output_yaml_path=output_yaml,
            scripts_output_path=scripts_output_path,
            dry_run=True,
        )

        # The function should still report what it *would* have done.
        assert jobs_processed == 5
        assert scripts_created == 7

        # But no files or directories should have been created.
        assert not output_yaml.exists(), "Output YAML should not be created on dry run"
        assert not scripts_output_path.exists(), "Scripts directory should not be created on dry run"

    def test_shred_gitlab_ci_no_scripts_to_shred(self, tmp_path: Path):
        """Tests behavior when the input YAML contains no scripts to extract."""
        no_script_content = "job_a:\n  image: node\njob_b:\n  stage: test\n"
        input_yaml = tmp_path / "ci.yml"
        input_yaml.write_text(no_script_content, encoding="utf-8")
        output_yaml = tmp_path / "output.yml"
        scripts_output_path = tmp_path / "scripts"

        jobs_processed, scripts_created = shred_gitlab_ci(
            input_yaml_path=input_yaml,
            output_yaml_path=output_yaml,
            scripts_output_path=scripts_output_path,
        )

        assert jobs_processed == 0
        assert scripts_created == 0
        assert not output_yaml.exists(), "Output YAML should not be created if no changes are made"
        assert not scripts_output_path.exists()

    def test_shred_file_not_found(self, tmp_path: Path):
        """Ensures a FileNotFoundError is raised for a non-existent input file."""
        with pytest.raises(FileNotFoundError, match="Input YAML file not found"):
            shred_gitlab_ci(
                input_yaml_path=tmp_path / "nonexistent.yml",
                output_yaml_path=tmp_path / "output.yml",
                scripts_output_path=tmp_path / "scripts",
            )
