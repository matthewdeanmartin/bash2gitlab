# tests/test_ci_lint.py
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

import bash2gitlab.commands.lint_all as mod  # preferred path

# --- Test api_url -----------------------------------------------------------


def test_api_url_global_vs_project():
    assert mod.api_url("https://gitlab.example.com/", None) == "https://gitlab.example.com/api/v4/ci/lint"
    assert mod.api_url("https://gitlab.example.com", 123) == "https://gitlab.example.com/api/v4/projects/123/ci/lint"
    # trailing slashes should be handled
    assert mod.api_url("https://gitlab.example.com////", None) == "https://gitlab.example.com/api/v4/ci/lint"


# --- Helpers for mocking urlopen -------------------------------------------


class _FakeHTTPResponse:
    def __init__(self, data: bytes):
        self._buf = io.BytesIO(data)

    def read(self) -> bytes:
        return self._buf.getvalue()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# --- Test post_json (no real network) --------------------------------------


def test_post_json_sends_headers_and_parses(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout):
        # capture what was sent
        captured["url"] = req.full_url
        captured["data"] = req.data
        captured["headers"] = dict(req.header_items())
        # respond with valid JSON
        body = json.dumps({"ok": True}).encode("utf-8")
        return _FakeHTTPResponse(body)

    monkeypatch.setattr(mod.request, "urlopen", fake_urlopen)

    result = mod.post_json(
        url="https://gitlab.example.com/api/v4/ci/lint",
        payload={"content": "stages: []"},
        private_token="glpat-XXX",
        timeout=5.0,
    )

    assert result == {"ok": True}
    assert captured["url"].endswith("/ci/lint")
    sent = json.loads(captured["data"].decode("utf-8"))
    assert sent == {"content": "stages: []"}
    # headers include content-type and token
    hdrs = {k.lower(): v for k, v in captured["headers"].items()}
    assert hdrs["content-type"] == "application/json"
    assert hdrs["private-token"] == "glpat-XXX"


def test_post_json_invalid_json_raises(monkeypatch):
    def fake_urlopen(req, timeout):
        return _FakeHTTPResponse(b"{not-json}")

    monkeypatch.setattr(mod.request, "urlopen", fake_urlopen)

    with pytest.raises(Exception):  # noqa
        mod.post_json(
            url="https://gitlab.example.com/api/v4/ci/lint",
            payload={"content": "x"},
            private_token=None,
            timeout=1.0,
        )


# --- Test lint_single_text normalization -----------------------------------


def test_lint_single_text_global_status_valid_shape(monkeypatch):
    """GitLab sometimes returns {'status':'valid'/'invalid'}."""

    def fake_post_json(url, payload, private_token, timeout):
        assert "content" in payload and payload["content"] == "foo"
        return {"status": "valid", "errors": [], "warnings": []}

    monkeypatch.setattr(mod, "post_json", fake_post_json)

    res = mod.lint_single_text(
        "foo",
        gitlab_url="https://gitlab.example.com",
        project_id=None,
    )
    assert res.ok is True
    assert res.status == "valid"
    assert res.errors == []
    assert res.warnings == []
    assert res.merged_yaml is None
    assert res.path == Path("<string>")


def test_lint_single_text_global_valid_bool_shape(monkeypatch):
    """Other versions return {'valid': True/False} only."""

    def fake_post_json(url, payload, private_token, timeout):
        return {"valid": False, "errors": ["bad!"]}

    monkeypatch.setattr(mod, "post_json", fake_post_json)

    res = mod.lint_single_text(
        "foo",
        gitlab_url="https://gitlab.example.com",
        project_id=None,
    )
    assert res.ok is False
    assert res.status in {"invalid", "False"}  # normalized code uses 'invalid'
    assert [e.message for e in res.errors] == ["bad!"]


def test_lint_single_text_collects_structured_messages(monkeypatch):
    def fake_post_json(url, payload, private_token, timeout):
        return {
            "valid": False,
            "errors": [{"message": "E1", "line": 3, "severity": "error"}],
            "warnings": [{"message": "W1", "severity": "warning"}],
        }

    monkeypatch.setattr(mod, "post_json", fake_post_json)

    res = mod.lint_single_text("x", gitlab_url="https://g", project_id=None)
    assert res.ok is False
    assert len(res.errors) == 1 and res.errors[0].message == "E1" and res.errors[0].line == 3
    assert len(res.warnings) == 1 and res.warnings[0].message == "W1"


