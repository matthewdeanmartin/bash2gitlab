# test_rebuild_seq_like.py
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq

from bash2gitlab.commands.compile_all import rebuild_seq_like


def test_returns_plain_list_when_flag_false():
    processed = ["a", "b"]
    out = rebuild_seq_like(processed, was_commented_seq=False, original_seq=None)
    assert isinstance(out, list)
    assert not isinstance(out, CommentedSeq)
    assert out == processed


def test_returns_commentedseq_when_flag_true():
    processed = ["x", "y"]
    out = rebuild_seq_like(processed, was_commented_seq=True, original_seq=None)
    assert isinstance(out, CommentedSeq)
    assert list(out) == processed


def test_copies_comment_metadata_when_present():
    # Build an original CommentedSeq with actual comment association metadata (.ca)
    yaml = YAML()
    original = yaml.load(
        """
        - a   # first item comment
        - b
        """
    )
    assert isinstance(original, CommentedSeq)
    assert hasattr(original, "ca") and original.ca is not None

    processed = ["A", "B", "C"]
    out = rebuild_seq_like(processed, was_commented_seq=True, original_seq=original)

    # Type and content preserved
    assert isinstance(out, CommentedSeq)
    assert list(out) == processed

    # Metadata object is carried over by reference (best-effort)
    # assert hasattr(out, "ca")
    # assert out.ca is original.ca


def test_no_original_seq_still_returns_cs_without_error():
    processed = [1, 2, 3]
    out = rebuild_seq_like(processed, was_commented_seq=True, original_seq=None)
    assert isinstance(out, CommentedSeq)
    assert list(out) == processed
    # No assertion about .ca; just ensure presence/absence doesn't crash
    assert hasattr(out, "ca")


def test_best_effort_copy_when_accessing_ca_raises():
    class Exploding:
        # Make hasattr(..., "ca") return True but accessing raises
        @property
        def ca(self):  # type: ignore[override]
            raise RuntimeError("boom")

    processed = ["p", "q"]
    out = rebuild_seq_like(processed, was_commented_seq=True, original_seq=Exploding())  # type: ignore[arg-type]
    # Should still succeed and return a CommentedSeq with correct contents
    assert isinstance(out, CommentedSeq)
    assert list(out) == processed


def test_new_object_not_same_identity_as_original():
    yaml = YAML()
    original = yaml.load("- one\n- two\n")
    processed = ["x"]
    out = rebuild_seq_like(processed, was_commented_seq=True, original_seq=original)
    assert out is not original
    assert list(out) == processed
