#!/usr/bin/env python3
"""
Check upgrade status of all Python.org installs on Windows.

- Enumerates installs via `py -0p` and Windows registry.
- Compares installed versions against latest patch for their minor cycle
  using endoflife.date's Python JSON API.
- Flags EOL series and suggests moving to the newest maintained cycle.

Exit codes:
  0 = all installs are up to date (or newer than known latest)
  1 = at least one install could/should be upgraded
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.request import urlopen

# ------------------------------- Models -------------------------------------


@dataclass(frozen=True)
class Install:
    path: Path
    version: str  # e.g. "3.11.9"
    cycle: str    # e.g. "3.11"


@dataclass(frozen=True)
class CycleInfo:
    cycle: str            # "3.11"
    latest: Optional[str] # "3.11.9" (may be None/"" if unknown)
    eol: Optional[date]   # EOL date if known


# --------------------------- Version Utilities -------------------------------

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_version(v: str) -> Tuple[int, int, int]:
    m = _VERSION_RE.match(v.strip())
    if not m:
        # Try to chop off any trailing tags (e.g., 3.13.0rc2 -> 3.13.0)
        base = re.split(r"[^\d.]", v.strip())[0]
        m2 = _VERSION_RE.match(base)
        if not m2:
            raise ValueError(f"Unrecognized version format: {v!r}")
        m = m2
    return tuple(map(int, m.groups()))  # type: ignore[return-value]


def version_lt(a: str, b: str) -> bool:
    return parse_version(a) < parse_version(b)


def version_cycle(v: str) -> str:
    major, minor, _ = parse_version(v)
    return f"{major}.{minor}"


# --------------------------- Discovery (Windows) -----------------------------

def _discover_with_py_launcher() -> List[Path]:
    """Use `py -0p` to list interpreter paths."""
    try:
        out = subprocess.check_output(["py", "-0p"], text=True, stderr=subprocess.STDOUT)
    except (OSError, subprocess.CalledProcessError):
        return []
    paths: List[Path] = []
    for line in out.splitlines():
        line = line.strip()
        # Example lines:
        #  -3.12-64        C:\Users\me\AppData\Local\Programs\Python\Python312\python.exe
        #  -3.11-32        C:\Python311-32\python.exe
        # Sometimes it can just be a path line when using older launcher versions.
        m = re.search(r"([A-Za-z]:\\.*?python\.exe)\s*$", line, flags=re.IGNORECASE)
        if m:
            paths.append(Path(m.group(1)))
    return paths


def _discover_from_registry() -> List[Path]:
    """Look in PythonCore InstallPath keys (both HKLM/HKCU, 32/64)."""
    import winreg  # type: ignore

    roots = [
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Python\PythonCore"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Python\PythonCore"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Python\PythonCore"),
    ]
    exe_paths: List[Path] = []

    for root, base in roots:
        try:
            with winreg.OpenKey(root, base) as h:
                i = 0
                while True:
                    try:
                        ver = winreg.EnumKey(h, i)  # e.g., "3.11"
                        i += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(h, fr"{ver}\InstallPath") as pkey:
                            # Prefer ExecutablePath value if present
                            try:
                                exe, _ = winreg.QueryValueEx(pkey, "ExecutablePath")
                                exe_paths.append(Path(exe))
                                continue
                            except OSError:
                                pass
                            # Else use (Default) value as directory\python.exe
                            try:
                                inst_dir, _ = winreg.QueryValueEx(pkey, None)
                                exe_paths.append(Path(inst_dir) / "python.exe")
                            except OSError:
                                pass
                    except OSError:
                        continue
        except OSError:
            continue

    # De-dup and keep only existing files
    cleaned = []
    seen = set()
    for p in exe_paths:
        try:
            rp = p.resolve(strict=True)
        except FileNotFoundError:
            continue
        if rp not in seen:
            seen.add(rp)
            cleaned.append(rp)
    return cleaned


def discover_python_executables() -> List[Path]:
    paths = _discover_with_py_launcher()
    # Add registry finds
    for p in _discover_from_registry():
        if p not in paths:
            paths.append(p)
    # Keep only unique existing
    unique = []
    seen = set()
    for p in paths:
        try:
            rp = p.resolve(strict=True)
        except FileNotFoundError:
            continue
        if rp not in seen:
            seen.add(rp)
            unique.append(rp)
    return unique


def get_python_version(exe: Path) -> Optional[str]:
    try:
        out = subprocess.check_output(
            [str(exe), "-c", "import sys;print(sys.version.split()[0])"],
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
        # Normalize rc/beta to base if present
        base = re.split(r"[^\d.]", out)[0]
        return base if base else out
    except Exception:
        return None


# ----------------------------- Remote metadata -------------------------------

def fetch_python_cycles() -> Dict[str, CycleInfo]:
    """
    Pull Python cycle info from endoflife.date.
    Fallback: if the API is unreachable, return empty dict (script still reports local installs).
    """
    url = "https://endoflife.date/api/python.json"
    try:
        with urlopen(url, timeout=10) as resp:
            data = json.load(resp)
    except Exception:
        return {}

    cycles: Dict[str, CycleInfo] = {}
    for row in data:
        cycle = str(row.get("cycle", "")).strip()
        latest = (row.get("latest") or "").strip() or None
        eol_raw = (row.get("eol") or "").strip()
        eol_dt: Optional[date] = None
        if eol_raw and eol_raw.lower() not in {"false", "true"}:
            try:
                y, m, d = map(int, eol_raw.split("-"))
                eol_dt = date(y, m, d)
            except Exception:
                eol_dt = None
        if cycle:
            cycles[cycle] = CycleInfo(cycle=cycle, latest=latest, eol=eol_dt)
    return cycles


def newest_maintained_cycle(cycles: Dict[str, CycleInfo]) -> Optional[str]:
    today = date.today()
    maintained = []
    for c in cycles.values():
        # Consider maintained if EOL unknown or in the future and latest is known
        if c.latest and (c.eol is None or c.eol >= today):
            maintained.append(c.cycle)
    if not maintained:
        return None
    # Pick numerically greatest X.Y
    def keyfn(s: str) -> Tuple[int, int]:
        x, y = s.split(".")
        return int(x), int(y)
    return max(maintained, key=keyfn)


# ------------------------------- Reporting -----------------------------------

def main() -> int:
    if os.name != "nt":
        print("This script is intended for Windows.", file=sys.stderr)
        return 1

    exes = discover_python_executables()
    if not exes:
        print("No Python installations found (py launcher/registry).")
        return 1

    installs: List[Install] = []
    for exe in exes:
        v = get_python_version(exe)
        if not v:
            continue
        installs.append(Install(path=exe, version=v, cycle=version_cycle(v)))

    # Fetch remote cycles metadata
    cycles = fetch_python_cycles()
    newest_cycle = newest_maintained_cycle(cycles)

    print("\nDiscovered Python installations:\n")
    for inst in installs:
        print(f"  - {inst.version:<8}  {inst.path}")

    if not cycles:
        print("\nWarning: Could not fetch latest version info. "
              "Network blocked or API unavailable. Showing only local installs.")
        # No remote comparison possible -> treat as no actionable signal
        return 0

    print("\nUpgrade assessment:\n")
    any_action = False
    today = date.today()

    for inst in installs:
        ci = cycles.get(inst.cycle)
        status_lines: List[str] = []
        recs: List[str] = []

        # Patch status for same cycle
        if ci and ci.latest:
            try:
                if version_lt(inst.version, ci.latest):
                    status_lines.append(
                        f"• Patch available for {inst.cycle}: {inst.version} → {ci.latest}"
                    )
                    recs.append(f"Install Python {ci.latest} (same series).")
                else:
                    status_lines.append(f"• Up-to-date on {inst.cycle} (installed {inst.version}).")
            except Exception:
                status_lines.append(f"• Comparison failed versus latest {ci.latest} for {inst.cycle}.")
        else:
            status_lines.append(f"• No 'latest' info found for cycle {inst.cycle}.")

        # EOL check
        if ci and ci.eol:
            if ci.eol < today:
                status_lines.append(f"• {inst.cycle} is **EOL** (ended {ci.eol.isoformat()}).")
                if newest_cycle and newest_cycle != inst.cycle:
                    recs.append(f"Upgrade to maintained series {newest_cycle} (latest {cycles[newest_cycle].latest}).")
            else:
                # Not EOL yet, but suggest newer series if available
                if newest_cycle and newest_cycle != inst.cycle:
                    recs.append(f"Consider moving to {newest_cycle} (latest {cycles[newest_cycle].latest}) for newest features.")
        elif ci and ci.eol is None:
            # Unknown EOL
            pass

        # Summarize
        print(f"{inst.version:<8} {inst.path}")
        for s in status_lines:
            print(f"    {s}")
        if recs:
            any_action = True
            print("    Recommendation:")
            for r in recs:
                print(f"      - {r}")
        print()

    if any_action:
        print("One or more installations can be upgraded.\n")
        print("Notes:")
        print("  • Download official Windows installers from https://www.python.org/downloads/windows/")
        print("  • After installing a new version, you can keep older ones side-by-side.")
        print("  • Ensure the py launcher is updated (comes with python.org installers).")
        return 1

    print("All discovered Python installations are up to date.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
