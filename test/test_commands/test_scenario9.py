from __future__ import annotations

import shutil
from pathlib import Path
from test.temp_change_dir import chdir_to_file_dir

from bash2gitlab.commands.compile_all import run_compile_all


def test_yaml_it_src_to_out_hidden_jobs_9():
    with chdir_to_file_dir(__file__):
        uncompiled = Path("scenario9/in")
        output_root = Path("scenario9/out")
        shutil.rmtree(str(Path(__file__).parent / "scenario9/out"), ignore_errors=True)

        run_compile_all(uncompiled, output_root)

        found = 0
        for file in output_root.rglob("*.yml"):
            output = file.read_text(encoding="utf-8")
            for line in output.split("\n"):
                if ">>>" not in line and "<<<" not in line:
                    # inlining "jobs" with custom names is not safe. This could be dereferenced into
                    # something that isn't a script. Maybe need pragma to handle this.
                    assert ".sh" in line or ".some-script:" in line or "# " in line
                    # assert ".sh" not in line or ". before_script.sh" in line
            found += 1
        assert found
