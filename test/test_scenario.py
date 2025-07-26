from pathlib import Path

from bash2gitlab.compile_all import process_uncompiled_directory
from bash2gitlab.inline_bash_to_yaml import inline_gitlab_scripts


def test_yaml_it():
    # Example usage:
    # Assumes this script is run from repo root
    uncompiled = Path("scenario1/uncompiled")
    output_root = Path("scenario1")
    process_uncompiled_directory(uncompiled, output_root)
