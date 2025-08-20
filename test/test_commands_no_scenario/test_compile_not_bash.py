from pathlib import Path

from bash2gitlab.commands.compile_not_bash import maybe_inline_interpreter_command, shell_single_quote


def write_script(tmp_path: Path, name: str, content: str) -> Path:
    """Helper to create a script file with UTF-8 encoding."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_python_m_module_inlines(tmp_path: Path):
    (tmp_path / "pkg").mkdir(exist_ok=True)
    write_script(tmp_path / "pkg", "tool.py", "print('hi')")
    line = "python -m pkg.tool"
    result, _found_path = maybe_inline_interpreter_command(line, tmp_path)
    assert result is not None
    assert result[0].startswith("# >>> BEGIN inline: python -m pkg.tool")
    assert "python -c" in result[1]
    assert "print" in result[1]


def test_python_script_inlines(tmp_path: Path):
    script = write_script(tmp_path, "hello.py", "print('world')")
    line = f"python {script.name}"
    result, _found_path = maybe_inline_interpreter_command(line, tmp_path)
    assert result is not None
    assert "python -c" in result[1]
    assert "print" in result[1]
    assert "world" in result[1]


def test_node_script_inlines(tmp_path: Path):
    script = write_script(tmp_path, "app.js", "console.log('js');")
    line = f"node {script.name}"
    result, _found_path = maybe_inline_interpreter_command(line, tmp_path)
    assert result is not None
    assert result[0].startswith("# >>> BEGIN inline: node")
    assert "node -e" in result[1]
    assert "console.log" in result[1]


def test_awk_program_inlines(tmp_path: Path):
    script = write_script(tmp_path, "prog.awk", "{ print $1 }")
    line = f"awk {script.name}"
    result, _found_path = maybe_inline_interpreter_command(line, tmp_path)
    assert result is not None
    assert result[0].startswith("# >>> BEGIN inline: awk")
    # awk has no flag, code is first arg
    assert result[1].startswith("awk '")
    assert "{ print $1 }" in result[1]


def test_unmatched_line_returns_none(tmp_path: Path):
    line = "echo hello"
    result, _found_path = maybe_inline_interpreter_command(line, tmp_path)
    assert result is None


def test_missing_file_returns_none(tmp_path: Path):
    line = "python missing.py"
    result, _found_path = maybe_inline_interpreter_command(line, tmp_path)
    assert result is None


def test_unexpected_extension_returns_none(tmp_path: Path):
    script = write_script(tmp_path, "not_a_py.txt", "print('nope')")
    line = f"python {script.name}"
    result, _found_path = maybe_inline_interpreter_command(line, tmp_path)
    assert result is None


def test_large_payload_skips(tmp_path: Path, monkeypatch):
    script = write_script(tmp_path, "big.py", "x" * 20000)
    line = f"python {script.name}"
    monkeypatch.setenv("BASH2GITLAB_MAX_INLINE_LEN", "1000")
    result, _found_path = maybe_inline_interpreter_command(line, tmp_path)
    assert result is None


def test_shebang_and_bom_stripped(tmp_path: Path):
    content = "#!/usr/bin/env python\nprint('shebang removed')"
    script = write_script(tmp_path, "shebang.py", "\ufeff" + content)
    line = f"python {script.name}"
    result, _found_path = maybe_inline_interpreter_command(line, tmp_path)
    assert result is not None
    # The shebang and BOM should be stripped
    assert "#!/usr/bin/env" not in result[1]
    assert "shebang removed" in result[1]


def test_shell_single_quote_handles_apostrophe():
    s = "abc'def"
    quoted = shell_single_quote(s)
    # Ensure it’s wrapped and escaped
    assert quoted.startswith("'") and quoted.endswith("'")
    assert "'\"'\"'" in quoted
