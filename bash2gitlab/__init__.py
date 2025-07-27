__all__ = ["process_uncompiled_directory", "__version__", "shred_gitlab_ci"]

from bash2gitlab.__about__ import __version__
from bash2gitlab.compile_all import process_uncompiled_directory
from bash2gitlab.shred_all import shred_gitlab_ci
