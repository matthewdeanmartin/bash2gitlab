from __future__ import annotations

import argparse
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

logger = logging.getLogger(__name__)

# Known non-job top-level keys in GitLab CI
NON_JOB_TOPLEVEL = {
    "stages",
    "default",
    "workflow",
    "include",
    "variables",
    "cache",
    "image",
    "services",
    "before_script",
    "after_script",
}

yaml_loader = YAML(typ="rt")  # round-trip to keep comments


@dataclass
class RuleSummary:
    """Summarizes rule conditions from a GitLab CI job."""

    when: str | None = None
    if_count: int = 0
    exists_count: int = 0
    changes_count: int = 0

    @staticmethod
    def from_rules(rules: Any) -> RuleSummary:
        """Parse rules list and count condition types."""
        rs = RuleSummary()
        if not isinstance(rules, (list, CommentedSeq)):
            return rs
        for r in rules:
            if not isinstance(r, (dict, CommentedMap)):
                continue
            when = r.get("when")
            if when:
                rs.when = when  # last wins (just a hint)
            if "if" in r:
                rs.if_count += 1
            if "exists" in r:
                rs.exists_count += 1
            if "changes" in r:
                rs.changes_count += 1
        return rs


@dataclass
class ComponentInput:
    """Represents a GitLab CI component input parameter."""

    name: str
    description: str | None = None
    type: str | None = None
    default: str | None = None
    required: bool | None = None


@dataclass
class VariableInfo:
    """Represents a GitLab CI variable with optional description."""

    name: str
    value: str
    description: str | None = None


@dataclass
class JobDoc:
    """Documentation metadata extracted from a GitLab CI job definition."""

    name: str
    stage: str | None = None
    extends: list[str] = field(default_factory=list)
    image: str | None = None
    tags: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    needs: list[str] = field(default_factory=list)
    artifacts_paths: list[str] = field(default_factory=list)
    variables: list[VariableInfo] = field(default_factory=list)  # Changed to support descriptions
    script_len: int = 0
    has_before_script: bool = False
    has_after_script: bool = False
    rules: RuleSummary | None = None
    description: str | None = None  # For @Description decorator
    comment: str | None = None  # leading YAML comment for the job


@dataclass
class FileDoc:
    """Documentation metadata extracted from a GitLab CI YAML file."""

    path: Path
    jobs: list[JobDoc] = field(default_factory=list)
    component_inputs: list[ComponentInput] = field(default_factory=list)
    file_comment: str | None = None
    global_variables: list[VariableInfo] = field(default_factory=list)


def load_yaml(path: Path) -> CommentedMap | None:  # type: ignore[return-value]
    """Load YAML file preserving comments, returns None on error."""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml_loader.load(f)
        if not isinstance(data, (dict, CommentedMap)):
            return None
        return data  # type: ignore[return-value]
    except Exception as e:
        logger.warning("Failed to parse %s: %s", path, e)
        return None


def extract_comment_text(comment_tokens: list[Any]) -> str:
    """
    Extract text from comment tokens, handling the nested structure.
    """
    lines = []
    for token in comment_tokens:
        if hasattr(token, "value"):
            value = token.value
            # Handle case where value is a list [None, list_of_comment_tokens]
            if isinstance(value, list) and len(value) >= 2:
                nested_tokens = value[1] if value[1] is not None else []
                if isinstance(nested_tokens, list):
                    for nested_token in nested_tokens:
                        if hasattr(nested_token, "value") and isinstance(nested_token.value, str):
                            lines.append(nested_token.value)
            elif isinstance(value, str):
                lines.append(value)

    # Clean up comment markers and whitespace
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if line.startswith("#"):
            line = line[1:].strip()
        if line:  # Only add non-empty lines
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines) if cleaned_lines else ""


def get_leading_comment_for_key(cm: CommentedMap, key: str) -> str | None:
    """
    Extract the leading comment (above the key) if present.
    """
    if getattr(cm, "ca", None) and cm.ca.items and key in cm.ca.items:
        entry = cm.ca.items[key]
        # entry is a 4-tuple (pre, post, inline, ...)
        pre = entry[0]
        if pre and isinstance(pre, list):
            text = extract_comment_text(pre)
            return text if text else None
    return None


def get_file_leading_comment(doc: CommentedMap) -> str | None:
    """
    Extract file-level header comment (comment before the first key).
    """
    if getattr(doc, "ca", None) and hasattr(doc.ca, "comment") and doc.ca.comment:
        text = extract_comment_text(doc.ca.comment)
        return text if text else None
    return None


