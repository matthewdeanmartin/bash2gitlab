from __future__ import annotations

from pathlib import Path
from test.temp_change_dir import chdir_to_file_dir

from bash2gitlab.commands.compile_all import run_compile_all


def test_yaml_it():
    with chdir_to_file_dir(__file__):
        uncompiled = Path("scenario1/uncompiled")
        output_root = Path("scenario1/.out")

        run_compile_all(uncompiled, output_root)

        for file in output_root.rglob("*.yml"):
            output = file.read_text(encoding="utf-8")
            for line in output.split("\n"):
                if ">>>" not in line and "<<<" not in line:
                    assert ".sh" not in line or ". before_script.sh" in line
