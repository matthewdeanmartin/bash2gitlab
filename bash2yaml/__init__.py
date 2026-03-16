"""
A tool for making development of centralized yaml gitlab templates more pleasant.
"""

__all__ = [
    "__version__",
    "__about__",
    # decompile
    "run_decompile_gitlab_file",
    "run_decompile_gitlab_tree",
    # clean
    "clean_targets",
    # copy2local
    "clone_repository_ssh",
    "fetch_repository_archive",
    # doctor
    "run_doctor",
    # drift
    "run_detect_drift",
    # compile
    "run_compile_all",
    # map deploy
    "run_map_deploy",
    "run_commit_map",
    # show config
    "run_show_config",
    # plugin support
    "config",
    "get_pm",
    # initialization
    "generate_config",
    "run_init",
    # precommit
    "install",
    "uninstall",
    "PrecommitHookError",
    # lint
    "lint_output_folder",
    "summarize_results",
    # watch
    "start_watch",
    # graph
    "generate_dependency_graph",
    # run
    "best_efforts_run",
]

# CI Server, Core
from bash2yaml import __about__, config
from bash2yaml.__about__ import __version__
from bash2yaml.commands.best_effort_runner import best_efforts_run
from bash2yaml.commands.clean_all import clean_targets
from bash2yaml.commands.compile_all import run_compile_all
from bash2yaml.commands.decompile_all import run_decompile_gitlab_file, run_decompile_gitlab_tree
from bash2yaml.commands.detect_drift import run_detect_drift
from bash2yaml.commands.lint_all import lint_output_folder, summarize_results
from bash2yaml.commands.show_config import run_show_config
from bash2yaml.plugins import get_pm
from bash2yaml.utils.logging_config import generate_config

try:
    from bash2yaml.commands.copy2local import clone_repository_ssh, fetch_repository_archive
    from bash2yaml.commands.doctor import run_doctor
    from bash2yaml.commands.graph_all import generate_dependency_graph
    from bash2yaml.commands.init_project import run_init
    from bash2yaml.commands.map_commit import run_commit_map
    from bash2yaml.commands.map_deploy import run_map_deploy
    from bash2yaml.commands.precommit import PrecommitHookError, install, uninstall
    from bash2yaml.watch_files import start_watch
except ModuleNotFoundError:
    pass
