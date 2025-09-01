# toml_reader.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping  # noqa

# --- Backend choice (simple & up-front) --------------------------------------

BACKEND: str
LOADER: ModuleType | None

try:
    import rtoml as LOADER  # type: ignore

    BACKEND = "rtoml"
except Exception:
    try:
        import tomllib as LOADER  # type: ignore[attr-defined]

        BACKEND = "tomllib"
    except Exception:
        try:
            import tomli as LOADER  # type: ignore

            BACKEND = "tomli"
        except Exception:
            LOADER = None
            BACKEND = "unavailable"


# --- Unified error ------------------------------------------------------------


class TomlError(ValueError):
    """Unified TOML decode error raised by this wrapper."""


def raise_toml_error(err: Exception, *, source: str) -> TomlError:
    return TomlError(f"TOML parse error ({source}): {err}")


# --- Loading helpers ----------------------------------------------------------


def load_from_path(path: Path) -> Mapping[str, Any]:
    """
    Load a TOML file from disk using the selected backend and return the native mapping.

    rtoml uses text I/O; tomllib/tomli use binary I/O.
    """
    if LOADER is None:
        raise RuntimeError(
            "No TOML backend available. Install 'rtoml' (preferred), "
            "'tomli' on Python < 3.11, or use Python 3.11+ for 'tomllib'."
        )

    try:
        if BACKEND == "rtoml":
            with path.open("r", encoding="utf-8") as f:
                return LOADER.load(f)  # type: ignore[call-arg]
        else:
            with path.open("rb") as f:
                return LOADER.load(f)  # type: ignore[call-arg]
    except FileNotFoundError:
        raise
    except Exception as e:
        raise raise_toml_error(e, source=str(path)) from e


def loads_from_string(s: str) -> Mapping[str, Any]:
    """
    Parse TOML from a string using the selected backend and return the native mapping.
    """
    if LOADER is None:
        raise RuntimeError(
            "No TOML backend available. Install 'rtoml' (preferred), "
            "'tomli' on Python < 3.11, or use Python 3.11+ for 'tomllib'."
        )

    try:
        if BACKEND == "rtoml":
            return LOADER.loads(s)  # type: ignore[attr-defined]
        elif BACKEND == "tomllib":
            return LOADER.loads(s.encode("utf-8"))  # type: ignore[attr-defined]
        else:  # tomli
            return LOADER.loads(s)  # type: ignore[attr-defined]
    except Exception as e:
        raise raise_toml_error(e, source="<string>") from e


# --- Public API (read-only interface: only readers) ---------------------------


@dataclass(frozen=True)
class TomlReader:
    """
    Reader-only TOML interface that normalizes rtoml/tomllib/tomli behavior.

    Attributes:
        backend: 'rtoml', 'tomllib', 'tomli', or 'unavailable'
    """

    backend: str = BACKEND

    def load(self, path: str | Path) -> Mapping[str, Any]:
        """Load TOML from a file path and return the backend's native mapping."""
        return load_from_path(Path(path))

    def loads(self, content: str) -> Mapping[str, Any]:
        """Parse TOML from a string and return the backend's native mapping."""
        return loads_from_string(content)


# Convenience top-level functions

_reader = TomlReader()


def read_toml(path: str | Path) -> Mapping[str, Any]:
    """Load TOML from a file path; returns the backend's native mapping."""
    return _reader.load(path)


def parse_toml(content: str) -> Mapping[str, Any]:
    """Parse TOML from a string; returns the backend's native mapping."""
    return _reader.loads(content)


def toml_backend() -> str:
    """Return the backend in use: 'rtoml', 'tomllib', 'tomli', or 'unavailable'."""
    return _reader.backend
