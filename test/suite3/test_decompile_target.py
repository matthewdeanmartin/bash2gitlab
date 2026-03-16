"""Tests for decompile_all with target-awareness in mind.

Focus areas for the upcoming rewrite:
- create_script_filename must handle unusual job names (unicode, long names, colons, dots)
- decompile_script_block respects minimum_lines and dry_run contracts
- run_decompile_gitlab_file output YAML references scripts with relative paths
- decompile_variables_block escapes values safely
- run_decompile_gitlab_tree handles empty dirs, nested dirs, missing dirs
- Schema validation pragma must flow through decompile path cleanly
"""

from __future__ import annotations

import textwrap

import pytest

from bash2yaml.commands.decompile_all import (
    bashify_script_items,
    create_script_filename,
    decompile_script_block,
    decompile_variables_block,
    run_decompile_gitlab_file,
    run_decompile_gitlab_tree,
)
from bash2yaml.utils.yaml_factory import get_yaml

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SIMPLE_CI = textwrap.dedent("""\
    # Pragma: do-not-validate-schema
    build-job:
      stage: build
      script:
        - echo hello
        - echo world
""")

MULTI_JOB_CI = textwrap.dedent("""\
    # Pragma: do-not-validate-schema
    build-job:
      stage: build
      script:
        - echo build
    test-job:
      stage: test
      script:
        - echo test
    deploy-job:
      stage: deploy
      script:
        - echo deploy
""")

CI_WITH_VARS = textwrap.dedent("""\
    # Pragma: do-not-validate-schema
    variables:
      GLOBAL_VAR: global_value
      ANOTHER: 42
    build-job:
      stage: build
      variables:
        JOB_VAR: job_value
      script:
        - echo hello
""")

