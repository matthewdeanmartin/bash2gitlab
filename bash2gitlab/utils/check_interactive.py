from __future__ import annotations

import os
import sys
from typing import Literal

EnvType = Literal["interactive", "non-interactive"]


def detect_environment() -> EnvType:
    """
    Detect if the current process is running interactively (likely a user
    on a laptop/terminal) or in a non-interactive context (CI, build server,
    cron, etc.).

    Returns:
        "interactive" or "non-interactive"

    Detection strategy:
    - CI markers: CI=true, GITHUB_ACTIONS, GITLAB_CI, BUILD_ID, etc.
    - Headless signals: DISPLAY unset (on Linux), running as PID 1 in container.
    - Non-TTY stdin/stdout/stderr (not attached to terminal).
    - Fallback: default to "interactive".
    """
    # --- CI / build system markers ---
    ci_env_markers = [
        "CI",
        "BUILD_ID",
        "BUILD_NUMBER",
        "TEAMCITY_VERSION",
        "JENKINS_HOME",
        "GITHUB_ACTIONS",
        "GITLAB_CI",
        "CIRCLECI",
        "TRAVIS",
        "APPVEYOR",
        "AZURE_HTTP_USER_AGENT",
    ]
    for marker in ci_env_markers:
        if os.getenv(marker):
            return "non-interactive"

    # --- Headless signals ---
    if sys.platform.startswith("linux") and not os.getenv("DISPLAY"):
        # But ignore WSL and interactive shells where DISPLAY may not be set
        if "WSL_DISTRO_NAME" not in os.environ and "TERM" not in os.environ:
            return "non-interactive"

    # --- Container heuristics ---
    if os.path.exists("/.dockerenv"):
        return "non-interactive"
    try:
        with open("/proc/1/cgroup") as f:
            if "docker" in f.read() or "kubepods" in f.read():
                return "non-interactive"
    except OSError:
        pass  # not Linux, skip

    # --- TTY checks ---
    if not (sys.stdin.isatty() and sys.stdout.isatty() and sys.stderr.isatty()):
        return "non-interactive"

    # --- Default ---
    return "interactive"
