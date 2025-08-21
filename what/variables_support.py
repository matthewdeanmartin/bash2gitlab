"""
Implementation draft: variables handling & local-bash helpers for bash2gitlab

This module adds:

1) File-scoped variables discovery next to the uncompiled YAML file:
   - <stem>.variables.env (KEY=VALUE lines)
   - <stem>.variables.sh  (sourced; exported vars captured via subshell)

2) Job-scoped variables discovery:
   - vars/<normalized-job-name>.variables.env
   - vars/<normalized-job-name>.variables.sh
   - <normalized-job-name>.variables.env
   - <normalized-job-name>.variables.sh

   Where "normalized" means job name with non [A-Za-z0-9_] replaced by '_'.

3) Merge policy (deterministic): YAML wins on conflicts.

4) Inheritance hints (optional):
   - If a job has a comment "# b2gl:inherit:variables=false" we emit `inherit:variables:false`.
   - If it has "# b2gl:inherit:variables=FOO,BAR" we emit whitelist form.

5) CLI helpers (to wire into your __main__.py):
   - `env <yaml> <job>` -> prints KEY=VALUE lines (dotenv style) for local testing
   - `export <yaml> <job>` -> prints `export KEY=VALUE` lines
   - `print-yaml-vars <yaml> <job>` -> prints JSON map of what will be injected into YAML

Integrations:
- Call `load_file_and_job_variables(uncompiled_yaml_path, job_name)` to fetch two dicts.
- Use `merge_into_yaml(data, file_vars, job_vars_map)` BEFORE dumping with ruamel.
- Wire CLI subcommands via `add_cli_subcommands(subparsers)`.

Notes:
- For `.sh` vars files we launch a bash subshell with a controlled, empty env, source the file with `set -a`, and then capture the diff of `env -0`.
- We never attempt to materialize UI/group/project protected/masked variables.
- We never evaluate arbitrary code at compile-time except in the explicit `.variables.sh` files the user created for this purpose.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import dict

from ruamel.yaml import CommentedMap
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

from bash2gitlab.utils.dotenv import parse_env_file  # type: ignore

SAFE_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _normalize_job_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def _collect_exported_env_from_sh(path: Path) -> dict[str, str]:
    """Source a .sh in a clean bash subshell and capture exported env as a dict.

    We deliberately use an *empty* environment so the file must set each var it wants
    exported. Functions/aliases are ignored because we only read `env`.
    """
    if not path.exists():
        return {}

    # Use `set -a` so simple assignments export automatically
    script = f"set -a\n. {shlex.quote(str(path))}\nset +a\nenv -0"

    # Empty base env; ensure predictable locale
    proc = subprocess.run(  # noqa
        ["bash", "-c", script],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={},
        text=False,
    )
    raw = proc.stdout.split(b"\x00")
    out: dict[str, str] = {}
    for chunk in raw:
        if not chunk:
            continue
        try:
            s = chunk.decode("utf-8", "replace")
        except Exception:
            continue
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        if SAFE_KEY_RE.match(k):
            out[k] = v
    return out


def _load_vars_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    if path.suffix == ".env":
        return parse_env_file(path.read_text(encoding="utf-8"))
    if path.suffix == ".sh":
        return _collect_exported_env_from_sh(path)
    return {}


@dataclass
class VariablesBundle:
    file_level: dict[str, str]
    job_level: dict[str, dict[str, str]]  # job_name -> vars


def discover_variables_files(uncompiled_yaml: Path, job_names: Iterable[str]) -> VariablesBundle:
    stem = uncompiled_yaml.with_suffix("")
    base_dir = uncompiled_yaml.parent

    file_level: dict[str, str] = {}
    # File-level candidates (ordered)
    for suffix in (".variables.env", ".variables.sh"):
        file_level |= _load_vars_file(Path(str(stem) + suffix))

    job_level: dict[str, dict[str, str]] = {}
    vars_dir = base_dir / "vars"

    for job in job_names:
        jnorm = _normalize_job_name(job)
        merged: dict[str, str] = {}
        # Look in vars/ then next to YAML
        for root in (vars_dir, base_dir):
            for suffix in (".variables.env", ".variables.sh"):
                merged |= _load_vars_file(root / f"{jnorm}{suffix}")
        job_level[job] = merged

    # validate keys
    def _validate(d: dict[str, str]) -> dict[str, str]:
        clean: dict[str, str] = {}
        for k, v in d.items():
            if SAFE_KEY_RE.match(k):
                clean[k] = v
        return clean

    file_level = _validate(file_level)
    for j in list(job_level.keys()):
        job_level[j] = _validate(job_level[j])

    return VariablesBundle(file_level=file_level, job_level=job_level)


def _yaml_map_from(d: dict[str, str]) -> CommentedMap:
    # Quote to avoid YAML edge cases (e.g., leading zeros, true/false, colon)
    m = CommentedMap()
    for k, v in d.items():
        m[k] = DoubleQuotedScalarString(str(v))
    return m


def merge_into_yaml(data, file_vars: dict[str, str], job_vars: dict[str, dict[str, str]]) -> None:
    """Merge discovered variables into a ruamel data tree.

    - YAML wins on conflicts.
    - File-level goes into top-level `variables:`
    - Job-level goes into each job's `variables:`
    """
    # Top-level
    if file_vars:
        existing = data.get("variables")
        merged: dict[str, str] = dict(file_vars)
        if isinstance(existing, dict):
            # YAML wins
            merged.update({str(k): str(v) for k, v in existing.items()})
        data["variables"] = _yaml_map_from(merged)

    # Jobs
    for key, node in list(data.items()):
        if not isinstance(node, dict):
            continue
        # Heuristic: is a job (has script-ish keys) or an extends/template
        is_job_like = any(k in node for k in ("script", "before_script", "after_script", "pre_get_sources_script"))
        if not is_job_like:
            continue
        jvars = job_vars.get(key) or {}
        if not jvars:
            continue
        existing = node.get("variables")
        merged: dict[str, str] = dict(jvars)
        if isinstance(existing, dict):
            merged.update({str(k): str(v) for k, v in existing.items()})
        node["variables"] = _yaml_map_from(merged)


def extract_job_names_from_yaml(data) -> tuple[str, ...]:
    names: list[str] = []
    for key, node in list(data.items()):
        if isinstance(node, dict) and any(k in node for k in ("script", "before_script", "after_script", "pre_get_sources_script")):
            names.append(key)
    return tuple(names)


# ------------------ CLI helpers ------------------


def _load_yaml(path: Path):
    from bash2gitlab.utils.yaml_factory import get_yaml  # lazy import to use project's config

    yaml = get_yaml()
    return yaml.load(path.read_text(encoding="utf-8"))


def _collect_yaml_inline_vars_for_job(data, job: str) -> dict[str, str]:
    node = data.get(job)
    if not isinstance(node, dict):
        return {}
    vars_node = node.get("variables")
    if not isinstance(vars_node, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in vars_node.items():
        out[str(k)] = str(v)
    return out


def load_file_and_job_variables(uncompiled_yaml: Path, job: str) -> tuple[dict[str, str], dict[str, str]]:
    data = _load_yaml(uncompiled_yaml)
    jobs = extract_job_names_from_yaml(data)
    bundle = discover_variables_files(uncompiled_yaml, jobs)

    file_vars = dict(bundle.file_level)
    job_vars = dict(bundle.job_level.get(job, {}))

    # YAML wins
    yaml_top = data.get("variables")
    if isinstance(yaml_top, dict):
        file_vars.update({str(k): str(v) for k, v in yaml_top.items()})

    yaml_job = _collect_yaml_inline_vars_for_job(data, job)
    job_vars.update(yaml_job)

    return file_vars, job_vars


def cli_env(uncompiled_yaml: Path, job: str) -> str:
    """Return KEY=VALUE lines for easy `eval`/dotenv usage locally."""
    file_vars, job_vars = load_file_and_job_variables(uncompiled_yaml, job)
    merged = {**file_vars, **job_vars}  # job wins after file-level + YAML merges applied above
    lines = [f"{k}={v}" for k, v in merged.items()]
    return "\n".join(lines) + "\n"


def cli_export(uncompiled_yaml: Path, job: str) -> str:
    """Return `export KEY=VALUE` lines for shells that prefer it."""
    file_vars, job_vars = load_file_and_job_variables(uncompiled_yaml, job)
    merged = {**file_vars, **job_vars}
    lines = [f"export {k}={shlex.quote(str(v))}" for k, v in merged.items()]
    return "\n".join(lines) + "\n"


def cli_print_yaml_vars(uncompiled_yaml: Path, job: str) -> str:
    file_vars, job_vars = load_file_and_job_variables(uncompiled_yaml, job)
    return json.dumps({"file": file_vars, "job": job_vars}, indent=2, sort_keys=True)


def add_cli_subcommands(subparsers) -> None:
    """Wire into your existing argparse setup in __main__.py.

    Example:
        p_env = subparsers.add_parser("env", help="Print merged KEY=VALUE vars for a job")
        p_env.add_argument("yaml", type=Path)
        p_env.add_argument("job", type=str)
        p_env.set_defaults(func=_cmd_env)
    """

    def _cmd_env(args):
        print(cli_env(args.yaml, args.job), end="")

    def _cmd_export(args):
        print(cli_export(args.yaml, args.job), end="")

    def _cmd_print(args):
        print(cli_print_yaml_vars(args.yaml, args.job))

    p_env = subparsers.add_parser("env", help="Print merged KEY=VALUE vars for a job")
    p_env.add_argument("yaml", type=Path)
    p_env.add_argument("job", type=str)
    p_env.set_defaults(func=_cmd_env)

    p_exp = subparsers.add_parser("export", help="Print `export KEY=VALUE` lines for a job")
    p_exp.add_argument("yaml", type=Path)
    p_exp.add_argument("job", type=str)
    p_exp.set_defaults(func=_cmd_export)

    p_print = subparsers.add_parser("print-yaml-vars", help="Debug: show file/job vars JSON")
    p_print.add_argument("yaml", type=Path)
    p_print.add_argument("job", type=str)
    p_print.set_defaults(func=_cmd_print)


# -------------- Optional: inheritance hints --------------
HINT_INHERIT_RE = re.compile(r"b2gl:inherit:variables\s*=\s*([^\s#]+)")


def apply_inheritance_hints(data) -> None:
    """Scan for inline hints and inject `inherit:variables` accordingly.

    Supported:
      # b2gl:inherit:variables=false
      # b2gl:inherit:variables=FOO,BAR
    """
    for _key, node in list(data.items()):
        if not isinstance(node, dict):
            continue
        # ruamel preserves comments in .ca; try both key/head comments
        ca = getattr(node, "ca", None)
        if not ca:
            continue
        comments = []
        for attr in ("comment", "end", "items"):
            val = getattr(ca, attr, None)
            if not val:
                continue
            # val can be complex; collect strings we see
            if isinstance(val, list):
                for t in val:
                    if t and hasattr(t, "value"):
                        comments.append(getattr(t, "value", ""))
            elif hasattr(val, "value"):
                comments.append(getattr(val, "value", ""))
        blob = "\n".join(x or "" for x in comments)
        m = HINT_INHERIT_RE.search(blob)
        if not m:
            continue
        raw = m.group(1).strip()
        if raw.lower() == "false":
            node["inherit"] = CommentedMap({"variables": False})
        else:
            allow = [s.strip() for s in raw.split(",") if s.strip()]
            node["inherit"] = CommentedMap({"variables": allow})


# -------------- Integration shim --------------


def integrate_into_compiler(data, uncompiled_yaml_path: Path) -> None:
    """Call this inside your `inline_gitlab_scripts` after loading YAML and before dump.

    It discovers jobs, loads file/job variables, merges them with YAML (YAML wins),
    and applies optional inheritance hints.
    """
    jobs = extract_job_names_from_yaml(data)
    bundle = discover_variables_files(uncompiled_yaml_path, jobs)
    merge_into_yaml(data, bundle.file_level, bundle.job_level)
    apply_inheritance_hints(data)
