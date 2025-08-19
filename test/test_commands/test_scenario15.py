from __future__ import annotations

import shutil
from pathlib import Path
from test.temp_change_dir import chdir_to_file_dir

from bash2gitlab.commands.compile_all import run_compile_all


def test_yaml_it_src_to_out_15_python():
    with chdir_to_file_dir(__file__):
        uncompiled = Path("scenario15/src")
        output_root = Path("scenario15/out")
        shutil.rmtree(str(Path(__file__).parent / "scenario15/out"))

        run_compile_all(uncompiled, output_root)

        for file in output_root.rglob("*.yml"):
            output = file.read_text(encoding="utf-8")
            assert 'print("hello")' in output or 'print(\\"hello\\")' in output

        for file in output_root.rglob("*.yaml"):
            output = file.read_text(encoding="utf-8")
            assert 'print("hello")' in output
