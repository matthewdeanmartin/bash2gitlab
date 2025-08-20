import bash2gitlab.gui
import bash2gitlab.interactive
import bash2gitlab.tui


def test_imports():
    assert dir(bash2gitlab.tui)


def test_interactive():
    assert dir(bash2gitlab.interactive)


def test_gui():
    assert dir(bash2gitlab.gui)
