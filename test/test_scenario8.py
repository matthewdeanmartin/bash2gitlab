from __future__ import annotations

from pathlib import Path
from test.temp_change_dir import chdir_to_file_dir

from bash2gitlab.compile_all import process_uncompiled_directory


def test_yaml_it_src_to_out_hidden_jobs_8():
    with chdir_to_file_dir(__file__):
        uncompiled = Path("scenario8/in")
        output_root = Path("scenario8/out")
        templates_dir = Path("scenario8/in")
        output_templates_dir = output_root
        scripts_dir = uncompiled

        process_uncompiled_directory(uncompiled, output_root, scripts_dir, templates_dir, output_templates_dir, 0)

        found = 0
        for file in output_root.rglob("*.yml"):
            output = file.read_text(encoding="utf-8")
            for line in output.split("\n"):
                if ">>>" not in line and "<<<" not in line:
                    assert ".sh" not in line or ". before_script.sh" in line
            found += 1
        assert found

        found = 0
        for file in output_root.glob("templates/*.yml"):
            output = file.read_text(encoding="utf-8")
            for line in output.split("\n"):
                if ">>>" not in line and "<<<" not in line:
                    assert ".sh" not in line or ". before_script.sh" in line
            found += 1
        assert found

        found = 0
        for file in output_root.glob("templates/sub_template/*.yml"):
            output = file.read_text(encoding="utf-8")
            for line in output.split("\n"):
                if ">>>" not in line and "<<<" not in line:
                    assert ".sh" not in line or ". before_script.sh" in line
            found += 1
        assert found
