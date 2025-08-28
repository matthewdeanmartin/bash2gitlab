from __future__ import annotations

import logging
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema
import orjson as json
import ruamel.yaml

logger = logging.getLogger(__name__)

# Import compatibility for Python 3.8+
if sys.version_info >= (3, 9):  # noqa: UP036
    from importlib.resources import files
else:
    try:
        from importlib_resources import files
    except ImportError:
        files = None


class GitLabCIValidator:
    """Validates GitLab CI YAML files against the official schema."""

    def __init__(self, cache_dir: str | None = None):
        """
        Initialize the validator.

        Args:
            cache_dir: Directory to cache the schema file. If None, uses system temp directory.
        """
        self.schema_url = (
            "https://gitlab.com/gitlab-org/gitlab/-/raw/master/app/assets/javascripts/editor/schema/ci.json"
        )
        self.cache_dir = Path(cache_dir) if cache_dir else Path(tempfile.gettempdir())
        self.cache_file = self.cache_dir / "gitlab_ci_schema.json"
        self.fallback_schema_path = "schemas/gitlab_ci_schema.json"  # Package resource path
        self.yaml = ruamel.yaml.YAML(typ="rt")

    def _fetch_schema_from_url(self) -> dict[str, Any] | None:
        """
        Fetch the schema from GitLab's repository.

        Returns:
            Schema dictionary if successful, None otherwise.
        """
        try:
            with urllib.request.urlopen(self.schema_url, timeout=5) as response:  # nosec
                schema_data = response.read().decode("utf-8")
                return json.loads(schema_data)
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError) as e:
            print(f"Failed to fetch schema from URL: {e}")
            return None

    def _load_schema_from_cache(self) -> dict[str, Any] | None:
        """
        Load the schema from cache file.

        Returns:
            Schema dictionary if successful, None otherwise.
        """
        try:
            if self.cache_file.exists():
                with open(self.cache_file, encoding="utf-8") as f:
                    return json.loads(f.read())
        except (OSError, json.JSONDecodeError) as e:
            print(f"Failed to load schema from cache: {e}")
        return None

    def _save_schema_to_cache(self, schema: dict[str, Any]) -> None:
        """
        Save the schema to cache file.

        Args:
            schema: Schema dictionary to cache.
        """
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                f.write(json.dumps(schema).decode())
        except OSError as e:
            print(f"Failed to save schema to cache: {e}")

    def _load_fallback_schema(self) -> dict[str, Any] | None:
        """
        Load the fallback schema from package resources.

        Returns:
            Schema dictionary if successful, None otherwise.
        """
        try:
            # Try modern importlib.resources approach (Python 3.9+) or importlib_resources backport
            if files is not None:
                try:
                    package_files = files(__package__ or __name__.split(".", maxsplit=1)[0])
                    schema_file = package_files / self.fallback_schema_path
                    if schema_file.is_file():
                        schema_data = schema_file.read_text(encoding="utf-8")
                        return json.loads(schema_data)
                except (FileNotFoundError, AttributeError, TypeError):
                    pass

            # Fallback: try to load from relative path
            try:
                current_dir = Path(__file__).parent if "__file__" in globals() else Path.cwd()
                fallback_file = current_dir / self.fallback_schema_path
                if fallback_file.exists():
                    with open(fallback_file, encoding="utf-8") as f:
                        return json.loads(f.read())
            except (OSError, FileNotFoundError):
                pass

        except (json.JSONDecodeError, Exception) as e:
            print(f"Failed to load fallback schema: {e}")

        return None

    def get_schema(self) -> dict[str, Any]:
        """
        Get the GitLab CI schema, trying URL first, then cache, then fallback.

        Returns:
            Schema dictionary.

        Raises:
            RuntimeError: If no schema could be loaded from any source.
        """
        # Try to fetch from URL first
        schema = self._fetch_schema_from_url()
        if schema:
            self._save_schema_to_cache(schema)
            return schema

        # Fall back to cache
        schema = self._load_schema_from_cache()
        if schema:
            print("Using cached schema (could not fetch from URL)")
            return schema

        # Fall back to package resource
        schema = self._load_fallback_schema()
        if schema:
            print("Using fallback schema from package (could not fetch from URL or cache)")
            return schema

        raise RuntimeError("Could not load schema from URL, cache, or fallback resource")

    def yaml_to_json(self, yaml_content: str) -> dict[str, Any]:
        """
        Convert YAML content to JSON-compatible dictionary.

        Args:
            yaml_content: YAML string content.

        Returns:
            Dictionary representation of the YAML.

        Raises:
            ruamel.yaml.YAMLError: If YAML parsing fails.
        """
        return self.yaml.load(yaml_content)

    def validate_ci_config(self, yaml_content: str) -> tuple[bool, list[str]]:
        """
        Validate GitLab CI YAML configuration against the schema.

        Args:
            yaml_content: YAML configuration as string.

        Returns:
            tuple of (is_valid, list_of_error_messages).
        """
        if "pragma" in yaml_content.lower() and "do-not-validate-schema" in yaml_content.lower():
            logger.debug("Skipping validation found do-not-validate-schema Pragma")
            return True, []

        try:
            # Convert YAML to JSON-compatible dict
            config_dict = self.yaml_to_json(yaml_content)

            # Get the schema
            schema = self.get_schema()

            # Validate against schema
            validator = jsonschema.Draft7Validator(schema)
            errors = []

            for error in validator.iter_errors(config_dict):
                error_path = " -> ".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
                error_msg = f"Path '{error_path}': {error.message}"
                errors.append(error_msg)

            is_valid = len(errors) == 0
            return is_valid, errors

        except ruamel.yaml.YAMLError as e:
            return False, [f"YAML parsing error: {str(e)}"]
        except Exception as e:
            return False, [f"Validation error: {str(e)}"]


@dataclass
class ValidationResult:
    """Result of validating a single YAML file."""

    file_path: Path
    is_valid: bool
    errors: list[str]

    def __post_init__(self) -> None:
        """Ensure file_path is a Path object."""
        if not isinstance(self.file_path, Path):
            self.file_path = Path(self.file_path)


def validate_gitlab_ci_yaml(yaml_content: str, cache_dir: str | None = None) -> tuple[bool, list[str]]:
    """
    Convenience function to validate GitLab CI YAML configuration.

    Args:
        yaml_content: YAML configuration as string.
        cache_dir: Optional directory for caching schema.

    Returns:
        tuple of (is_valid, list_of_error_messages).
    """
    validator = GitLabCIValidator(cache_dir=cache_dir)
    return validator.validate_ci_config(yaml_content)
