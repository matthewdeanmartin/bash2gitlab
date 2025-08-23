"""Pluggy related code"""

import os

import pluggy

from bash2gitlab import hookspecs

_pm = None


def get_pm() -> pluggy.PluginManager:
    """Get a singleton plugin manager"""
    global _pm
    if _pm is None:
        _pm = pluggy.PluginManager("bash2gitlab")
        _pm.add_hookspecs(hookspecs)
        # Builtins keep current behavior:
        from bash2gitlab.builtin_plugins import Defaults

        _pm.register(Defaults())
        # Third-party:
        if not os.environ.get("BASH2GITLAB_NO_PLUGINS"):
            _pm.load_setuptools_entrypoints("bash2gitlab")
    return _pm


def call_seq(func_name: str, value, **kwargs):
    """Apply all hook returns in sequence (for yaml_*)."""
    pm = get_pm()
    results = getattr(pm.hook, func_name)(value, **kwargs)
    for r in results:
        if r is not None:
            value = r
    return value
