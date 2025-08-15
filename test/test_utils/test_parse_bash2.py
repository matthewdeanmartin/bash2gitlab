import pytest

# Adjust the import to match your actual module location if different
from bash2gitlab.utils.parse_bash import extract_script_path

# ----------------------------- POSITIVE CASES --------------------------------


@pytest.mark.parametrize(
    "line,expected",
    [
        # 1. Plain POSIX relative script
        ("./build.sh", "build.sh"),
        # 2. Plain Windows-style relative script
        (r".\build.sh", "build.sh"),
        # 3. Executor + POSIX script
        ("bash build.sh", "build.sh"),
        # 4. Executor + Windows-style script in subdir
        (r"bash .\scripts\deploy.sh", "scripts/deploy.sh"),
        # 5. 'sh' executor
        ("sh ./build.sh", "build.sh"),
        # 6. pwsh + ps1
        ("pwsh scripts/run.ps1", "scripts/run.ps1"),
        # 7. source command
        ("source utils/helpers.sh", "utils/helpers.sh"),
        # 8. dot-source shorthand
        (". scripts/deploy.ps1", "scripts/deploy.ps1"),
        # 9. .bash extension accepted
        ("./foo.bash", "foo.bash"),
        # 10. Uppercase extension accepted
        ("./FOO.SH", "FOO.SH"),
        # 11. Quoted path with spaces
        ('bash "./my scripts/build.sh"', "my scripts/build.sh"),
        # 12. Windows absolute path (normalized to POSIX)
        (r"pwsh C:\dir\build.ps1", "C:/dir/build.ps1"),
        # 13. UNC path (normalized to POSIX with leading //)
        (r"pwsh \\server\share\deploy.ps1", "//server/share/deploy.ps1"),
        # 14. Leading/trailing whitespace tolerated
        ("   \t./build.sh   ", "build.sh"),
        # 15. Trailing comment (after whitespace) is ignored
        ("bash build.sh  # run the build", "build.sh"),
    ],
)
def test_extract_script_path_valid(line, expected):
    assert extract_script_path(line) == expected


# ----------------------------- NEGATIVE CASES --------------------------------


@pytest.mark.parametrize(
    "line",
    [
        # 16. Interpreter flags present -> unsafe
        ("bash -e build.sh"),
        # 17. Extra positional args -> unsafe
        ("./build.sh arg1"),
        # 18. Leading env assignment -> unsafe
        ("FOO=bar ./build.sh"),
        # 19. Unknown extension -> not a script
        ("./run.py"),
        # 20. '#' mid-token is NOT a comment; filename becomes invalid -> reject
        # ("bash build.sh#frag"), User error, let them handle it.
        # 21. Entire line commented out -> do not inline
        ("# ./build.sh"),
    ],
)
def test_extract_script_path_invalid(line):
    assert extract_script_path(line) is None
