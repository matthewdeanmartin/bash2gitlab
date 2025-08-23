from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from ruamel.yaml.scalarstring import LiteralScalarString

# Module under test
from bash2gitlab.commands import compile_all as mod
from bash2gitlab.utils.yaml_factory import get_yaml

# ---------- helpers for monkeypatching ----------


class _DummyHook:
    """Very small plugin hook stub so we don't depend on real plugin discovery."""

    def extract_script_path(self, line: str) -> str | None:
        # We accept either "./script.sh" or "bash ./script.sh" style lines
        return "./script.sh" if "script.sh" in line else None

    def inline_command(self, line: str, scripts_root: Path):
        # No interpreter-based inlining in these tests
        return None


class _DummyPM:
    hook = _DummyHook()


def _read_bash_script_passthrough(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _always_valid_ci(*args, **kwargs):
    # GitLabCIValidator.validate_ci_config returns (ok, problems)
    return True, []


class _DiffStats(SimpleNamespace):
    changed: int = 0
    insertions: int = 0
    deletions: int = 0


def _diff_stats_stub(_diff_text: str) -> _DiffStats:
    # Keep it simple; numbers don't matter for our assertions
    return _DiffStats(changed=1, insertions=1, deletions=0)


# ---------- fixtures ----------


@pytest.fixture(autouse=True)
def minimal_monkeypatch(monkeypatch):
    """
    Apply minimal, targeted monkeypatches across tests:

    - Plugin manager -> tiny stub that can find "./script.sh"
    - Bash reader -> just reads the file from disk
    - CI validator -> always OK (we're not testing GitLab API here)
    - Diff helpers -> light stubs to avoid depending on formatting details
    """
    monkeypatch.setattr(mod, "get_pm", lambda: _DummyPM())
    monkeypatch.setattr(mod, "read_bash_script", _read_bash_script_passthrough)

    # validator lives in class GitLabCIValidator; patch its method
    monkeypatch.setattr(mod.GitLabCIValidator, "validate_ci_config", _always_valid_ci)

    # diff helpers used only for logging/metrics in write paths
    monkeypatch.setattr(mod.diff_helpers, "diff_stats", _diff_stats_stub)
    # Keep unified_diff callable; its exact output is not asserted


# ---------- tests ----------


def test_process_script_list_inlines_and_collapses_to_literal(tmp_path: Path):
    """process_script_list should inline ./script.sh and collapse to a single literal block."""
    scripts_root = tmp_path
    (scripts_root / "script.sh").write_text('#!/usr/bin/env bash\necho "hello"\n', encoding="utf-8")

    # Provide a simple one-line list with a direct ./script.sh reference
    script = ["./script.sh"]

    result = mod.process_script_list(script, scripts_root)

    # Expect a single LiteralScalarString with BEGIN/END markers and the echoed line inside
    assert isinstance(result, LiteralScalarString)
    text = str(result)
    assert "# >>> BEGIN inline: script.sh" in text
    assert 'echo "hello"' in text
    assert "# <<< END inline" in text
    # Should be multi-line block
    assert "\n" in text


def test_inline_gitlab_scripts_merges_globals_and_job_vars_and_inlines(tmp_path: Path, monkeypatch):
    """
    inline_gitlab_scripts should:
      - inline ./script.sh
      - merge global variables (global wins only when YAML absent; YAML entries keep precedence)
      - merge *job-specific* variables from <job>_variables.sh with YAML variables taking precedence
    """
    scripts_root = tmp_path
    (scripts_root / "script.sh").write_text('echo "hi from job"\n', encoding="utf-8")

    # Create job-specific variables file: "build_variables.sh"
    (scripts_root / "build_variables.sh").write_text("FROM_FILE=1\nKEEP_ME=yes\n", encoding="utf-8")

    # Make parse_env_file very simple for this test (KEY=VAL lines)
    def parse_env_file_lines(content: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
        return out

    monkeypatch.setattr(mod, "parse_env_file", parse_env_file_lines)

    yaml_text = """
variables:
  YAML_VAR: from_yaml
  KEEP_ME: override_me
build:
  stage: test
  script:
    - ./script.sh
  variables:
    KEEP_ME: from_yaml_job
"""

    global_vars = {"GLOBAL": "G1", "YAML_VAR": "from_global_should_not_win"}

    inlined_count, out_text = mod.inline_gitlab_scripts(
        gitlab_ci_yaml=yaml_text,
        scripts_root=scripts_root,
        global_vars=global_vars,
        uncompiled_path=scripts_root,
    )

    assert inlined_count >= 2  # variables merge + script inlining at minimum

    # Load resulting YAML to assert structure/values
    yaml = get_yaml()
    data = yaml.load(io.StringIO(out_text))

    # 1) script inlined into a literal (acceptable if list preserved too; check content either way)
    script_block = data["build"]["script"]
    if isinstance(script_block, list):
        # list retained; entries should contain inline markers around the contents
        joined = "\n".join(str(x) for x in script_block)
        assert "# >>> BEGIN inline: script.sh" in joined
        assert "# <<< END inline" in joined
    else:
        # collapsed to literal
        assert isinstance(script_block, LiteralScalarString)
        s = str(script_block)
        assert "# >>> BEGIN inline: script.sh" in s
        assert 'echo "hi from job"' in s

    # 2) Global variables merged and YAML precedence maintained
    assert data["variables"]["GLOBAL"] == "G1"
    assert data["variables"]["YAML_VAR"] == "from_yaml"  # YAML wins over global for same key

    # 3) Job-specific variables merged; YAML job vars take precedence
    assert data["build"]["variables"]["FROM_FILE"] == "1"
    assert data["build"]["variables"]["KEEP_ME"] == "from_yaml_job"  # YAML job var wins


def test_write_compiled_file_creates_and_hashes_then_no_rewrite_on_same_content(tmp_path: Path, monkeypatch):
    """
    Validate write_compiled_file:
      - First write creates file and .hash
      - Second write with equivalent content (yaml_is_same True) does nothing and returns False
    """
    target = tmp_path / ".gitlab-ci.yml"
    content = "stages: [test]\nbuild:\n  stage: test\n  script:\n    - echo hi\n"

    # No rewrite on identical content: force yaml_is_same to return True
    monkeypatch.setattr(mod, "yaml_is_same", lambda a, b: True)

    wrote = mod.write_compiled_file(target, content, dry_run=False)
    assert wrote is True
    assert target.exists()
    hash_file = tmp_path / ".gitlab-ci.yml.hash"
    assert hash_file.exists()
    assert hash_file.read_text(encoding="utf-8").strip() != ""

    wrote_again = mod.write_compiled_file(target, content, dry_run=False)
    assert wrote_again is False  # unchanged; skipped


def test_run_compile_all_end_to_end_inlines_and_writes(tmp_path: Path, monkeypatch):
    """
    End-to-end compile:
      - uncompiled dir has a single YAML referencing ./script.sh
      - output dir starts empty
      - force=True to skip needs_compilation checks
      - result file exists, contains banner + inline markers
    """
    uncompiled = tmp_path / "uncompiled"
    output = tmp_path / "compiled"
    uncompiled.mkdir()

    # tiny pipeline with a single ./script.sh reference
    (uncompiled / ".gitlab-ci.yml").write_text(
        "build:\n  stage: test\n  script:\n    - ./script.sh\n", encoding="utf-8"
    )
    (uncompiled / "script.sh").write_text('echo "E2E"\n', encoding="utf-8")

    # Keep report_targets simple: no stray files
    monkeypatch.setattr(mod, "report_targets", lambda _p: [])

    # Force mode avoids needs_compilation; still patch to be safe if called
    monkeypatch.setattr(mod, "needs_compilation", lambda _p: True)
    monkeypatch.setattr(mod, "mark_compilation_complete", lambda _p: None)

    total_inlined = mod.run_compile_all(
        uncompiled_path=uncompiled,
        output_path=output,
        dry_run=False,
        parallelism=None,
        force=True,
    )

    assert total_inlined >= 1
    out_file = output / ".gitlab-ci.yml"
    assert out_file.exists()
    text = out_file.read_text(encoding="utf-8")
    # Banner should be prepended when any inlining happened
    assert "DO NOT EDIT" in text
    # Inline markers should be present
    assert "# >>> BEGIN inline: script.sh" in text
    assert "# <<< END inline" in text
