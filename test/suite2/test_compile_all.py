"""Tests for compile_all: inline_gitlab_scripts, process_script_list, write_yaml_and_hash."""

import base64
import textwrap

import pytest

from bash2gitlab.commands.compile_all import (
    as_items,
    compact_runs_to_literal,
    get_banner,
    infer_cli,
    inline_gitlab_scripts,
    write_compiled_file,
    write_yaml_and_hash,
)
from bash2gitlab.errors.exceptions import CompileError

# ---------------------------------------------------------------------------
# infer_cli / get_banner
# ---------------------------------------------------------------------------


class TestInferCli:
    def test_basic(self, tmp_path):
        cmd = infer_cli(tmp_path / "in", tmp_path / "out")
        assert "compile" in cmd
        assert "--in" in cmd
        assert "--out" in cmd

    def test_dry_run_flag(self, tmp_path):
        cmd = infer_cli(tmp_path / "in", tmp_path / "out", dry_run=True)
        assert "--dry-run" in cmd

    def test_parallelism_flag(self, tmp_path):
        cmd = infer_cli(tmp_path / "in", tmp_path / "out", parallelism=4)
        assert "--parallelism 4" in cmd


class TestGetBanner:
    def test_contains_do_not_edit(self):
        banner = get_banner("bash2gitlab compile --in in --out out")
        assert "DO NOT EDIT" in banner

    def test_contains_command(self):
        cmd = "bash2gitlab compile --in in --out out"
        banner = get_banner(cmd)
        assert cmd in banner


# ---------------------------------------------------------------------------
# as_items
# ---------------------------------------------------------------------------


class TestAsItems:
    def test_string_input(self):
        items, was_seq, orig = as_items("echo hello")
        assert items == ["echo hello"]
        assert was_seq is False
        assert orig is None

    def test_list_input(self):
        items, was_seq, orig = as_items(["a", "b"])
        assert items == ["a", "b"]
        assert was_seq is False

    def test_commented_seq(self):
        from ruamel.yaml.comments import CommentedSeq

        cs = CommentedSeq(["x", "y"])
        items, was_seq, orig = as_items(cs)
        assert items == ["x", "y"]
        assert was_seq is True
        assert orig is cs


# ---------------------------------------------------------------------------
# compact_runs_to_literal
# ---------------------------------------------------------------------------


class TestCompactRunsToLiteral:
    def test_merges_multiple_strings(self):
        from ruamel.yaml.scalarstring import LiteralScalarString

        result = compact_runs_to_literal(["echo a", "echo b", "echo c"])
        assert len(result) == 1
        assert isinstance(result[0], LiteralScalarString)
        assert "echo a" in result[0]

    def test_single_string_not_merged(self):
        from ruamel.yaml.scalarstring import LiteralScalarString

        result = compact_runs_to_literal(["echo a"])
        # single item, min_lines=2 means it stays as-is
        assert result == ["echo a"]
        assert not isinstance(result[0], LiteralScalarString)

    def test_tagged_scalar_is_boundary(self):
        from ruamel.yaml.comments import TaggedScalar

        ts = TaggedScalar(value="!reference [.job, script]", tag="!reference")
        items = ["echo before", ts, "echo after"]
        result = compact_runs_to_literal(items)
        # tagged scalar should sit in between - strings around it compacted separately
        assert ts in result


# ---------------------------------------------------------------------------
# inline_gitlab_scripts
# ---------------------------------------------------------------------------


SIMPLE_YAML = textwrap.dedent("""\
    build-job:
      stage: build
      script:
        - echo hello
""")

YAML_WITH_SCRIPT_REF = textwrap.dedent("""\
    build-job:
      stage: build
      script:
        - ./build.sh
""")


@pytest.fixture(autouse=False)
def skip_root_checks(monkeypatch):
    """Allow scripts outside the project root (needed when using tmp_path)."""
    monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")


