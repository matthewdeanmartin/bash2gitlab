"""Tests for compile_bash_reader: inline_bash_source, read_bash_script, secure_join."""

import pytest

from bash2gitlab.commands.compile_bash_reader import (
    SOURCE_COMMAND_REGEX,
    PragmaError,
    SourceSecurityError,
    read_bash_script,
    secure_join,
)

# ---------------------------------------------------------------------------
# SOURCE_COMMAND_REGEX
# ---------------------------------------------------------------------------


class TestSourceCommandRegex:
    def test_matches_source_command(self):
        m = SOURCE_COMMAND_REGEX.match("source helpers.sh")
        assert m is not None
        assert m.group("path") == "helpers.sh"

    def test_matches_dot_command(self):
        m = SOURCE_COMMAND_REGEX.match(". helpers.sh")
        assert m is not None
        assert m.group("path") == "helpers.sh"

    def test_matches_relative_path(self):
        m = SOURCE_COMMAND_REGEX.match("source ./subdir/helpers.sh")
        assert m is not None
        assert m.group("path") == "./subdir/helpers.sh"

    def test_matches_with_trailing_comment(self):
        m = SOURCE_COMMAND_REGEX.match("source helpers.sh # load helpers")
        assert m is not None

    def test_no_match_with_extra_arg(self):
        # source with extra arguments should not match
        assert SOURCE_COMMAND_REGEX.match("source helpers.sh extra_arg") is None

    def test_no_match_plain_command(self):
        assert SOURCE_COMMAND_REGEX.match("echo hello") is None

    def test_matches_with_leading_whitespace(self):
        m = SOURCE_COMMAND_REGEX.match("  source helpers.sh")
        assert m is not None


# ---------------------------------------------------------------------------
# secure_join
# ---------------------------------------------------------------------------


