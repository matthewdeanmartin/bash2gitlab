# test_compact_runs_to_literal.py
import pytest
from ruamel.yaml import CommentedMap
from ruamel.yaml.comments import TaggedScalar
from ruamel.yaml.scalarstring import LiteralScalarString

from bash2gitlab.commands.compile_all import compact_runs_to_literal


def is_lit(obj):
    return isinstance(obj, LiteralScalarString)


def test_empty_list_returns_empty():
    assert compact_runs_to_literal([]) == []


def test_single_string_below_min_lines_stays_plain():
    out = compact_runs_to_literal(["echo hi"], min_lines=2)
    assert out == ["echo hi"]
    assert not any(is_lit(x) for x in out)


def test_two_strings_default_min2_becomes_literal():
    out = compact_runs_to_literal(["a", "b"])  # min_lines defaults to 2
    assert len(out) == 1
    assert is_lit(out[0])
    assert str(out[0]) == "a\nb"


def test_requires_three_when_min_lines_3():
    out = compact_runs_to_literal(["a", "b"], min_lines=3)
    # Not enough strings → keep as separate plain strings
    assert out == ["a", "b"]
    assert not any(is_lit(x) for x in out)

    out2 = compact_runs_to_literal(["a", "b", "c"], min_lines=3)
    assert len(out2) == 1 and is_lit(out2[0]) and str(out2[0]) == "a\nb\nc"


def test_newline_forces_literal_even_if_single_item():
    out = compact_runs_to_literal(["line1\nline2"], min_lines=99)
    assert len(out) == 1 and is_lit(out[0]) and str(out[0]) == "line1\nline2"


def test_existing_LiteralScalarString_joins_with_neighbors():
    # Existing LiteralScalarString is a str subclass (and not TaggedScalar),
    # so it should join with adjacent plain strings.
    lhs = LiteralScalarString("a")
    out = compact_runs_to_literal([lhs, "b"])
    assert len(out) == 1 and is_lit(out[0]) and str(out[0]) == "a\nb"

    out2 = compact_runs_to_literal(["x", lhs, "y"])
    assert len(out2) == 1 and is_lit(out2[0]) and str(out2[0]) == "x\na\ny"


def test_taggedscalar_is_boundary():
    tag = TaggedScalar("!Ref", "VALUE")
    out = compact_runs_to_literal(["a", "b", tag, "c", "d"])
    assert len(out) == 3
    assert is_lit(out[0]) and str(out[0]) == "a\nb"
    assert out[1] is tag
    assert is_lit(out[2]) and str(out[2]) == "c\nd"


@pytest.mark.parametrize("boundary", [TaggedScalar("!X", "y"), 42, CommentedMap()])
def test_any_non_plain_str_is_boundary(boundary):
    out = compact_runs_to_literal(["a", "b", boundary, "c"])
    assert len(out) == 3
    assert is_lit(out[0]) and str(out[0]) == "a\nb"
    assert out[1] is boundary
    # trailing run below min_lines=2? No, it has 1 item → stays plain
    assert out[2] == "c" and not is_lit(out[2])


def test_multiple_groups_and_mixed_newlines():
    items = [
        "one",
        "two",
        TaggedScalar("!K", "V"),
        "alpha\nbeta",  # newline forces literal
        "gamma",  # starts a new buffer
        TaggedScalar("!Stop", "Here"),
        "X",
        "Y",
        "Z",
    ]
    out = compact_runs_to_literal(items)
    # Expect:
    # 0: "one\ntwo" (literal)
    # 1: tagged
    # 2: "alpha\nbeta" (literal due to newline; remains literal)
    # 3: "gamma" (single plain string)
    # 4: tagged
    # 5: "X\nY\nZ" (literal)
    assert len(out) == 5
    assert is_lit(out[0]) and str(out[0]) == "one\ntwo"
    assert isinstance(out[1], TaggedScalar)
    assert is_lit(out[2]) and str(out[2]) == "alpha\nbeta\ngamma"
    assert isinstance(out[3], TaggedScalar)
    assert is_lit(out[4]) and str(out[4]) == "X\nY\nZ"


def test_order_is_preserved_and_no_extra_nodes():
    items = ["a", TaggedScalar("!T", "v"), "b", "c"]
    out = compact_runs_to_literal(items)
    # Positions should map 0→0, 1→1, 2-3 merged to 2
    assert len(out) == 3
    assert str(out[0]) == "a"
    assert isinstance(out[1], TaggedScalar)
    assert is_lit(out[2]) and str(out[2]) == "b\nc"
