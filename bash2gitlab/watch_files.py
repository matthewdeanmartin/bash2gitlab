"""
Watch mode for bash2gitlab.

Usage (internal):
    from pathlib import Path
    from bash2gitlab.watch import start_watch

    start_watch(
        input_dir=Path("./ci"),
        output_path=Path("./compiled"),
        scripts_path=Path("./ci"),
        templates_dir=Path("./ci/templates"),
        output_templates_dir=Path("./compiled/templates"),
        dry_run=False,
    )
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from bash2gitlab.commands.compile_all import run_compile_all
from bash2gitlab.plugins import get_pm

logger = logging.getLogger(__name__)


class _RecompileHandler(FileSystemEventHandler):
    """
    Fire the compiler every time a *.yml, *.yaml or *.sh file changes.
    """

    def __init__(
        self,
        *,
        input_dir: Path,
        output_path: Path,
        dry_run: bool = False,
        parallelism: int | None = None,
    ) -> None:
        super().__init__()
        self._paths = {
            "input_dir": input_dir,
            "output_path": output_path,
        }
        self._flags = {"dry_run": dry_run, "parallelism": parallelism}
        self._debounce: float = 0.5  # seconds
        self._last_run = 0.0

    def on_any_event(self, event: FileSystemEvent) -> None:
        # Skip directories, temp files, and non-relevant extensions
        if event.is_directory:
            return
        if event.src_path.endswith((".tmp", ".swp", "~")):  # type: ignore[arg-type]
            return
        exts = {".yml", ".yaml", ".sh", ".bash"}
        for extra in get_pm().hook.watch_file_extensions():
            if extra:
                exts.update(extra)
        if not event.src_path.endswith(tuple(exts)):  # type: ignore[arg-type]
            return

        now = time.monotonic()
        if now - self._last_run < self._debounce:
            return
        self._last_run = now

        logger.info("🔄 Source changed; recompiling…")
        try:
            run_compile_all(**self._paths, **self._flags)  # type: ignore[arg-type]
            logger.info("✅ Recompiled successfully.")
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("❌ Recompilation failed: %s", exc, exc_info=True)


def start_watch(
    *,
    input_dir: Path,
    output_path: Path,
    dry_run: bool = False,
    parallelism: int | None = None,
) -> None:
    """
    Start an in-process watchdog that recompiles whenever source files change.

    Blocks forever (Ctrl-C to stop).
    """
    handler = _RecompileHandler(
        input_dir=input_dir,
        output_path=output_path,
        dry_run=dry_run,
        parallelism=parallelism,
    )

    observer = Observer()
    observer.schedule(handler, str(input_dir), recursive=True)

    try:
        observer.start()
        logger.info("👀 Watching for changes to *.yml, *.yaml, *.sh … (Ctrl-C to quit)")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("⏹  Stopping watcher.")
    finally:
        observer.stop()
        observer.join()
