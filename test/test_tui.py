import bash2yaml.gui
import bash2yaml.interactive
import bash2yaml.tui


def test_imports():
    assert dir(bash2yaml.tui)


def test_interactive():
    assert dir(bash2yaml.interactive)


def test_gui():
    assert dir(bash2yaml.gui)
