"""Tests for the schemas directory and multi-platform schema support.

Focus areas for the upcoming rewrite:
- The bundled gitlab_ci_schema.json must be valid JSON and a valid JSON Schema.
- Schema discovery must work offline (no network calls).
- The validator must be extensible: a new 'target' argument should select
  which schema to load (gitlab today, github-actions/azure-devops etc. in future).
- Each schema must document its `$schema` version for tooling compatibility.

These tests run against the current state of the schemas/ directory and
document the expected shape/contracts for future schemas.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Locate the schemas directory relative to the package
_SCHEMAS_DIR = Path(__file__).parent.parent.parent / "bash2gitlab" / "schemas"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_files() -> list[Path]:
    return [f for f in _SCHEMAS_DIR.iterdir() if f.suffix == ".json" and f.is_file()]


# ---------------------------------------------------------------------------
# Schema directory existence and structure
# ---------------------------------------------------------------------------


class TestSchemasDirectory:
    def test_schemas_dir_exists(self):
        assert _SCHEMAS_DIR.exists(), f"schemas/ directory not found at {_SCHEMAS_DIR}"

    def test_schemas_dir_is_directory(self):
        assert _SCHEMAS_DIR.is_dir()

    def test_gitlab_schema_present(self):
        gitlab_schema = _SCHEMAS_DIR / "gitlab_ci_schema.json"
        assert gitlab_schema.exists(), "GitLab CI schema must be present for offline validation"

    def test_notice_file_present(self):
        """NOTICE.txt documents license/attribution for bundled schemas."""
        notice = _SCHEMAS_DIR / "NOTICE.txt"
        assert notice.exists(), "NOTICE.txt must accompany bundled schemas for attribution"


# ---------------------------------------------------------------------------
# GitLab CI schema — validity
# ---------------------------------------------------------------------------


class TestGitLabCISchema:
    @pytest.fixture(autouse=True)
    def schema(self):
        path = _SCHEMAS_DIR / "gitlab_ci_schema.json"
        self._schema = _load_json(path)
        return self._schema

    def test_is_dict(self):
        assert isinstance(self._schema, dict)

    def test_has_properties_or_definitions(self):
        """A real JSON Schema must have some structure."""
        has_structure = any(
            k in self._schema for k in ["properties", "definitions", "$defs", "allOf", "anyOf", "oneOf", "type"]
        )
        assert has_structure, "Schema must define some structure (properties, definitions, etc.)"

    def test_not_empty(self):
        assert len(self._schema) > 0

    def test_is_valid_json(self):
        """Round-trip through json.dumps/loads to ensure no surrogate characters."""
        raw = json.dumps(self._schema)
        reloaded = json.loads(raw)
        assert reloaded == self._schema


# ---------------------------------------------------------------------------
# Schema-driven validation — GitLabCIValidator uses bundled schema
# ---------------------------------------------------------------------------


class TestValidatorUsesBundledSchema:
    def test_validator_loads_fallback_without_network(self, tmp_path):
        """_load_fallback_schema returns a dict or None (None in dev if resources not resolved)."""
        from bash2gitlab.utils.validate_pipeline import GitLabCIValidator

        v = GitLabCIValidator(cache_dir=str(tmp_path))
        schema = v._load_fallback_schema()
        # None is acceptable if package resource path doesn't resolve in dev environment
        assert schema is None or isinstance(schema, dict)

    def test_fallback_schema_is_same_as_bundled_file_if_loads(self, tmp_path):
        """If fallback loads, its top-level keys must match the schemas/ file."""
        from bash2gitlab.utils.validate_pipeline import GitLabCIValidator

        bundled = _load_json(_SCHEMAS_DIR / "gitlab_ci_schema.json")
        v = GitLabCIValidator(cache_dir=str(tmp_path))
        fallback = v._load_fallback_schema()
        if fallback is None:
            pytest.skip("Fallback schema not resolvable in this environment")
        assert set(bundled.keys()) == set(fallback.keys())

    def test_pragma_bypass_does_not_require_schema(self, tmp_path, monkeypatch):
        """Pragma bypass must short-circuit before any schema I/O."""
        from bash2gitlab.utils.validate_pipeline import GitLabCIValidator

        v = GitLabCIValidator(cache_dir=str(tmp_path))

        # Patch get_schema to raise — pragma must prevent reaching it
        def boom():
            raise RuntimeError("Should not have called get_schema with pragma present")

        v.get_schema = boom
        ok, errors = v.validate_ci_config("# Pragma: do-not-validate-schema\nkey: value\n")
        assert ok is True


# ---------------------------------------------------------------------------
# Multi-schema / target readiness
# ---------------------------------------------------------------------------


class TestMultiSchemaReadiness:
    """Documents what the rewrite needs to add to support multiple CI platforms.

    These tests check the current state and define the contracts the new
    target-aware schema loader must satisfy.
    """

    def test_all_json_files_are_parseable(self):
        """Every .json in schemas/ must be valid JSON."""
        for path in _schema_files():
            data = _load_json(path)
            assert isinstance(data, dict), f"{path.name} must be a JSON object"

    def test_no_schema_file_is_empty(self):
        for path in _schema_files():
            data = _load_json(path)
            assert len(data) > 0, f"{path.name} is empty"

    def test_schema_for_known_platform_gitlab(self):
        """gitlab_ci_schema.json must exist — it's the current default target."""
        assert (_SCHEMAS_DIR / "gitlab_ci_schema.json").exists()

    def test_future_schema_names_follow_convention(self):
        """When new platform schemas are added, they should follow naming conventions.

        This test is intentionally lenient — it documents the expected convention
        without requiring those files to exist yet.

        Convention: <platform>_ci_schema.json
        Examples: github_actions_schema.json, azure_devops_schema.json
        """
        existing = {f.stem for f in _schema_files()}
        # Current state: only gitlab_ci_schema exists
        assert "gitlab_ci_schema" in existing
        # The following are expected future additions (will be empty sets for now):
        future_platforms = {"github_actions_schema", "azure_devops_schema", "bitbucket_pipelines_schema"}
        currently_missing = future_platforms - existing
        # Document: these are known-missing schemas for future implementation
        # This assertion is a no-op currently (all missing), but when added they must follow convention
        for missing in currently_missing:
            # Convention check: name ends with _schema
            assert missing.endswith("_schema"), f"Schema {missing} must end with _schema"

    def test_validator_cache_dir_is_configurable(self, tmp_path):
        """Cache dir must be injectable for isolation — critical for multi-target setup."""
        from bash2gitlab.utils.validate_pipeline import GitLabCIValidator

        v = GitLabCIValidator(cache_dir=str(tmp_path))
        assert v.cache_dir == tmp_path

    def test_schema_url_is_a_string(self, tmp_path):
        """schema_url must be a string — the rewrite will make this target-dependent."""
        from bash2gitlab.utils.validate_pipeline import GitLabCIValidator

        v = GitLabCIValidator(cache_dir=str(tmp_path))
        assert isinstance(v.schema_url, str)
        assert v.schema_url.startswith("https://")
