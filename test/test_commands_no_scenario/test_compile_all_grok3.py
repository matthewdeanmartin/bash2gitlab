import logging
import sys
from pathlib import Path

import pytest

from bash2gitlab.commands.compile_all import infer_cli, run_compile_all
from bash2gitlab.errors.exceptions import CompileError, ValidationFailed
from bash2gitlab.utils.temp_env import temporary_env_var

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@pytest.fixture
def setup_dirs(tmp_path: Path):
    """Set up input and output directories with a simple .gitlab-ci.yml and script."""
    uncompiled_dir = tmp_path / "uncompiled"
    output_dir = tmp_path / "output"
    uncompiled_dir.mkdir()
    output_dir.mkdir()

    # Create a simple .gitlab-ci.yml with one script reference
    yaml_content = """
stages:
  - test
my_job:
  stage: test
  script:
    - ./script.sh
"""
    yaml_file = uncompiled_dir / ".gitlab-ci.yml"
    yaml_file.write_text(yaml_content, encoding="utf-8")

    # Create a simple script.sh
    script_content = """#!/bin/bash
echo "Hello, World!"
"""
    script_file = uncompiled_dir / "script.sh"
    script_file.write_text(script_content, encoding="utf-8")

    return uncompiled_dir, output_dir, yaml_file, script_file


def test_compile_single_script_reference(setup_dirs: tuple[Path, Path, Path, Path]):
    """Test compiling a .gitlab-ci.yml with a single script reference."""
    with temporary_env_var("BASH2GITLAB_SKIP_ROOT_CHECKS", "1"):
        uncompiled_dir, output_dir, yaml_file, script_file = setup_dirs
        output_file = output_dir / ".gitlab-ci.yml"

        # Run the compilation
        inlined_count = run_compile_all(
            uncompiled_path=uncompiled_dir, output_path=output_dir, dry_run=False, force=True
        )

        # Assertions
        assert inlined_count == 1, "Expected one section to be inlined"
        assert output_file.exists(), "Output file should be created"

        # Read and verify the output content
        compiled_content = output_file.read_text(encoding="utf-8")
        assert "# DO NOT EDIT" in compiled_content, "Banner should be present"
        assert 'echo "Hello, World!"' in compiled_content, "Script content should be inlined"
        assert "# >>> BEGIN inline: script.sh" in compiled_content, "Begin marker should be present"
        assert "# <<< END inline" in compiled_content, "End marker should be present"


def test_dry_run_no_changes(setup_dirs: tuple[Path, Path, Path, Path]):
    """Test dry run mode does not write files but reports changes."""
    with temporary_env_var("BASH2GITLAB_SKIP_ROOT_CHECKS", "1"):
        uncompiled_dir, output_dir, yaml_file, _ = setup_dirs
        output_file = output_dir / ".gitlab-ci.yml"

        # Run in dry run mode
        inlined_count = run_compile_all(
            uncompiled_path=uncompiled_dir, output_path=output_dir, dry_run=True, force=True
        )

        assert inlined_count == 1, "Expected one section to be inlined"
        assert not output_file.exists(), "Output file should not be created in dry run"


def test_no_changes_no_write(setup_dirs: tuple[Path, Path, Path, Path]):
    """Test that no changes result in no file write."""
    with temporary_env_var("BASH2GITLAB_SKIP_ROOT_CHECKS", "1"):
        uncompiled_dir, output_dir, yaml_file, script_file = setup_dirs
        output_dir / ".gitlab-ci.yml"

        # First compilation
        run_compile_all(uncompiled_path=uncompiled_dir, output_path=output_dir, dry_run=False, force=True)

        # Modify script file to have same content (no structural change)
        script_file.write_text('#!/bin/bash\necho "Hello, World!"\n', encoding="utf-8")

        # Run again
        inlined_count = run_compile_all(
            uncompiled_path=uncompiled_dir, output_path=output_dir, dry_run=False, force=False
        )

        assert inlined_count == 0, "No inlining should occur if no changes"


