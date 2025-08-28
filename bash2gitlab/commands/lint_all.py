"""Utilities to lint compiled GitLab CI YAML files against a GitLab instance.

This module scans an *output* directory for YAML files and submits each file's
content to GitLab's CI Lint API. It supports both the global lint endpoint and
project-scoped linting (recommended for configs that rely on `include:` or
project-level context).

The entrypoint is :func:`lint_output_folder`.

Design goals
------------
- Pure standard library HTTP (``urllib.request``) to avoid extra deps.
- Safe defaults, clear logging, and mypy-friendly type hints.
- Google-style docstrings, small focused helpers, and testable pieces.

Example:
-------
>>> from pathlib import Path
>>> results = lint_output_folder(
...     output_root=Path("dist"),
...     gitlab_url="https://gitlab.example.com",
...     private_token="glpat-...",
...     project_id=1234,
...     ref="main",
...     include_merged_yaml=True,
... )
>>> any(r.ok for r in results)
True

Notes:
-----
- The project-scoped endpoint provides more accurate validation for pipelines
  that depend on project context, variables, or remote includes.
- GitLab API reference:
  - Global lint:   ``POST /api/v4/ci/lint`` (body: {"content": "..."})
  - Project lint:  ``POST /api/v4/projects/:id/ci/lint`` with optional
    parameters such as ``ref`` and ``include_merged_yaml``.
"""

from __future__ import annotations

import logging
import multiprocessing
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from urllib import error, request

import orjson as json

from bash2gitlab.utils.utils import short_path

logger = logging.getLogger(__name__)

__all__ = ["LintIssue", "LintResult", "lint_single_text", "lint_single_file", "lint_output_folder", "summarize_results"]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LintIssue:
    """Represents a single message from GitLab CI Lint.

    Attributes:
        severity: Message severity (e.g., "error", "warning").
        message: Human-readable message.
        line: Optional line number in the YAML (GitLab may omit).
    """

    severity: str
    message: str
    line: int | None = None


@dataclass(frozen=True)
class LintResult:
    """Result of linting one YAML payload.

    Attributes:
        path: Source file path (``Path``) or synthetic path for raw text.
        ok: ``True`` when the configuration is valid according to GitLab.
        status: Raw status string from API (e.g., "valid", "invalid").
        errors: List of error messages (as :class:`LintIssue`).
        warnings: List of warning messages (as :class:`LintIssue`).
        merged_yaml: The resolved/merged YAML returned by project-scoped lint
            when ``include_merged_yaml=True``; otherwise ``None``.
        raw_response: The decoded API JSON for debugging.
    """

    path: Path
    ok: bool
    status: str
    errors: list[LintIssue]
    warnings: list[LintIssue]
    merged_yaml: str | None
    raw_response: dict


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def api_url(
    base_url: str,
    project_id: int | None,
) -> str:
    """Build the CI Lint API URL.

    Args:
        base_url: Base GitLab URL, e.g., ``https://gitlab.com``.
        project_id: If provided, use project-scoped lint endpoint.

    Returns:
        Fully-qualified API endpoint URL.
    """
    base = base_url.rstrip("/")
    if project_id is None:
        return f"{base}/api/v4/ci/lint"
    return f"{base}/api/v4/projects/{project_id}/ci/lint"


def post_json(
    url: str,
    payload: dict,
    *,
    private_token: str | None,
    timeout: float,
) -> dict:
    """POST JSON to ``url`` and return decoded JSON response.

    Args:
        url: Target endpoint.
        payload: JSON payload to send.
        private_token: Optional GitLab token for authentication.
        timeout: Request timeout in seconds.

    Returns:
        Decoded JSON response as a ``dict``.

    Raises:
        URLError / HTTPError on network issues (logged and re-raised).
        ValueError if response cannot be parsed as JSON.
    """
    # body = json.dumps(payload).encode("utf-8")
    body = json.dumps(payload)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "bash2gitlab-lint/1.0",
    }
    if private_token:
        headers["PRIVATE-TOKEN"] = private_token

    req = request.Request(url=url, data=body, headers=headers, method="POST")

    try:
        #  controlled URL
        with request.urlopen(req, timeout=timeout) as resp:  # nosec
            raw = resp.read()
    except error.HTTPError as e:  # pragma: no cover - network dependent
        detail = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
        logger.error("HTTP %s from %s: %s", getattr(e, "code", "?"), url, detail)
        raise
    except error.URLError as e:  # pragma: no cover - network dependent
        logger.error("Network error calling %s: %s", url, e)
        raise

    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        logger.error("Failed to decode JSON from %s: %s", url, e)
        raise


