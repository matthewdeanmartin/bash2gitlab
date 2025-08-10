"""Cache and centralize the YAML object"""

import functools

from ruamel.yaml import YAML


@functools.lru_cache(maxsize=1)
def get_yaml() -> YAML:
    y = YAML()
    y.width = 4096
    y.preserve_quotes = False  # Maybe minimize quotes?
    y.default_style = None  # minimize quotes
    y.explicit_start = False  # no '---'
    y.explicit_end = False  # no '...'
    return y
