from __future__ import annotations

from pathlib import Path
from test.temp_change_dir import chdir_to_file_dir

from bash2gitlab.compile_all import process_uncompiled_directory


def test_yaml_it_src_to_out():
    with chdir_to_file_dir(__file__):
        uncompiled = Path("scenario4/uncompiled")
        output_root = Path("scenario4/.out")
        templates_dir = Path("scenario4/uncompiled/templates/")
        output_templates_dir = output_root
        scripts_dir = uncompiled / "scripts"

        process_uncompiled_directory(uncompiled, output_root, scripts_dir, templates_dir, output_templates_dir)

        for file in output_root.rglob("*.yml"):
            output = file.read_text(encoding="utf-8")
            assert ".sh" not in output or ". before_script.sh" in output

        for file in output_root.rglob("*.yaml"):
            output = file.read_text(encoding="utf-8")
            assert ".sh" not in output or ". before_script.sh" in output