# ---------------------------------------------------------------------------
# Lint operations
# ---------------------------------------------------------------------------


def lint_single_text(
    content: str,
    *,
    gitlab_url: str,
    private_token: str | None = None,
    project_id: int | None = None,
    ref: str | None = None,
    include_merged_yaml: bool = False,
    timeout: float = 20.0,
    synthetic_path: Path | None = None,
) -> LintResult:
    """Lint a single YAML *content* string via GitLab CI Lint API.

    Args:
        content: The YAML text to validate.
        gitlab_url: Base GitLab URL, e.g., ``https://gitlab.com``.
        private_token: Optional personal access token (PAT) or CI job token.
        project_id: If provided, use project-scoped endpoint.
        ref: Optional Git ref for project-scoped lint (e.g., "main").
        include_merged_yaml: If True, ask GitLab to resolve includes and return
            the merged YAML (project-scoped lint only).
        timeout: HTTP timeout in seconds.
        synthetic_path: Optional path label for reporting (used when linting
            text not originating from a file).

    Returns:
        A :class:`LintResult` with structured details.
    """
    url = api_url(gitlab_url, project_id)

    payload: dict = {"content": content}

    # Project-scoped knobs
    if project_id is not None and ref is not None:
        payload["ref"] = ref
    if project_id is not None and include_merged_yaml:
        payload["include_merged_yaml"] = True

    resp = post_json(url, payload, private_token=private_token, timeout=timeout)

    # GitLab returns varying shapes across versions. Normalize defensively.
    status = str(resp.get("status") or ("valid" if resp.get("valid") else "invalid"))
    valid = bool(resp.get("valid", status == "valid"))

    def collect(kind: str) -> list[LintIssue]:
        out: list[LintIssue] = []
        items = resp.get(kind) or []
        if isinstance(items, list):
            for m in items:
                if isinstance(m, dict):
                    out.append(
                        LintIssue(
                            severity=str(m.get("severity", kind.rstrip("s"))),
                            message=str(m.get("message", m)),
                            line=m.get("line"),
                        )
                    )
                else:
                    out.append(LintIssue(severity=kind.rstrip("s"), message=str(m)))
        return out

    errors = collect("errors")
    warnings = collect("warnings")
    merged_yaml: str | None = None
    if include_merged_yaml:
        merged_yaml = resp.get("merged_yaml") or resp.get("mergedYaml")

    path = synthetic_path or Path("<string>")
    return LintResult(
        path=path,
        ok=valid,
        status=status,
        errors=errors,
        warnings=warnings,
        merged_yaml=merged_yaml,
        raw_response=resp,
    )


def lint_single_file(
    path: Path,
    *,
    gitlab_url: str,
    private_token: str | None = None,
    project_id: int | None = None,
    ref: str | None = None,
    include_merged_yaml: bool = False,
    timeout: float = 20.0,
    encoding: str = "utf-8",
) -> LintResult:
    """Lint one YAML file at *path*.

    Args:
        path: File to lint.
        gitlab_url: Base GitLab URL, e.g., ``https://gitlab.com``.
        private_token: Optional personal access token (PAT) or CI job token.
        project_id: Optional project id for project-scoped lint.
        ref: Optional git ref when using project-scoped lint.
        include_merged_yaml: Whether to return merged YAML (project lint only).
        timeout: HTTP timeout.
        encoding: File encoding.

    Returns:
        A :class:`LintResult`.
    """
    text = path.read_text(encoding=encoding)
    return lint_single_text(
        text,
        gitlab_url=gitlab_url,
        private_token=private_token,
        project_id=project_id,
        ref=ref,
        include_merged_yaml=include_merged_yaml,
        timeout=timeout,
        synthetic_path=path,
    )


