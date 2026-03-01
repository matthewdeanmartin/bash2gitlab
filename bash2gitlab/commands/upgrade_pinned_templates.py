from __future__ import annotations

import dataclasses
import re
import ssl
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote_plus

import certifi
import orjson  # Using orjson for JSON operations as in the helper
import urllib3
from packaging.version import InvalidVersion, Version
from ruamel.yaml import YAML
from urllib3.util import Retry

# -------------------------------
# Types and data structures
# -------------------------------

RefType = Literal["none", "branch", "tag", "commit", "unknown"]


@dataclass(frozen=True)
class SimpleResponse:
    """A minimal, requests.Response-like object for urllib3 responses."""

    status_code: int
    data: bytes

    def json(self) -> Any:
        """Parse response data as JSON."""
        if not self.data:
            return None
        return orjson.loads(self.data)


@dataclass(frozen=True)
class IncludeSpec:
    kind: Literal["project", "remote", "local", "template"]
    raw: dict[str, Any]  # Original mapping from YAML for this include
    project: str | None = None
    ref: str | None = None
    file: str | None | list[str] = None
    remote: str | None = None
    local: str | None = None
    template: str | None = None


@dataclass(frozen=True)
class Suggestion:
    new_ref: str
    reason: str  # e.g., "newer tag available", "un pinned; suggesting latest tag"


@dataclass(frozen=True)
class IncludeAnalysis:
    include: IncludeSpec
    ref_type: RefType
    pinned: bool
    current_ref: str | None
    suggestion: Suggestion | None
    notes: str | None = None


# -------------------------------
# GitLab API client (minimal, using urllib3)
# -------------------------------


class GitLabClient:
    """
    Minimal GitLab API helper using urllib3.

    Auth: Personal Access Token (header: PRIVATE-TOKEN) or OAuth Bearer (header: Authorization).
    """

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        oauth_token: str | None = None,
        timeout: float = 15.0,
        max_retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        # Setup headers
        self.headers = {
            "User-Agent": "gitlab-include-pin-checker/1.0",
            "Accept": "application/json",
        }
        if token:
            self.headers["PRIVATE-TOKEN"] = token
        if oauth_token:
            self.headers["Authorization"] = f"Bearer {oauth_token}"

        # Setup urllib3 PoolManager based on the provided helper's pattern
        _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
        _RETRIES = Retry(
            total=max_retries,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            raise_on_status=False,
        )
        self.http = urllib3.PoolManager(
            maxsize=10,
            retries=_RETRIES,
            ssl_context=_SSL_CTX,
        )

    def _get(self, path: str, ok=(200,)) -> SimpleResponse:
        """Execute GET request with retries and connection pooling."""
        url = f"{self.base_url}{path}"
        try:
            with self.http.request(
                "GET",
                url,
                headers=self.headers,
                timeout=self.timeout,
                preload_content=False,
                decode_content=True,
            ) as r:
                # The caller will check the status code against its 'ok' tuple.
                # We read the data inside the `with` block to release the connection.
                data = r.read()
                return SimpleResponse(status_code=r.status, data=data)
        except urllib3.exceptions.MaxRetryError as e:
            raise RuntimeError(f"GET failed for {url} too many retries") from e
        except urllib3.exceptions.HTTPError as e:
            raise RuntimeError(f"A network error occurred for GET {url}") from e

    @staticmethod
    def _proj_id(project_path: str) -> str:
        """URL-encode project path for GitLab API."""
        # project path like "group/subgroup/name" must be URL-encoded
        return quote_plus(project_path)

    # ---- project info ----

    def get_project(self, project_path: str) -> dict[str, Any] | None:
        """Fetch project metadata from GitLab API."""
        r = self._get(f"/api/v4/projects/{self._proj_id(project_path)}", ok=(200, 404))
        return None if r.status_code == 404 else r.json()

    def get_default_branch(self, project_path: str) -> str | None:
        """Get default branch name for a project."""
        proj = self.get_project(project_path)
        if not proj:
            return None
        return proj.get("default_branch")

    # ---- tags, branches, commits ----

    def list_tags(self, project_path: str, per_page: int = 100) -> list[dict[str, Any]]:
        """Fetch all tags for a project, paginating as needed."""
        tags: list[dict[str, Any]] = []
        page = 1
        while True:
            r = self._get(
                f"/api/v4/projects/{self._proj_id(project_path)}/repository/tags" f"?per_page={per_page}&page={page}",
                ok=(200, 404),
            )
            if r.status_code != 200:
                break
            batch = r.json()
            if not batch:
                break
            tags.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        return tags

    def get_branch(self, project_path: str, branch: str) -> dict[str, Any] | None:
        """Fetch branch metadata from GitLab API."""
        r = self._get(
            f"/api/v4/projects/{self._proj_id(project_path)}/repository/branches/{quote_plus(branch)}",
            ok=(200, 404),
        )
        return None if r.status_code == 404 else r.json()

    def get_tag(self, project_path: str, tag: str) -> dict[str, Any] | None:
        """Fetch tag metadata from GitLab API."""
        r = self._get(
            f"/api/v4/projects/{self._proj_id(project_path)}/repository/tags/{quote_plus(tag)}",
            ok=(200, 404),
        )
        return None if r.status_code == 404 else r.json()

    def get_commit(self, project_path: str, sha: str) -> dict[str, Any] | None:
        """Fetch commit metadata from GitLab API."""
        r = self._get(
            f"/api/v4/projects/{self._proj_id(project_path)}/repository/commits/{quote_plus(sha)}",
            ok=(200, 404),
        )
        return None if r.status_code == 404 else r.json()