def as_list(val: Any) -> list[str]:
    """Normalize value to list of strings."""
    if val is None:
        return []
    if isinstance(val, (list, CommentedSeq)):
        return [str(x) for x in val]
    return [str(val)]


def parse_description_from_comment(comment_text: str) -> tuple[str | None, str]:
    """
    Parses a clean comment string to find a @Description decorator.
    The description can be multi-line, continuing until a blank line or another decorator.
    Returns a tuple of (description, remaining_comment).
    """
    lines = comment_text.splitlines()
    description_lines = []
    remaining_lines = []
    in_description = False

    for line in lines:
        stripped_line = line.strip()
        if not in_description and stripped_line.startswith("@Description"):
            in_description = True
            desc_part = stripped_line[len("@Description") :].strip()
            if desc_part:
                description_lines.append(desc_part)
        elif in_description:
            if not stripped_line or stripped_line.startswith("@"):
                in_description = False
                remaining_lines.append(line)
            else:
                description_lines.append(stripped_line)
        else:
            remaining_lines.append(line)

    description = " ".join(description_lines) if description_lines else None
    remaining_comment = "\n".join(remaining_lines).strip()
    return description, remaining_comment if remaining_comment else ""


def parse_variables(vars_node: Any) -> list[VariableInfo]:
    """
    Parse variables supporting both simple and complex syntax:
    - Simple: VAR_NAME: "value"
    - Complex: VAR_NAME: { value: "value", description: "desc" }
    """
    variables: list[VariableInfo] = []

    if not isinstance(vars_node, (dict, CommentedMap)):
        return variables

    for k, v in vars_node.items():
        var_name = str(k)

        if isinstance(v, (dict, CommentedMap)):
            # Complex syntax with value/description
            value = v.get("value", "")
            description = v.get("description")
            variables.append(
                VariableInfo(
                    name=var_name,
                    value=str(value) if value is not None else "",
                    description=str(description) if description is not None else None,
                )
            )
        else:
            # Simple syntax - just a value
            variables.append(VariableInfo(name=var_name, value=str(v) if v is not None else "", description=None))

    return variables


def collect_component_inputs(doc: CommentedMap) -> list[ComponentInput]:
    """
    Component templates can expose `inputs` with descriptions/defaults/types.
    These are part of the component template contract.
    """
    inputs_node = doc.get("spec", {}).get("inputs")  # Also checking inside spec for component structure
    if not inputs_node:
        inputs_node = doc.get("inputs")

    out: list[ComponentInput] = []
    if not isinstance(inputs_node, (dict, CommentedMap)):
        return out
    for name, spec in inputs_node.items():
        if not isinstance(spec, (dict, CommentedMap)):
            continue
        out.append(
            ComponentInput(
                name=str(name),
                description=spec.get("description"),
                type=spec.get("type"),
                default=spec.get("default"),
                required=spec.get("required"),
            )
        )
    return out


def summarize_job(name: str, body: CommentedMap) -> JobDoc:
    """Extract documentation metadata from a GitLab CI job definition."""
    stage = body.get("stage")
    extends = as_list(body.get("extends"))
    image_val = body.get("image")
    image = None
    if isinstance(image_val, (dict, CommentedMap)):
        image = image_val.get("name")
    elif isinstance(image_val, str):
        image = image_val

    tags = as_list(body.get("tags"))
    services = []
    raw_services = body.get("services")
    if isinstance(raw_services, (list, CommentedSeq)):
        for s in raw_services:
            if isinstance(s, (dict, CommentedMap)):
                services.append(str(s.get("name") or s.get("alias") or "service"))
            else:
                services.append(str(s))
    needs = []
    raw_needs = body.get("needs")
    if isinstance(raw_needs, (list, CommentedSeq)):
        for n in raw_needs:
            if isinstance(n, (dict, CommentedMap)):
                needs.append(str(n.get("job") or n.get("project") or "need"))
            else:
                needs.append(str(n))
    artifacts_paths: list[str] = []
    artifacts = body.get("artifacts")
    if isinstance(artifacts, (dict, CommentedMap)):
        paths = artifacts.get("paths")
        if isinstance(paths, (list, CommentedSeq)):
            artifacts_paths = [str(p) for p in paths]

    # Parse variables with new function
    variables = parse_variables(body.get("variables"))

    def script_len_of(key: str) -> int:
        s = body.get(key)
        if isinstance(s, (list, CommentedSeq)):
            return len(s)
        if isinstance(s, str):
            return 1
        return 0

    script_len = script_len_of("script")
    has_before = bool(script_len_of("before_script"))
    has_after = bool(script_len_of("after_script"))

    rules_summary = None
    if "rules" in body:
        rules_summary = RuleSummary.from_rules(body.get("rules"))

    jd = JobDoc(
        name=name,
        stage=str(stage) if stage is not None else None,
        extends=extends,
        image=str(image) if image else None,
        tags=tags,
        services=services,
        needs=needs,
        artifacts_paths=artifacts_paths,
        variables=variables,
        script_len=script_len,
        has_before_script=has_before,
        has_after_script=has_after,
        rules=rules_summary,
        description=None,  # filled by caller
        comment=None,  # filled by caller using container map
    )
    return jd


