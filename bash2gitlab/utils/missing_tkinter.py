import platform
import sys
import textwrap


def check_for_python_3_13_0() -> bool:
    """
    Check if the running interpreter is Python 3.13.0.
    If so, advise the user to upgrade to 3.13.1+.
    """
    version_info = sys.version_info
    if (version_info.major, version_info.minor, version_info.micro) == (3, 13, 0):
        msg = textwrap.dedent(
            f"""
        ⚠️ You are running Python {platform.python_version()}.

        This is an initial release of Python 3.13 and has known bugs.
        You should upgrade to 3.13.1 or newer.

        Suggested upgrade methods:
          • Windows (python.org installer): download the latest 3.13.x from https://www.python.org/downloads/windows/
          • macOS (Homebrew):    brew upgrade python@3.13
          • Linux (Debian/Ubuntu): sudo apt update && sudo apt install python3.13
          • Linux (Fedora/RHEL): sudo dnf upgrade python3.13
          • Universal (pyenv):   pyenv install 3.13.1 && pyenv global 3.13.1

        """
        ).strip()
        print(msg)
        return True
    return False
