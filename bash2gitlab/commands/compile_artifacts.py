"""Support for inlining artifacts (files and directories) as compressed, base64-encoded payloads.

Turns pragmas like:
    - # Pragma: inline-artifact ./config-bundle --output=/tmp/config

Into extraction shims:
    # >>> BEGIN inline-artifact: ./config-bundle (zip, 1.2KB compressed)
    __B2G_ARTIFACT='<base64-encoded-zip-data>'
    mkdir -p /tmp/config
    echo "$__B2G_ARTIFACT" | base64 -d | unzip -q -d /tmp/config -
    unset __B2G_ARTIFACT
    # <<< END inline-artifact

Artifacts are always compressed as zip and base64-encoded for YAML safety.
File permissions are NOT preserved (simplicity over features).
"""

from __future__ import annotations

import base64
import io
import logging
import os
import re
import zipfile
from pathlib import Path

from bash2gitlab.config import config

__all__ = ["maybe_inline_artifact"]

logger = logging.getLogger(__name__)


def get_max_artifact_size() -> int:
    """Get max artifact size from config or environment."""
    config_mb = config.max_artifact_size_mb
    if config_mb is not None:
        return int(config_mb * 1024 * 1024)
    return int(os.getenv("BASH2GITLAB_MAX_ARTIFACT_SIZE", str(1024 * 1024)))  # 1 MB default


def get_warn_artifact_size() -> int:
    """Get warning artifact size from config or environment."""
    config_kb = config.artifact_warn_size_kb
    if config_kb is not None:
        return int(config_kb * 1024)
    return int(os.getenv("BASH2GITLAB_ARTIFACT_WARN_SIZE", str(100 * 1024)))  # 100 KB default


