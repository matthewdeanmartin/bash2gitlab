"""Cache and centralize the YAML object"""

import functools

from ruamel.yaml import YAML


@functools.lru_cache(maxsize=1)
def get_yaml() -> YAML:
    # https://stackoverflow.com/a/70496481/33264
    y = YAML(typ="rt")  # rt to support !reference tag
    y.width = 4096
    y.preserve_quotes = True  # Want to minimize quotes, but "1.0" -> 1.0 is a type change.
    # maximize quotes
    # y.default_style = '"'  # type: ignore[assignment]
    y.explicit_start = False  # no '---'
    y.explicit_end = False  # no '...'
    return y
