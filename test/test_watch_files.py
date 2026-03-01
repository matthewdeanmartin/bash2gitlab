from __future__ import annotations

import types

from bash2gitlab.watch_files import _RecompileHandler, start_watch


class _Evt:
    """Tiny stand-in for watchdog FileSystemEvent."""

    def __init__(self, src_path: str, is_directory: bool = False):
        self.src_path = src_path
        self.is_directory = is_directory


def test_handler_ignores_dirs_and_irrelevant_extensions(tmp_path, monkeypatch):
    called = {"count": 0}

    def fake_compile(**kwargs):
        called["count"] += 1

    monkeypatch.setattr("bash2gitlab.watch_files.run_compile_all", fake_compile)

    handler = _RecompileHandler(
        input_dir=tmp_path,
        output_path=tmp_path / "out",
        dry_run=False,
        parallelism=None,
    )
    handler._debounce = 0.0  # avoid timing flake

    # Directory -> ignored
    handler.on_any_event(_Evt(str(tmp_path), is_directory=True))

    # Temp files -> ignored
    handler.on_any_event(_Evt(str(tmp_path / "foo.yml.swp")))
    handler.on_any_event(_Evt(str(tmp_path / "bar.tmp")))
    handler.on_any_event(_Evt(str(tmp_path / "baz~")))

    # Irrelevant extension -> ignored
    handler.on_any_event(_Evt(str(tmp_path / "note.txt")))

    # Behavior: no compile should have been triggered
    assert called["count"] == 0


def test_handler_triggers_on_yaml_and_sh(tmp_path, monkeypatch):
    recorded = {"kwargs": None, "call_count": 0}

    def fake_compile(**kwargs):
        recorded["kwargs"] = kwargs
        recorded["call_count"] += 1

    monkeypatch.setattr("bash2gitlab.watch_files.run_compile_all", fake_compile)

    handler = _RecompileHandler(
        input_dir=tmp_path,
        output_path=tmp_path / "out",
        dry_run=True,
        parallelism=4,
    )
    handler._debounce = 0.0  # fire immediately

    # Behavior: should trigger compile for .yml with correct parameters
    handler.on_any_event(_Evt(str(tmp_path / "pipeline.yml")))
    assert recorded["call_count"] == 1
    assert recorded["kwargs"]["input_dir"] == tmp_path
    assert recorded["kwargs"]["output_path"] == tmp_path / "out"
    assert recorded["kwargs"]["dry_run"] is True
    assert recorded["kwargs"]["parallelism"] == 4

    # Behavior: should trigger compile for .sh files too
    handler.on_any_event(_Evt(str(tmp_path / "script.sh")))
    assert recorded["call_count"] == 2


def test_handler_debounce(monkeypatch, tmp_path):
    calls = {"n": 0}

    def fake_compile(**kwargs):
        calls["n"] += 1

    # Control time.monotonic so we can test the debounce window deterministically
    times = [100.0, 100.3, 101.0]  # first call at 100, second inside 0.5s, third outside

    def fake_monotonic():
        return times.pop(0)

    monkeypatch.setattr("bash2gitlab.watch_files.run_compile_all", fake_compile)
    monkeypatch.setattr("bash2gitlab.watch_files.time", types.SimpleNamespace(monotonic=fake_monotonic))

    handler = _RecompileHandler(
        input_dir=tmp_path,
        output_path=tmp_path / "out",
        dry_run=False,
        parallelism=None,
    )
    # keep default debounce 0.5s

    handler.on_any_event(_Evt(str(tmp_path / "a.yaml")))  # fires
    handler.on_any_event(_Evt(str(tmp_path / "b.yaml")))  # within 0.5s -> skipped
    handler.on_any_event(_Evt(str(tmp_path / "c.yaml")))  # after 0.5s -> fires

    assert calls["n"] == 2


def test_handler_handles_exception_gracefully(tmp_path, monkeypatch):
    exception_raised = {"value": False}

    def boom(**kwargs):
        exception_raised["value"] = True
        raise RuntimeError("boom")

    monkeypatch.setattr("bash2gitlab.watch_files.run_compile_all", boom)

    handler = _RecompileHandler(
        input_dir=tmp_path,
        output_path=tmp_path / "out",
        dry_run=False,
        parallelism=None,
    )
    handler._debounce = 0.0

    # Behavior: handler should catch and handle exceptions without crashing
    handler.on_any_event(_Evt(str(tmp_path / "bad.yml")))
    assert exception_raised["value"] is True


def test_start_watch_wires_observer_and_stops_on_keyboardinterrupt(tmp_path, monkeypatch):
    scheduled = {"args": None, "recursive": None}
    started = {"value": False}
    stopped = {"value": False}
    joined = {"value": False}

    class FakeObserver:
        def schedule(self, handler, path, recursive: bool):
            scheduled["args"] = (handler, path)
            scheduled["recursive"] = recursive

        def start(self):
            started["value"] = True

        def stop(self):
            stopped["value"] = True

        def join(self):
            joined["value"] = True

    # Patch Observer used by start_watch
    monkeypatch.setattr("bash2gitlab.watch_files.Observer", FakeObserver)

    # Make the main loop raise KeyboardInterrupt immediately after start
    sleep_calls = {"n": 0}

    def fake_sleep(_):
        sleep_calls["n"] += 1
        raise KeyboardInterrupt

    monkeypatch.setattr("bash2gitlab.watch_files.time", types.SimpleNamespace(sleep=fake_sleep))

    # Patch run_compile_all so it's not accidentally called here
    monkeypatch.setattr("bash2gitlab.watch_files.run_compile_all", lambda **_: None)

    # Call start_watch: it should start, then promptly stop due to KeyboardInterrupt
    start_watch(
        input_dir=tmp_path,
        output_path=tmp_path / "compiled",
        dry_run=False,
        parallelism=None,
    )

    # Behavior: observer lifecycle should be correct
    assert started["value"] is True
    assert stopped["value"] is True
    assert joined["value"] is True
    # Behavior: scheduled on the provided input_dir, recursive=True
    assert scheduled["args"] is not None
    assert scheduled["args"][1] == str(tmp_path)
    assert scheduled["recursive"] is True
