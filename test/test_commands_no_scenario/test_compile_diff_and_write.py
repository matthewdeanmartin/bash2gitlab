# test_diff_and_write.py
from __future__ import annotations

import base64
from pathlib import Path

import pytest
from ruamel.yaml import YAML

import bash2gitlab.commands.compile_all as m
from bash2gitlab.commands.compile_all import write_compiled_file
from bash2gitlab.utils.diff_helpers import diff_stats, unified_diff

# --- Helpers used in monkeypatching -------------------------------------------------


def _yaml_loader():
    return YAML()


def _yaml_struct_equal(a: str, b: str) -> bool:
    """Compare YAML structures (ignores formatting/ordering differences)."""
    y = _yaml_loader()
    return y.load(a) == y.load(b)


def _identity(s: str) -> str:
    return s


def _write_yaml_and_hash(dest: Path, content: str, hash_file: Path) -> None:
    """Minimal stand-in for your write_yaml_and_hash()."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    hash_file.write_text(base64.b64encode(content.encode("utf-8")).decode("ascii"), encoding="utf-8")


# --- unified_diff tests --------------------------------------------------------------


def test_unified_diff_includes_filenames_and_labels(tmp_path: Path):
    p = tmp_path / "config.yml"
    old = "a: 1\nb: 2\n"
    new = "a: 1\nb: 3\nc: 4\n"
    d = unified_diff(old, new, p, from_label="current", to_label="new")

    # Headers contain the filenames + labels
    assert f"{p} (current)" in d
    assert f"{p} (new)" in d

    # Shows +/- lines (content-wise)
    assert "-b: 2" in d
    assert "+b: 3" in d
    assert "+c: 4" in d


def test_diff_stats_counts_insertions_deletions():
    diff_text = """--- a
+++ b
@@ -1,3 +1,3 @@
-a: 1
+b: 1
 c: 2
+d: 3
-zz: 9
"""
    different = diff_stats(diff_text)
    # Lines starting '+' or '-' excluding headers/hunks:
    # +b: 1, +d: 3  => 2 insertions
    # -a: 1, -zz: 9 => 2 deletions
    assert (different.changed, different.insertions, different.deletions) == (4, 2, 2)


# --- write_compiled_file tests -------------------------------------------------------


@pytest.fixture(autouse=True)
def patch_yaml_helpers(monkeypatch):
    """
    Keep filesystem real; replace only helper functions with small, predictable versions.
    """
    monkeypatch.setattr(m, "get_yaml", _yaml_loader, raising=True)
    monkeypatch.setattr(m, "yaml_is_same", _yaml_struct_equal, raising=True)
    monkeypatch.setattr(m, "normalize_for_compare", _identity, raising=True)
    monkeypatch.setattr(m, "write_yaml_and_hash", _write_yaml_and_hash, raising=True)
    # short_path is only used for logging; keep it simple and deterministic.
    monkeypatch.setattr(m, "short_path", lambda p: Path(p).name, raising=True)


def test_dry_run_new_file_returns_true(tmp_path: Path, caplog):
    out = tmp_path / "out.yml"
    result = write_compiled_file(out, "a: 1\n", dry_run=True)
    assert result is True
    # No file should be created in dry-run
    assert not out.exists()
    assert not (out.with_suffix(".yml.hash")).exists()


def test_dry_run_existing_no_change_returns_false(tmp_path: Path):
    out = tmp_path / "out.yml"
    out.write_text("a: 1\n", encoding="utf-8")
    # Same content (structurally), so no change
    result = write_compiled_file(out, "a: 1\n", dry_run=True)
    assert result is False


def test_dry_run_existing_change_returns_true(tmp_path: Path):
    out = tmp_path / "out.yml"
    out.write_text("a: 1\n", encoding="utf-8")
    # Different content (structurally), so would rewrite
    result = write_compiled_file(out, "a: 2\n", dry_run=True)
    assert result is True


def test_first_write_creates_file_and_hash(tmp_path: Path):
    out = tmp_path / "compiled.yml"
    hash_file = tmp_path / "compiled.yml.hash"
    assert not out.exists() and not hash_file.exists()

    result = write_compiled_file(out, "a: 1\n", dry_run=False)
    assert result is True
    assert out.exists() and hash_file.exists()

    # Hash contains base64(content)
    expected_hash = base64.b64encode(b"a: 1\n").decode("ascii")
    assert hash_file.read_text(encoding="utf-8").strip() == expected_hash


def test_rewrite_when_hash_valid_and_new_differs(tmp_path: Path):
    out = tmp_path / "compiled.yml"
    hash_file = tmp_path / "compiled.yml.hash"

    # Seed with last-known content (file + matching .hash)
    last_known = "a: 1\n"
    out.write_text(last_known, encoding="utf-8")
    hash_file.write_text(base64.b64encode(last_known.encode("utf-8")).decode("ascii"), encoding="utf-8")

    # Provide a different new content; should rewrite
    result = write_compiled_file(out, "a: 2\n", dry_run=False)
    assert result is True

    # File and hash updated
    assert out.read_text(encoding="utf-8") == "a: 2\n"
    new_hash = base64.b64encode(b"a: 2\n").decode("ascii")
    assert hash_file.read_text(encoding="utf-8").strip() == new_hash


def test_skip_when_no_changes_structurally(tmp_path: Path):
    out = tmp_path / "compiled.yml"
    hash_file = tmp_path / "compiled.yml.hash"

    # Seed file + matching hash for "a: 1\n"
    content = "a: 1\n"
    out.write_text(content, encoding="utf-8")
    hash_file.write_text(base64.b64encode(content.encode("utf-8")).decode("ascii"), encoding="utf-8")

    # New content is semantically the same YAML (different formatting)
    new_content = "a: 1\n"  # could also try "a: 1\r\n" or add trailing spaces
    result = write_compiled_file(out, new_content, dry_run=False)

    assert result is False
    # Nothing changed on disk
    assert out.read_text(encoding="utf-8") == content
    assert hash_file.read_text(encoding="utf-8").strip() == base64.b64encode(content.encode("utf-8")).decode("ascii")
