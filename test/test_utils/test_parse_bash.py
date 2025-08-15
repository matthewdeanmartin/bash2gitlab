from bash2gitlab.utils.parse_bash import extract_script_path


def test_extract_script():
    assert extract_script_path("bash -e ./build.sh --flag") is None
    assert extract_script_path("FOO=1 bash -xe scripts/deploy.sh arg1") is None
    assert extract_script_path("pwsh -NoProfile ./do.ps1") is None
    assert extract_script_path("source utils/helpers.sh") == "utils/helpers.sh"
    assert extract_script_path("./plain.sh a b c") is None
    assert extract_script_path("echo not-a-script") is None
