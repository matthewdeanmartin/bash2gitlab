from __future__ import annotations

import shutil
from pathlib import Path
from test.temp_change_dir import chdir_to_file_dir

from bash2gitlab.commands.compile_all import run_compile_all


def test_yaml_must_preserve_references_and_multiscripts():
    with chdir_to_file_dir(__file__):
        uncompiled = Path("scenario11/uncompiled")
        output_root = Path("scenario11/out")
        shutil.rmtree(str(Path(__file__).parent / "scenario11/out"), ignore_errors=True)

        run_compile_all(uncompiled, output_root)

        found = 0
        for file in output_root.rglob("*.yml"):
            output = file.read_text(encoding="utf-8")
            for line in output.split("\n"):
                if ">>>" not in line and "<<<" not in line:
                    assert ".sh" not in line or ". before_script.sh" in line
            assert "echo build1" in output
            assert "echo build2" in output
            assert "echo test1" in output
            assert "echo test2" in output
            assert "!reference" in output
            found += 1
        assert found
