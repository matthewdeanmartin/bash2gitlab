from __future__ import annotations

import re
from pathlib import Path

import pytest

from bash2gitlab.commands import doctor as doctor_mod
from bash2gitlab.config import _Config as ConfigClass

# --------- helpers -----------------------------------------------------------


def _set_doctor_config(monkeypatch: pytest.MonkeyPatch, *, input_dir: Path | None, output_dir: Path | None) -> None:
    """
    Configure the doctor module to use a fresh _Config instance that reads values
    from environment variables. We only set env vars that are provided.
    """
    if input_dir is not None:
        monkeypatch.setenv("BASH2GITLAB_INPUT_DIR", str(input_dir))
    else:
        monkeypatch.delenv("BASH2GITLAB_INPUT_DIR", raising=False)

    if output_dir is not None:
        monkeypatch.setenv("BASH2GITLAB_OUTPUT_DIR", str(output_dir))
    else:
        monkeypatch.delenv("BASH2GITLAB_OUTPUT_DIR", raising=False)

    cfg = ConfigClass()
    monkeypatch.setattr(doctor_mod, "config", cfg, raising=False)


def _patch_yaml_loader_to_truthy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make doctor.get_yaml().load(...) return a truthy object without requiring ruamel."""

    class _DummyLoader:
        def load(self, _content: str):
            # any truthy object is fine; doctor never inspects the parsed structure
            return {"ok": True}

    monkeypatch.setattr(doctor_mod, "get_yaml", lambda: _DummyLoader(), raising=False)


def _patch_graph_reference_scanner(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Replace find_script_references_in_node with a light-weight implementation that:
    - Reads the yaml file text itself (yaml_path)
    - Finds any *.sh or *.py tokens (relative or ./nested)
    - Adds resolved paths into processed_scripts (the name the doctor module passes in)
    This approximates your graph logic without mocking the whole module.
    """

    def _stub(_yaml_data, yaml_path: Path, root_path: Path, _graph: dict, *, processed_scripts: set[Path]):
        text = yaml_path.read_text(encoding="utf-8")
        # Grab script-like tokens; tolerate leading './' or nested dirs
        for m in re.findall(r"(?P<p>(?:\.?/)?[\w./-]+\.(?:sh|py))", text):
            p = (yaml_path.parent / m).resolve()
            # only count files under root_path to mirror expected behavior
            try:
                p.relative_to(root_path.resolve())
            except Exception:
                continue
            processed_scripts.add(p)

    monkeypatch.setattr(doctor_mod, "find_script_references_in_node", _stub, raising=False)


def _write(p: Path, content: str = "") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# --------- unit tests --------------------------------------------------------


def test_check_prints_and_returns(capsys: pytest.CaptureFixture[str]):
    assert doctor_mod.check("something good", True) is True
    assert doctor_mod.check("something bad", False) is False
    out = capsys.readouterr().out
    assert "OK" in out
    assert "FAILED" in out
    assert "something good" in out and "something bad" in out


def test_get_command_version_not_found(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda _: None)
    res = doctor_mod.get_command_version("definitely-not-a-real-cmd-xyz")
    assert "not found" in res  # colored text is fine; we check the phrase


def test_get_command_version_error(monkeypatch: pytest.MonkeyPatch):
    # Pretend the command exists but running it fails (e.g., non-zero exit)
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda _: "/bin/fake")

    class _Boom(Exception):
        pass

    def _run(*_args, **_kwargs):
        raise doctor_mod.subprocess.CalledProcessError(2, ["fake", "--version"])

    monkeypatch.setattr(doctor_mod.subprocess, "run", _run)
    res = doctor_mod.get_command_version("fake")
    assert "Error checking version" in res


def test_run_doctor_missing_config(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    # No env, no file: both "configured" checks should fail
    _set_doctor_config(monkeypatch, input_dir=None, output_dir=None)
    _patch_yaml_loader_to_truthy(monkeypatch)
    # versions harmless and fast
    monkeypatch.setattr(doctor_mod, "get_command_version", lambda cmd: f"{cmd} v1.0", raising=False)

    rc = doctor_mod.run_doctor()
    out = capsys.readouterr().out
    assert rc == 1
    assert "Input directory is configured" in out and "FAILED" in out
    assert "Output directory is configured" in out and "FAILED" in out
