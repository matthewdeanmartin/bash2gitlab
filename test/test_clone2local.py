from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from bash2gitlab.clone2local import clone_repository


def test_clone_repository_calls_git(monkeypatch):
    calls: list[dict[str, Any]] = []

    def fake_run(cmd, *_, **kwargs):
        calls.append({"cmd": cmd, "cwd": kwargs.get("cwd"), "check": kwargs.get("check")})

        class Dummy:
            returncode = 0

        return Dummy()

    monkeypatch.setattr(subprocess, "run", fake_run)

    repo_url = "https://example.com/repo.git"
    sparse_dirs = ["dir1", "dir2"]
    clone_dir = Path("clone")

    clone_repository(repo_url, sparse_dirs, clone_dir)

    assert calls[0]["cmd"] == [
        "git",
        "clone",
        "--depth",
        "1",
        "--filter=blob:none",
        "--sparse",
        repo_url,
        str(clone_dir),
    ]
    assert calls[0]["check"] is True
    assert calls[1]["cmd"] == ["git", "sparse-checkout", "init", "--cone"]
    assert calls[1]["cwd"] == clone_dir
    assert calls[2]["cmd"] == ["git", "sparse-checkout", "set", *sparse_dirs]
    assert calls[2]["cwd"] == clone_dir
