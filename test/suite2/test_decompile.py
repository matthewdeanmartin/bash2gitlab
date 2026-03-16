"""Tests for decompile_all: extract scripts from GitLab CI YAML."""

import textwrap

import pytest

from bash2gitlab.commands.decompile_all import (
    bashify_script_items,
    create_script_filename,
    decompile_script_block,
    decompile_variables_block,
    run_decompile_gitlab_file,
    run_decompile_gitlab_tree,
)
from bash2gitlab.utils.yaml_factory import get_yaml

SIMPLE_GITLAB_CI = textwrap.dedent("""\
    # Pragma: do-not-validate-schema
    build-job:
      stage: build
      script:
        - echo hello
        - echo world
""")

GITLAB_CI_WITH_VARS = textwrap.dedent("""\
    # Pragma: do-not-validate-schema
    variables:
      GLOBAL_VAR: global_value
    build-job:
      stage: build
      variables:
        JOB_VAR: job_value
      script:
        - echo hello
""")

GITLAB_CI_BEFORE_AFTER = textwrap.dedent("""\
    # Pragma: do-not-validate-schema
    build-job:
      stage: build
      before_script:
        - echo setup
      script:
        - echo main
      after_script:
        - echo teardown
""")


# ---------------------------------------------------------------------------
# create_script_filename
# ---------------------------------------------------------------------------


class TestCreateScriptFilename:
    def test_main_script_key(self):
        assert create_script_filename("my-job", "script") == "my-job.sh"

    def test_before_script_key(self):
        assert create_script_filename("my-job", "before_script") == "my-job_before_script.sh"

    def test_after_script_key(self):
        assert create_script_filename("my-job", "after_script") == "my-job_after_script.sh"

    def test_special_chars_sanitized(self):
        name = create_script_filename("My Job: with spaces!", "script")
        assert " " not in name
        assert ":" not in name
        assert name.endswith(".sh")

    def test_uppercase_lowered(self):
        name = create_script_filename("BuildJob", "script")
        assert name == name.lower()


# ---------------------------------------------------------------------------
# bashify_script_items
# ---------------------------------------------------------------------------


class TestBashifyScriptItems:
    def test_plain_strings_pass_through(self):
        yaml = get_yaml()
        result = bashify_script_items(["echo a", "echo b"], yaml)
        assert result == ["echo a", "echo b"]

    def test_string_value_split_by_lines(self):
        yaml = get_yaml()
        result = bashify_script_items("echo a\necho b", yaml)
        assert "echo a" in result
        assert "echo b" in result

    def test_empty_lines_dropped(self):
        yaml = get_yaml()
        result = bashify_script_items(["echo a", "", "  ", "echo b"], yaml)
        assert "" not in result
        assert "  " not in result
        assert "echo a" in result
        assert "echo b" in result


# ---------------------------------------------------------------------------
# decompile_variables_block
# ---------------------------------------------------------------------------


class TestDecompileVariablesBlock:
    def test_creates_sh_file(self, tmp_path):
        variables = {"FOO": "bar", "BAZ": "qux"}
        filename = decompile_variables_block(variables, "global", tmp_path)
        assert filename == "global_variables.sh"
        script_file = tmp_path / "global_variables.sh"
        assert script_file.exists()
        content = script_file.read_text()
        assert 'export FOO="bar"' in content
        assert 'export BAZ="qux"' in content

    def test_dry_run_no_file(self, tmp_path):
        variables = {"FOO": "bar"}
        filename = decompile_variables_block(variables, "global", tmp_path, dry_run=True)
        assert filename == "global_variables.sh"
        assert not (tmp_path / "global_variables.sh").exists()

    def test_empty_dict_returns_none(self, tmp_path):
        result = decompile_variables_block({}, "global", tmp_path)
        assert result is None

    def test_none_returns_none(self, tmp_path):
        result = decompile_variables_block(None, "global", tmp_path)
        assert result is None

    def test_escapes_quotes_in_values(self, tmp_path):
        variables = {"MSG": 'say "hello"'}
        _filename = decompile_variables_block(variables, "test", tmp_path)
        content = (tmp_path / "test_variables.sh").read_text()
        assert '\\"' in content


# ---------------------------------------------------------------------------
# decompile_script_block
# ---------------------------------------------------------------------------


class TestDecompileScriptBlock:
    def test_creates_script_file(self, tmp_path):
        script_path, cmd = decompile_script_block(
            script_content=["echo hello", "echo world"],
            job_name="build-job",
            script_key="script",
            scripts_output_path=tmp_path,
            yaml_dir=tmp_path,
        )
        assert script_path is not None
        assert cmd is not None
        sh = tmp_path / "build-job.sh"
        assert sh.exists()
        content = sh.read_text()
        assert "echo hello" in content
        assert "echo world" in content
        assert "#!/bin/bash" in content

    def test_dry_run_no_file(self, tmp_path):
        script_path, cmd = decompile_script_block(
            script_content=["echo hello"],
            job_name="build-job",
            script_key="script",
            scripts_output_path=tmp_path,
            yaml_dir=tmp_path,
            dry_run=True,
        )
        assert cmd is not None
        assert not (tmp_path / "build-job.sh").exists()

    def test_empty_content_returns_none(self, tmp_path):
        script_path, cmd = decompile_script_block(
            script_content=[],
            job_name="build-job",
            script_key="script",
            scripts_output_path=tmp_path,
            yaml_dir=tmp_path,
        )
        assert script_path is None
        assert cmd is None

    def test_command_is_relative(self, tmp_path):
        _, cmd = decompile_script_block(
            script_content=["echo hello"],
            job_name="build-job",
            script_key="script",
            scripts_output_path=tmp_path,
            yaml_dir=tmp_path,
        )
        assert cmd.startswith("./")

    def test_global_vars_sourced_in_header(self, tmp_path):
        _, _ = decompile_script_block(
            script_content=["echo hello"],
            job_name="build-job",
            script_key="script",
            scripts_output_path=tmp_path,
            yaml_dir=tmp_path,
            global_vars_filename="global_variables.sh",
        )
        content = (tmp_path / "build-job.sh").read_text()
        assert "global_variables.sh" in content
        assert "CI" in content  # the CI guard

    def test_minimum_lines_respected(self, tmp_path):
        script_path, cmd = decompile_script_block(
            script_content=["echo hello"],
            job_name="build-job",
            script_key="script",
            scripts_output_path=tmp_path,
            yaml_dir=tmp_path,
            minimum_lines=5,
        )
        assert script_path is None
        assert cmd is None