# ---------------------------------------------------------------------------
# Folder scanning / orchestration
# ---------------------------------------------------------------------------

_YAML_GLOBS: tuple[str, ...] = ("*.yml", "*.yaml")


def discover_yaml_files(root: Path) -> list[Path]:
    """Recursively find YAML files under *root*.

    Files with suffixes ``.yml`` or ``.yaml`` are included.
    """
    out: list[Path] = []
    for pat in _YAML_GLOBS:
        out.extend(root.rglob(pat))
    # Deterministic order aids testing and stable logs
    return sorted(p for p in out if p.is_file())


def lint_output_folder(
    output_root: Path,
    *,
    gitlab_url: str,
    private_token: str | None = None,
    project_id: int | None = None,
    ref: str | None = None,
    include_merged_yaml: bool = False,
    parallelism: int | None = None,
    timeout: float = 20.0,
) -> list[LintResult]:
    """Lint every YAML file under *output_root* using GitLab CI Lint.

    Args:
        output_root: Directory containing compiled YAML outputs to validate.
        gitlab_url: Base GitLab URL, e.g., ``https://gitlab.com``.
        private_token: Optional personal access token (PAT) or CI job token.
        project_id: Optional project id for project-scoped lint.
        ref: Optional git ref when using project-scoped lint.
        include_merged_yaml: Whether to return merged YAML (project lint only).
        parallelism: Max worker processes for concurrent lint requests. If
            ``None``, a reasonable default will be used for small sets.
        timeout: HTTP timeout per request.

    Returns:
        List of :class:`LintResult`, one per file.
    """
    files = discover_yaml_files(output_root)
    if not files:
        logger.warning("No YAML files found under %s", output_root)
        return []

    # Heuristic: don't over-parallelize small sets
    if parallelism is None:
        parallelism = min(max(1, len(files)), multiprocessing.cpu_count())

    logger.info(
        "Linting %d YAML file(s) under %s using %s endpoint",
        len(files),
        output_root,
        "project" if project_id is not None else "global",
    )

    if parallelism <= 1:
        return [
            lint_single_file(
                p,
                gitlab_url=gitlab_url,
                private_token=private_token,
                project_id=project_id,
                ref=ref,
                include_merged_yaml=include_merged_yaml,
                timeout=timeout,
            )
            for p in files
        ]

    # Use processes for simple isolation; network-bound so processes vs threads
    # is not critical, but this avoids GIL considerations for file IO + json.

    worker = partial(
        lint_single_file,
        gitlab_url=gitlab_url,
        private_token=private_token,
        project_id=project_id,
        ref=ref,
        include_merged_yaml=include_merged_yaml,
        timeout=timeout,
    )

    with multiprocessing.Pool(processes=parallelism) as pool:
        results = pool.map(worker, files)

    return results


# ---------------------------------------------------------------------------
# Reporting helpers (optional)
# ---------------------------------------------------------------------------


def summarize_results(results: Sequence[LintResult]) -> tuple[int, int]:
    """Log a concise summary and return counts.

    Args:
        results: Sequence of lint results.

    Returns:
        Tuple of (ok_count, fail_count).
    """
    ok = sum(1 for r in results if r.ok)
    fail = len(results) - ok

    for r in results:
        if r.ok:
            logger.info("OK: %s", short_path(r.path))
            if r.warnings:
                for w in r.warnings:
                    logger.warning("%s: %s", short_path(r.path), w.message)
        else:
            logger.error("INVALID: %s (status=%s)", short_path(r.path), r.status)
            for e in r.errors:
                if e.line is not None:
                    logger.error("%s:%s: %s", short_path(r.path), e.line, e.message)
                else:
                    logger.error("%s: %s", short_path(r.path), e.message)

    logger.info("Lint summary: %d ok, %d failed", ok, fail)
    return ok, fail
