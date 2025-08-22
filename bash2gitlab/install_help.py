from bash2gitlab import __about__
from bash2gitlab.utils.check_interactive import detect_environment

APP = __about__.__title__
HELP = f"""
To unlock the *full* experience of this {APP}, you should install the [all] extra.
By default, `pip install {APP}` only gives you the minimal core.

Here are the most common ways to install `{APP}[all]`:

─────────────────────────────
Command line (pip):
─────────────────────────────
    pip install "{APP}[all]"
    pip install "{APP}[all]" --upgrade
    python -m pip install "{APP}[all]"

─────────────────────────────
Command line (uv / pipx / poetry run):
─────────────────────────────
    uv pip install "{APP}[all]"
    pipx install "{APP}[all]"
    pipx install {APP} --pip-args='.[all]'
    poetry run pip install "{APP}[all]"

─────────────────────────────
requirements.txt:
─────────────────────────────
Add one of these lines:
    {APP}[all]
    {APP}[all]==1.2.3        # pin a version
    {APP}[all]>=1.2.0,<2.0   # version range

─────────────────────────────
pyproject.toml (PEP 621 / Poetry / Hatch / uv):
─────────────────────────────
[tool.poetry.dependencies]
{APP} = {{ version = "1.2.3", extras = ["all"] }}

# or for PEP 621 (uv, hatchling, setuptools):
[project]
dependencies = [
    "{APP}[all]>=1.2.3",
]

─────────────────────────────
setup.cfg (setuptools):
─────────────────────────────
[options]
install_requires =
    {APP}[all]

─────────────────────────────
environment.yml (conda/mamba):
─────────────────────────────
dependencies:
  - pip
  - pip:
      - {APP}[all]

─────────────────────────────
Other notes:
─────────────────────────────
- Quoting is sometimes required: "{APP}[all]"
- If you already installed core, run: pip install --upgrade "{APP}[all]"
- Wheels/conda may not provide all extras; fall back to pip if needed.

Summary:
▶ Default install = minimal.
▶ `{APP}[all]` = full, recommended.
"""


def print_install_help():
    if detect_environment() == "interactive":
        print(HELP)