def test_lint_single_text_project_params_and_merged_yaml(monkeypatch):
    captured = {}

    def fake_post_json(url, payload, private_token, timeout):
        captured["url"] = url
        captured["payload"] = payload
        # GitLab may use merged_yaml or mergedYaml depending on version.
        return {"valid": True, "mergedYaml": "stages:\n- test\n"}

    monkeypatch.setattr(mod, "post_json", fake_post_json)

    res = mod.lint_single_text(
        "content",
        gitlab_url="https://gitlab.example.com",
        private_token=None,
        project_id=42,
        ref="main",
        include_merged_yaml=True,
        timeout=2.0,
    )

    assert "/projects/42/ci/lint" in captured["url"]
    assert captured["payload"]["ref"] == "main"
    assert captured["payload"]["include_merged_yaml"] is True
    assert res.ok is True
    assert res.merged_yaml.strip().startswith("stages:")


def test_lint_single_file_reads_and_delegates(tmp_path, monkeypatch):
    p = tmp_path / "x.yaml"
    p.write_text("foo: bar", encoding="utf-8")

    called = {}

    def fake_lint_single_text(content, **kwargs):
        called["content"] = content
        called["kwargs"] = kwargs
        return mod.LintResult(
            path=kwargs["synthetic_path"],
            ok=True,
            status="valid",
            errors=[],
            warnings=[],
            merged_yaml=None,
            raw_response={"valid": True},
        )

    monkeypatch.setattr(mod, "lint_single_text", fake_lint_single_text)

    res = mod.lint_single_file(
        p,
        gitlab_url="https://gitlab.example.com",
        project_id=None,
    )

    assert called["content"] == "foo: bar"
    assert called["kwargs"]["gitlab_url"].startswith("https://gitlab.example.com")
    assert res.ok is True
    assert res.path == p


# --- Test discovery and folder orchestration --------------------------------


def test_discover_yaml_files_finds_both_suffixes(tmp_path):
    (tmp_path / "a.yaml").write_text("a: 1")
    (tmp_path / "b.yml").write_text("b: 2")
    (tmp_path / "c.txt").write_text("nope")
    found = mod.discover_yaml_files(tmp_path)
    assert [p.name for p in found] == ["a.yaml", "b.yml"]


def test_lint_output_folder_no_files_logs_and_returns_empty(tmp_path, caplog):
    out = mod.lint_output_folder(
        tmp_path,
        gitlab_url="https://gitlab.example.com",
    )
    assert out == []
    assert any("No YAML files found" in m for m in caplog.text.splitlines())


def test_lint_output_folder_serial_calls_each(tmp_path, monkeypatch):
    files = [
        tmp_path / "f1.yaml",
        tmp_path / "f2.yml",
    ]
    for i, f in enumerate(files, start=1):
        f.write_text(f"stages:\n- s{i}\n")

    # Make discover deterministic and only return ours
    monkeypatch.setattr(mod, "discover_yaml_files", lambda root: files)

    calls = []

    def fake_lint_single_file(path, **kwargs):
        calls.append(path)
        return mod.LintResult(
            path=path,
            ok=True,
            status="valid",
            errors=[],
            warnings=[],
            merged_yaml=None,
            raw_response={"valid": True},
        )

    monkeypatch.setattr(mod, "lint_single_file", fake_lint_single_file)

    results = mod.lint_output_folder(
        tmp_path,
        gitlab_url="https://gitlab.example.com",
        project_id=777,
        ref="main",
        include_merged_yaml=True,
        parallelism=1,  # force serial path (easier to test)
        timeout=3.0,
    )

    assert [p.name for p in calls] == ["f1.yaml", "f2.yml"]
    assert len(results) == 2 and all(r.ok for r in results)


# --- Test summarize_results --------------------------------------------------


def test_summarize_results_logging_and_counts(monkeypatch, caplog, tmp_path):
    # Make logging use short paths we control
    monkeypatch.setattr(mod, "short_path", lambda p: p.name)

    ok_res = mod.LintResult(
        path=tmp_path / "ok.yml",
        ok=True,
        status="valid",
        errors=[],
        warnings=[mod.LintIssue("warning", "Heads up!", None)],
        merged_yaml=None,
        raw_response={"valid": True},
    )
    bad_res = mod.LintResult(
        path=tmp_path / "bad.yml",
        ok=False,
        status="invalid",
        errors=[mod.LintIssue("error", "No stages defined", 2)],
        warnings=[],
        merged_yaml=None,
        raw_response={"valid": False},
    )

    ok, fail = mod.summarize_results([ok_res, bad_res])

    assert (ok, fail) == (1, 1)
    text = caplog.text

    assert "warning" in text.lower() and "Heads up!" in text
    assert "INVALID: bad.yml (status=invalid)" in text
    assert "bad.yml:2: No stages defined" in text