def test_manual_edit_prevents_overwrite(setup_dirs: tuple[Path, Path, Path, Path]):
    """Test that manual edits to output file prevent overwrite."""
    with temporary_env_var("BASH2GITLAB_SKIP_ROOT_CHECKS", "1"):
        uncompiled_dir, output_dir, yaml_file, _ = setup_dirs
        output_file = output_dir / ".gitlab-ci.yml"

        # First compilation
        run_compile_all(uncompiled_path=uncompiled_dir, output_path=output_dir, dry_run=False, force=True)

        # Manually edit the output file
        original_content = output_file.read_text(encoding="utf-8")
        modified_content = original_content.replace("my_job", "my_job_modified")
        output_file.write_text(modified_content, encoding="utf-8")

        # Attempt to compile again
        with pytest.raises(CompileError):
            run_compile_all(uncompiled_path=uncompiled_dir, output_path=output_dir, dry_run=False, force=True)


def test_invalid_yaml_validation(setup_dirs: tuple[Path, Path, Path, Path]):
    """Test that invalid YAML output raises ValidationFailed."""
    with temporary_env_var("BASH2GITLAB_SKIP_ROOT_CHECKS", "1"):
        uncompiled_dir, output_dir, yaml_file, _ = setup_dirs
        output_dir / ".gitlab-ci.yml"

        # Create an invalid .gitlab-ci.yml
        invalid_yaml = """
    stages:
      - test
    my_job:
      stage: test
      script:
        - ./script.sh
    invalid_key: [invalid: syntax]
    """
        yaml_file.write_text(invalid_yaml, encoding="utf-8")

        with pytest.raises(ValidationFailed):
            run_compile_all(uncompiled_path=uncompiled_dir, output_path=output_dir, dry_run=False, force=True)


def test_global_variables(setup_dirs: tuple[Path, Path, Path, Path]):
    """Test inlining global variables from global_variables.sh."""
    with temporary_env_var("BASH2GITLAB_SKIP_ROOT_CHECKS", "1"):
        uncompiled_dir, output_dir, yaml_file, _ = setup_dirs
        output_file = output_dir / ".gitlab-ci.yml"

        # Add global_variables.sh
        global_vars_content = """export MY_VAR="test_value"
    export ANOTHER_VAR="another_value"
    """
        global_vars_file = uncompiled_dir / "global_variables.sh"
        global_vars_file.write_text(global_vars_content, encoding="utf-8")

        # Run compilation
        inlined_count = run_compile_all(
            uncompiled_path=uncompiled_dir, output_path=output_dir, dry_run=False, force=True
        )

        assert inlined_count >= 1, "Expected at least one section inlined (variables)"
        compiled_content = output_file.read_text(encoding="utf-8")
        assert "MY_VAR: test_value" in compiled_content, "Global variable should be inlined"
        assert "ANOTHER_VAR: another_value" in compiled_content, "Global variable should be inlined"


@pytest.mark.skipif(sys.platform == "win32", reason="Windows path quirk")
def test_infer_cli():
    """Test the infer_cli function generates correct command."""
    with temporary_env_var("BASH2GITLAB_SKIP_ROOT_CHECKS", "1"):
        uncompiled_path = Path("/path/to/uncompiled")
        output_path = Path("/path/to/output")

        # Test without dry_run and parallelism
        command = infer_cli(uncompiled_path, output_path).replace("C:", "")
        assert command == f"bash2gitlab compile --in {uncompiled_path} --out {output_path}"

        # Test with dry_run
        command = infer_cli(uncompiled_path, output_path, dry_run=True).replace("C:", "")
        assert command == f"bash2gitlab compile --in {uncompiled_path} --out {output_path} --dry-run"

        # Test with parallelism
        command = infer_cli(uncompiled_path, output_path, parallelism=4).replace("C:", "")
        assert command == f"bash2gitlab compile --in {uncompiled_path} --out {output_path} --parallelism 4"
