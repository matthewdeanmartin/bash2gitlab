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


#
# @functools.lru_cache(maxsize=1)
# def get_yaml() -> YAML:
#     y = YAML()
#     y.width = 4096
#     y.preserve_quotes = True  # Want to minimize quotes, but "1.0" -> 1.0 is a type change.
#
#     # Don't set default_style for all strings - let LiteralScalarString work naturally
#     # y.default_style = '"'  # COMMENTED OUT - this was preventing | syntax
#
#     # Instead, set up a custom representer that quotes regular strings but not literal blocks
#     def custom_str_representer(dumper, data):
#         if isinstance(data, LiteralScalarString):
#             return dumper.represent_literal_scalar(data)
#         # Force quotes on regular strings to prevent type changes like "1.0" -> 1.0
#         return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')
#
#     y.representer.add_representer(str, custom_str_representer)
#     y.representer.add_representer(LiteralScalarString, y.representer.represent_literal_scalarstring)
#
#     y.explicit_start = False  # no '---'
#     y.explicit_end = False  # no '...'
#     return y
