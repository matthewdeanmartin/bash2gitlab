# bash2gitlab/commands/autogit.py

from __future__ import annotations

import logging
import subprocess  # nosec: B404
from pathlib import Path
from typing import Literal

from bash2gitlab.config import Config
from bash2gitlab.errors.exceptions import Bash2GitlabError, ConfigInvalid

logger = logging.getLogger(__name__)

AutogitMode = Literal["off", "stage", "commit", "push"]


def _run_git_command(command: list[str], cwd: Path) -> str:
    """Runs a Git command, captures its output, and handles errors."""
    try:
        logger.debug("Running git command: git %s", " ".join(command))
        result = subprocess.run(  # nosec
            ["git", *command],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
            encoding="utf-8",
        )
        logger.debug("Git command stdout:\n%s", result.stdout)
        return result.stdout.strip()
    except FileNotFoundError:
        raise Bash2GitlabError("Git command not found. Is Git installed and in your PATH?") from None
    except subprocess.CalledProcessError as e:
        logger.error("Git command failed: git %s", " ".join(command))
        logger.error("Stderr:\n%s", e.stderr)
        raise Bash2GitlabError(f"Git command failed. Stderr: {e.stderr.strip()}") from e


def _get_repo_root(path: Path) -> Path:
    """Finds the git repository root from a given path."""
    return Path(_run_git_command(["rev-parse", "--show-toplevel"], cwd=path))


def _paths_under_repo(repo_root: Path, *paths: Path) -> list[Path]:
    """Return the subset of *existing* paths that are under the given repo root.

    Raises Bash2GitlabError if any provided path is outside the repository.
    """
    kept: list[Path] = []
    for p in paths:
        try:
            rel = p.resolve().relative_to(repo_root)
        except ValueError as ve:
            raise Bash2GitlabError(
                f"Configured path {p} is not inside repository root {repo_root}."
            ) from ve
        # Keep if either the absolute path exists or the relative path exists in the worktree
        if p.exists() or (repo_root / rel).exists():
            kept.append(rel)
        else:
            logger.info("Skipping non-existent path: %s", p)
    return kept


def _current_branch(repo_root: Path) -> str:
    """Return current branch name or 'HEAD' if detached."""
    return _run_git_command(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)


def _has_upstream(repo_root: Path) -> bool:
    """Return True iff the current branch has an upstream set."""
    try:
        _run_git_command(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=repo_root)
        return True
    except Bash2GitlabError:
        return False


def run_autogit(config: Config, commit_message: str | None = None) -> int:
    """
    Performs git operations (stage, commit, push) based on configuration.

    This function reads the `input_dir` and `output_dir` from the global
    configuration to determine which folders to operate on.

    Args:
        config: The application's configuration object.
        commit_message: An optional commit message to override the config.

    Returns:
        0 on success, 1 on failure.
    """
    mode = config.autogit_mode
    if not mode or mode == "off":
        logger.debug("Autogit is disabled ('off' or not set in config).")
        return 0

    input_dir_str = config.input_dir
    output_dir_str = config.output_dir

    if not input_dir_str or not output_dir_str:
        msg = "Autogit failed: 'input_dir' and 'output_dir' must be set in the global config."
        logger.error(msg)
        raise ConfigInvalid(msg)

    try:
        input_dir = Path(input_dir_str).resolve()
        output_dir = Path(output_dir_str).resolve()

        repo_root = _get_repo_root(input_dir)
        logger.info(f"Git repository root found at: {repo_root}")

        rel_paths = _paths_under_repo(repo_root, input_dir, output_dir)
        # Keep log output deterministic
        rel_paths_str = sorted(str(p) for p in rel_paths)

        if not rel_paths_str:
            logger.info("No existing configured paths to stage.")
            return 0

        # Stage files, including deletions (use -A) and protect against pathspec issues by using '--'
        logger.info("Staging changed files in: %s", ", ".join(rel_paths_str))
        _run_git_command(["add", "-A", "--", *rel_paths_str], cwd=repo_root)

        status_output = _run_git_command(["status", "--porcelain"], cwd=repo_root)
        if not status_output:
            logger.info("No changes to commit.")
            return 0

        if mode in ["commit", "push"]:
            message = commit_message or config.autogit_commit_message or "chore: auto-commit by bash2gitlab"
            logger.info(f"Committing with message: '{message}'")
            _run_git_command(["commit", "-m", message], cwd=repo_root)

        if mode == "push":
            remote = config.autogit_remote or "origin"
            branch = config.autogit_branch
            if not branch:
                branch = _current_branch(repo_root)
                if branch == "HEAD":
                    raise Bash2GitlabError(
                        "Detached HEAD; set [autogit].branch or check out a branch before pushing."
                    )
            push_args = ["push", remote, branch]
            # For a first push where upstream isn't set, choose -u
            if not _has_upstream(repo_root):
                push_args = ["push", "-u", remote, branch]
            logger.info("Pushing to %s/%s...", remote, branch)
            _run_git_command(push_args, cwd=repo_root)

        logger.info(f"Autogit action '{mode}' completed successfully.")
        return 0

    except Bash2GitlabError as e:
        logger.error(f"Autogit failed: {e}")
        return 1
    except Exception as e:
        logger.error(f"An unexpected error occurred during autogit: {e}", exc_info=True)
        return 1
