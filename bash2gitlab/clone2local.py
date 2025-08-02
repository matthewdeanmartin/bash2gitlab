from __future__ import annotations

import logging
import subprocess  # nosec
from collections.abc import Sequence
from pathlib import Path

logger = logging.getLogger(__name__)


def clone_repository(repo_url: str, sparse_dirs: Sequence[str], clone_dir: str | Path) -> None:
    """Clone a repository using Git's sparse checkout.

    Parameters
    ----------
    repo_url:
        The URL of the repository to clone.
    sparse_dirs:
        Iterable of directories to include in the sparse checkout.
    clone_dir:
        Destination directory for the clone.
    """
    clone_path = Path(clone_dir)
    logger.debug("Cloning repo %s into %s with sparse dirs %s", repo_url, clone_path, list(sparse_dirs))
    subprocess.run(  # nosec
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",
            "--sparse",
            repo_url,
            str(clone_path),
        ],
        check=True,
    )
    subprocess.run(  # nosec
        ["git", "sparse-checkout", "init", "--cone"],
        cwd=clone_path,
        check=True,
    )
    subprocess.run(  # nosec
        ["git", "sparse-checkout", "set", *sparse_dirs],
        cwd=clone_path,
        check=True,
    )


def clone2local_handler(args) -> None:
    """Argparse handler for the clone2local command."""
    clone_repository(args.repo_url, args.sparse_dirs, args.clone_dir)
