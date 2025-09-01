# perf_update_checker_real.py
"""
Real-network performance harness for update_checker.py (no mocks, no sleeps).

What it does:
  - Baseline direct GET to pypi.org with urllib3 (timings + headers)
  - Runs your module's check_for_updates() with cache_ttl_seconds=0
  - Calls get_version_info_from_pypi() with configurable timeout/retries/backoff
  - Sequential and concurrent rounds (to reveal throttling / 429s)
  - Resets your cache in between runs

Adjust the SETTINGS section below to change packages, rounds, workers, etc.
"""

from __future__ import annotations

import datetime as dt
import json
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

# -- External direct baseline (independent of your wrapper)
import urllib3

# -- Module under test (must be importable from CWD)
import bash2gitlab.utils.update_checker as uc

# ============================
# SETTINGS
# ============================

# Primary package to test *your* flow with (cache path is per-package)
PKG = "bash2gitlab"
CURRENT_VER = "0.0.0"   # use a very old version to likely trigger an update message

# Additional packages to probe pypi.org behavior under concurrency
# (Use popular packages to test cache/CDN behavior across multiple endpoints)
EXTRA_PKGS = ["requests", "urllib3", "pip", "setuptools", "wheel", "pytest", "flask", "django"]

# Sequential rounds for check_for_updates (each forces network)
SEQUENTIAL_ROUNDS = 3

# Concurrency config for direct PyPI JSON GETs and get_version_info_from_pypi()
CONCURRENT_WORKERS = 8

# get_version_info_from_pypi() knobs (these are your function's parameters)
TIMEOUT = 5.0
RETRIES = 2
BACKOFF = 0.5

# Pool manager for direct calls (reuse connections)
HTTP = urllib3.PoolManager(num_pools=10, maxsize=CONCURRENT_WORKERS, retries=False)


# ============================
# UTILITIES
# ============================

def ts() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

@dataclass
class Result:
    label: str
    ok: bool
    total_s: float
    details: dict[str, Any]

def log(line: str) -> None:
    print(f"[{ts()}] {line}")

def reset_cache_for(pkg: str) -> None:
    # Use your public API, then double-check the path
    uc.reset_cache(pkg)
    _, cache_file = uc.cache_paths(pkg)
    try:
        if cache_file.exists():
            cache_file.unlink(missing_ok=True)
    except OSError:
        pass


# ============================
# DIAGNOSTICS (REAL NETWORK)
# ============================

def dns_resolve(host: str = "pypi.org") -> Result:
    t0 = time.perf_counter()
    log(f"DNS resolve start: {host}")
    addrs = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    t1 = time.perf_counter()
    details = {
        "host": host,
        "addr_count": len(addrs),
        "unique_ips": sorted({a[4][0] for a in addrs}),
    }
    return Result("dns_resolve", True, t1 - t0, details)


def pypi_direct_get(package: str) -> Result:
    url = f"https://pypi.org/pypi/{package}/json"
    t0 = time.perf_counter()
    log(f"Direct GET start: {url}")
    try:
        resp = HTTP.request("GET", url, timeout=urllib3.Timeout(connect=TIMEOUT, read=TIMEOUT), preload_content=False)
        raw = resp.read()
        size = len(raw)
        status = resp.status
        headers = {k: v for k, v in resp.headers.items()}
        # parse to ensure JSON is sane
        parsed = json.loads(raw.decode("utf-8"))
        releases_len = len(parsed.get("releases", {}))
        t1 = time.perf_counter()
        ok = (200 <= status < 300)
        return Result(
            "pypi_direct_get",
            ok,
            t1 - t0,
            {
                "package": package,
                "status": status,
                "size_bytes": size,
                "releases": releases_len,
                "headers": {
                    # show interesting potential throttling/CDN signals if present
                    k: headers.get(k)
                    for k in [
                        "Server",
                        "Via",
                        "Age",
                        "CF-RAY",
                        "CF-Cache-Status",
                        "Retry-After",
                        "X-Served-By",
                        "X-Cache",
                        "X-CDN",
                        "X-RateLimit-Remaining",
                        "X-RateLimit-Reset",
                    ]
                    if headers.get(k) is not None
                },
            },
        )
    except Exception as e:
        t1 = time.perf_counter()
        return Result("pypi_direct_get", False, t1 - t0, {"package": package, "error": repr(e)})