class TestSecureJoin:
    def test_normal_join(self, tmp_path):
        (tmp_path / "lib.sh").write_text("echo lib\n")
        result = secure_join(tmp_path, "lib.sh", tmp_path)
        assert result == (tmp_path / "lib.sh").resolve()

    def test_path_traversal_blocked(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        outside = tmp_path / "outside.sh"
        outside.write_text("echo outside\n")
        with pytest.raises(SourceSecurityError):
            secure_join(sub, "../outside.sh", sub)

    def test_bypass_security_check(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        outside = tmp_path / "outside.sh"
        outside.write_text("echo outside\n")
        result = secure_join(sub, "../outside.sh", sub, bypass_security_check=True)
        assert result == outside.resolve()

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            secure_join(tmp_path, "nonexistent.sh", tmp_path)


# ---------------------------------------------------------------------------
# inline_bash_source / read_bash_script
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=False)
def skip_root_checks(monkeypatch):
    """Allow scripts outside the project root (needed when using tmp_path)."""
    monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")


class TestReadBashScript:
    def test_simple_script(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")
        script = tmp_path / "run.sh"
        script.write_text("#!/bin/bash\necho hello\n")
        result = read_bash_script(script)
        assert "echo hello" in result
        # shebang should be stripped
        assert "#!/bin/bash" not in result

    def test_empty_script_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")
        script = tmp_path / "empty.sh"
        script.write_text("#!/bin/bash\n   \n")
        from bash2gitlab.errors.exceptions import Bash2GitlabError

        with pytest.raises((Bash2GitlabError, Exception)):
            read_bash_script(script)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises((FileNotFoundError, Exception)):
            read_bash_script(tmp_path / "missing.sh")

    def test_inlines_sourced_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")
        lib = tmp_path / "lib.sh"
        lib.write_text("echo from_lib\n")
        main = tmp_path / "main.sh"
        main.write_text("#!/bin/bash\nsource lib.sh\necho main\n")
        result = read_bash_script(main)
        assert "echo from_lib" in result
        assert "echo main" in result
        # the source line itself should not be in output (replaced by content)
        assert "source lib.sh" not in result

    def test_dot_source_inlined(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")
        lib = tmp_path / "lib.sh"
        lib.write_text("MYVAR=42\n")
        main = tmp_path / "main.sh"
        main.write_text("#!/bin/bash\n. lib.sh\necho $MYVAR\n")
        result = read_bash_script(main)
        assert "MYVAR=42" in result

    def test_nested_source(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")
        deep = tmp_path / "deep.sh"
        deep.write_text("echo deep\n")
        mid = tmp_path / "mid.sh"
        mid.write_text("source deep.sh\necho mid\n")
        main = tmp_path / "main.sh"
        main.write_text("#!/bin/bash\nsource mid.sh\necho main\n")
        result = read_bash_script(main)
        assert "echo deep" in result
        assert "echo mid" in result
        assert "echo main" in result

    def test_circular_source_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")
        a = tmp_path / "a.sh"
        b = tmp_path / "b.sh"
        a.write_text("echo a\nsource b.sh\n")
        b.write_text("echo b\nsource a.sh\n")
        main = tmp_path / "main.sh"
        main.write_text("#!/bin/bash\nsource a.sh\n")
        # Should not infinite loop - circular references are skipped
        result = read_bash_script(main)
        assert "echo a" in result
        assert "echo b" in result

    def test_shebang_stripped_from_main_only(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")
        lib = tmp_path / "lib.sh"
        lib.write_text("#!/bin/bash\necho lib\n")
        main = tmp_path / "main.sh"
        main.write_text("#!/bin/bash\nsource lib.sh\n")
        result = read_bash_script(main)
        # lib's shebang should remain (only top-level stripped)
        assert "#!/bin/bash" in result
        assert result.count("#!/bin/bash") == 1  # lib's shebang stays; main's gone

    def test_ends_with_newline(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")
        script = tmp_path / "run.sh"
        script.write_text("#!/bin/bash\necho hi")  # no trailing newline
        result = read_bash_script(script)
        assert result.endswith("\n")


class TestInlineBashSourcePragmas:
    def test_do_not_inline_pragma_skips_sourcing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")
        lib = tmp_path / "lib.sh"
        lib.write_text("echo lib\n")
        main = tmp_path / "main.sh"
        # do-not-inline pragma on source line
        main.write_text("#!/bin/bash\nsource lib.sh # Pragma: do-not-inline\necho main\n")
        result = read_bash_script(main)
        # The pragma line itself is stripped but source is NOT inlined
        assert "echo lib" not in result
        assert "echo main" in result

    def test_do_not_inline_next_line_pragma(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")
        lib = tmp_path / "lib.sh"
        lib.write_text("echo lib\n")
        main = tmp_path / "main.sh"
        main.write_text("#!/bin/bash\n# Pragma: do-not-inline-next-line\nsource lib.sh\necho main\n")
        result = read_bash_script(main)
        # lib content NOT inlined (pragma blocks it); the source line itself is skipped/dropped
        assert "echo lib" not in result
        assert "echo main" in result

    def test_start_end_do_not_inline_block(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")
        lib = tmp_path / "lib.sh"
        lib.write_text("echo lib\n")
        main = tmp_path / "main.sh"
        main.write_text(
            "#!/bin/bash\n"
            "# Pragma: start-do-not-inline\n"
            "source lib.sh\n"
            "# Pragma: end-do-not-inline\n"
            "echo after\n"
        )
        result = read_bash_script(main)
        assert "echo lib" not in result
        assert "echo after" in result

    def test_nested_start_do_not_inline_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")
        main = tmp_path / "main.sh"
        main.write_text(
            "#!/bin/bash\n"
            "# Pragma: start-do-not-inline\n"
            "# Pragma: start-do-not-inline\n"
            "echo x\n"
            "# Pragma: end-do-not-inline\n"
        )
        with pytest.raises((PragmaError, Exception)):
            read_bash_script(main)

    def test_end_without_start_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")
        main = tmp_path / "main.sh"
        main.write_text("#!/bin/bash\n# Pragma: end-do-not-inline\necho x\n")
        with pytest.raises((PragmaError, Exception)):
            read_bash_script(main)

    def test_unclosed_block_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASH2GITLAB_SKIP_ROOT_CHECKS", "1")
        main = tmp_path / "main.sh"
        main.write_text("#!/bin/bash\n# Pragma: start-do-not-inline\necho x\n")
        with pytest.raises((PragmaError, Exception)):
            read_bash_script(main)
