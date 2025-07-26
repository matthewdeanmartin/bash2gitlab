from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString
from pathlib import Path
from typing import Optional, Dict, Union
import io


def read_bash_script(path: str, script_sources: Optional[Dict[str, str]]) -> str:
    """Reads bash script from memory or filesystem."""
    if script_sources and path in script_sources:
        return script_sources[path].strip()
    else:
        return Path(path).read_text(encoding="utf-8").strip()


def inline_gitlab_scripts(
    gitlab_ci_yaml: str,
    script_sources: Optional[Dict[str, str]] = None,
) -> str:
    """
    Inline .sh script references in GitLab CI YAML into the `script` field.

    Args:
        gitlab_ci_yaml (str): The original .gitlab-ci.yml contents.
        script_sources (dict): Optional dict for testing: {path: contents}

    Returns:
        str: Transformed YAML with inlined scripts.
    """
    yaml = YAML()
    yaml.preserve_quotes = True
    data = yaml.load(io.StringIO(gitlab_ci_yaml))

    for job_name, job_data in data.items():
        if not isinstance(job_data, dict) or "script" not in job_data:
            continue

        original_script = job_data["script"]

        if not isinstance(original_script, list):
            continue  # Skip if script isn't a list

        new_script: Union[list, LiteralScalarString]
        inlined_lines = []

        for line in original_script:
            if isinstance(line, str) and line.strip().endswith(".sh") and line.strip().startswith("./"):
                script_path = line.strip()
                bash_code = read_bash_script(script_path, script_sources)
                bash_lines = bash_code.strip().splitlines()

                if len(bash_lines) <= 3:
                    inlined_lines.extend(bash_lines)
                else:
                    # Use literal block style if script is long
                    job_data["script"] = LiteralScalarString(bash_code)
                    break
            else:
                inlined_lines.append(line)

        if isinstance(job_data["script"], list) or isinstance(job_data["script"], str):
            job_data["script"] = inlined_lines

    stream = io.StringIO()
    yaml.dump(data, stream)
    return stream.getvalue()
