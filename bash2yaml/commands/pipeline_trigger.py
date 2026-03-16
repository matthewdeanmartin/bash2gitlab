# gitlab_pipeline_trigger.py

from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

import gitlab
from gitlab import Gitlab
from gitlab.exceptions import GitlabAuthenticationError, GitlabHttpError

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@dataclass(frozen=True)
class ProjectSpec:
    """A single project's pipeline trigger specification.

    Attributes:
        project_id: Numeric GitLab project ID (not path).
        ref: The Git ref (branch, tag, or SHA) to run the pipeline on.
        variables: Optional CI/CD variables to pass to the pipeline.
                   Keys must be strings; values are strings.
    """

    project_id: int
    ref: str
    variables: Mapping[str, str] | None = field(default=None)


@dataclass(frozen=True)
class TriggerResult:
    """Represents a triggered pipeline."""

    project_id: int
    pipeline_id: int
    web_url: str


@dataclass(frozen=True)
class PollResult:
    """Represents the final status of a pipeline after polling."""

    project_id: int
    pipeline_id: int
    status: str
    web_url: str


# Terminal (complete) pipeline states as defined by GitLab API
# https://docs.gitlab.com/ee/ci/pipelines/#pipeline-statuses
TERMINAL_STATUSES = {"success", "failed", "canceled", "skipped", "manual", "scheduled"}


def get_gitlab_client(
    url: str | None = None,
    token: str | None = None,
    per_page: int = 50,
    timeout: int = 30,
) -> Gitlab:
    """Create and return an authenticated python-gitlab client.

    Args:
        url: Base GitLab URL (default: env GITLAB_URL or 'https://gitlab.com').
        token: Personal Access Token with `api` scope
               (default: env GITLAB_TOKEN).
        per_page: Pagination page size for API calls.
        timeout: HTTP timeout in seconds for API requests.

    Returns:
        An authenticated Gitlab client.

    Raises:
        GitlabAuthenticationError: If authentication fails.
        ValueError: If token is missing.
    """
    base_url = url or os.getenv("GITLAB_URL", "https://gitlab.com")
    api_token = token or os.getenv("GITLAB_TOKEN")

    if not api_token:
        raise ValueError("A GitLab API token is required. Provide `token=` or set GITLAB_TOKEN.")

    gl = gitlab.Gitlab(url=base_url, private_token=api_token, per_page=per_page, timeout=timeout)
    try:
        gl.auth()  # Validates token; inexpensive call
    except GitlabAuthenticationError as e:
        raise GitlabAuthenticationError(
            "Failed to authenticate to GitLab. Ensure your token is valid and has 'api' scope."
        ) from e
    return gl


def trigger_pipelines(
    gl: Gitlab,
    specs: Iterable[ProjectSpec],
) -> list[TriggerResult]:
    """Trigger pipelines for a set of projects.

    Args:
        gl: An authenticated python-gitlab client.
        specs: Iterable of ProjectSpec, each with project_id, ref, and optional variables.

    Returns:
        list of TriggerResult with pipeline IDs and web URLs.

    Notes:
        - Uses the Pipeline Create endpoint via python-gitlab.
        - If a project's ref is invalid or user lacks permission, an exception will be raised.
    """
    results: list[TriggerResult] = []

    for spec in specs:
        logger.info("Triggering pipeline: project_id=%s ref=%s", spec.project_id, spec.ref)
        project = gl.projects.get(spec.project_id)

        data: dict[str, Any] = {"ref": spec.ref}
        # GitLab expects variables list of dicts: [{"key": "FOO", "value": "BAR"}, ...]
        if spec.variables:
            data["variables"] = [{"key": k, "value": v} for k, v in spec.variables.items()]

        try:
            pipeline = project.pipelines.create(data)
        except GitlabHttpError as e:
            # Common causes: 400 invalid ref, 403/404 permission, 409 conflict
            logger.error("Failed to trigger pipeline for project %s on ref '%s': %s", spec.project_id, spec.ref, e)
            raise

        results.append(
            TriggerResult(
                project_id=spec.project_id,
                pipeline_id=int(pipeline.id),
                web_url=str(pipeline.web_url),
            )
        )
        logger.info("Triggered: project_id=%s pipeline_id=%s url=%s", spec.project_id, pipeline.id, pipeline.web_url)

    return results


