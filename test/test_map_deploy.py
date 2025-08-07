# test_map_deploy_command.py
from pathlib import Path

import pytest
import toml

from bash2gitlab.map_deploy_command import get_deployment_map, map_deploy


@pytest.fixture
def setup_test_environment(tmp_path: Path):
    """Sets up a temporary directory structure for testing."""
    # Source directories
    source_angular = tmp_path / "src" / "angular"
    source_java = tmp_path / "src" / "java" / "deep"
    source_angular.mkdir(parents=True)
    source_java.mkdir(parents=True)

    # Source files
    (source_angular / "script1.js").write_text("console.log('angular');")
    (source_java / "script2.java").write_text('System.out.println("java");')

    # Target directories
    target_angular = tmp_path / "dest" / "angular_app"
    target_java = tmp_path / "dest" / "java_app"
    # We don't create these, the script should do it.

    # pyproject.toml
    pyproject_content = {
        "tool": {
            "bash2gitlab": {
                "map": {
                    str(source_angular): str(target_angular),
                    str(source_java.parent): str(target_java),  # testing parent dir mapping
                }
            }
        }
    }
    pyproject_path = tmp_path / "pyproject.toml"
    with open(pyproject_path, "w") as f:
        toml.dump(pyproject_content, f)

    return tmp_path, pyproject_path


def test_get_deployment_map(setup_test_environment):
    """Tests parsing of the pyproject.toml file."""
    tmp_path, pyproject_path = setup_test_environment

    deployment_map = get_deployment_map(pyproject_path)

    assert len(deployment_map) == 2
    assert str(tmp_path / "src" / "angular") in deployment_map
    assert deployment_map[str(tmp_path / "src" / "angular")] == str(tmp_path / "dest" / "angular_app")


def test_initial_deployment(setup_test_environment):
    """Tests the first run where no target files exist."""
    tmp_path, pyproject_path = setup_test_environment
    deployment_map = get_deployment_map(pyproject_path)

    map_deploy(deployment_map)

    # Check Angular deployment
    target_angular_file = tmp_path / "dest" / "angular_app" / "script1.js"
    assert target_angular_file.exists()
    assert (tmp_path / "dest" / "angular_app" / ".gitignore").exists()
    assert (tmp_path / "dest" / "angular_app" / "script1.js.hash").exists()

    # Check Java deployment
    target_java_file = tmp_path / "dest" / "java_app" / "deep" / "script2.java"
    assert target_java_file.exists()
    assert (tmp_path / "dest" / "java_app" / ".gitignore").exists()
    assert (tmp_path / "dest" / "java_app" / "deep" / "script2.java.hash").exists()


def test_unchanged_redeployment(setup_test_environment):
    """Tests a second run where source files have not changed."""
    tmp_path, pyproject_path = setup_test_environment
    deployment_map = get_deployment_map(pyproject_path)

    map_deploy(deployment_map)  # First run

    # Capture last modified times
    target_angular_file = tmp_path / "dest" / "angular_app" / "script1.js"
    mtime_before = target_angular_file.stat().st_mtime

    map_deploy(deployment_map)  # Second run
    mtime_after = target_angular_file.stat().st_mtime

    assert mtime_before == mtime_after


def test_modified_destination_skip(setup_test_environment):
    """Tests that a modified destination file is skipped."""
    tmp_path, pyproject_path = setup_test_environment
    deployment_map = get_deployment_map(pyproject_path)
    map_deploy(deployment_map)

    target_file = tmp_path / "dest" / "angular_app" / "script1.js"
    original_content = target_file.read_text()

    # Modify the destination file
    target_file.write_text("console.log('modified');")

    map_deploy(deployment_map)  # Attempt redeploy

    # Content should remain modified because it was skipped
    assert target_file.read_text() == "console.log('modified');"
    assert target_file.read_text() != original_content


def test_modified_destination_force(setup_test_environment):
    """Tests that --force overwrites a modified destination file."""
    tmp_path, pyproject_path = setup_test_environment
    deployment_map = get_deployment_map(pyproject_path)
    map_deploy(deployment_map)

    target_file = tmp_path / "dest" / "angular_app" / "script1.js"
    original_content = (tmp_path / "src" / "angular" / "script1.js").read_text()

    # Modify the destination file
    target_file.write_text("console.log('modified');")

    # Attempt redeploy with force
    map_deploy(deployment_map, force=True)

    # Content should be reverted to the source content
    assert target_file.read_text() == original_content


def test_dry_run(setup_test_environment):
    """Tests that --dry-run prevents any file system changes."""
    tmp_path, pyproject_path = setup_test_environment
    deployment_map = get_deployment_map(pyproject_path)

    map_deploy(deployment_map, dry_run=True)

    # No files or directories should have been created
    assert not (tmp_path / "dest").exists()
