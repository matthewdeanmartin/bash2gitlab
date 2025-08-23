import os
import platform
from pathlib import Path


def detect_shell() -> str:
    """
    Basic shell detection that works on Linux, macOS, WSL, Git Bash, Cygwin, etc.

    Returns:
        str: shell name ("bash", "zsh", "fish", "cmd", "powershell", "unknown")
    """
    # If SHELL is set (typical on POSIX, Git Bash, Cygwin, MSYS2), prefer it
    shell = os.environ.get("SHELL")
    if shell:
        return Path(shell).name.lower()

    system = platform.system().lower()

    # Windows native (no SHELL set)
    if system == "windows":
        comspec = os.environ.get("COMSPEC", "").lower()
        if "powershell" in comspec:
            return "powershell"
        if "cmd" in comspec:
            return "cmd"
        return Path(comspec).stem if comspec else "cmd"

    return "unknown"


def supports_underline() -> bool:
    """
    Guess whether the current terminal supports ANSI underline.

    Uses detect_shell() and env vars. Conservative: return False if unsure.
    """
    if os.getenv("NO_COLOR"):
        return False

    shell = detect_shell()
    system = platform.system().lower()

    # Windows cases
    if system == "windows":
        # Git Bash / Cygwin / MSYS2 → these export SHELL=/usr/bin/bash
        if shell in {"bash", "zsh", "fish"}:
            return True
        # Windows Terminal (env var set)
        if os.environ.get("WT_SESSION"):
            return True
        if shell == "powershell":
            return True
        # Classic cmd.exe
        return False

    # POSIX cases (Linux, macOS, WSL)
    term = os.environ.get("TERM", "")
    if term in ("dumb", ""):
        return False

    return True
