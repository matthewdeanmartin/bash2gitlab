from __future__ import annotations

import base64
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from bash2gitlab.utils.utils import short_path

logger = logging.getLogger(__name__)

# --- Helpers -----------------------------------------------------------------


def partner_hash_file(base_file: Path) -> Path:
    """Return the expected .hash file for a target file.

    Example: foo/bar.yml -> foo/bar.yml.hash
    """
    return base_file.with_suffix(base_file.suffix + ".hash")


def base_from_hash(hash_file: Path) -> Path:
    """Return the expected base file for a .hash file.

    Works even on older Python without Path.removesuffix().
    Example: foo/bar.yml.hash -> foo/bar.yml
    """
    s = str(hash_file)
    suffix = ".hash"
    if s.endswith(suffix):
        return Path(s[: -len(suffix)])
    return hash_file  # unexpected, but avoid throwing


# --- Inspection utilities -----------------------------------------------------


def iter_target_pairs(root: Path) -> Iterator[tuple[Path, Path]]:
    """Yield (base_file, hash_file) pairs under *root* recursively.

    Only yields pairs where *both* files exist.
    """
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if p.name.endswith(".hash"):
            base = base_from_hash(p)
            if base.exists() and base.is_file():
                yield (base, p)
        else:
            hashf = partner_hash_file(p)
            if hashf.exists() and hashf.is_file():
                # Pair will also be seen when rglob hits the .hash file; skip duplicates
                continue


def list_stray_files(root: Path) -> list[Path]:
    """Return files under *root* that do **not** have a hash pair.

    A "stray" is either:
    - a non-.hash file with no corresponding ``<file>.hash``; or
    - a ``.hash`` file whose base file is missing.
    """
    strays: list[Path] = []

    # Track pairs we've seen to avoid extra disk checks
    paired_bases: set[Path] = set()
    paired_hashes: set[Path] = set()

    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if p.suffix == "":
            # still fine; pairing is based on full name + .hash
            pass

        if p.name.endswith(".hash"):
            base = base_from_hash(p)
            if base.exists():
                paired_bases.add(base)
                paired_hashes.add(p)
            else:
                strays.append(p)
        else:
            hashf = partner_hash_file(p)
            if hashf.exists():
                paired_bases.add(p)
                paired_hashes.add(hashf)
            else:
                strays.append(p)

    logger.info("Found %d stray file(s) under %s", len(strays), root)
    for s in strays:
        logger.debug("Stray: %s", s)
    return sorted(strays)


# --- Hash verification --------------------------------------------------------


def read_current_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_hash_text(hash_file: Path) -> str | None:
    """Decode base64 content of *hash_file* to text.

    Returns None if decoding fails.
    """
    try:
        raw = hash_file.read_text(encoding="utf-8").strip()
        return base64.b64decode(raw).decode("utf-8")
    # best-effort guard
    except Exception as e:  # nosec
        logger.warning("Failed to decode hash file %s: %s", hash_file, e)
        return None


def is_target_unchanged(base_file: Path, hash_file: Path) -> bool | None:
    """Check if *base_file* matches the content recorded in *hash_file*.

    Returns:
        - True if contents match
        - False if they differ
        - None if the hash file cannot be decoded
    """
    expected = read_hash_text(hash_file)
    if expected is None:
        return None
    current = read_current_text(base_file)
    return current == expected


# --- Cleaning -----------------------------------------------------------------
@dataclass(frozen=True)
class CleanReport:
    deleted_pairs: int
    skipped_changed: int
    skipped_invalid_hash: int


def clean_targets(root: Path, *, dry_run: bool = False) -> CleanReport:
    """Delete generated target files (and their .hash files) under *root*.

    Only deletes when a valid pair exists **and** the base file content matches
    the recorded hash. "Stray" files are always left alone.

    Args:
        root: Directory containing compiled outputs and ``*.hash`` files.
        dry_run: If True, log what would be deleted but do not delete.

    Returns:
        tuple of (deleted_pairs, skipped_changed, skipped_invalid_hash)
    """
    deleted = 0
    skipped_changed = 0
    skipped_invalid = 0

    # Build a unique set of pairs to consider
    seen_pairs: set[tuple[Path, Path]] = set()
    for p in root.rglob("*.hash"):
        if p.is_dir():
            continue
        base_file = base_from_hash(p)
        if not base_file.exists() or not base_file.is_file():
            # Stray .hash; leave it
            continue
        seen_pairs.add((base_file, p))

    if not seen_pairs:
        logger.info("No target pairs found under %s", short_path(root))
        return CleanReport(0, 0, 0)

    for base_file, hash_file in sorted(seen_pairs):
        status = is_target_unchanged(base_file, hash_file)
        if status is None:
            logger.warning(
                "Refusing to remove %s (invalid/corrupt hash at %s)", short_path(base_file), short_path(hash_file)
            )
            skipped_invalid += 1
            continue
        if not status:
            skipped_changed += 1
            logger.warning("Refusing to remove %s (content has changed since last write)", short_path(base_file))
            continue

        # status is True: safe to delete
        if dry_run:
            logger.info("[DRY RUN] Would delete %s and %s", short_path(base_file), short_path(hash_file))
        else:
            try:
                base_file.unlink(missing_ok=False)
                hash_file.unlink(missing_ok=True)
                logger.info("Deleted %s and %s", short_path(base_file), short_path(hash_file))
            # narrow surface area; logs any fs issues
            except Exception as e:  # nosec
                logger.error("Failed to delete %s / %s: %s", short_path(base_file), short_path(hash_file), e)
                continue
        deleted += 1

    logger.info(
        "Clean summary: %d pair(s) deleted, %d changed file(s) skipped, %d invalid hash(es) skipped",
        deleted,
        skipped_changed,
        skipped_invalid,
    )
    return CleanReport(deleted_pairs=deleted, skipped_changed=skipped_changed, skipped_invalid_hash=skipped_invalid)


# --- Optional: quick report helper -------------------------------------------


def report_targets(root: Path) -> list[Path]:
    """Log a concise report of pairs, strays, and safety status.

    Useful for diagnostics before/after ``clean_targets``.
    """
    pairs = list(iter_target_pairs(root))
    strays = list_stray_files(root)

    logger.debug("Target report for %s", short_path(root))
    logger.debug("Pairs found: %d", len(pairs))
    for bash_file, hash_file in pairs:
        status = is_target_unchanged(bash_file, hash_file)
        if status:
            logger.debug("OK: %s (hash matches)", short_path(bash_file))
        elif status is False:
            logger.warning("CHANGED: %s (hash mismatch)", short_path(bash_file))
        else:
            logger.warning("INVALID HASH: %s (cannot decode %s)", short_path(bash_file), short_path(hash_file))

    logger.debug("Strays: %d", len(strays))
    for s in strays:
        logger.debug("Stray: %s", short_path(s))
    return strays
