# tests/test_main.py

from __future__ import annotations

from unittest.mock import patch

import pytest

from bash2yaml.__main__ import main


def test_version_flag():
    """Tests the --version flag."""
    with patch("sys.argv", ["bash2yaml", "--version"]):
        with pytest.raises(SystemExit) as e:
            main()
        assert e.type is SystemExit
        assert e.value.code == 0


def test_help_flag():
    """Tests the --version flag."""
    with patch("sys.argv", ["bash2yaml", "--help"]):
        with pytest.raises(SystemExit) as e:
            main()
        assert e.type is SystemExit
        assert e.value.code == 0