def run_check_for_updates_once(package: str, current_version: str) -> Result:
    reset_cache_for(package)  # force real network
    t0 = time.perf_counter()
    log(f"check_for_updates() start: package={package}")
    try:
        msg = uc.check_for_updates(
            package_name=package,
            current_version=current_version,
            cache_ttl_seconds=0,          # FORCE network
            include_prereleases=False,
        )
        t1 = time.perf_counter()
        return Result(
            "check_for_updates",
            True,
            t1 - t0,
            {
                "package": package,
                "msg_present": bool(msg),
                "msg_len": len(msg or ""),
            },
        )
    except Exception as e:
        t1 = time.perf_counter()
        return Result("check_for_updates", False, t1 - t0, {"package": package, "error": repr(e)})


def run_get_version_info_once(package: str, current_version: str) -> Result:
    reset_cache_for(package)  # not strictly necessary, but keeps behavior deterministic
    t0 = time.perf_counter()
    log(f"get_version_info_from_pypi() start: package={package}")
    try:
        info = uc.get_version_info_from_pypi(
            package, current_version,
            include_prereleases=False,
            timeout=TIMEOUT,
            retries=RETRIES,
            backoff=BACKOFF,
        )
        t1 = time.perf_counter()
        return Result(
            "get_version_info_from_pypi",
            True,
            t1 - t0,
            {
                "package": package,
                "latest_stable": info.latest_stable,
                "latest_dev": info.latest_dev,
                "current_yanked": info.current_yanked,
                "timeout": TIMEOUT,
                "retries": RETRIES,
                "backoff": BACKOFF,
            },
        )
    except Exception as e:
        t1 = time.perf_counter()
        return Result("get_version_info_from_pypi", False, t1 - t0, {
            "package": package,
            "error": repr(e),
            "timeout": TIMEOUT,
            "retries": RETRIES,
            "backoff": BACKOFF,
        })


# ============================
# RUNNERS
# ============================

def print_result(r: Result) -> None:
    status = "OK " if r.ok else "ERR"
    log(f"{r.label:28} | {status} | {r.total_s:7.3f}s | {r.details}")

def sequential_rounds() -> None:
    log("=" * 84)
    log(f"SEQUENTIAL check_for_updates() rounds (cache_ttl_seconds=0), package={PKG}")
    for i in range(1, SEQUENTIAL_ROUNDS + 1):
        log(f"-- round {i}/{SEQUENTIAL_ROUNDS} --")
        res = run_check_for_updates_once(PKG, CURRENT_VER)
        print_result(res)

def concurrent_direct_gets() -> None:
    log("=" * 84)
    all_pkgs = [PKG] + EXTRA_PKGS
    log(f"CONCURRENT direct GETs to PyPI JSON (workers={CONCURRENT_WORKERS})")
    with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as ex:
        futs = [ex.submit(pypi_direct_get, pkg) for pkg in all_pkgs]
        for fut in as_completed(futs):
            print_result(fut.result())

def concurrent_version_info() -> None:
    log("=" * 84)
    all_pkgs = [PKG] + EXTRA_PKGS
    log(f"CONCURRENT get_version_info_from_pypi() (workers={CONCURRENT_WORKERS}, "
        f"timeout={TIMEOUT}, retries={RETRIES}, backoff={BACKOFF})")
    with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as ex:
        futs = [ex.submit(run_get_version_info_once, pkg, CURRENT_VER) for pkg in all_pkgs]
        for fut in as_completed(futs):
            print_result(fut.result())


# ============================
# MAIN
# ============================

def main() -> None:
    log("=" * 84)
    log("update_checker.py REAL-NETWORK PERFORMANCE HARNESS")
    log("=" * 84)
    # Pin color/CI env to reduce noise in output behavior
    for k in ("NO_COLOR", "CI"):
        if k in sys.argv:
            pass
    # 1) DNS timing (helps distinguish name resolution from HTTP latency)
    print_result(dns_resolve("pypi.org"))

    # 2) Baseline direct GET (module-independent)
    print_result(pypi_direct_get(PKG))

    # 3) Sequential module calls (force network every time)
    sequential_rounds()

    # 4) Concurrent direct GETs (surface throttling / 429s if any)
    concurrent_direct_gets()

    # 5) Concurrent module-level metadata fetches with your retry/backoff
    concurrent_version_info()

    log("=" * 84)
    log("Done.")


if __name__ == "__main__":
    main()
