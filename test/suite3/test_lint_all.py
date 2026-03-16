"""Tests for lint_all — data structures, URL building, folder discovery, result summarization.

The network-dependent functions (post_json, lint_single_text, lint_single_file,
lint_output_folder) are tested at the unit level via lightweight stubs rather than
live HTTP calls. Folder discovery and summarize_results are tested against the
filesystem with tmp_path.

Focus areas for the upcoming rewrite:
- api_url must be composable for different platforms (GitLab today, others tomorrow).
- LintResult / LintIssue are frozen dataclasses — their shape is the API contract.
- discover_yaml_files drives what gets linted; any target-awareness hooks in here.
- summarize_results only reads LintResult fields — safe to extend without breaking.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from bash2gitlab.commands.lint_all import (
    LintIssue,
    LintResult,
    api_url,
    discover_yaml_files,
    lint_single_text,
    summarize_results,
)

# ---------------------------------------------------------------------------
# LintIssue dataclass
# ---------------------------------------------------------------------------


class TestLintIssue:
    def test_minimal_construction(self):
        issue = LintIssue(severity="error", message="something broke")
        assert issue.severity == "error"
        assert issue.message == "something broke"
        assert issue.line is None

    def test_with_line_number(self):
        issue = LintIssue(severity="warning", message="deprecated key", line=42)
        assert issue.line == 42

    def test_frozen(self):
        issue = LintIssue(severity="error", message="msg")
        with pytest.raises((AttributeError, TypeError)):
            issue.severity = "warning"  # type: ignore[misc]

    def test_equality(self):
        a = LintIssue(severity="error", message="m", line=1)
        b = LintIssue(severity="error", message="m", line=1)
        assert a == b

    def test_inequality_on_message(self):
        a = LintIssue(severity="error", message="msg1")
        b = LintIssue(severity="error", message="msg2")
        assert a != b


# ---------------------------------------------------------------------------
# LintResult dataclass
# ---------------------------------------------------------------------------


class TestLintResult:
    def _make(self, ok=True, status="valid", errors=None, warnings=None):
        return LintResult(
            path=Path("ci.yml"),
            ok=ok,
            status=status,
            errors=errors or [],
            warnings=warnings or [],
            merged_yaml=None,
            raw_response={},
        )

    def test_ok_result(self):
        r = self._make(ok=True, status="valid")
        assert r.ok is True
        assert r.status == "valid"

    def test_failed_result(self):
        err = LintIssue(severity="error", message="job missing script")
        r = self._make(ok=False, status="invalid", errors=[err])
        assert r.ok is False
        assert len(r.errors) == 1

    def test_frozen(self):
        r = self._make()
        with pytest.raises((AttributeError, TypeError)):
            r.ok = False  # type: ignore[misc]

    def test_merged_yaml_none_by_default(self):
        r = self._make()
        assert r.merged_yaml is None

    def test_with_merged_yaml(self):
        r = LintResult(
            path=Path("ci.yml"),
            ok=True,
            status="valid",
            errors=[],
            warnings=[],
            merged_yaml="key: value\n",
            raw_response={},
        )
        assert r.merged_yaml == "key: value\n"

    def test_raw_response_preserved(self):
        raw = {"status": "valid", "valid": True, "errors": []}
        r = LintResult(
            path=Path("ci.yml"),
            ok=True,
            status="valid",
            errors=[],
            warnings=[],
            merged_yaml=None,
            raw_response=raw,
        )
        assert r.raw_response is raw


# ---------------------------------------------------------------------------
# api_url
# ---------------------------------------------------------------------------


class TestApiUrl:
    def test_global_endpoint_no_project(self):
        url = api_url("https://gitlab.example.com", None)
        assert url == "https://gitlab.example.com/api/v4/ci/lint"

    def test_project_scoped_endpoint(self):
        url = api_url("https://gitlab.example.com", 1234)
        assert url == "https://gitlab.example.com/api/v4/projects/1234/ci/lint"

    def test_trailing_slash_stripped(self):
        url = api_url("https://gitlab.example.com/", None)
        assert not url.endswith("//")
        assert url.endswith("/lint")

    def test_gitlab_com(self):
        url = api_url("https://gitlab.com", None)
        assert "gitlab.com" in url
        assert "ci/lint" in url

    def test_different_base_url(self):
        """Base URL should be composable — important for self-hosted instances."""
        url = api_url("https://my-gitlab.internal", 99)
        assert "my-gitlab.internal" in url
        assert "99" in url

    def test_project_id_zero_treated_as_none_behavior(self):
        """project_id=0 is falsy — documents current behavior for edge case."""
        # api_url receives 0 which is falsy in Python but a valid int
        # Document: currently 0 means project-scoped (it's not None)
        url = api_url("https://gitlab.com", 0)
        assert "projects/0" in url


# ---------------------------------------------------------------------------
# discover_yaml_files
# ---------------------------------------------------------------------------


class TestDiscoverYamlFiles:
    def test_finds_yml_files(self, tmp_path):
        (tmp_path / "a.yml").write_text("key: value\n")
        (tmp_path / "b.yaml").write_text("key: value\n")
        files = discover_yaml_files(tmp_path)
        names = {f.name for f in files}
        assert "a.yml" in names
        assert "b.yaml" in names

    def test_ignores_non_yaml_files(self, tmp_path):
        (tmp_path / "script.sh").write_text("echo hi\n")
        (tmp_path / "readme.txt").write_text("readme\n")
        (tmp_path / "ci.yml").write_text("key: v\n")
        files = discover_yaml_files(tmp_path)
        assert all(f.suffix in (".yml", ".yaml") for f in files)

    def test_finds_nested_yaml(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "ci.yml").write_text("key: value\n")
        files = discover_yaml_files(tmp_path)
        assert any("subdir" in str(f) for f in files)

    def test_empty_dir_returns_empty(self, tmp_path):
        files = discover_yaml_files(tmp_path)
        assert files == []

    def test_returns_sorted_deterministic(self, tmp_path):
        for name in ["z.yml", "a.yml", "m.yml"]:
            (tmp_path / name).write_text("k: v\n")
        files = discover_yaml_files(tmp_path)
        names = [f.name for f in files]
        assert names == sorted(names)

    def test_only_files_not_dirs(self, tmp_path):
        (tmp_path / "subdir.yml").mkdir()  # directory with .yml name
        (tmp_path / "real.yml").write_text("k: v\n")
        files = discover_yaml_files(tmp_path)
        assert all(f.is_file() for f in files)

    def test_deeply_nested(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "deep.yml").write_text("k: v\n")
        files = discover_yaml_files(tmp_path)
        assert any("deep.yml" in str(f) for f in files)


# ---------------------------------------------------------------------------
# summarize_results
# ---------------------------------------------------------------------------


class TestSummarizeResults:
    def _make_result(self, path, ok, errors=None, warnings=None):
        return LintResult(
            path=Path(path),
            ok=ok,
            status="valid" if ok else "invalid",
            errors=errors or [],
            warnings=warnings or [],
            merged_yaml=None,
            raw_response={},
        )

    def test_all_ok(self):
        results = [self._make_result(f"ci{i}.yml", ok=True) for i in range(3)]
        ok, fail = summarize_results(results)
        assert ok == 3
        assert fail == 0

    def test_all_failed(self):
        results = [
            self._make_result(f"ci{i}.yml", ok=False, errors=[LintIssue(severity="error", message="bad")])
            for i in range(2)
        ]
        ok, fail = summarize_results(results)
        assert ok == 0
        assert fail == 2

    def test_mixed_results(self):
        results = [
            self._make_result("a.yml", ok=True),
            self._make_result("b.yml", ok=False, errors=[LintIssue(severity="error", message="bad")]),
            self._make_result("c.yml", ok=True),
        ]
        ok, fail = summarize_results(results)
        assert ok == 2
        assert fail == 1

    def test_empty_returns_zeros(self):
        ok, fail = summarize_results([])
        assert ok == 0
        assert fail == 0

    def test_return_type_is_tuple_of_ints(self):
        results = [self._make_result("a.yml", ok=True)]
        result = summarize_results(results)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert all(isinstance(v, int) for v in result)


# ---------------------------------------------------------------------------
# lint_single_text — stub the HTTP call
# ---------------------------------------------------------------------------


class TestLintSingleText:
    def _fake_post(self, resp_dict):
        """Return a patcher that makes post_json return resp_dict."""
        return patch("bash2gitlab.commands.lint_all.post_json", return_value=resp_dict)

    def test_valid_response_parsed(self):
        resp = {"valid": True, "status": "valid", "errors": [], "warnings": []}
        with self._fake_post(resp):
            result = lint_single_text("key: value\n", gitlab_url="https://gitlab.com")
        assert result.ok is True
        assert result.status == "valid"
        assert result.errors == []

    def test_invalid_response_parsed(self):
        resp = {
            "valid": False,
            "status": "invalid",
            "errors": [{"severity": "error", "message": "missing script"}],
            "warnings": [],
        }
        with self._fake_post(resp):
            result = lint_single_text("bad: yaml\n", gitlab_url="https://gitlab.com")
        assert result.ok is False
        assert len(result.errors) == 1
        assert result.errors[0].message == "missing script"

    def test_warnings_parsed(self):
        resp = {
            "valid": True,
            "status": "valid",
            "errors": [],
            "warnings": [{"severity": "warning", "message": "deprecated key", "line": 3}],
        }
        with self._fake_post(resp):
            result = lint_single_text("key: value\n", gitlab_url="https://gitlab.com")
        assert len(result.warnings) == 1
        assert result.warnings[0].line == 3

    def test_merged_yaml_extracted(self):
        resp = {
            "valid": True,
            "status": "valid",
            "errors": [],
            "warnings": [],
            "merged_yaml": "resolved: yaml\n",
        }
        with self._fake_post(resp):
            result = lint_single_text("k: v\n", gitlab_url="https://gitlab.com", include_merged_yaml=True)
        assert result.merged_yaml == "resolved: yaml\n"

    def test_synthetic_path_used(self):
        resp = {"valid": True, "status": "valid", "errors": [], "warnings": []}
        with self._fake_post(resp):
            result = lint_single_text(
                "k: v\n",
                gitlab_url="https://gitlab.com",
                synthetic_path=Path("my/fake.yml"),
            )
        assert result.path == Path("my/fake.yml")

    def test_default_path_is_string_sentinel(self):
        resp = {"valid": True, "status": "valid", "errors": [], "warnings": []}
        with self._fake_post(resp):
            result = lint_single_text("k: v\n", gitlab_url="https://gitlab.com")
        assert "<string>" in str(result.path)

    def test_response_without_status_field(self):
        """Older GitLab API versions may omit 'status'; must not crash."""
        resp = {"valid": True, "errors": [], "warnings": []}
        with self._fake_post(resp):
            result = lint_single_text("k: v\n", gitlab_url="https://gitlab.com")
        assert result.ok is True

    def test_string_errors_in_list(self):
        """Some GitLab versions return errors as plain strings, not dicts."""
        resp = {
            "valid": False,
            "status": "invalid",
            "errors": ["plain string error"],
            "warnings": [],
        }
        with self._fake_post(resp):
            result = lint_single_text("bad\n", gitlab_url="https://gitlab.com")
        assert len(result.errors) == 1
        assert result.errors[0].message == "plain string error"

    def test_raw_response_preserved(self):
        resp = {"valid": True, "status": "valid", "errors": [], "warnings": [], "extra": "data"}
        with self._fake_post(resp):
            result = lint_single_text("k: v\n", gitlab_url="https://gitlab.com")
        assert result.raw_response["extra"] == "data"

    def test_project_id_included_in_url(self):
        """When project_id is given, url must include it."""
        resp = {"valid": True, "status": "valid", "errors": [], "warnings": []}
        captured_urls = []

        def fake_post(url, payload, *, private_token, timeout):
            captured_urls.append(url)
            return resp

        with patch("bash2gitlab.commands.lint_all.post_json", side_effect=fake_post):
            lint_single_text("k: v\n", gitlab_url="https://gitlab.com", project_id=55)

        assert len(captured_urls) == 1
        assert "projects/55" in captured_urls[0]


# ---------------------------------------------------------------------------
# Target platform readiness
# ---------------------------------------------------------------------------


class TestTargetAwarenessReadiness:
    """Documents contracts that must hold when multi-platform support is added.

    These test the current behavior as a baseline; the rewrite must preserve
    or explicitly change these behaviors.
    """

    def test_api_url_is_composable_with_any_host(self):
        """The URL builder must accept arbitrary hosts for self-hosted installs."""
        for host in [
            "https://gitlab.example.com",
            "https://gitlab.internal.corp",
            "http://localhost:8080",
        ]:
            url = api_url(host, None)
            assert host.rstrip("/") in url

    def test_lint_result_path_is_pathlib(self):
        """Path field is always a Path — downstream code can call .name/.suffix."""
        r = LintResult(
            path=Path("ci.yml"),
            ok=True,
            status="valid",
            errors=[],
            warnings=[],
            merged_yaml=None,
            raw_response={},
        )
        assert isinstance(r.path, Path)

    def test_discover_finds_both_yml_and_yaml_extensions(self, tmp_path):
        """Both .yml and .yaml must be discovered regardless of target platform."""
        (tmp_path / "gitlab-ci.yml").write_text("k: v\n")
        (tmp_path / "github-actions.yaml").write_text("k: v\n")
        files = discover_yaml_files(tmp_path)
        assert len(files) == 2