# -------------------------------
# YAML parsing helpers
# -------------------------------

_HEX40 = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


def _load_yaml(path: str) -> dict[str, Any]:
    """Load and parse YAML file, ensuring root is a dict."""
    yaml = YAML(typ="rt")  # round-trip preserves formatting if you later want to write
    with open(path, encoding="utf-8") as f:
        data = yaml.load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("Root of .gitlab-ci.yml must be a mapping.")
    return data


def _normalize_includes(root: dict[str, Any]) -> list[IncludeSpec]:
    """
    Normalize every include into IncludeSpec with 'kind' in {'project', 'remote', 'local', 'template'}.

    GitLab allows:
      include:
        - local: path.yml
        - remote: https://...
        - template: Auto-DevOps.gitlab-ci.yml
        - project: group/repo
          ref: v1.2.3
          file:
            - path1.yml
            - path2.yml
      include: 'path.yml'           # shorthand local
      include: { local: 'x.yml' }   # mapping
    """

    def one_include(obj: Any) -> Iterable[IncludeSpec]:
        if isinstance(obj, str):
            yield IncludeSpec(kind="local", raw={"local": obj}, local=obj)
            return
        if isinstance(obj, dict):
            if "project" in obj:
                yield IncludeSpec(
                    kind="project",
                    raw=obj,
                    project=obj.get("project"),
                    ref=obj.get("ref"),
                    file=obj.get("file"),
                )
            elif "remote" in obj:
                yield IncludeSpec(kind="remote", raw=obj, remote=obj.get("remote"))
            elif "local" in obj:
                yield IncludeSpec(kind="local", raw=obj, local=obj.get("local"))
            elif "template" in obj:
                yield IncludeSpec(kind="template", raw=obj, template=obj.get("template"))
            else:
                # Unknown mapping; keep raw for transparency
                yield IncludeSpec(kind="local", raw=obj)  # safest default
            return
        # Unknown scalar/sequence -> ignore
        return

    inc = root.get("include")
    specs: list[IncludeSpec] = []
    if inc is None:
        return specs
    if isinstance(inc, list):
        for entry in inc:
            specs.extend(list(one_include(entry)))
    else:
        # single include (scalar or mapping)
        specs.extend(list(one_include(inc)))
    return specs


# -------------------------------
# SemVer + Tag sorting helpers
# -------------------------------


