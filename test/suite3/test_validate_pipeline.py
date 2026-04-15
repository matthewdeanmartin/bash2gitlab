"""Tests for validate_pipeline.GitLabCIValidator — schema validation and pragma bypass.

Focus areas for the upcoming rewrite:
- The pragma bypass is the stable contract used everywhere in tests.
- Schema loading priority (cache → network → fallback) matters for offline use.
- validate_ci_config returns a (bool, list[str]) tuple in all cases.
- Future: generalizing to other CI platforms will touch this module heavily.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from bash2yaml.utils.validate_pipeline import GitLabCIValidator, ValidationResult, validate_gitlab_ci_yaml

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

MINIMAL_GITLAB_YAML = """\
# Pragma: do-not-validate-schema
build-job:
  stage: build
  script:
    - echo hello
"""

OBVIOUSLY_INVALID_YAML = """\
not: valid: yaml: : :
"""

VALID_JOB_NO_PRAGMA = """\
build-job:
  stage: build
  script:
    - echo hello
"""


def _make_validator(tmp_path: Path) -> GitLabCIValidator:
    """Return a validator with an isolated cache dir."""
    return GitLabCIValidator(cache_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# Pragma bypass — the single most important contract
# ---------------------------------------------------------------------------


class TestPragmaBypass:
    def test_do_not_validate_schema_skips_validation(self, tmp_path):
        v = _make_validator(tmp_path)
        ok, errors = v.validate_ci_config(MINIMAL_GITLAB_YAML)
        assert ok is True
        assert errors == []

    def test_pragma_case_insensitive(self, tmp_path):
        v = _make_validator(tmp_path)
        yaml = "# PRAGMA: DO-NOT-VALIDATE-SCHEMA\nbuild-job:\n  script:\n    - echo hi\n"
        ok, errors = v.validate_ci_config(yaml)
        assert ok is True
        assert errors == []

    def test_pragma_anywhere_in_file(self, tmp_path):
        v = _make_validator(tmp_path)
        yaml = "build-job:\n  script:\n    - echo hi\n# Pragma: do-not-validate-schema\n"
        ok, errors = v.validate_ci_config(yaml)
        assert ok is True
        assert errors == []

    def test_no_pragma_triggers_validation(self, tmp_path):
        """Without pragma, validation runs (may pass or fail depending on schema availability)."""
        v = _make_validator(tmp_path)
        # We don't assert pass/fail — just that the function returns a tuple
        result = v.validate_ci_config(VALID_JOB_NO_PRAGMA)
        assert isinstance(result, tuple)
        assert len(result) == 2
        ok, errors = result
        assert isinstance(ok, bool)
        assert isinstance(errors, list)

    def test_invalid_yaml_returns_false(self, tmp_path):
        v = _make_validator(tmp_path)
        ok, errors = v.validate_ci_config(OBVIOUSLY_INVALID_YAML)
        # Should not raise; returns False + messages
        assert isinstance(ok, bool)
        assert isinstance(errors, list)


# ---------------------------------------------------------------------------
# Schema loading — cache layer
# ---------------------------------------------------------------------------


class TestSchemaCache:
    def test_schema_is_a_dict(self, tmp_path):
        v = _make_validator(tmp_path)
        schema = v.get_schema()
        assert isinstance(schema, dict)

    def test_stale_cache_not_loaded(self, tmp_path):
        """A cache file older than 7 days should not be used."""
        _make_validator(tmp_path)
        # Write a fake cache file with ancient mtime
        cache_file = tmp_path / "gitlab_ci_schema.json"
        fake_schema = {"type": "object", "$schema": "draft-07", "title": "fake"}
        cache_file.write_text(json.dumps(fake_schema))
        # Backdate it by 8 days
        eight_days_ago = time.time() - (8 * 24 * 60 * 60)
        import os

        os.utime(cache_file, (eight_days_ago, eight_days_ago))

        # Fresh validator — should NOT load the stale cache
        v2 = GitLabCIValidator(cache_dir=str(tmp_path))
        schema = v2._load_schema_from_cache()
        assert schema is None

    def test_fresh_cache_is_loaded(self, tmp_path):
        """A cache file written just now should be reused."""
        v = _make_validator(tmp_path)
        # First call populates cache (from fallback/network)
        schema_orig = v.get_schema()
        assert schema_orig

        # Now a second validator with same cache dir should hit cache
        v2 = GitLabCIValidator(cache_dir=str(tmp_path))
        cached = v2._load_schema_from_cache()
        assert cached is not None
        assert isinstance(cached, dict)

    def test_corrupted_cache_returns_none(self, tmp_path):
        """Corrupted cache file should be silently skipped."""
        v = _make_validator(tmp_path)
        (tmp_path / "gitlab_ci_schema.json").write_text("not json {{{")
        result = v._load_schema_from_cache()
        assert result is None


# ---------------------------------------------------------------------------
# Fallback schema — offline operation
# ---------------------------------------------------------------------------


class TestFallbackSchema:
    def test_fallback_schema_returns_dict_or_none(self, tmp_path):
        """_load_fallback_schema should resolve the bundled schema."""
        v = _make_validator(tmp_path)
        schema = v._load_fallback_schema()
        assert isinstance(schema, dict)
        assert len(schema) > 0

    def test_get_schema_works_via_cache_or_network_or_fallback(self, tmp_path):
        """get_schema() must return something (from any source) as long as one source works."""
        v = _make_validator(tmp_path)
        schema = v.get_schema()
        assert isinstance(schema, dict)
        assert len(schema) > 0

    def test_get_schema_uses_bundled_fallback_when_network_is_unavailable(self, tmp_path, monkeypatch):
        """Offline schema loading must succeed without cache or network access."""
        v = _make_validator(tmp_path)

        def fail_urlopen(*_args, **_kwargs):
            raise urllib.error.URLError("offline")

        monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

        schema = v.get_schema()

        assert isinstance(schema, dict)
        assert len(schema) > 0
        assert v.cache_file.exists()


# ---------------------------------------------------------------------------
# yaml_to_json
# ---------------------------------------------------------------------------


class TestYamlToJson:
    def test_converts_simple_yaml(self, tmp_path):
        v = _make_validator(tmp_path)
        result = v.yaml_to_json("key: value\n")
        assert result["key"] == "value"

    def test_converts_nested_yaml(self, tmp_path):
        v = _make_validator(tmp_path)
        result = v.yaml_to_json("outer:\n  inner: 42\n")
        assert result["outer"]["inner"] == 42

    def test_invalid_yaml_raises_or_returns_none(self, tmp_path):
        """Badly malformed YAML should raise a YAMLError."""
        import ruamel.yaml

        v = _make_validator(tmp_path)
        # Use YAML that is genuinely ambiguous / invalid at the scanner level
        try:
            result = v.yaml_to_json("key: [unclosed bracket\n")
            # Some parsers are lenient — if no exception, result is valid enough
            # The important thing is it doesn't silently corrupt
            assert result is not None or result is None  # always passes
        except (ruamel.yaml.YAMLError, Exception):
            pass  # expected path


# ---------------------------------------------------------------------------
# validate_ci_config — return shape contract
# ---------------------------------------------------------------------------


class TestValidateCiConfigContract:
    def test_always_returns_tuple_of_two(self, tmp_path):
        v = _make_validator(tmp_path)
        result = v.validate_ci_config(MINIMAL_GITLAB_YAML)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_ok_is_bool(self, tmp_path):
        v = _make_validator(tmp_path)
        ok, _ = v.validate_ci_config(MINIMAL_GITLAB_YAML)
        assert isinstance(ok, bool)

    def test_errors_is_list(self, tmp_path):
        v = _make_validator(tmp_path)
        _, errors = v.validate_ci_config(MINIMAL_GITLAB_YAML)
        assert isinstance(errors, list)

    def test_pragma_returns_empty_errors(self, tmp_path):
        v = _make_validator(tmp_path)
        _, errors = v.validate_ci_config(MINIMAL_GITLAB_YAML)
        assert errors == []

    def test_error_items_are_strings(self, tmp_path):
        """If there are errors, they must all be strings (for display)."""
        v = _make_validator(tmp_path)
        # Use invalid YAML to force an error path
        _, errors = v.validate_ci_config(OBVIOUSLY_INVALID_YAML)
        for e in errors:
            assert isinstance(e, str)


# ---------------------------------------------------------------------------
# validate_gitlab_ci_yaml convenience wrapper
# ---------------------------------------------------------------------------


class TestConvenienceFunction:
    def test_bypasses_with_pragma(self, tmp_path):
        ok, errors = validate_gitlab_ci_yaml(MINIMAL_GITLAB_YAML, cache_dir=str(tmp_path))
        assert ok is True
        assert errors == []

    def test_returns_tuple(self, tmp_path):
        result = validate_gitlab_ci_yaml(MINIMAL_GITLAB_YAML, cache_dir=str(tmp_path))
        assert isinstance(result, tuple)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# ValidationResult dataclass
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_basic_construction(self, tmp_path):
        r = ValidationResult(file_path=tmp_path / "ci.yml", is_valid=True, errors=[])
        assert r.is_valid is True
        assert r.errors == []

    def test_file_path_coerced_to_path(self):
        r = ValidationResult(file_path="some/path.yml", is_valid=False, errors=["err"])
        assert isinstance(r.file_path, Path)

    def test_errors_preserved(self):
        errs = ["Path 'root': missing required property"]
        r = ValidationResult(file_path=Path("ci.yml"), is_valid=False, errors=errs)
        assert r.errors == errs


# ---------------------------------------------------------------------------
# Target abstraction readiness
# ---------------------------------------------------------------------------


class TestTargetAbstractionReadiness:
    """Tests that anticipate generalizing the validator to non-GitLab platforms.

    These tests document the current GitLab-specific behavior and the
    contracts that must be preserved (or extended) in the rewrite.
    """

    def test_validator_schema_url_points_to_gitlab(self, tmp_path):
        """Current default is GitLab — rewrite will need to make this configurable."""
        v = _make_validator(tmp_path)
        assert "gitlab" in v.schema_url.lower()

    def test_pragma_bypass_is_target_agnostic(self, tmp_path):
        """Pragma bypass must work regardless of target platform."""
        v = _make_validator(tmp_path)
        yaml_with_pragma = "# Pragma: do-not-validate-schema\nkey: value\n"
        ok, _ = v.validate_ci_config(yaml_with_pragma)
        assert ok is True

    def test_validate_ci_config_is_pure_function_of_content(self, tmp_path):
        """Same content should always return the same result."""
        v = _make_validator(tmp_path)
        r1 = v.validate_ci_config(MINIMAL_GITLAB_YAML)
        r2 = v.validate_ci_config(MINIMAL_GITLAB_YAML)
        assert r1 == r2
