from __future__ import annotations

import ssl
from typing import Any

import certifi
import orjson
import urllib3
from urllib3.util import Retry

from bash2gitlab.errors.exceptions import Bash2GitlabError

# --- Module-level client (reused for perf via connection pooling) ---
_SSL_CTX = ssl.create_default_context(cafile=certifi.where())

_RETRIES = Retry(
    total=1,  # network resiliency
    connect=1,
    read=1,
    backoff_factor=0.3,  # exponential backoff: 0.3, 0.6, 1.2, ...
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({"GET", "HEAD"}),
    raise_on_status=False,  # we’ll check r.status ourselves
)

_HTTP = urllib3.PoolManager(
    # tune these to your concurrency/throughput needs
    maxsize=10,  # sockets per host
    retries=_RETRIES,
    ssl_context=_SSL_CTX,  # verified TLS, SNI + hostname verify by default
    headers={
        "User-Agent": "bash2gitlab-update-checker/2",
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate, br",  # allow compression (urllib3 will auto-decode)
    },
)


def fetch_json(url: str, timeout: float) -> dict[str, Any]:
    """
    Fetch JSON metadata from PyPI (or any HTTPS JSON endpoint) using urllib3.

    Args:
        url: HTTPS URL to fetch.
        timeout: Total read timeout (seconds). Connect timeout is derived.

    Returns:
        Parsed JSON data as a dict.

    Raises:
        ValueError: If the URL is not HTTPS.
        RuntimeError: For non-2xx HTTP responses.
        urllib3.exceptions.HTTPError: For lower-level connection/timeout issues.
        json.JSONDecodeError: If the response isn't valid JSON.
    """
    if not url.lower().startswith("https://"):
        raise ValueError("Refusing to fetch non-HTTPS URL for security.")

    # # Split timeout into connect/read parts. Adjust to your latency profile.
    # connect_to = min(max(timeout * 0.3, 0.5), 5.0)  # 30% of total, clamped 0.5..5s
    # read_to = timeout

    # Stream then read so the connection is safely returned to the pool.
    # decode_content=True lets urllib3 transparently decompress gzip/deflate/br.
    with _HTTP.request(
        "GET",
        url,
        # timeout=urllib3.Timeout(connect=connect_to, read=read_to),
        timeout=urllib3.Timeout(connect=0.5, read=0.5),
        preload_content=False,
        decode_content=True,
    ) as r:
        if r.status == 404:
            raise Bash2GitlabError("Not Found")
        if r.status < 200 or r.status >= 300:
            # You can include response text if small; avoid logging huge bodies.
            raise RuntimeError(f"Unexpected HTTP status {r.status} for {url}")

        # JSON is UTF-8 by spec; if you want to honor charset, parse r.headers.
        raw = r.read()
        return orjson.loads(raw.decode("utf-8"))