def _sort_tags_semver_first(tags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Return tags sorted preferring SemVer (descending), then by commit date (newest first).
    """
    # def parse_created_at(tag: dict[str, Any]) -> float:
    #     # GitLab tag JSON usually includes 'commit': {'created_at': "..."}; be defensive.
    #     try:
    #         # crude parse: "2024-08-30T12:34:56.000+00:00"
    #         s = tag.get("commit", {}).get("created_at") or tag.get("release", {}).get("created_at")
    #         return time.mktime(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")) if s else 0.0
    #     except Exception:
    #         return 0.0
    #
    # def semver_key(name: str) -> Tuple[int, dict[str, Any] | None]:
    #     # Returns (is_semver, Version or None)
    #     try:
    #         # Accept tags like "v1.2.3" or "1.2.3"
    #         normalized = name[1:] if name.startswith("v") else name
    #         return (1, Version(normalized))
    #     except InvalidVersion:
    #         return (0, None)

    # unused?
    # def composite_key(tag: dict[str, Any]):
    #     name = tag.get("name", "")
    #     is_semver, ver = semver_key(name)
    #     # Sort: semver first and higher version first; else by created_at descending.
    #     return (
    #         -is_semver,
    #         -(ver or Version("0"))._key if ver else 0,  # using Version's internal sortable key
    #         -parse_created_at(tag),
    #     )

    # Python can't sort by Version's private key directly inside tuple cleanly; workaround:
    # We'll sort in two passes: semver desc by Version, then date desc for non-semver.
    semver_tags = []
    other_tags = []
    for t in tags:
        name = t.get("name", "")
        try:
            v = Version(name[1:] if name.startswith("v") else name)
            semver_tags.append((v, t))
        except InvalidVersion:
            other_tags.append(t)
    semver_tags.sort(key=lambda vt: vt[0], reverse=True)
    other_tags.sort(key=lambda t: t.get("commit", {}).get("created_at", ""), reverse=True)
    return [t for _, t in semver_tags] + other_tags


# -------------------------------
# Ref classification
# -------------------------------


def _classify_ref(gl: GitLabClient, project: str, ref: str | None) -> RefType:
    """Classify a ref as none, tag, branch, commit, or unknown."""
    if not ref:
        return "none"
    if _HEX40.match(ref):
        # make sure commit exists
        return "commit" if gl.get_commit(project, ref) else "unknown"
    if gl.get_tag(project, ref):
        return "tag"
    if gl.get_branch(project, ref):
        return "branch"
    return "unknown"


# -------------------------------
# Core: analyze includes and suggest pins
# -------------------------------


def suggest_include_pins(
    gitlab_ci_path: str,
    gitlab_base_url: str,
    *,
    token: str | None = None,
    oauth_token: str | None = None,
    pin_tags_only: bool = True,
) -> list[IncludeAnalysis]:
    """
    Analyze `.gitlab-ci.yml` includes and suggest re-pinning strategies.

    Args:
        gitlab_ci_path: Path to the .gitlab-ci.yml file.
        gitlab_base_url: Base URL of GitLab instance, e.g., "https://gitlab.com".
        token: GitLab Personal Access Token (PRIVATE-TOKEN), if needed for private projects.
        oauth_token: OAuth token (Bearer), alternative to 'token'.
        pin_tags_only: If True, suggestions always use tags. If False, may return branch's latest commit (but still prefers tags).

    Returns:
        A list of IncludeAnalysis entries (one per include item).
    """
    root = _load_yaml(gitlab_ci_path)
    includes = _normalize_includes(root)
    gl = GitLabClient(gitlab_base_url, token=token, oauth_token=oauth_token)

    analyses: list[IncludeAnalysis] = []
    for spec in includes:
        # Only 'project' kind can/should be repinned via project/ref/file.
        if spec.kind != "project" or not spec.project:
            analyses.append(
                IncludeAnalysis(
                    include=spec,
                    ref_type="unknown" if spec.kind == "remote" else "none",
                    pinned=False,
                    current_ref=None,
                    suggestion=None,
                    notes="Non-project include (remote/local/template) not analyzed for pinning.",
                )
            )
            continue

        ref_type = _classify_ref(gl, spec.project, spec.ref)
        pinned = ref_type in ("tag", "commit")
        current_ref = spec.ref

        # Gather tags; we prefer tags for stability.
        tags = gl.list_tags(spec.project)
        latest_tag_name: str | None = None
        if tags:
            latest_tag_name = tags_sorted[0]["name"] if (tags_sorted := _sort_tags_semver_first(tags)) else None

        suggestion: Suggestion | None = None
        notes: str | None = None

        if ref_type == "none":
            # No ref: GitLab uses project's default branch -> unpinned
            if pin_tags_only:
                if latest_tag_name:
                    suggestion = Suggestion(
                        new_ref=latest_tag_name, reason="no ref (default branch); suggesting latest tag"
                    )
                else:
                    notes = "No tags found to suggest; consider creating and pinning a release tag."
            else:
                # Could choose branch tip; still prefer tags if present
                if latest_tag_name:
                    suggestion = Suggestion(new_ref=latest_tag_name, reason="no ref; suggesting latest tag")
                else:
                    default_branch = gl.get_default_branch(spec.project) or "main"
                    suggestion = Suggestion(
                        new_ref=default_branch,
                        reason="no ref; no tags found; suggest pinning to default branch name (still unpinned)",
                    )

        elif ref_type == "branch":
            # Unpinned; we should suggest a pin
            if pin_tags_only:
                if latest_tag_name:
                    suggestion = Suggestion(
                        new_ref=latest_tag_name, reason=f"unpinned branch '{current_ref}'; suggesting latest tag"
                    )
                else:
                    notes = f"Branch '{current_ref}' is unpinned and project has no tags."
            else:
                # Could pin to branch tip SHA; still prefer tags first
                if latest_tag_name:
                    suggestion = Suggestion(
                        new_ref=latest_tag_name, reason=f"unpinned branch '{current_ref}'; suggesting latest tag"
                    )
                else:
                    # If you truly want to pin to a commit, you could fetch the branch to get its commit SHA.
                    br = gl.get_branch(spec.project, current_ref or (gl.get_default_branch(spec.project) or "main"))
                    if br and "commit" in br and br["commit"].get("id"):
                        suggestion = Suggestion(
                            new_ref=br["commit"]["id"],
                            reason=f"unpinned branch '{current_ref}'; suggesting latest commit SHA",
                        )
                    else:
                        notes = f"Could not resolve branch tip for '{current_ref}'."

        elif ref_type == "tag":
            # Pinned to a tag: see if there's a newer tag
            if latest_tag_name and latest_tag_name != current_ref:
                is_newer = False
                try:
                    newest = (
                        Version(latest_tag_name[1:]) if latest_tag_name.startswith("v") else Version(latest_tag_name)
                    )
                    current = (
                        Version(current_ref[1:])
                        if current_ref and current_ref.startswith("v")
                        else Version(current_ref or "")
                    )
                    is_newer = newest > current
                except InvalidVersion:
                    # fall back to position in sorted list (newest first)
                    all_names = [t["name"] for t in _sort_tags_semver_first(tags)]
                    if current_ref in all_names and all_names.index(latest_tag_name) < all_names.index(current_ref):
                        is_newer = True
                if is_newer:
                    suggestion = Suggestion(new_ref=latest_tag_name, reason="newer tag available")

        elif ref_type == "commit":
            # Pinned to a SHA. If tags-only, suggest the latest tag (or a tag that contains the commit if you want that policy).
            if pin_tags_only:
                if latest_tag_name:
                    suggestion = Suggestion(
                        new_ref=latest_tag_name, reason="currently pinned to SHA; suggesting latest tag"
                    )
                else:
                    notes = "Pinned to SHA, but no tags exist to suggest."
            else:
                # Could stay on SHA or suggest a newer tag if available
                if latest_tag_name:
                    suggestion = Suggestion(new_ref=latest_tag_name, reason="pinned to SHA; newer tag exists")

        else:
            notes = f"Ref '{current_ref}' is unknown or not found."

        analyses.append(
            IncludeAnalysis(
                include=spec,
                ref_type=ref_type,
                pinned=pinned,
                current_ref=current_ref,
                suggestion=suggestion,
                notes=notes,
            )
        )

    return analyses


# -------------------------------
# Pretty-print / JSON helpers (optional)
# -------------------------------


def analyses_to_table(analyses: list[IncludeAnalysis]) -> str:
    """
    Render a compact table for CLI output.
    """
    lines = []
    header = f"{'KIND':8} {'PROJECT':35} {'REF':22} {'TYPE':8} {'PINNED':7} {'SUGGESTION':22} {'REASON/NOTES'}"
    lines.append(header)
    lines.append("-" * len(header))
    for a in analyses:
        sug = a.suggestion.new_ref if a.suggestion else "-"
        reason = a.suggestion.reason if a.suggestion else (a.notes or "")
        proj = a.include.project or "-"
        ref = a.current_ref or "-"
        lines.append(
            f"{a.include.kind:8} {proj:35.35} {ref:22.22} {a.ref_type:8} {str(a.pinned):7} {sug:22.22} {reason}"
        )
    return "\n".join(lines)


def analyses_to_json(analyses: list[IncludeAnalysis]) -> str:
    def encode(o: Any) -> Any:
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)  # type: ignore[arg-type]
        if isinstance(o, set):
            return list(o)
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    # Use orjson for performance, returns bytes so we decode to string.
    return orjson.dumps(analyses, default=encode, option=orjson.OPT_INDENT_2).decode("utf-8")