def is_likely_job_key(key: str, value: Any) -> bool:
    if key in NON_JOB_TOPLEVEL:
        return False
    if key.startswith("."):  # Hidden jobs are templates, not executable jobs
        return False
    # A job is generally a mapping with job keywords like 'script', 'stage', etc.
    if not isinstance(value, (dict, CommentedMap)):
        return False
    # GitLab CI components use 'spec', so we shouldn't treat them as jobs
    if "spec" in value:
        return False
    return "script" in value or "stage" in value or "extends" in value or "rules" in value


def parse_file(path: Path) -> FileDoc | None:
    root = load_yaml(path)
    if root is None:
        return None

    file_doc = FileDoc(path=path)
    file_doc.file_comment = get_file_leading_comment(root)

    # Collect component inputs if present
    file_doc.component_inputs = collect_component_inputs(root)

    if "variables" in root:
        file_doc.global_variables = parse_variables(root.get("variables"))

    for key, val in root.items():
        if not is_likely_job_key(str(key), val):
            continue
        job = summarize_job(str(key), val)

        raw_comment = get_leading_comment_for_key(root, str(key))
        if raw_comment:
            description, remaining_comment = parse_description_from_comment(raw_comment)
            job.description = description
            job.comment = remaining_comment if remaining_comment else None

        file_doc.jobs.append(job)

    return file_doc


def iter_yaml_files(base: Path) -> Iterable[Path]:
    for p in base.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".yml", ".yaml"}:
            yield p


