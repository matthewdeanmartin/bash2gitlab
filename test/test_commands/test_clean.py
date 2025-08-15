from __future__ import annotations

import base64
from pathlib import Path

from bash2gitlab.commands.clean_all import (
    base_from_hash,
    clean_targets,
    is_target_unchanged,
    iter_target_pairs,
    list_stray_files,
    partner_hash_file,
    read_hash_text,
    report_targets,
)


# -------------------------
# Helpers for test fixtures
# -------------------------
def write_text(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def make_pair(root: Path, rel: str, content: str) -> tuple[Path, Path]:
    """
    Create a base file and a matching .hash file under root.
    The hash file stores base64(content).
    """
    base = write_text(root / rel, content)
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    h = write_text(partner_hash_file(base), encoded)
    return base, h


def make_invalid_hash(root: Path, rel: str, content: str, hash_payload: str) -> tuple[Path, Path]:
    base = write_text(root / rel, content)
    h = write_text(partner_hash_file(base), hash_payload)
    return base, h


# -------------
# Unit tests
# -------------
def test_partner_hash_and_base_inverse(tmp_path: Path):
    base = tmp_path / "foo" / "bar.yml"
    base.parent.mkdir(parents=True)
    base.touch()
    h = partner_hash_file(base)
    assert h.name == "bar.yml.hash"
    # round-trip base_from_hash
    assert base_from_hash(h) == base

    # no .hash suffix returns input path unchanged
    assert base_from_hash(base) == base


def test_iter_target_pairs_yields_only_existing_pairs_once(tmp_path: Path):
    # Pair A (exists)
    a_base, a_hash = make_pair(tmp_path, "a/one.yml", "ONE")
    # Pair B (exists)
    b_base, b_hash = make_pair(tmp_path, "b/two.txt", "TWO")
    # Strays:
    #   - base without hash
    write_text(tmp_path / "c/three.txt", "THREE")
    #   - hash without base
    stray_hash = write_text(tmp_path / "d/four.txt.hash", base64.b64encode(b"FOUR").decode("ascii"))

    pairs = list(iter_target_pairs(tmp_path))
    # Order is not strictly defined; compare as sets
    assert set(pairs) == {(a_base, a_hash), (b_base, b_hash)}
    # Ensure the stray files didn't appear
    for _, h in pairs:
        assert h != stray_hash


def test_list_stray_files_reports_both_kinds(tmp_path: Path):
    # Good pair
    make_pair(tmp_path, "ok/file.yml", "OK")
    # Base without hash
    base_only = write_text(tmp_path / "solo/base.txt", "BASE")
    # Hash without base
    hash_only = write_text(tmp_path / "ghost/missing.py.hash", base64.b64encode(b"X").decode("ascii"))

    strays = list_stray_files(tmp_path)
    # Sorted result expected
    assert strays == sorted([base_only, hash_only])


def test__read_hash_text_valid_and_invalid(tmp_path: Path, caplog):
    base, h = make_pair(tmp_path, "data.txt", "hello")
    assert read_hash_text(h) == "hello"

    # Corrupt payload
    bad = write_text(tmp_path / "data2.txt.hash", "!!!!!not base64!!!!")
    with caplog.at_level("WARNING"):
        assert read_hash_text(bad) is None
        # Ensure we warned about failure
        assert any("Failed to decode hash file" in r.message for r in caplog.records)


def test_is_target_unchanged_states(tmp_path: Path):
    base, h = make_pair(tmp_path, "x.yml", "same")
    assert is_target_unchanged(base, h) is True

    # Change base content
    base.write_text("different", encoding="utf-8")
    assert is_target_unchanged(base, h) is False

    # Invalid hash -> None
    bad_hash = write_text(tmp_path / "x.yml.hash", "notbase64")
    assert is_target_unchanged(base, bad_hash) is None


def test_clean_targets_dry_run_does_not_delete(tmp_path: Path):
    base, h = make_pair(tmp_path, "dr/file.txt", "D")
    deleted, sc, si = clean_targets(tmp_path, dry_run=True)
    assert (deleted, sc, si) == (1, 0, 0)
    assert base.exists() and h.exists()


def test_report_targets_returns_same_strays_as_list_stray_files(tmp_path: Path):
    # Make one good pair and two strays
    make_pair(tmp_path, "p/good.yml", "G")
    s1 = write_text(tmp_path / "p/only_base.txt", "B")
    s2 = write_text(tmp_path / "p/only_hash.txt.hash", base64.b64encode(b"H").decode("ascii"))

    reported = report_targets(tmp_path)
    assert sorted(reported) == sorted([s1, s2])
