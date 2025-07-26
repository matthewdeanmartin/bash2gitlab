import io
import logging
from pathlib import Path
from typing import Dict
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def read_bash_script(path: Path, script_sources: Dict[str, str]) -> str:
    if str(path) not in script_sources:
        raise FileNotFoundError(f"Script not found in source map: {path}")
    logger.debug(f"Reading script from source map: {path}")
    content = script_sources[str(path)].strip()
    if not content:
        raise ValueError(f"Script is empty: {path}")
    return content

def process_job(job_data, scripts_root: Path, script_sources: Dict[str, str]):
    if not isinstance(job_data, dict):
        raise TypeError("Job data must be a dictionary")
    if "script" not in job_data:
        raise KeyError("Missing 'script' in job definition")

    original_script = job_data["script"]
    if not isinstance(original_script, list):
        raise TypeError("'script' field must be a list")

    inlined_lines: list[str] = []
    found_script = False

    for line in original_script:
        if (
            isinstance(line, str)
            and line.strip().endswith(".sh")
            and line.strip().startswith("./")
        ):
            rel_path = line.strip().lstrip("./")
            script_path = scripts_root / rel_path
            bash_code = read_bash_script(script_path, script_sources)
            bash_lines = bash_code.splitlines()
            found_script = True
            if len(bash_lines) <= 3:
                inlined_lines.extend(bash_lines)
            else:
                job_data["script"] = LiteralScalarString(bash_code)
                return
        else:
            inlined_lines.append(line)

    if not found_script:
        raise ValueError("No bash script references found in job.")

    job_data["script"] = inlined_lines

def inline_gitlab_scripts(
    gitlab_ci_yaml: str,
    scripts_root: Path,
    script_sources: Dict[str, str],
) -> str:
    yaml = YAML()
    yaml.preserve_quotes = True
    data = yaml.load(io.StringIO(gitlab_ci_yaml))

    for job_name, job_data in data.items():
        if job_name not in "stages":
            process_job(job_data, scripts_root, script_sources)

    out_stream = io.StringIO()
    yaml.dump(data, out_stream)
    return out_stream.getvalue()

def collect_script_sources(uncompiled_path: Path) -> Dict[str, str]:
    scripts_dir = uncompiled_path / "scripts"
    if not scripts_dir.exists():
        raise FileNotFoundError("Scripts directory not found.")

    script_sources = {}
    for script_file in scripts_dir.glob("**/*.sh"):
        content = script_file.read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError(f"Script is empty: {script_file}")
        script_sources[str(script_file)] = content

    if not script_sources:
        raise RuntimeError("No scripts found in 'scripts' directory.")

    return script_sources

def process_uncompiled_directory(
    uncompiled_path: Path,
    output_path: Path
):
    yaml = YAML()
    yaml.preserve_quotes = True

    scripts_root = uncompiled_path # / "scripts"
    templates_dir = uncompiled_path / "templates"
    output_templates_dir = output_path / "templates"
    output_templates_dir.mkdir(parents=True, exist_ok=True)

    script_sources = collect_script_sources(uncompiled_path)
    written_files = 0

    # Process root .gitlab-ci.yml
    root_yaml = uncompiled_path / ".gitlab-ci.yml"
    if root_yaml.exists():
        compiled = inline_gitlab_scripts(root_yaml.read_text(encoding="utf-8"), scripts_root, script_sources)
        (output_path / ".gitlab-ci.yml").write_text(compiled, encoding="utf-8")
        written_files += 1

    # Process templates/*.yml and *.yaml
    template_files = list(templates_dir.glob("*.yml")) + list(templates_dir.glob("*.yaml"))
    if not template_files:
        raise RuntimeError("No template YAML files found.")

    for template_path in template_files:
        compiled = inline_gitlab_scripts(template_path.read_text(encoding="utf-8"), scripts_root, script_sources)
        (output_templates_dir / template_path.name).write_text(compiled, encoding="utf-8")
        written_files += 1

    if written_files == 0:
        raise RuntimeError("No output files written. Nothing was processed.")

if __name__ == "__main__":
    uncompiled = Path("uncompiled")
    output_root = Path(".")
    process_uncompiled_directory(uncompiled, output_root)
