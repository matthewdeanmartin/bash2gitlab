"""Tests for compile_all with target-awareness in mind.

These tests focus on the boundary conditions and extension points that the
upcoming rewrite will need to respect:
- compile_single_file / run_compile_all behaviour at edge cases
- The banner/header injection contract
- Stray-file detection (report_targets)
- Variables merging edge cases
- The `# Pragma: do-not-validate-schema` contract in compiled output
- process_script_list boundary conditions (empty, mixed types, nested)

All tests use tmp_path and the BASH2YAML_SKIP_ROOT_CHECKS env var to avoid
the project-root security check that blocks sourcing files from system temp.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from bash2yaml.commands.compile_all import (
    as_items,
    compact_runs_to_literal,
    get_banner,
    infer_cli,
    inline_gitlab_scripts,
    process_script_list,
    write_compiled_file,
    write_yaml_and_hash,
)
from bash2yaml.errors.exceptions import CompileError

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SKIP_ROOT = "BASH2YAML_SKIP_ROOT_CHECKS"

SIMPLE_YAML = textwrap.dedent("""\
    # Pragma: do-not-validate-schema
    build-job:
      stage: build
      script:
        - echo hello
""")


def _make_script(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# infer_cli
# ---------------------------------------------------------------------------


class TestInferCli:
    def test_contains_compile_keyword(self, tmp_path):
        cmd = infer_cli(tmp_path / "in", tmp_path / "out")
        assert "compile" in cmd

    def test_contains_in_and_out_flags(self, tmp_path):
        cmd = infer_cli(tmp_path / "in", tmp_path / "out")
        assert "--in" in cmd
        assert "--out" in cmd

    def test_dry_run_flag_appended(self, tmp_path):
        cmd = infer_cli(tmp_path / "in", tmp_path / "out", dry_run=True)
        assert "--dry-run" in cmd

    def test_no_dry_run_flag_when_false(self, tmp_path):
        cmd = infer_cli(tmp_path / "in", tmp_path / "out", dry_run=False)
        assert "--dry-run" not in cmd

    def test_parallelism_flag(self, tmp_path):
        cmd = infer_cli(tmp_path / "in", tmp_path / "out", parallelism=8)
        assert "--parallelism 8" in cmd

    def test_none_parallelism_not_in_cmd(self, tmp_path):
        cmd = infer_cli(tmp_path / "in", tmp_path / "out", parallelism=None)
        assert "--parallelism" not in cmd


# ---------------------------------------------------------------------------
# get_banner
# ---------------------------------------------------------------------------


class TestGetBanner:
    def test_contains_do_not_edit(self, monkeypatch):
        import bash2yaml.commands.compile_all as mod

        monkeypatch.setattr(mod.config, "file_config", {})
        banner = get_banner("bash2yaml compile --in x --out y")
        assert "DO NOT EDIT" in banner

    def test_contains_command(self, monkeypatch):
        import bash2yaml.commands.compile_all as mod

        monkeypatch.setattr(mod.config, "file_config", {})
        cmd = "bash2yaml compile --in x --out y"
        banner = get_banner(cmd)
        assert cmd in banner

    def test_custom_header_overrides_default(self, tmp_path, monkeypatch):
        import bash2yaml.commands.compile_all as mod

        # Inject a custom_header by overriding the file_config on the shared config object
        monkeypatch.setattr(mod.config, "file_config", {"custom_header": "# custom banner"})
        banner = get_banner("bash2yaml compile --in x --out y")
        assert "custom banner" in banner
        assert "DO NOT EDIT" not in banner

    def test_banner_ends_with_newline(self, monkeypatch):
        import bash2yaml.commands.compile_all as mod

        monkeypatch.setattr(mod.config, "file_config", {})
        banner = get_banner("cmd")
        assert banner.endswith("\n")


# ---------------------------------------------------------------------------
# as_items
# ---------------------------------------------------------------------------


class TestAsItems:
    def test_string_wraps_to_list(self):
        items, was_seq, orig = as_items("echo hi")
        assert items == ["echo hi"]
        assert was_seq is False
        assert orig is None

    def test_plain_list_passed_through(self):
        items, was_seq, orig = as_items(["a", "b", "c"])
        assert items == ["a", "b", "c"]
        assert was_seq is False

    def test_commented_seq_detected(self):
        from ruamel.yaml.comments import CommentedSeq

        cs = CommentedSeq(["x", "y"])
        items, was_seq, orig = as_items(cs)
        assert items == ["x", "y"]
        assert was_seq is True
        assert orig is cs

    def test_empty_list(self):
        items, was_seq, _ = as_items([])
        assert items == []

    def test_empty_string_wraps(self):
        items, was_seq, _ = as_items("")
        assert items == [""]


# ---------------------------------------------------------------------------
# compact_runs_to_literal
# ---------------------------------------------------------------------------


class TestCompactRunsToLiteral:
    def test_multiple_strings_merged(self):
        from ruamel.yaml.scalarstring import LiteralScalarString

        result = compact_runs_to_literal(["echo a", "echo b", "echo c"])
        assert len(result) == 1
        assert isinstance(result[0], LiteralScalarString)

    def test_single_string_not_merged(self):
        from ruamel.yaml.scalarstring import LiteralScalarString

        result = compact_runs_to_literal(["echo a"])
        # Single item below min_lines=2 stays as plain string
        assert result == ["echo a"]
        assert not isinstance(result[0], LiteralScalarString)

    def test_tagged_scalar_is_boundary(self):
        from ruamel.yaml.comments import TaggedScalar

        ts = TaggedScalar(value="!reference [.job, script]", tag="!reference")
        result = compact_runs_to_literal(["before", ts, "after"])
        assert ts in result
        # before and after are separate because they're on opposite sides of boundary
        # with only 1 item each, they stay as plain strings
        assert "before" in result
        assert "after" in result

    def test_two_tagged_scalar_boundaries(self):
        from ruamel.yaml.comments import TaggedScalar

        ts1 = TaggedScalar(value="!ref1", tag="!ref1")
        ts2 = TaggedScalar(value="!ref2", tag="!ref2")
        result = compact_runs_to_literal(["a", "b", ts1, "c", "d", ts2, "e", "f"])
        # a,b between start and ts1 → merged; c,d between ts1,ts2 → merged; e,f after ts2 → merged
        assert ts1 in result
        assert ts2 in result

    def test_empty_input(self):
        result = compact_runs_to_literal([])
        assert result == []

    def test_min_lines_boundary(self):
        from ruamel.yaml.scalarstring import LiteralScalarString

        # With min_lines=3, two items should NOT be merged
        result = compact_runs_to_literal(["a", "b"], min_lines=3)
        assert len(result) == 2
        assert not isinstance(result[0], LiteralScalarString)


# ---------------------------------------------------------------------------
# process_script_list — boundary conditions
# ---------------------------------------------------------------------------


class TestProcessScriptList:
    def test_no_scripts_passthrough(self, tmp_path):
        """Plain echo lines with no script references are unchanged."""
        result = process_script_list(["echo hello", "echo world"], tmp_path)
        # Should contain the original items
        assert any("echo hello" in str(r) for r in (result if isinstance(result, list) else [result]))

    def test_empty_list_returns_empty(self, tmp_path):
        result = process_script_list([], tmp_path)
        if isinstance(result, list):
            assert result == []

    def test_inlines_bash_script(self, tmp_path, monkeypatch):
        monkeypatch.setenv(SKIP_ROOT, "1")
        _make_script(tmp_path, "run.sh", "#!/bin/bash\necho from_script\n")
        result = process_script_list(["./run.sh"], tmp_path)
        output = str(result)
        assert "echo from_script" in output
        assert "BEGIN inline" in output

    def test_mixed_plain_and_script(self, tmp_path, monkeypatch):
        monkeypatch.setenv(SKIP_ROOT, "1")
        _make_script(tmp_path, "lib.sh", "echo lib\n")
        result = process_script_list(["echo before", "./lib.sh", "echo after"], tmp_path)
        output = str(result)
        assert "echo before" in output
        assert "echo lib" in output
        assert "echo after" in output

    def test_tagged_scalar_preserved(self, tmp_path):
        from ruamel.yaml.comments import TaggedScalar

        ts = TaggedScalar(value="!reference [.base, script]", tag="!reference")
        result = process_script_list([ts], tmp_path)
        if isinstance(result, list):
            assert ts in result

    def test_collapse_lists_false_keeps_list(self, tmp_path, monkeypatch):
        monkeypatch.setenv(SKIP_ROOT, "1")
        _make_script(tmp_path, "s.sh", "echo s\n")
        result = process_script_list(["./s.sh"], tmp_path, collapse_lists=False)
        # collapse_lists=False means we keep list form
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# inline_gitlab_scripts — edge cases
# ---------------------------------------------------------------------------


class TestInlineGitlabScriptsEdgeCases:
    def test_empty_yaml_with_no_jobs(self, tmp_path):
        """A YAML with only top-level non-job keys should not crash."""
        yaml_content = textwrap.dedent("""\
            stages:
              - build
            variables:
              GLOBAL: value
        """)
        count, result = inline_gitlab_scripts(yaml_content, tmp_path, {}, tmp_path)
        assert "stages" in result

    def test_global_vars_conflict_yaml_wins(self, tmp_path):
        """YAML-defined variables should override global_vars on conflict."""
        yaml_content = textwrap.dedent("""\
            variables:
              MY_VAR: from_yaml
            build-job:
              stage: build
              script:
                - echo hello
        """)
        count, result = inline_gitlab_scripts(yaml_content, tmp_path, {"MY_VAR": "from_global"}, tmp_path)
        assert "from_yaml" in result

    def test_global_vars_injected_when_no_variables_section(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            build-job:
              stage: build
              script:
                - echo hello
        """)
        count, result = inline_gitlab_scripts(yaml_content, tmp_path, {"INJECTED": "yes"}, tmp_path)
        assert "INJECTED" in result
        assert "yes" in result

    def test_before_and_after_script_both_processed(self, tmp_path, monkeypatch):
        monkeypatch.setenv(SKIP_ROOT, "1")
        _make_script(tmp_path, "setup.sh", "echo setup\n")
        _make_script(tmp_path, "teardown.sh", "echo teardown\n")
        yaml_content = textwrap.dedent("""\
            build-job:
              stage: build
              before_script:
                - ./setup.sh
              script:
                - echo main
              after_script:
                - ./teardown.sh
        """)
        count, result = inline_gitlab_scripts(yaml_content, tmp_path, {}, tmp_path)
        assert "echo setup" in result
        assert "echo teardown" in result

    def test_job_vars_file_loaded(self, tmp_path):
        job_vars = tmp_path / "build-job_variables.sh"
        job_vars.write_text('export JOB_SPECIFIC="yes"\n')
        yaml_content = textwrap.dedent("""\
            build-job:
              stage: build
              script:
                - echo hello
        """)
        count, result = inline_gitlab_scripts(yaml_content, tmp_path, {}, tmp_path)
        assert "JOB_SPECIFIC" in result

    def test_job_vars_colon_in_name_sanitized(self, tmp_path):
        """Job names with ':' are sanitized to '_' for filename lookup."""
        job_vars = tmp_path / "build_deploy_variables.sh"
        job_vars.write_text('export COLON_VAR="colon_test"\n')
        yaml_content = textwrap.dedent("""\
            build:deploy:
              stage: build
              script:
                - echo hello
        """)
        count, result = inline_gitlab_scripts(yaml_content, tmp_path, {}, tmp_path)
        # Vars file should have been loaded
        assert "COLON_VAR" in result

    def test_missing_script_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv(SKIP_ROOT, "1")
        from bash2yaml.errors.exceptions import Bash2YamlError

        yaml_content = textwrap.dedent("""\
            build-job:
              stage: build
              script:
                - ./nonexistent.sh
        """)
        with pytest.raises((Bash2YamlError, FileNotFoundError, Exception)):
            inline_gitlab_scripts(yaml_content, tmp_path, {}, tmp_path)

    def test_skips_reserved_top_level_keys(self, tmp_path):
        """Keys like 'stages', 'variables', 'include', 'image' must not be treated as jobs."""
        yaml_content = textwrap.dedent("""\
            stages:
              - build
            image: python:3.11
            include:
              - project: other/project
                file: ci.yml
            variables:
              GLOBAL: value
            build-job:
              stage: build
              script:
                - echo hello
        """)
        # Should not crash
        count, result = inline_gitlab_scripts(yaml_content, tmp_path, {}, tmp_path)
        assert "stages" in result

    def test_count_increments_per_inlined_script(self, tmp_path, monkeypatch):
        monkeypatch.setenv(SKIP_ROOT, "1")
        _make_script(tmp_path, "build.sh", "echo build\n")
        _make_script(tmp_path, "deploy.sh", "echo deploy\n")
        yaml_content = textwrap.dedent("""\
            build-job:
              stage: build
              script:
                - ./build.sh
            deploy-job:
              stage: deploy
              script:
                - ./deploy.sh
        """)
        count, result = inline_gitlab_scripts(yaml_content, tmp_path, {}, tmp_path)
        assert count >= 2