class TestInlineGitlabScripts:
    def test_passthrough_no_scripts(self, tmp_path):
        count, result = inline_gitlab_scripts(SIMPLE_YAML, tmp_path, {}, tmp_path)
        assert count == 0
        assert "echo hello" in result

    def test_inlines_bash_script(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")
        script = tmp_path / "build.sh"
        script.write_text("#!/bin/bash\necho building\n")
        count, result = inline_gitlab_scripts(YAML_WITH_SCRIPT_REF, tmp_path, {}, tmp_path)
        assert count > 0
        assert "echo building" in result
        assert "BEGIN inline" in result

    def test_missing_script_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")
        from bash2gitlab.errors.exceptions import Bash2GitlabError

        with pytest.raises((Bash2GitlabError, FileNotFoundError, Exception)):
            inline_gitlab_scripts(YAML_WITH_SCRIPT_REF, tmp_path, {}, tmp_path)

    def test_global_variables_merged(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            build-job:
              stage: build
              script:
                - echo hello
        """)
        count, result = inline_gitlab_scripts(yaml_content, tmp_path, {"MY_VAR": "hello"}, tmp_path)
        assert "MY_VAR" in result
        assert "hello" in result

    def test_job_variables_from_file(self, tmp_path):
        job_vars_file = tmp_path / "build-job_variables.sh"
        job_vars_file.write_text('export JOB_VAR="world"\n')
        yaml_content = textwrap.dedent("""\
            build-job:
              stage: build
              script:
                - echo hello
        """)
        count, result = inline_gitlab_scripts(yaml_content, tmp_path, {}, tmp_path)
        assert "JOB_VAR" in result

    def test_skips_non_job_keys(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            stages:
              - build
            variables:
              GLOBAL: value
            build-job:
              stage: build
              script:
                - echo hello
        """)
        count, result = inline_gitlab_scripts(yaml_content, tmp_path, {}, tmp_path)
        # Should not crash on stages/variables keys
        assert "stages" in result

    def test_before_script_inlined(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")
        script = tmp_path / "setup.sh"
        script.write_text("echo setup\n")
        yaml_content = textwrap.dedent("""\
            build-job:
              stage: build
              before_script:
                - ./setup.sh
              script:
                - echo main
        """)
        count, result = inline_gitlab_scripts(yaml_content, tmp_path, {}, tmp_path)
        assert "echo setup" in result

    def test_after_script_inlined(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")
        script = tmp_path / "teardown.sh"
        script.write_text("echo teardown\n")
        yaml_content = textwrap.dedent("""\
            build-job:
              stage: build
              script:
                - echo main
              after_script:
                - ./teardown.sh
        """)
        count, result = inline_gitlab_scripts(yaml_content, tmp_path, {}, tmp_path)
        assert "echo teardown" in result


# ---------------------------------------------------------------------------
# write_yaml_and_hash / write_compiled_file
# ---------------------------------------------------------------------------


MINIMAL_VALID_YAML = textwrap.dedent("""\
    # Pragma: do-not-validate-schema
    build-job:
      stage: build
      script:
        - echo hello
""")


class TestWriteYamlAndHash:
    def test_writes_output_and_hash(self, tmp_path):
        out_file = tmp_path / "out" / "ci.yml"
        hash_file = tmp_path / "hashes" / "ci.yml.hash"
        write_yaml_and_hash(out_file, MINIMAL_VALID_YAML, hash_file)
        assert out_file.exists()
        assert hash_file.exists()
        # Hash file should be base64 encoded
        encoded = hash_file.read_text()
        decoded = base64.b64decode(encoded).decode("utf-8")
        # write_yaml_and_hash strips leading blank lines before writing
        assert "# Pragma: do-not-validate-schema" in decoded
        assert "echo hello" in decoded

    def test_creates_parent_dirs(self, tmp_path):
        out_file = tmp_path / "deep" / "nested" / "ci.yml"
        hash_file = tmp_path / "hashes" / "deep" / "ci.yml.hash"
        write_yaml_and_hash(out_file, MINIMAL_VALID_YAML, hash_file)
        assert out_file.exists()


class TestWriteCompiledFile:
    def test_creates_new_file(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        out_file = out_base / "ci.yml"
        wrote = write_compiled_file(out_file, MINIMAL_VALID_YAML, out_base)
        assert wrote is True
        assert out_file.exists()

    def test_skips_if_content_unchanged(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        out_file = out_base / "ci.yml"
        # First write
        write_compiled_file(out_file, MINIMAL_VALID_YAML, out_base)
        # Second write with same content
        wrote = write_compiled_file(out_file, MINIMAL_VALID_YAML, out_base)
        assert wrote is False

    def test_rewrites_on_content_change(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        out_file = out_base / "ci.yml"
        write_compiled_file(out_file, MINIMAL_VALID_YAML, out_base)
        new_content = textwrap.dedent("""\
            # Pragma: do-not-validate-schema
            build-job:
              stage: build
              script:
                - echo changed
        """)
        wrote = write_compiled_file(out_file, new_content, out_base)
        assert wrote is True
        assert "echo changed" in out_file.read_text()

    def test_raises_if_manually_edited(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        out_file = out_base / "ci.yml"
        write_compiled_file(out_file, MINIMAL_VALID_YAML, out_base)
        # Manually edit the file with a structural YAML change (adds a new key)
        manually_edited = textwrap.dedent("""\
            # Pragma: do-not-validate-schema
            build-job:
              stage: build
              script:
                - echo hello
              manually_added_key: value
        """)
        out_file.write_text(manually_edited)
        with pytest.raises((CompileError, Exception)):
            write_compiled_file(out_file, MINIMAL_VALID_YAML, out_base)

    def test_raises_if_hash_missing(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        out_file = out_base / "ci.yml"
        # Write file but no hash
        out_file.write_text(MINIMAL_VALID_YAML)
        with pytest.raises((CompileError, Exception)):
            write_compiled_file(out_file, MINIMAL_VALID_YAML, out_base)

    def test_dry_run_no_file_written(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        out_file = out_base / "ci.yml"
        write_compiled_file(out_file, MINIMAL_VALID_YAML, out_base, dry_run=True)
        assert not out_file.exists()
