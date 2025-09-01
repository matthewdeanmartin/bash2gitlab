from __future__ import annotations

from typing import Any

import ryml  # module name: ryml

from bash2gitlab.utils.yaml_file_same import normalize_for_compare

# keep your existing helpers
# normalize_for_compare(...)
# (removed) get_yaml(), YAMLError


def _ryml_to_obj(tree: ryml.Tree, node: int) -> Any:
    """
    Convert a ryml node (map/seq/scalar) into plain Python
    structures (dict/list/str) for order-insensitive equality.
    """
    # maps
    if getattr(tree, "is_map", None) and tree.is_map(node):
        out: dict[str, Any] = {}
        for ch in ryml.children(tree, node):
            k = tree.key(ch)
            k_s = (k if isinstance(k, (bytes, bytearray, memoryview)) else bytes(k)).decode("utf-8")
            # child can be key+scalar, key+map, or key+seq
            if tree.has_val(ch) and not tree.has_children(ch):
                v = tree.val(ch)
                v_s = (v if isinstance(v, (bytes, bytearray, memoryview)) else bytes(v)).decode("utf-8")
                out[k_s] = v_s
            else:
                # value is a nested map/seq under this child
                # value node is the first child of ch
                val_node = tree.first_child(ch)
                out[k_s] = _ryml_to_obj(tree, val_node)
        # sort keys to make mapping order irrelevant for equality
        return {k: out[k] for k in sorted(out.keys())}

    # sequences
    if getattr(tree, "is_seq", None) and tree.is_seq(node):
        items: list[Any] = []
        for ch in ryml.children(tree, node):
            if tree.is_val(ch) and not tree.has_children(ch):
                v = tree.val(ch)
                v_s = (v if isinstance(v, (bytes, bytearray, memoryview)) else bytes(v)).decode("utf-8")
                items.append(v_s)
            else:
                items.append(_ryml_to_obj(tree, ch))
        return items

    # scalar value (root could also be a bare scalar doc)
    if tree.is_val(node):
        v = tree.val(node)
        return (v if isinstance(v, (bytes, bytearray, memoryview)) else bytes(v)).decode("utf-8")

    # empty doc / nothing
    return None


def _parse_with_ryml(s: str) -> Any:
    """
    Parse YAML string into a normalized Python structure using ryml.
    ryml requires bytes/bytearray input.
    """
    # immutable parse that owns its arena
    tree = ryml.parse_in_arena(s.encode("utf-8"))
    root = tree.root_id()
    # some inputs are a map/seq directly at root, others are a doc node
    # if the root is a DOC container, drill into first child
    if getattr(tree, "is_doc", None) and tree.is_doc(root) and tree.has_children(root):
        return _ryml_to_obj(tree, tree.first_child(root))
    return _ryml_to_obj(tree, root)


def yaml_is_same(current_content: str, new_content: str) -> bool:
    # 1) quick trims
    if current_content.strip("\n") == new_content.strip("\n"):
        return True

    # 2) your existing normalization
    current_norm = normalize_for_compare(current_content)
    new_norm = normalize_for_compare(new_content)
    if current_norm == new_norm:
        return True

    # 3) parse & compare via RapidYAML
    try:
        curr_obj = _parse_with_ryml(current_content)
        new_obj = _parse_with_ryml(new_content)
    except Exception:
        # if either fails to parse as YAML, not equal
        return False

    return curr_obj == new_obj
