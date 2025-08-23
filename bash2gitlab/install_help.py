"""Let people know how to install bash2gitlab[all]"""

import os

from bash2gitlab import __about__
from bash2gitlab.utils.check_interactive import detect_environment
from bash2gitlab.utils.what_shell import supports_underline

APP = __about__.__title__


def print_install_help() -> None:
    """Prints recommendation to install bash2gitlab[all]"""
    if detect_environment() == "interactive" and not os.environ.get("BASH2GITLAB_HIDE_CORE_HELP"):
        if supports_underline():
            u = "\033[4m"
            r = "\033[0m"
        else:
            u = ""
            r = ""

        help_text = f"""To use interactive commands of {APP}, you should install the [all] extra.

        {u}Command line (pip):{r}
            pip install "{APP}[all]"

        {u}Command line (uv / pipx / poetry run):{r}
            uv pip install "{APP}[all]"
            pipx install "{APP}[all]"
            poetry run pip install "{APP}[all]"

        {u}pyproject.toml (PEP 621 / Poetry / Hatch / uv):{r}
        [tool.poetry.dependencies]
        {APP} = {{ version = ">={__about__.__version__}", extras = ["all"] }}

        # or for PEP 621 (uv, hatchling, setuptools):
        [project]
        dependencies = [
            "{APP}[all]>={__about__.__version__}",
        ]

        Select your preferred installation style above."""

        print(help_text)


if __name__ == "__main__":
    print_install_help()