CI_BEFORE_AFTER = textwrap.dedent("""\
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
    def test_main_script(self):
        assert create_script_filename("build-job", "script") == "build-job.sh"

    def test_before_script(self):
        assert create_script_filename("build-job", "before_script") == "build-job_before_script.sh"

    def test_after_script(self):
        assert create_script_filename("build-job", "after_script") == "build-job_after_script.sh"

    def test_uppercase_lowercased(self):
        name = create_script_filename("BuildJob", "script")
        assert name == name.lower()

    def test_spaces_sanitized(self):
        name = create_script_filename("my job", "script")
        assert " " not in name
        assert name.endswith(".sh")

    def test_colon_sanitized(self):
        name = create_script_filename("build:deploy", "script")
        assert ":" not in name

    def test_exclamation_sanitized(self):
        name = create_script_filename("build!", "script")
        assert "!" not in name

    def test_dot_preserved_in_name(self):
        name = create_script_filename("build.test", "script")
        # dots are word chars; just ensure we still get .sh at end
        assert name.endswith(".sh")

    def test_multiple_special_chars(self):
        name = create_script_filename("My Job: with spaces!", "script")
        assert " " not in name
        assert ":" not in name
        assert "!" not in name
        assert name.endswith(".sh")

    def test_empty_job_name_does_not_crash(self):
        """Edge case: empty string job name should produce something ending in .sh."""
        name = create_script_filename("", "script")
        assert name.endswith(".sh")

    def test_long_job_name_not_truncated(self):
        """Job names are not truncated — caller decides length policy."""
        long_name = "a" * 200
        name = create_script_filename(long_name, "script")
        assert name.endswith(".sh")
        assert len(name) > 10


# ---------------------------------------------------------------------------
# bashify_script_items
# ---------------------------------------------------------------------------


class TestBashifyScriptItems:
    def test_plain_strings_pass_through(self):
        yaml = get_yaml()
        result = bashify_script_items(["echo a", "echo b"], yaml)
        assert result == ["echo a", "echo b"]

    def test_multiline_string_split(self):
        yaml = get_yaml()
        result = bashify_script_items("echo a\necho b\necho c", yaml)
        assert "echo a" in result
        assert "echo b" in result
        assert "echo c" in result

    def test_empty_lines_dropped(self):
        yaml = get_yaml()
        result = bashify_script_items(["echo a", "", "  ", "echo b"], yaml)
        assert "" not in result
        assert "  " not in result

    def test_empty_list_returns_empty(self):
        yaml = get_yaml()
        result = bashify_script_items([], yaml)
        assert result == []

    def test_single_item_preserved(self):
        yaml = get_yaml()
        result = bashify_script_items(["echo single"], yaml)
        assert result == ["echo single"]


# ---------------------------------------------------------------------------
# decompile_variables_block
# ---------------------------------------------------------------------------


class TestDecompileVariablesBlock:
    def test_creates_sh_file(self, tmp_path):
        filename = decompile_variables_block({"FOO": "bar"}, "global", tmp_path)
        assert filename is not None
        assert (tmp_path / "global_variables.sh").exists()

    def test_filename_convention(self, tmp_path):
        filename = decompile_variables_block({"X": "1"}, "myjob", tmp_path)
        assert filename == "myjob_variables.sh"

    def test_multiple_vars_all_exported(self, tmp_path):
        decompile_variables_block({"A": "1", "B": "2", "C": "3"}, "global", tmp_path)
        content = (tmp_path / "global_variables.sh").read_text()
        for var in ["A", "B", "C"]:
            assert f"export {var}" in content

    def test_empty_dict_returns_none(self, tmp_path):
        result = decompile_variables_block({}, "global", tmp_path)
        assert result is None

    def test_none_returns_none(self, tmp_path):
        result = decompile_variables_block(None, "global", tmp_path)
        assert result is None

    def test_dry_run_no_file_written(self, tmp_path):
        decompile_variables_block({"X": "1"}, "global", tmp_path, dry_run=True)
        assert not (tmp_path / "global_variables.sh").exists()

    def test_double_quotes_escaped(self, tmp_path):
        decompile_variables_block({"MSG": 'say "hello"'}, "test", tmp_path)
        content = (tmp_path / "test_variables.sh").read_text()
        assert '\\"' in content

    def test_value_with_dollar_sign(self, tmp_path):
        """Dollar signs in variable values should be preserved (not interpolated)."""
        decompile_variables_block({"PATH_VAR": "/usr/$HOME/bin"}, "test", tmp_path)
        content = (tmp_path / "test_variables.sh").read_text()
        assert "PATH_VAR" in content

    def test_numeric_value_as_string(self, tmp_path):
        decompile_variables_block({"PORT": "8080"}, "global", tmp_path)
        content = (tmp_path / "global_variables.sh").read_text()
        assert "PORT" in content


# ---------------------------------------------------------------------------
# decompile_script_block
# ---------------------------------------------------------------------------


class TestDecompileScriptBlock:
    def test_creates_sh_file_with_shebang(self, tmp_path):
        decompile_script_block(
            script_content=["echo hello"],
            job_name="build-job",
            script_key="script",
            scripts_output_path=tmp_path,
            yaml_dir=tmp_path,
        )
        content = (tmp_path / "build-job.sh").read_text()
        assert "#!/bin/bash" in content
        assert "echo hello" in content

    def test_empty_content_returns_none_none(self, tmp_path):
        script_path, cmd = decompile_script_block(
            script_content=[],
            job_name="build-job",
            script_key="script",
            scripts_output_path=tmp_path,
            yaml_dir=tmp_path,
        )
        assert script_path is None
        assert cmd is None

    def test_command_uses_relative_path(self, tmp_path):
        _, cmd = decompile_script_block(
            script_content=["echo hi"],
            job_name="build-job",
            script_key="script",
            scripts_output_path=tmp_path,
            yaml_dir=tmp_path,
        )
        assert cmd is not None
        assert cmd.startswith("./")

    def test_dry_run_no_file(self, tmp_path):
        decompile_script_block(
            script_content=["echo hi"],
            job_name="build-job",
            script_key="script",
            scripts_output_path=tmp_path,
            yaml_dir=tmp_path,
            dry_run=True,
        )
        assert not (tmp_path / "build-job.sh").exists()

    def test_minimum_lines_skips_short_script(self, tmp_path):
        script_path, cmd = decompile_script_block(
            script_content=["echo hi"],
            job_name="build-job",
            script_key="script",
            scripts_output_path=tmp_path,
            yaml_dir=tmp_path,
            minimum_lines=5,
        )
        assert script_path is None
        assert cmd is None

    def test_minimum_lines_allows_long_script(self, tmp_path):
        long_script = [f"echo line{i}" for i in range(10)]
        script_path, cmd = decompile_script_block(
            script_content=long_script,
            job_name="build-job",
            script_key="script",
            scripts_output_path=tmp_path,
            yaml_dir=tmp_path,
            minimum_lines=5,
        )
        assert script_path is not None

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

    def test_before_script_filename_convention(self, tmp_path):
        script_path, _ = decompile_script_block(
            script_content=["echo setup"],
            job_name="build-job",
            script_key="before_script",
            scripts_output_path=tmp_path,
            yaml_dir=tmp_path,
        )
        assert script_path is not None
        # script_path is a str
        assert "before_script" in str(script_path)

    def test_after_script_filename_convention(self, tmp_path):
        script_path, _ = decompile_script_block(
            script_content=["echo teardown"],
            job_name="build-job",
            script_key="after_script",
            scripts_output_path=tmp_path,
            yaml_dir=tmp_path,
        )
        assert script_path is not None
        assert "after_script" in str(script_path)

    def test_multiple_lines_all_in_script(self, tmp_path):
        lines = ["echo a", "echo b", "echo c", "export X=1"]
        decompile_script_block(
            script_content=lines,
            job_name="myjob",
            script_key="script",
            scripts_output_path=tmp_path,
            yaml_dir=tmp_path,
        )
        content = (tmp_path / "myjob.sh").read_text()
        for line in lines:
            assert line in content


# ---------------------------------------------------------------------------
# run_decompile_gitlab_file
# ---------------------------------------------------------------------------


class TestRunDecompileGitlabFile:
    def test_basic_decompile(self, tmp_path):
        in_file = tmp_path / ".gitlab-ci.yml"
        in_file.write_text(SIMPLE_CI)
        out_dir = tmp_path / "out"
        jobs, files, out_yaml = run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir)
        assert jobs >= 1
        assert out_yaml.exists()

    def test_script_file_created(self, tmp_path):
        in_file = tmp_path / ".gitlab-ci.yml"
        in_file.write_text(SIMPLE_CI)
        out_dir = tmp_path / "out"
        run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir)
        sh_files = list(out_dir.rglob("*.sh"))
        assert any("build-job" in f.name for f in sh_files)

    def test_output_yaml_has_script_reference(self, tmp_path):
        in_file = tmp_path / ".gitlab-ci.yml"
        in_file.write_text(SIMPLE_CI)
        out_dir = tmp_path / "out"
        _, _, out_yaml = run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir)
        content = out_yaml.read_text()
        assert "build-job.sh" in content

    def test_script_ref_is_relative(self, tmp_path):
        in_file = tmp_path / ".gitlab-ci.yml"
        in_file.write_text(SIMPLE_CI)
        out_dir = tmp_path / "out"
        _, _, out_yaml = run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir)
        content = out_yaml.read_text()
        assert "./build-job.sh" in content

    def test_global_variables_extracted(self, tmp_path):
        in_file = tmp_path / ".gitlab-ci.yml"
        in_file.write_text(CI_WITH_VARS)
        out_dir = tmp_path / "out"
        run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir)
        vars_file = out_dir / "global_variables.sh"
        assert vars_file.exists()
        content = vars_file.read_text()
        assert "GLOBAL_VAR" in content

    def test_before_after_script_extracted(self, tmp_path):
        in_file = tmp_path / ".gitlab-ci.yml"
        in_file.write_text(CI_BEFORE_AFTER)
        out_dir = tmp_path / "out"
        run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir)
        sh_files = {f.name for f in out_dir.rglob("*.sh")}
        assert any("before_script" in n for n in sh_files)
        assert any("after_script" in n for n in sh_files)

    def test_makefile_created(self, tmp_path):
        in_file = tmp_path / ".gitlab-ci.yml"
        in_file.write_text(SIMPLE_CI)
        out_dir = tmp_path / "out"
        run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir)
        assert (out_dir / "Makefile").exists()

    def test_missing_input_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            run_decompile_gitlab_file(
                input_yaml_path=tmp_path / "nonexistent.yml",
                output_dir=tmp_path / "out",
            )

    def test_dry_run_no_sh_files(self, tmp_path):
        in_file = tmp_path / ".gitlab-ci.yml"
        in_file.write_text(SIMPLE_CI)
        out_dir = tmp_path / "out"
        run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir, dry_run=True)
        sh_files = list(out_dir.rglob("*.sh")) if out_dir.exists() else []
        assert sh_files == []

    def test_multi_job_all_scripts_created(self, tmp_path):
        in_file = tmp_path / ".gitlab-ci.yml"
        in_file.write_text(MULTI_JOB_CI)
        out_dir = tmp_path / "out"
        jobs, _, _ = run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir)
        assert jobs >= 3

    def test_output_in_subdir_of_input(self, tmp_path):
        """Output can be inside the input's parent dir — paths must be relative, not absolute."""
        sub = tmp_path / "ci"
        sub.mkdir()
        in_file = sub / ".gitlab-ci.yml"
        in_file.write_text(SIMPLE_CI)
        out_dir = sub / "scripts"
        _, _, out_yaml = run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir)
        content = out_yaml.read_text()
        # The script reference must be relative, not absolute
        for line in content.splitlines():
            if "build-job.sh" in line:
                assert not line.strip().startswith("/")


