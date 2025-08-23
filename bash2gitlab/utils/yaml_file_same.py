from __future__ import annotations

import re

from ruamel.yaml.error import YAMLError

from bash2gitlab.utils.yaml_factory import get_yaml


def normalize_for_compare(text: str) -> str:
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Trim trailing whitespace per line
    text = "\n".join(line.rstrip() for line in text.splitlines())
    # Ensure exactly one newline at EOF
    if not text.endswith("\n"):
        text += "\n"
    # Collapse multiple blank lines at EOF to one (optional)
    text = re.sub(r"\n{3,}$", "\n\n", text)
    return text.strip(" \n")


def yaml_is_same(current_content: str, new_content: str) -> bool:
    if current_content.strip("\n") == new_content.strip("\n"):
        # Simple match.
        return True

    current_norm = normalize_for_compare(current_content)
    new_norm = normalize_for_compare(new_content)

    if current_norm == new_norm:
        return True

    yaml = get_yaml()
    try:
        new_doc = yaml.load(new_content)
        curr_doc = yaml.load(current_content)
    except YAMLError:
        return False

    if curr_doc == new_doc:
        return True

    return False
