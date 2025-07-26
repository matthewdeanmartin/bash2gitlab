from __future__ import annotations

from pathlib import Path

import pytest
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

from bash2gitlab.compile_all import extract_script_path, parse_env_file, process_uncompiled_directory

# Initialize YAML parser for checking output
yaml = YAML()


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


class TestProcessUncompiledDirectory:
    """Integration tests for the main directory processing function."""

    @pytest.fixture
    def setup_project_structure(self, tmp_path: Path):
        """Creates a realistic project structure within a temporary directory."""
        uncompiled_path = tmp_path / "uncompiled"
        scripts_path = uncompiled_path / "scripts"
        output_path = tmp_path / "output"
        templates_dir = uncompiled_path / "templates"
        output_templates_dir = output_path / "ci-templates"

        # Create directories
        for p in [uncompiled_path, scripts_path, output_path, templates_dir, output_templates_dir]:
            p.mkdir(parents=True, exist_ok=True)

        # --- Create Source Files ---

        # 1. Global Variables
        (uncompiled_path / "global_variables.sh").write_text(
            'export GLOBAL_VAR="GlobalValue"\n' 'PROJECT_NAME="MyProject"'
        )

        # 2. Scripts
        (scripts_path / "short_task.sh").write_text("echo 'Short task line 1'\n" "echo 'Short task line 2'")
        (scripts_path / "long_task.sh").write_text(
            "echo 'Line 1'\n" "echo 'Line 2'\n" "echo 'Line 3'\n" "echo 'Line 4 is too many'"
        )
        (scripts_path / "template_script.sh").write_text("echo 'From a template'")

        # 3. Root GitLab CI file
        (uncompiled_path / ".gitlab-ci.yml").write_text(
            """
include:
  - project: 'my-group/my-project'
    ref: main
    file: '/templates/.gitlab-ci-template.yml'

variables:
  LOCAL_VAR: "LocalValue"

stages:
  - build
  - test
  - deploy

before_script:
  - bash ./short_task.sh

build_job:
  stage: build
  script:
    - echo "Building..."
    - bash ./long_task.sh
    - echo "Build finished."

test_job:
  stage: test
  script:
    - echo "Testing..."
    - bash ./short_task.sh
"""
        )

        # 4. Template CI file
        (templates_dir / "backend.yml").write_text(
            """
template_job:
  image: alpine
  script:
    - bash ./template_script.sh
"""
        )
        return uncompiled_path, output_path, scripts_path, templates_dir, output_templates_dir

    def test_full_processing(self, setup_project_structure):
        """
        Tests the end-to-end processing of a directory structure,
        verifying inlining, variable merging, and file output.
        """
        uncompiled_path, output_path, scripts_path, templates_dir, output_templates_dir = setup_project_structure

        # --- Run the main function ---
        process_uncompiled_directory(uncompiled_path, output_path, scripts_path, templates_dir, output_templates_dir)

        # --- Assertions for Root .gitlab-ci.yml ---
        output_ci_file = output_path / ".gitlab-ci.yml"
        assert output_ci_file.exists()

        data = yaml.load(output_ci_file)

        # Check key order
        expected_order = ["include", "variables", "stages", "before_script", "build_job", "test_job"]
        assert list(data.keys()) == expected_order

        # Check merged variables
        assert data["variables"]["GLOBAL_VAR"] == "GlobalValue"
        assert data["variables"]["PROJECT_NAME"] == "MyProject"
        assert data["variables"]["LOCAL_VAR"] == "LocalValue"

        # Check inlined top-level before_script
        assert data["before_script"] == [
            "echo 'Short task line 1'",
            "echo 'Short task line 2'",
        ]

        # Check build_job (long script becomes literal block)
        build_script = data["build_job"]["script"]
        assert isinstance(build_script, LiteralScalarString)
        assert build_script.strip() == (scripts_path / "long_task.sh").read_text().strip()

        # Check test_job (short script is inlined)
        assert data["test_job"]["script"] == [
            'echo "Testing..."',
            "echo 'Short task line 1'",
            "echo 'Short task line 2'",
        ]

        # --- Assertions for Template File ---
        output_template_file = output_templates_dir / "backend.yml"
        assert output_template_file.exists()
        template_data = yaml.load(output_template_file)

        # Global variables should NOT be in templates
        assert "variables" not in template_data
        assert template_data["template_job"]["script"] == ["echo 'From a template'"]
