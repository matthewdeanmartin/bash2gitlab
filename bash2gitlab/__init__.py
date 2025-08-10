"""
A tool for making development of centralized yaml gitlab templates more pleasant.
"""

__all__ = ["run_compile_all", "__version__", "run_shred_gitlab"]

from bash2gitlab.__about__ import __version__
from bash2gitlab.commands.compile_all import run_compile_all
from bash2gitlab.commands.shred_all import run_shred_gitlab