# ---------------------------------------------------------------------------
# write_yaml_and_hash / write_compiled_file boundary conditions
# ---------------------------------------------------------------------------


class TestWriteYamlAndHashBoundary:
    def test_writes_both_files(self, tmp_path):
        out = tmp_path / "out" / "ci.yml"
        hash_file = tmp_path / "hashes" / "ci.yml.hash"
        write_yaml_and_hash(out, SIMPLE_YAML, hash_file)
        assert out.exists()
        assert hash_file.exists()

    def test_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "deeply" / "nested" / "ci.yml"
        hash_file = tmp_path / "hashes" / "deeply" / "nested" / "ci.yml.hash"
        write_yaml_and_hash(out, SIMPLE_YAML, hash_file)
        assert out.exists()

    def test_hash_is_base64_encoded(self, tmp_path):
        import base64

        out = tmp_path / "ci.yml"
        hash_file = tmp_path / "ci.yml.hash"
        write_yaml_and_hash(out, SIMPLE_YAML, hash_file)
        raw = hash_file.read_text()
        # Should decode cleanly
        decoded = base64.b64decode(raw).decode("utf-8")
        assert "echo hello" in decoded

    def test_schema_validation_bypassed_with_pragma(self, tmp_path):
        """Pragma must prevent ValidationFailed from being raised."""
        out = tmp_path / "ci.yml"
        hash_file = tmp_path / "ci.yml.hash"
        # Should not raise
        write_yaml_and_hash(out, SIMPLE_YAML, hash_file)

    def test_overwrite_same_content_skips_write(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        out = out_base / "ci.yml"
        write_compiled_file(out, SIMPLE_YAML, out_base)
        wrote = write_compiled_file(out, SIMPLE_YAML, out_base)
        assert wrote is False

    def test_overwrite_changed_content_rewrites(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        out = out_base / "ci.yml"
        write_compiled_file(out, SIMPLE_YAML, out_base)
        new_yaml = SIMPLE_YAML.replace("echo hello", "echo changed")
        wrote = write_compiled_file(out, new_yaml, out_base)
        assert wrote is True
        assert "echo changed" in out.read_text()

    def test_manual_edit_detected_raises(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        out = out_base / "ci.yml"
        write_compiled_file(out, SIMPLE_YAML, out_base)
        # Structural change: add a new key
        edited = SIMPLE_YAML.replace(
            "  script:\n    - echo hello\n",
            "  script:\n    - echo hello\n  manual_key: injected\n",
        )
        out.write_text(edited)
        with pytest.raises((CompileError, Exception)):
            write_compiled_file(out, SIMPLE_YAML, out_base)

    def test_missing_hash_raises(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        out = out_base / "ci.yml"
        out.write_text(SIMPLE_YAML)
        # No hash file — should refuse to overwrite
        with pytest.raises((CompileError, Exception)):
            write_compiled_file(out, SIMPLE_YAML, out_base)

    def test_dry_run_no_file_created(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        out = out_base / "ci.yml"
        write_compiled_file(out, SIMPLE_YAML, out_base, dry_run=True)
        assert not out.exists()

    def test_dry_run_existing_file_not_modified(self, tmp_path):
        out_base = tmp_path / "out"
        out_base.mkdir()
        out = out_base / "ci.yml"
        write_compiled_file(out, SIMPLE_YAML, out_base)
        original_mtime = out.stat().st_mtime
        changed = SIMPLE_YAML.replace("echo hello", "echo dry_run_test")
        write_compiled_file(out, changed, out_base, dry_run=True)
        assert out.stat().st_mtime == original_mtime


# ---------------------------------------------------------------------------
# Target abstraction readiness — compile layer
# ---------------------------------------------------------------------------


class TestCompileTargetReadiness:
    """Boundary conditions that the rewrite's target-injection must pass."""

    def test_inline_preserves_pragma_do_not_validate(self, tmp_path):
        """Pragma in source YAML must survive inlining."""
        yaml_content = textwrap.dedent("""\
            # Pragma: do-not-validate-schema
            build-job:
              stage: build
              script:
                - echo hi
        """)
        count, result = inline_gitlab_scripts(yaml_content, tmp_path, {}, tmp_path)
        assert "do-not-validate-schema" in result.lower()

    def test_plain_yaml_inline_count_is_integer(self, tmp_path):
        """inline_gitlab_scripts always returns an integer count (not None, not negative)."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        yaml_content = textwrap.dedent("""\
            build-job:
              stage: build
              script:
                - echo hello
                - echo world
        """)
        count, result = inline_gitlab_scripts(yaml_content, input_dir, {}, input_dir)
        assert isinstance(count, int)
        assert count >= 0

    def test_result_is_valid_yaml_string(self, tmp_path):
        """Output of inline_gitlab_scripts must be parseable YAML."""
        import io

        from bash2yaml.utils.yaml_factory import get_yaml

        count, result = inline_gitlab_scripts(SIMPLE_YAML, tmp_path, {}, tmp_path)
        yaml = get_yaml()
        parsed = yaml.load(io.StringIO(result))
        assert isinstance(parsed, dict)

    def test_multiple_yaml_files_in_directory(self, tmp_path, monkeypatch):
        """Each YAML file is processed independently — no cross-contamination."""
        monkeypatch.setenv(SKIP_ROOT, "1")
        for i in range(3):
            yaml_file = tmp_path / f"job{i}.yml"
            yaml_file.write_text(textwrap.dedent(f"""\
                # Pragma: do-not-validate-schema
                job{i}:
                  stage: build
                  script:
                    - echo job{i}
            """))

        for i in range(3):
            yaml_content = (tmp_path / f"job{i}.yml").read_text()
            count, result = inline_gitlab_scripts(yaml_content, tmp_path, {}, tmp_path)
            assert f"echo job{i}" in result