def render_markdown(files: list[FileDoc]) -> str:
    lines: list[str] = []
    lines.append("# GitLab CI Job Catalog\n")

    for f in sorted(files, key=lambda x: str(x.path)):
        rel = f.path.as_posix()
        lines.append(f"## `{rel}`\n")

        if f.file_comment:
            lines.append("> " + "\n> ".join(f.file_comment.splitlines()) + "\n")

        if f.component_inputs:
            lines.append("### Component Inputs\n")
            lines.append("| Name | Description | Type | Default | Required |")
            lines.append("|---|---|---|---|:---:|")
            for inp in sorted(f.component_inputs, key=lambda x: x.name):
                desc = inp.description or ""
                typ = f"`{inp.type}`" if inp.type else ""
                dfl = f"`{str(inp.default)}`" if inp.default is not None else ""
                req = "✔️" if inp.required else ""
                lines.append(f"| `{inp.name}` | {desc} | {typ} | {dfl} | {req} |")
            lines.append("")

        if f.global_variables:
            lines.append("### Global Variables\n")
            if any(var.description for var in f.global_variables):
                # Use 3-column table if any variables have descriptions
                lines.append("| Name | Default Value | Description |")
                lines.append("|---|---|---|")
                for var in sorted(f.global_variables, key=lambda x: x.name):
                    desc = var.description or ""
                    lines.append(f"| `{var.name}` | `{var.value}` | {desc} |")
            else:
                # Use simple 2-column table if no descriptions
                lines.append("| Name | Default Value |")
                lines.append("|---|---|")
                for var in sorted(f.global_variables, key=lambda x: x.name):
                    lines.append(f"| `{var.name}` | `{var.value}` |")
            lines.append("")

        if not f.jobs and not f.component_inputs and not f.global_variables:
            lines.append("_No jobs, inputs, or global variables detected in this file._\n")
        elif not f.jobs:
            lines.append("_No runnable jobs detected in this file._\n")

        if f.jobs:
            lines.append("### Jobs\n")
            for j in sorted(f.jobs, key=lambda x: x.name):
                lines.append(f"#### `{j.name}`\n")
                if j.description:
                    lines.append(j.description + "\n")
                if j.comment:
                    lines.append("> " + "\n> ".join(j.comment.splitlines()) + "\n")

                meta_rows: list[tuple[str, str]] = []
                if j.stage:
                    meta_rows.append(("Stage", f"`{j.stage}`"))
                if j.extends:
                    meta_rows.append(("Extends", ", ".join(f"`{e}`" for e in j.extends)))
                if j.image:
                    meta_rows.append(("Image", f"`{j.image}`"))
                if j.tags:
                    meta_rows.append(("Tags", ", ".join(f"`{t}`" for t in j.tags)))
                if j.services:
                    meta_rows.append(("Services", ", ".join(f"`{s}`" for s in j.services)))
                if j.needs:
                    meta_rows.append(("Needs", ", ".join(f"`{n}`" for n in j.needs)))
                if j.artifacts_paths:
                    meta_rows.append(("Artifacts", ", ".join(f"`{p}`" for p in j.artifacts_paths)))
                if j.script_len:
                    meta_rows.append(("Script lines", str(j.script_len)))
                if j.has_before_script or j.has_after_script:
                    hooks = []
                    if j.has_before_script:
                        hooks.append("`before_script`")
                    if j.has_after_script:
                        hooks.append("`after_script`")
                    meta_rows.append(("Hooks", " ".join(hooks)))
                if j.rules:
                    rs = j.rules
                    rule_bits = []
                    if rs.when:
                        rule_bits.append(f"when=`{rs.when}`")
                    if rs.if_count:
                        rule_bits.append(f"{rs.if_count} `if`")
                    if rs.exists_count:
                        rule_bits.append(f"{rs.exists_count} `exists`")
                    if rs.changes_count:
                        rule_bits.append(f"{rs.changes_count} `changes`")
                    if rule_bits:
                        meta_rows.append(("Rules", ", ".join(rule_bits)))

                if meta_rows:
                    lines.append("| Key | Value |")
                    lines.append("|---|---|")
                    for k, v in meta_rows:
                        lines.append(f"| {k} | {v} |")
                    lines.append("")

                if j.variables:
                    lines.append("**Job-Specific Variables**")
                    lines.append("")
                    if any(var.description for var in j.variables):
                        # Use 3-column table if any variables have descriptions
                        lines.append("| Name | Default Value | Description |")
                        lines.append("|---|---|---|")
                        for var in sorted(j.variables, key=lambda x: x.name):
                            desc = var.description or ""
                            lines.append(f"| `{var.name}` | `{var.value}` | {desc} |")
                    else:
                        # Use simple 2-column table if no descriptions
                        lines.append("| Name | Default Value |")
                        lines.append("|---|---|")
                        for var in sorted(j.variables, key=lambda x: x.name):
                            lines.append(f"| `{var.name}` | `{var.value}` |")
                    lines.append("")

        lines.append("---\n")

    return "\n".join(lines).rstrip() + "\n"


def build_catalog(root_dir: Path) -> str:
    files: list[FileDoc] = []
    for p in iter_yaml_files(root_dir):
        fd = parse_file(p)
        if fd:
            files.append(fd)
    return render_markdown(files)


def main():
    """
    Entrypoint for command-line execution.
    """
    parser = argparse.ArgumentParser(description="Generate Markdown documentation from GitLab CI YAML files.")
    parser.add_argument(
        "root_dir",
        type=Path,
        help="The root directory to scan for .yml/.yaml files.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("gitlab-ci-docs.md"),
        help="The output Markdown file path (default: gitlab-ci-docs.md).",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging.")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)

    if not args.root_dir.is_dir():
        print(f"Error: Provided root directory '{args.root_dir}' does not exist or is not a directory.")
        return

    print(f"Scanning for YAML files in '{args.root_dir}'...")
    markdown_content = build_catalog(args.root_dir)

    try:
        with args.output.open("w", encoding="utf-8") as f:
            f.write(markdown_content)
        print(f"Successfully generated documentation at '{args.output}'.")
    except OSError as e:
        print(f"Error writing to output file '{args.output}': {e}")


# if __name__ == "__main__":
#     main()
#


if __name__ == "__main__":
    # main()
    md = build_catalog(Path("../../.decompile_in/"))
    output = Path("../../.decompile_in/docs.md")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(md, encoding="utf-8")
