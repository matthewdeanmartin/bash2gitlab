import functools

from ruamel.yaml import YAML


@functools.lru_cache(maxsize=1)
def get_yaml() -> YAML:
    y = YAML()
    y.width = 4096
    y.preserve_quotes = True
    y.default_style = None
    return y