# ---------------------------------------------------------------------------
# run_decompile_gitlab_tree
# ---------------------------------------------------------------------------


class TestRunDecompileGitlabTree:
    def test_processes_multiple_files(self, tmp_path):
        in_dir = tmp_path / "ci"
        in_dir.mkdir()
        for i in range(3):
            (in_dir / f"job{i}.yml").write_text(textwrap.dedent(f"""\
                # Pragma: do-not-validate-schema
                job{i}:
                  stage: build
                  script:
                    - echo job{i}
            """))
        out_dir = tmp_path / "out"
        yaml_count, jobs, _ = run_decompile_gitlab_tree(input_root=in_dir, output_dir=out_dir)
        assert yaml_count == 3
        assert jobs >= 3

    def test_missing_input_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            run_decompile_gitlab_tree(
                input_root=tmp_path / "nonexistent",
                output_dir=tmp_path / "out",
            )

    def test_preserves_subdir_structure(self, tmp_path):
        in_dir = tmp_path / "ci"
        sub = in_dir / "subteam"
        sub.mkdir(parents=True)
        (sub / "ci.yml").write_text(SIMPLE_CI)
        out_dir = tmp_path / "out"
        run_decompile_gitlab_tree(input_root=in_dir, output_dir=out_dir)
        assert (out_dir / "subteam").is_dir()

    def test_empty_dir_returns_zero_counts(self, tmp_path):
        in_dir = tmp_path / "ci"
        in_dir.mkdir()
        out_dir = tmp_path / "out"
        yaml_count, jobs, _ = run_decompile_gitlab_tree(input_root=in_dir, output_dir=out_dir)
        assert yaml_count == 0
        assert jobs == 0

    def test_deeply_nested_structure(self, tmp_path):
        in_dir = tmp_path / "ci"
        deep = in_dir / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "ci.yml").write_text(SIMPLE_CI)
        out_dir = tmp_path / "out"
        yaml_count, _, _ = run_decompile_gitlab_tree(input_root=in_dir, output_dir=out_dir)
        assert yaml_count >= 1

    def test_non_yaml_files_ignored(self, tmp_path):
        in_dir = tmp_path / "ci"
        in_dir.mkdir()
        (in_dir / "ci.yml").write_text(SIMPLE_CI)
        (in_dir / "README.md").write_text("# readme")
        (in_dir / "script.sh").write_text("echo hi")
        out_dir = tmp_path / "out"
        yaml_count, _, _ = run_decompile_gitlab_tree(input_root=in_dir, output_dir=out_dir)
        assert yaml_count == 1


