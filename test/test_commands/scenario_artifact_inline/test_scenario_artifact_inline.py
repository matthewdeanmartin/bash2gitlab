"""Integration test for artifact inlining."""

from __future__ import annotations

import shutil
from pathlib import Path
from test.temp_change_dir import chdir_to_file_dir

from bash2gitlab.commands.compile_all import run_compile_all


def test_artifact_inline_scenario():
    """Test that artifact inlining works in a full compilation scenario."""
    with chdir_to_file_dir(__file__):
        uncompiled = Path("uncompiled")
        output_root = Path(".out")

        # Clean up previous runs
        shutil.rmtree(
            str(Path(__file__).parent / ".out"),
            ignore_errors=True,
        )
        shutil.rmtree(
            str(Path(__file__).parent / "uncompiled/.bash2gitlab"),
            ignore_errors=True,
        )

        # Run compilation
        run_compile_all(uncompiled, output_root)

        # Verify output file was created
        output_file = output_root / ".gitlab-ci.yml"
        assert output_file.exists()

        # Read and verify the compiled output
        output = output_file.read_text(encoding="utf-8")

        # Should contain artifact inline markers
        assert "BEGIN inline-artifact:" in output
        assert "END inline-artifact" in output

        # Should contain base64 artifact data
        assert "__B2G_ARTIFACT=" in output

        # Should contain extraction commands
        assert "base64 -d" in output
        assert "unzip" in output
        assert "./configs" in output

        # Should NOT contain the pragma comment
        assert "Pragma: inline-artifact" not in output

        # Should contain the rest of the job
        assert "Using inlined configs" in output
        assert "ls -la ./configs" in output
