# test_detect_environment.py
import os
import sys

import pytest

from bash2gitlab.utils.check_interactive import detect_environment


@pytest.mark.parametrize(
    "marker",
    [
        "CI",
        "GITHUB_ACTIONS",
        "GITLAB_CI",
        "TRAVIS",
        "CIRCLECI",
        "APPVEYOR",
        "TEAMCITY_VERSION",
    ],
)
def test_detect_environment_ci_markers(monkeypatch, marker):
    monkeypatch.setenv(marker, "1")
    assert detect_environment() == "non-interactive"


def test_detect_environment_headless_display(monkeypatch):
    # No DISPLAY or TERM
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    # Fallback TTYs true
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)

    assert detect_environment() == "non-interactive"


def test_detect_environment_non_tty(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    assert detect_environment() == "non-interactive"


def test_detect_environment_interactive(monkeypatch):
    # Clean environment
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)

    # Prevent docker markers
    monkeypatch.setattr(os.path, "exists", lambda path: False)
