#!/usr/bin/env python3
"""
Report which PyPI projects owned by a given username declare support for Python 3.14,
and the newest release version that does.

Signals for "supports 3.14":
  - Trove classifier "Programming Language :: Python :: 3.14"
  - OR requires_python specifier that includes 3.14

Notes:
  - Uses XML-RPC user_packages(user) to list projects (rate-limited/unsupported).
  - Uses JSON API for project/release metadata.
  - Safe to run multiple times; no auth required.

Dependencies:
  python -m pip install requests packaging
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import time
import xmlrpc.client
from dataclasses import dataclass
from collections.abc import Iterable

import requests
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

XMLRPC_URL = "https://pypi.org/pypi"
JSON_PROJECT = "https://pypi.org/pypi/{name}/json"
JSON_RELEASE = "https://pypi.org/pypi/{name}/{version}/json"
TIMEOUT = 20
MAX_WORKERS = 6

PY_TAG = "Programming Language :: Python :: 3.14"
PY_VERSION_STR = "3.14"

@dataclass(frozen=True)
class SupportResult:
    name: str
    supported: bool
    version: str | None  # newest release that supports 3.14 (or None)
    reason: str             # "classifier", "requires_python", or ""

def list_user_projects(username: str) -> list[str]:
    # XML-RPC is rate-limited; avoid rapid re-tries
    client = xmlrpc.client.ServerProxy(XMLRPC_URL)
    # polite pause in case caller loops this tool
    time.sleep(1.0)
    pairs: list[tuple[str, str]] = client.user_packages(username)  # [(role, package_name), ...]
    # dedupe & sort
    names = sorted({name for _role, name in pairs}, key=str.lower)
    return names

def _releases_sorted(name: str) -> list[str]:
    # hit project JSON once to get the release list cheaply
    r = requests.get(JSON_PROJECT.format(name=name), timeout=TIMEOUT)
    if r.status_code != 200:
        return []
    data = r.json()
    versions = list(data.get("releases", {}).keys())
    def key(v: str):
        try:
            return Version(v)
        except InvalidVersion:
            # put weird versions at the end, but keep determinism
            return Version("0!0")
    versions.sort(key=key, reverse=True)
    return versions

def _release_supports(name: str, version: str) -> tuple[bool, str]:
    # fetch per-release JSON for classifiers & requires_python
    r = requests.get(JSON_RELEASE.format(name=name, version=version), timeout=TIMEOUT)
    if r.status_code != 200:
        return (False, "")
    info = r.json().get("info", {})
    classifiers: Iterable[str] = info.get("classifiers", []) or []
    if PY_TAG in classifiers:
        return (True, "classifier")
    rp = (info.get("requires_python") or "").strip()
    if rp:
        try:
            if SpecifierSet(rp).contains(PY_VERSION_STR, prereleases=True):
                return (True, "requires_python")
        except Exception:
            pass
    return (False, "")

def check_project(name: str) -> SupportResult:
    versions = _releases_sorted(name)
    for v in versions:
        ok, why = _release_supports(name, v)
        if ok:
            return SupportResult(name=name, supported=True, version=v, reason=why)
    return SupportResult(name=name, supported=False, version=None, reason="")

def main() -> None:
    ap = argparse.ArgumentParser(description="Report which PyPI projects for a user support Python 3.14.")
    ap.add_argument("username", nargs="?", default="matthewdeanmartin")
    ap.add_argument("--max-workers", type=int, default=MAX_WORKERS, help="Concurrency for JSON reads.")
    args = ap.parse_args()

    try:
        projects = list_user_projects(args.username)
    except Exception as e:
        print("ERROR: Could not enumerate projects via XML-RPC. This endpoint is rate-limited/unsupported and may be removed.")
        print(f"Detail: {e}")
        print("Pivot options: libraries.io or pypi.rs (PyPIrs) APIs.")
        return

    if not projects:
        print(f"No projects found for user: {args.username}")
        return

    results: list[SupportResult] = []
    with cf.ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        for res in ex.map(check_project, projects):
            results.append(res)

    # stable order by name
    results.sort(key=lambda r: r.name.lower())

    # Output
    ok = [r for r in results if r.supported]
    no = [r for r in results if not r.supported]
    print(f"# PyPI projects owned by '{args.username}' that declare support for Python {PY_VERSION_STR}")
    print()
    print("## Supported")
    if ok:
        for r in ok:
            print(f"- {r.name}: {r.version}  ({r.reason})")
    else:
        print("- (none)")

    print()
    print("## Not supported (no 3.14 classifier or compatible requires_python found)")
    if no:
        for r in no:
            print(f"- {r.name}")
    else:
        print("- (none)")

if __name__ == "__main__":
    main()
