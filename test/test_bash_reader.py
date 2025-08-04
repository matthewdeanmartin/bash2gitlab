from pathlib import Path

import pytest

from bash2gitlab.bash_reader import inline_bash_source


def test_inline_bash_source_success_and_circular_dependency(tmp_path: Path):
    """
    Tests successful inlining of nested scripts and graceful handling of
    circular dependencies.
    """
    # --- Setup Test Files using pytest's tmp_path fixture ---
    helpers_dir = tmp_path / "helpers"
    helpers_dir.mkdir()
    nested_dir = tmp_path / "nested"
    nested_dir.mkdir()

    # Script 1: The main entry point
    main_sh = tmp_path / "main.sh"
    main_sh.write_text(
        "#!/bin/bash\n"
        'echo "Start of main script"\n'
        "\n"
        "# Source a helper script\n"
        "source ./helpers/utils.sh\n"
        "\n"
        'echo "End of main script"\n'
    )

    # Script 2: A helper script that sources another script and itself (circular)
    (helpers_dir / "utils.sh").write_text(
        'echo "This is the utils script"\n'
        "# Source a nested script\n"
        ". ../nested/data.sh\n"
        "# This next line demonstrates circular sourcing\n"
        "source ../main.sh\n"
    )

    # Script 3: A nested data script
    (nested_dir / "data.sh").write_text('DATA_VAR="Hello, World!"\n' "echo $DATA_VAR\n")

    # --- Call the function under test ---
    result = inline_bash_source(main_sh)

    # --- Assert the output ---
    # The content of utils.sh and data.sh should be inlined into main.sh.
    # The circular `source ../main.sh` call should result in an empty string.
    expected_output = (
        "#!/bin/bash\n"
        'echo "Start of main script"\n'
        "\n"
        "# Source a helper script\n"
        # Inlined content from utils.sh starts here
        'echo "This is the utils script"\n'
        "# Source a nested script\n"
        # Inlined content from data.sh starts here
        'DATA_VAR="Hello, World!"\n'
        "echo $DATA_VAR\n"
        # Inlined content from data.sh ends here
        "# This next line demonstrates circular sourcing\n"
        # The circular source call to main.sh is replaced with an empty string
        # Inlined content from utils.sh ends here
        "\n"
        'echo "End of main script"\n'
    )

    assert result == expected_output


def test_inline_bash_source_file_not_found(tmp_path: Path):
    """
    Tests that FileNotFoundError is raised when a sourced script does not exist.
    """
    # --- Setup Test File ---
    main_sh = tmp_path / "main.sh"
    main_sh.write_text("source non_existent_file.sh\n")

    # --- Assert that the correct exception is raised ---
    with pytest.raises(FileNotFoundError) as excinfo:
        inline_bash_source(main_sh)

    # Optionally, check the exception message for clarity
    assert "non_existent_file.sh" in str(excinfo.value)
    assert "Script not found" in str(excinfo.value)
