from __future__ import annotations

from pathlib import Path
from test.temp_change_dir import chdir_to_file_dir

from bash2gitlab.compile_all import process_uncompiled_directory


def test_yaml_must_preserve_references_and_multiscripts():
    with chdir_to_file_dir(__file__):
        uncompiled = Path("scenario10/uncompiled")
        output_root = Path("scenario10/out")
        templates_dir = Path("scenario10/uncompiled")
        output_templates_dir = output_root
        scripts_dir = uncompiled

        process_uncompiled_directory(uncompiled, output_root, scripts_dir, templates_dir, output_templates_dir)

        found = 0
        for file in output_root.rglob("*.yml"):
            output = file.read_text(encoding="utf-8")
            assert ".sh" not in output or ". before_script.sh" in output
            assert "echo build" in output
            assert "echo test" in output
            assert "!reference [.echo]" in output
            found += 1
        assert found