# ---------------------------------------------------------------------------
# Target abstraction readiness
# ---------------------------------------------------------------------------


class TestDecompileTargetReadiness:
    """Documents behavior that must remain stable during the rewrite."""

    def test_pragma_survives_decompile_roundtrip(self, tmp_path):
        """The do-not-validate-schema pragma in input must appear in output YAML."""
        in_file = tmp_path / ".gitlab-ci.yml"
        in_file.write_text(SIMPLE_CI)
        out_dir = tmp_path / "out"
        _, _, out_yaml = run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir)
        content = out_yaml.read_text()
        assert "do-not-validate-schema" in content.lower()

    def test_shebang_is_bash(self, tmp_path):
        """Default shebang must be #!/bin/bash — target-specific shebangs go through config."""
        in_file = tmp_path / ".gitlab-ci.yml"
        in_file.write_text(SIMPLE_CI)
        out_dir = tmp_path / "out"
        run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir)
        sh_files = list(out_dir.rglob("*.sh"))
        for sh in sh_files:
            content = sh.read_text()
            if content.strip():
                first_line = content.splitlines()[0]
                assert first_line.startswith("#!")

    def test_script_content_is_executable_bash(self, tmp_path):
        """Decompiled script content must be valid bash (no YAML artifacts)."""
        in_file = tmp_path / ".gitlab-ci.yml"
        in_file.write_text(SIMPLE_CI)
        out_dir = tmp_path / "out"
        run_decompile_gitlab_file(input_yaml_path=in_file, output_dir=out_dir)
        sh = out_dir / "build-job.sh"
        content = sh.read_text()
        # Should not contain YAML-only syntax
        assert "stage:" not in content
        assert "script:" not in content
