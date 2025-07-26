"""
Convert a bash script to pipeline using comments in bash to structure the yaml.
"""

from pathlib import Path
import re
import ruamel.yaml as ry

def to_job(script_path: Path) -> dict:
    meta = {}
    body = []
    for line in script_path.read_text().splitlines():
        if m := re.match(r"#\s*CI_(\w+)=(.*)", line):
            meta[m[1].lower()] = m[2].strip()
        else:
            body.append(line)

    job = {
        "stage":  meta.get("stage", "build"),
        "image":  meta.get("image", "bash:latest"),
        "script": [f"bash {script_path.name}"]
    }
    if meta.get("tags"):
        job["tags"] = meta["tags"].split(",")
    if meta.get("artifacts"):
        job["artifacts"] = {"paths": meta["artifacts"].split(",")}

    return {script_path.stem: job}

def generate_yaml(input_dir: Path, output_file: Path):
    yml = ry.YAML()
    jobs = {}
    for sh in input_dir.glob("*.sh"):
        jobs.update(to_job(sh))
    with output_file.open("w") as fp:
        yml.dump(jobs, fp)

