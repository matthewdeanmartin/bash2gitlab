from __future__ import annotations

from typing import Any

import ryml


# --- scalar casting (conservative, extend as needed) -------------------------
def _cast_scalar(s: str) -> Any:
    t = s.strip()
    if t in ("null", "~", "Null", "NULL", ""):
        return None
    if t in ("true", "True", "TRUE"):
        return True
    if t in ("false", "False", "FALSE"):
        return False
    # int?
    try:
        if t.startswith(("0x", "0X")):
            return int(t, 16)
        if t.startswith(("0o", "0O")):
            return int(t, 8)
        if t.startswith(("0b", "0B")):
            return int(t, 2)
        return int(t)
    except ValueError:
        pass
    # float?
    try:
        return float(t)
    except ValueError:
        pass
    return s


def _b2s(b: bytes | bytearray | memoryview) -> str:
    return (b if isinstance(b, (bytes, bytearray, memoryview)) else bytes(b)).decode("utf-8")


# --- ryml -> native ----------------------------------------------------------
def _node_to_obj(tree: ryml.Tree, node_id: int, cast_scalars: bool) -> Any:
    if tree.is_map(node_id):
        out: dict[str, Any] = {}
        for ch in ryml.children(tree, node_id):
            k = _b2s(tree.key(ch))
            if tree.has_val(ch) and not tree.has_children(ch):
                v = _b2s(tree.val(ch))
                out[k] = _cast_scalar(v) if cast_scalars else v
            else:
                # map/seq as value -> first child is the value node
                out[k] = _node_to_obj(tree, tree.first_child(ch), cast_scalars)
        return out

    if tree.is_seq(node_id):
        items: list[Any] = []
        for ch in ryml.children(tree, node_id):
            if tree.is_val(ch) and not tree.has_children(ch):
                v = _b2s(tree.val(ch))
                items.append(_cast_scalar(v) if cast_scalars else v)
            else:
                items.append(_node_to_obj(tree, ch, cast_scalars))
        return items

    if tree.is_val(node_id):
        v = _b2s(tree.val(node_id))
        return _cast_scalar(v) if cast_scalars else v

    return None  # empty


def loads(src: str, *, cast_scalars: bool = True) -> Any:
    """
    Return dict/list/str/None for single-doc YAML, or a list[...] for multi-doc YAML.
    """
    tree = ryml.parse_in_arena(src.encode("utf-8"))
    root = tree.root_id()

    # If the tree has multiple DOC children, return a list of parsed docs.
    if tree.has_children(root) and all(tree.is_doc(ch) for ch in ryml.children(tree, root)):
        return [_node_to_obj(tree, tree.first_child(doc), cast_scalars) if tree.has_children(doc) else None for doc in ryml.children(tree, root)]

    # Single-doc or bare map/seq/scalar at root:
    node = tree.first_child(root) if tree.is_doc(root) and tree.has_children(root) else root
    return _node_to_obj(tree, node, cast_scalars)