# Regex to match artifact inlining pragmas
# Pattern: - # Pragma: inline-artifact <path> [--output=<path>] [--format=<fmt>] [--strip=<N>]
ARTIFACT_PRAGMA_REGEX = re.compile(
    r"""
    ^\s*-?\s*\#\s*Pragma:\s*inline-artifact\s+
    (?P<source_path>[^\s]+)
    (?:\s+--output=(?P<output_path>[^\s]+))?
    (?:\s+--format=(?P<format>zip|tar\.gz|tar\.bz2|tar\.xz))?
    (?:\s+--strip=(?P<strip>\d+))?
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)


class ArtifactInlineError(Exception):
    """Raised when artifact inlining fails."""


def create_zip_artifact(source_path: Path) -> bytes:
    """Create a zip archive from a file or directory.

    Args:
        source_path: Path to file or directory to compress

    Returns:
        Bytes of the zip archive

    Raises:
        ArtifactInlineError: If compression fails
    """
    if not source_path.exists():
        raise ArtifactInlineError(f"Source path does not exist: {source_path}")

    zip_buffer = io.BytesIO()

    try:
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            if source_path.is_file():
                # Single file: add with just the filename
                zip_file.write(source_path, arcname=source_path.name)
                logger.debug("Added file to zip: %s", source_path.name)
            elif source_path.is_dir():
                # Directory: add all files recursively
                for file_path in source_path.rglob("*"):
                    if file_path.is_file():
                        # Calculate relative path from source_path
                        arcname = file_path.relative_to(source_path)
                        zip_file.write(file_path, arcname=str(arcname))
                        logger.debug("Added to zip: %s", arcname)
            else:
                raise ArtifactInlineError(f"Source path is neither file nor directory: {source_path}")

    except Exception as e:
        raise ArtifactInlineError(f"Failed to create zip archive: {e}") from e

    return zip_buffer.getvalue()


def encode_artifact(artifact_bytes: bytes) -> str:
    """Encode artifact bytes as base64 string.

    Args:
        artifact_bytes: Raw bytes to encode

    Returns:
        Base64-encoded string
    """
    return base64.b64encode(artifact_bytes).decode("ascii")


def generate_extraction_shim(
    artifact_base64: str,
    output_path: str,
    format_type: str = "zip",
    source_display: str = "",
    size_display: str = "",
) -> list[str]:
    """Generate bash script lines to extract the artifact.

    Args:
        artifact_base64: Base64-encoded artifact data
        output_path: Where to extract at runtime
        format_type: Compression format (zip, tar.gz, etc.)
        source_display: Source path for display in comments
        size_display: Size string for display in comments

    Returns:
        List of script lines
    """
    # Determine extraction command based on format
    if format_type == "zip":
        extract_cmd = f'echo "$__B2G_ARTIFACT" | base64 -d | unzip -q -d {output_path} -'
    elif format_type == "tar.gz":
        extract_cmd = f'echo "$__B2G_ARTIFACT" | base64 -d | tar -xzf - -C {output_path} --no-same-owner'
    elif format_type == "tar.bz2":
        extract_cmd = f'echo "$__B2G_ARTIFACT" | base64 -d | tar -xjf - -C {output_path} --no-same-owner'
    elif format_type == "tar.xz":
        extract_cmd = f'echo "$__B2G_ARTIFACT" | base64 -d | tar -xJf - -C {output_path} --no-same-owner'
    else:
        extract_cmd = f'echo "$__B2G_ARTIFACT" | base64 -d | unzip -q -d {output_path} -'

    lines = [
        f"# >>> BEGIN inline-artifact: {source_display} ({format_type}, {size_display})",
        f"__B2G_ARTIFACT='{artifact_base64}'",
        f"mkdir -p {output_path}",
        extract_cmd,
        "unset __B2G_ARTIFACT",
        "# <<< END inline-artifact",
    ]

    return lines


def format_size(size_bytes: int) -> str:
    """Format byte size as human-readable string.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string like "1.2KB" or "847 bytes"
    """
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    return f"{size_bytes / (1024 * 1024):.1f}MB"


def maybe_inline_artifact(line: str, input_dir: Path) -> tuple[list[str], Path] | tuple[None, None]:
    """Check if line is an artifact pragma and inline it.

    Args:
        line: YAML script line to check
        input_dir: Base directory for resolving relative paths

    Returns:
        Tuple of (inlined_lines, source_path) if inlining succeeded,
        or (None, None) if this line should not be inlined
    """
    match = ARTIFACT_PRAGMA_REGEX.match(line)
    if not match:
        return None, None

    source_path_str = match.group("source_path")
    output_path = match.group("output_path")
    format_type = match.group("format") or "zip"

    # Resolve source path relative to input_dir
    source_path = input_dir / source_path_str
    source_path = source_path.resolve()

    # Security check: ensure source is within input_dir
    try:
        source_path.relative_to(input_dir.resolve())
    except ValueError:
        logger.error(
            "Security: Artifact source path '%s' is outside input directory '%s'",
            source_path,
            input_dir,
        )
        return None, None

    # Default output path is the source directory/file name
    if not output_path:
        output_path = f"./{source_path.name}"

    # Check if source exists
    if not source_path.exists():
        logger.warning(
            "Artifact source path does not exist: %s (pragma will be preserved as-is)",
            source_path,
        )
        return None, None

    try:
        # Create zip archive
        logger.info("Creating artifact from: %s", source_path)
        artifact_bytes = create_zip_artifact(source_path)

        # Check size limits
        compressed_size = len(artifact_bytes)
        max_size = get_max_artifact_size()
        warn_size = get_warn_artifact_size()

        if compressed_size > max_size:
            logger.error(
                "Artifact too large: %s (%s exceeds limit of %s)",
                source_path,
                format_size(compressed_size),
                format_size(max_size),
            )
            raise ArtifactInlineError(
                f"Artifact {source_path} is too large: {format_size(compressed_size)} "
                f"exceeds limit of {format_size(max_size)}"
            )

        if compressed_size > warn_size:
            logger.warning(
                "Large artifact: %s (%s)",
                source_path,
                format_size(compressed_size),
            )

        # Encode as base64
        artifact_base64 = encode_artifact(artifact_bytes)

        # Generate extraction shim
        size_display = format_size(compressed_size)
        inlined_lines = generate_extraction_shim(
            artifact_base64=artifact_base64,
            output_path=output_path,
            format_type=format_type,
            source_display=source_path_str,
            size_display=size_display,
        )

        logger.info(
            "Inlined artifact: %s -> %s (%s compressed)",
            source_path_str,
            output_path,
            size_display,
        )

        return inlined_lines, source_path

    except ArtifactInlineError as e:
        logger.error("Failed to inline artifact %s: %s", source_path, e)
        # Return None to preserve the original pragma line
        return None, None
    except Exception as e:
        logger.error("Unexpected error inlining artifact %s: %s", source_path, e)
        return None, None