def poll_pipelines_until_complete(
    gl: Gitlab,
    triggered: Iterable[TriggerResult],
    *,
    timeout_seconds: int = 1800,
    poll_interval_seconds: int = 30,
    initial_delay_seconds: int | None = 30,
) -> list[PollResult]:
    """Politely poll pipelines until they reach a terminal state or timeout.

    Args:
        gl: An authenticated python-gitlab client.
        triggered: Iterable of TriggerResult from `trigger_pipelines`.
        timeout_seconds: Maximum total time to wait before giving up.
        poll_interval_seconds: Time between polls. Must be >= 30 to be polite.
        initial_delay_seconds: Optional initial delay before the first poll.
                               Defaults to 30 to avoid immediate API pressure.

    Returns:
        list of PollResult, one for each triggered pipeline. If timed out, the
        last observed non-terminal status will be reported.

    Raises:
        ValueError: If poll_interval_seconds < 30 (politeness guard).
    """
    if poll_interval_seconds < 30:
        raise ValueError("poll_interval_seconds must be >= 30 seconds to be polite.")

    # Optional initial wait to avoid hammering right after creation
    if initial_delay_seconds is None:
        initial_delay_seconds = 30
    if initial_delay_seconds > 0:
        logger.info("Initial delay before polling: %s seconds", initial_delay_seconds)
        time.sleep(initial_delay_seconds)

    # Prepare lookup table for projects/pipelines
    pending: dict[tuple[int, int], TriggerResult] = {(t.project_id, t.pipeline_id): t for t in triggered}
    results: dict[tuple[int, int], PollResult] = {}

    start = time.time()
    while pending and (time.time() - start) < timeout_seconds:
        to_remove: list[tuple[int, int]] = []

        for (project_id, pipeline_id), _trig in list(pending.items()):
            try:
                project = gl.projects.get(project_id)
                pipeline = project.pipelines.get(pipeline_id)
                status = str(pipeline.status)
                web_url = str(pipeline.web_url)
                logger.debug("Poll status: project=%s pipeline=%s status=%s", project_id, pipeline_id, status)
            except GitlabHttpError as e:
                # Treat as transient; keep waiting unless timeout. Log and continue.
                logger.warning("Transient error polling project=%s pipeline=%s: %s", project_id, pipeline_id, e)
                continue  # Next item

            if status in TERMINAL_STATUSES:
                results[(project_id, pipeline_id)] = PollResult(
                    project_id=project_id,
                    pipeline_id=pipeline_id,
                    status=status,
                    web_url=web_url,
                )
                to_remove.append((project_id, pipeline_id))

        for key in to_remove:
            pending.pop(key, None)

        if not pending:
            break

        # Sleep between polite polls
        remaining = timeout_seconds - (time.time() - start)
        if remaining <= 0:
            break
        sleep_for = min(poll_interval_seconds, max(1, int(remaining)))
        logger.info("Waiting %s seconds before next poll (%s pipeline(s) pending)...", sleep_for, len(pending))
        time.sleep(sleep_for)

    # Anything still pending after timeout gets its last known status (best-effort)
    for (project_id, pipeline_id), trig in pending.items():
        try:
            project = gl.projects.get(project_id)
            pipeline = project.pipelines.get(pipeline_id)
            status = str(pipeline.status)
            web_url = str(pipeline.web_url)
        except Exception:
            status = "unknown"
            web_url = trig.web_url

        results[(project_id, pipeline_id)] = PollResult(
            project_id=project_id,
            pipeline_id=pipeline_id,
            status=status,
            web_url=web_url,
        )

    return list(results.values())


# ---------- Convenience helpers ----------


def trigger_from_mapping(
    gl: Gitlab,
    project_to_ref: Mapping[int, str],
    *,
    variables_by_project: Mapping[int, Mapping[str, str]] | None = None,
) -> list[TriggerResult]:
    """Helper to build specs from a {project_id: ref} mapping and trigger pipelines.

    Args:
        gl: Authenticated GitLab client.
        project_to_ref: dict mapping project_id -> ref (branch/tag/SHA).
        variables_by_project: Optional dict mapping project_id -> variables dict.

    Returns:
        list of TriggerResult.
    """
    specs = []
    for pid, ref in project_to_ref.items():
        vars_for_project = variables_by_project.get(pid) if variables_by_project else None
        specs.append(ProjectSpec(project_id=pid, ref=ref, variables=vars_for_project))
    return trigger_pipelines(gl, specs)


def run_all(
    project_to_ref: Mapping[int, str],
    *,
    variables_by_project: Mapping[int, Mapping[str, str]] | None = None,
    url: str | None = None,
    token: str | None = None,
    timeout_seconds: int = 1800,
    poll_interval_seconds: int = 30,
    initial_delay_seconds: int = 30,
) -> list[PollResult]:
    """One-shot helper: auth, trigger across projects, and poll to completion.

    Args:
        project_to_ref: dict mapping project_id -> ref.
        variables_by_project: Optional dict mapping project_id -> variables dict.
        url: GitLab URL (default env or https://gitlab.com).
        token: API token (default env).
        timeout_seconds: Max total wait.
        poll_interval_seconds: Interval between polls (>= 30).
        initial_delay_seconds: Initial wait before first poll (default 30).

    Returns:
        Final PollResult list (status per pipeline).
    """
    gl = get_gitlab_client(url=url, token=token)
    triggered = trigger_from_mapping(gl, project_to_ref, variables_by_project=variables_by_project)
    return poll_pipelines_until_complete(
        gl,
        triggered,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        initial_delay_seconds=initial_delay_seconds,
    )


# ---------- Minimal CLI for ad-hoc use (optional) ----------

if __name__ == "__main__":

    def run():
        # Example usage:
        #   GITLAB_TOKEN=... python gitlab_pipeline_trigger.py
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        example_projects: dict[int, str] = {
            # Replace with your project IDs and branches:
            # 12345678: "main",
            # 87654321: "develop",
        }
        if not example_projects:
            logger.info("Populate `example_projects` in __main__ for a quick test.")
        else:
            results = run_all(example_projects)
            for r in results:
                print(f"[{r.project_id}] pipeline {r.pipeline_id} -> {r.status} ({r.web_url})")

    run()
