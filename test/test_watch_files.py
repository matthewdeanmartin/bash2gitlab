from __future__ import annotations

import types

from bash2gitlab.watch_files import _RecompileHandler, start_watch


class _Evt:
    """Tiny stand-in for watchdog FileSystemEvent."""

    def __init__(self, src_path: str, is_directory: bool = False):
        self.src_path = src_path
        self.is_directory = is_directory


def test_handler_ignores_dirs_and_irrelevant_extensions(tmp_path, monkeypatch, caplog):
    called = {"count": 0}

    def fake_compile(**kwargs):
        called["count"] += 1

    monkeypatch.setattr("bash2gitlab.watch_files.run_compile_all", fake_compile)

    handler = _RecompileHandler(
        uncompiled_path=tmp_path,
        output_path=tmp_path / "out",
        dry_run=False,
        parallelism=None,
    )
    handler._debounce = 0.0  # avoid timing flake

    caplog.set_level("INFO")

    # Directory -> ignored
    handler.on_any_event(_Evt(str(tmp_path), is_directory=True))

    # Temp files -> ignored
    handler.on_any_event(_Evt(str(tmp_path / "foo.yml.swp")))
    handler.on_any_event(_Evt(str(tmp_path / "bar.tmp")))
    handler.on_any_event(_Evt(str(tmp_path / "baz~")))

    # Irrelevant extension -> ignored
    handler.on_any_event(_Evt(str(tmp_path / "note.txt")))

    assert called["count"] == 0
    # No "recompiling" log produced
    assert not any("recompiling" in m.message.lower() for m in caplog.records)


def test_handler_triggers_on_yaml_and_sh(tmp_path, monkeypatch, caplog):
    recorded = {"kwargs": None}

    def fake_compile(**kwargs):
        recorded["kwargs"] = kwargs

    monkeypatch.setattr("bash2gitlab.watch_files.run_compile_all", fake_compile)

    handler = _RecompileHandler(
        uncompiled_path=tmp_path,
        output_path=tmp_path / "out",
        dry_run=True,
        parallelism=4,
    )
    handler._debounce = 0.0  # fire immediately

    caplog.set_level("INFO")

    # Should trigger for .yml
    handler.on_any_event(_Evt(str(tmp_path / "pipeline.yml")))
    assert recorded["kwargs"] is not None
    assert recorded["kwargs"]["uncompiled_path"] == tmp_path
    assert recorded["kwargs"]["output_path"] == tmp_path / "out"
    assert recorded["kwargs"]["dry_run"] is True
    assert recorded["kwargs"]["parallelism"] == 4
    assert any("recompiling" in m.message.lower() for m in caplog.records)
    assert any("recompiled successfully" in m.message.lower() for m in caplog.records)

    # Reset and trigger for .sh
    recorded["kwargs"] = None
    handler.on_any_event(_Evt(str(tmp_path / "script.sh")))
    assert recorded["kwargs"] is not None


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
        uncompiled_path=tmp_path,
        output_path=tmp_path / "out",
        dry_run=False,
        parallelism=None,
    )
    # keep default debounce 0.5s

    handler.on_any_event(_Evt(str(tmp_path / "a.yaml")))  # fires
    handler.on_any_event(_Evt(str(tmp_path / "b.yaml")))  # within 0.5s -> skipped
    handler.on_any_event(_Evt(str(tmp_path / "c.yaml")))  # after 0.5s -> fires

    assert calls["n"] == 2


def test_handler_logs_error_on_exception(tmp_path, monkeypatch, caplog):
    def boom(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("bash2gitlab.watch_files.run_compile_all", boom)

    handler = _RecompileHandler(
        uncompiled_path=tmp_path,
        output_path=tmp_path / "out",
        dry_run=False,
        parallelism=None,
    )
    handler._debounce = 0.0

    caplog.set_level("ERROR")
    handler.on_any_event(_Evt(str(tmp_path / "bad.yml")))
    assert any("recompilation failed" in m.message.lower() for m in caplog.records)


def test_start_watch_wires_observer_and_stops_on_keyboardinterrupt(tmp_path, monkeypatch, caplog):
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

    caplog.set_level("INFO")

    # Patch run_compile_all so it's not accidentally called here
    monkeypatch.setattr("bash2gitlab.watch_files.run_compile_all", lambda **_: None)

    # Call start_watch: it should start, then promptly stop due to KeyboardInterrupt
    start_watch(
        uncompiled_path=tmp_path,
        output_path=tmp_path / "compiled",
        dry_run=False,
        parallelism=None,
    )

    # Assertions about observer wiring & shutdown
    assert started["value"] is True
    assert stopped["value"] is True
    assert joined["value"] is True
    # Scheduled on the provided uncompiled_path, recursive=True
    assert scheduled["args"] is not None
    assert scheduled["args"][1] == str(tmp_path)
    assert scheduled["recursive"] is True
    # Saw "Stopping watcher." in logs
    assert any("stopping watcher" in m.message.lower() for m in caplog.records)
