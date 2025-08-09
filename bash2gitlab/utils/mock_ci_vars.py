"""Helper file for mocking common CI/CD variables"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def generate_mock_ci_variables_script(output_path: str = "mock_ci_variables.sh") -> None:
    """Generate a shell script exporting mock GitLab CI/CD variables."""
    ci_vars: dict[str, str] = {
        "CI": "false",
        "GITLAB_CI": "false",
        "CI_API_V4_URL": "https://gitlab.example.com/api/v4",
        "CI_API_GRAPHQL_URL": "https://gitlab.example.com/api/graphql",
        "CI_PROJECT_ID": "1234",
        "CI_PROJECT_NAME": "example-project",
        "CI_PROJECT_PATH": "group/example-project",
        "CI_PROJECT_NAMESPACE": "group",
        "CI_PROJECT_ROOT_NAMESPACE": "group",
        "CI_PROJECT_URL": "https://gitlab.example.com/group/example-project",
        "CI_PROJECT_VISIBILITY": "private",
        "CI_DEFAULT_BRANCH": "main",
        "CI_COMMIT_SHA": "abcdef1234567890abcdef1234567890abcdef12",
        "CI_COMMIT_SHORT_SHA": "abcdef12",
        "CI_COMMIT_BRANCH": "feature-branch",
        "CI_COMMIT_REF_NAME": "feature-branch",
        "CI_COMMIT_REF_SLUG": "feature-branch",
        "CI_COMMIT_BEFORE_SHA": "0000000000000000000000000000000000000000",
        "CI_COMMIT_MESSAGE": "Add new CI feature",
        "CI_COMMIT_TITLE": "Add new CI feature",
        "CI_COMMIT_TIMESTAMP": "2025-07-27T12:00:00Z",
        "CI_COMMIT_AUTHOR": "Test User <test@example.com>",
        "CI_PIPELINE_ID": "5678",
        "CI_PIPELINE_IID": "42",
        "CI_PIPELINE_SOURCE": "push",
        "CI_PIPELINE_URL": "https://gitlab.example.com/group/example-project/-/pipelines/5678",
        "CI_PIPELINE_CREATED_AT": "2025-07-27T12:00:05Z",
        "CI_JOB_ID": "91011",
        "CI_JOB_NAME": "test-job",
        "CI_JOB_STAGE": "test",
        "CI_JOB_STATUS": "running",
        "CI_JOB_TOKEN": "xyz-token",
        "CI_JOB_URL": "https://gitlab.example.com/group/example-project/-/jobs/91011",
        "CI_JOB_STARTED_AT": "2025-07-27T12:00:10Z",
        "CI_PROJECT_DIR": "/builds/group/example-project",
        "CI_BUILDS_DIR": "/builds",
        "CI_RUNNER_ID": "55",
        "CI_RUNNER_SHORT_TOKEN": "runner1234567890",
        "CI_RUNNER_VERSION": "17.3.0",
        "CI_SERVER_URL": "https://gitlab.example.com",
        "CI_SERVER_HOST": "gitlab.example.com",
        "CI_SERVER_PORT": "443",
        "CI_SERVER_PROTOCOL": "https",
        "CI_SERVER_NAME": "GitLab",
        "CI_SERVER_VERSION": "17.2.1",
        "CI_SERVER_VERSION_MAJOR": "17",
        "CI_SERVER_VERSION_MINOR": "2",
        "CI_SERVER_VERSION_PATCH": "1",
        "CI_REPOSITORY_URL": "https://gitlab-ci-token:$CI_JOB_TOKEN@gitlab.example.com/group/example-project.git",
    }

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("#!/usr/bin/env bash\n")
        f.write("# Auto-generated mock CI variables\n\n")
        for key, val in ci_vars.items():
            escaped = val.replace('"', '\\"')
            f.write(f'export {key}="{escaped}"\n')

    logger.info("Wrote %s with %d variables", output_path, len(ci_vars))


if __name__ == "__main__":
    generate_mock_ci_variables_script()
