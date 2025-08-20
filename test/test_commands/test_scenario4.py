from __future__ import annotations

import shutil
from pathlib import Path
from test.temp_change_dir import chdir_to_file_dir

from bash2gitlab.commands.compile_all import run_compile_all


def test_yaml_it_src_to_out_4():
    with chdir_to_file_dir(__file__):
        uncompiled = Path("scenario4/uncompiled")
        output_root = Path("scenario4/.out")
        shutil.rmtree(str(Path(__file__).parent / "scenario4/.out"), ignore_errors=True)
        shutil.rmtree(str(Path(__file__).parent / "scenario4/uncompiled/.bash2gitlab"), ignore_errors=True)

        run_compile_all(uncompiled, output_root)

        for file in output_root.rglob("*.yml"):
            output = file.read_text(encoding="utf-8")
            for line in output.split("\n"):
                if ">>>" not in line and "<<<" not in line:
                    assert ".sh" not in line or ". before_script.sh" in line

        for file in output_root.rglob("*.yaml"):
            output = file.read_text(encoding="utf-8")
            for line in output.split("\n"):
                if ">>>" not in line and "<<<" not in line:
                    assert ".sh" not in line or ". before_script.sh" in line
