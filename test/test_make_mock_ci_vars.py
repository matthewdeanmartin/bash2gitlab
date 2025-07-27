from bash2gitlab.mock_ci_vars import generate_mock_ci_variables_script


def test_generate_mock_ci_variables_script(tmp_path):
    generate_mock_ci_variables_script(str(tmp_path / "file.sh"))
    assert "CI" in (tmp_path / "file.sh").read_text(encoding="utf-8")