# ---------------------------------------------------------------------------
# run_decompile_gitlab_file
# ---------------------------------------------------------------------------


class TestRunDecompileGitlabFile:
    def test_decompiles_simple_yaml(self, tmp_path):
        in_file = tmp_path / "input" / ".gitlab-ci.yml"
        in_file.parent.mkdir()
        in_file.write_text(SIMPLE_GITLAB_CI)
        out_dir = tmp_path / "output"
        jobs, files, out_yaml = run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir)
        assert jobs >= 1
        assert out_yaml.exists()

    def test_script_file_created(self, tmp_path):
        in_file = tmp_path / ".gitlab-ci.yml"
        in_file.write_text(SIMPLE_GITLAB_CI)
        out_dir = tmp_path / "output"
        run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir)
        # build-job.sh should exist in output
        sh_files = list(out_dir.rglob("*.sh"))
        assert any("build-job" in f.name for f in sh_files)

    def test_output_yaml_references_script(self, tmp_path):
        in_file = tmp_path / ".gitlab-ci.yml"
        in_file.write_text(SIMPLE_GITLAB_CI)
        out_dir = tmp_path / "output"
        _, _, out_yaml = run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir)
        content = out_yaml.read_text()
        assert "./build-job.sh" in content

    def test_global_variables_extracted(self, tmp_path):
        in_file = tmp_path / ".gitlab-ci.yml"
        in_file.write_text(GITLAB_CI_WITH_VARS)
        out_dir = tmp_path / "output"
        run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir)
        vars_file = out_dir / "global_variables.sh"
        assert vars_file.exists()
        assert "GLOBAL_VAR" in vars_file.read_text()

    def test_before_after_scripts_extracted(self, tmp_path):
        in_file = tmp_path / ".gitlab-ci.yml"
        in_file.write_text(GITLAB_CI_BEFORE_AFTER)
        out_dir = tmp_path / "output"
        run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir)
        sh_files = {f.name for f in out_dir.rglob("*.sh")}
        assert any("before_script" in n for n in sh_files)
        assert any("after_script" in n for n in sh_files)

    def test_makefile_generated(self, tmp_path):
        in_file = tmp_path / ".gitlab-ci.yml"
        in_file.write_text(SIMPLE_GITLAB_CI)
        out_dir = tmp_path / "output"
        run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir)
        assert (out_dir / "Makefile").exists()

    def test_missing_input_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            run_decompile_gitlab_file(
                input_yaml_path=tmp_path / "nonexistent.yml",
                output_dir=tmp_path / "out",
            )

    def test_dry_run_no_files_written(self, tmp_path):
        in_file = tmp_path / ".gitlab-ci.yml"
        in_file.write_text(SIMPLE_GITLAB_CI)
        out_dir = tmp_path / "output"
        run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir, dry_run=True)
        # No .sh files should be written
        sh_files = list(out_dir.rglob("*.sh"))
        assert sh_files == []


# ---------------------------------------------------------------------------
# run_decompile_gitlab_tree
# ---------------------------------------------------------------------------


class TestRunDecompileGitlabTree:
    def test_processes_multiple_yaml_files(self, tmp_path):
        in_dir = tmp_path / "input"
        in_dir.mkdir()
        for i in range(3):
            f = in_dir / f"job{i}.yml"
            f.write_text(textwrap.dedent(f"""\
                    # Pragma: do-not-validate-schema
                    job{i}:
                      stage: build
                      script:
                        - echo job{i}
                """))
        out_dir = tmp_path / "output"
        yaml_count, jobs, created = run_decompile_gitlab_tree(input_root=in_dir, output_dir=out_dir)
        assert yaml_count == 3
        assert jobs >= 3

    def test_missing_input_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            run_decompile_gitlab_tree(
                input_root=tmp_path / "nonexistent",
                output_dir=tmp_path / "out",
            )

    def test_preserves_subdir_structure(self, tmp_path):
        in_dir = tmp_path / "input"
        sub = in_dir / "subdir"
        sub.mkdir(parents=True)
        f = sub / "ci.yml"
        f.write_text(SIMPLE_GITLAB_CI)
        out_dir = tmp_path / "output"
        run_decompile_gitlab_tree(input_root=in_dir, output_dir=out_dir)
        # The output should preserve the subdir structure
        assert (out_dir / "subdir").is_dir()
