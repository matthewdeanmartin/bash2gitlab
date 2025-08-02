"""
Watch mode for bash2gitlab.

Usage (internal):
    from pathlib import Path
    from bash2gitlab.watch import start_watch

    start_watch(
        uncompiled_path=Path("./ci"),
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

from bash2gitlab.compile_all import process_uncompiled_directory

logger = logging.getLogger(__name__)


class _RecompileHandler(FileSystemEventHandler):
    """
    Fire the compiler every time a *.yml, *.yaml or *.sh file changes.
    """

    def __init__(
        self,
        *,
        uncompiled_path: Path,
        output_path: Path,
        scripts_path: Path,
        templates_dir: Path,
        output_templates_dir: Path,
        dry_run: bool = False,
        parallelism: int | None = None,
    ) -> None:
        super().__init__()
        self._paths = {
            "uncompiled_path": uncompiled_path,
            "output_path": output_path,
            "scripts_path": scripts_path,
            "templates_dir": templates_dir,
            "output_templates_dir": output_templates_dir,
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
        if not event.src_path.endswith((".yml", ".yaml", ".sh")):  # type: ignore[arg-type]
            return

        now = time.monotonic()
        if now - self._last_run < self._debounce:
            return
        self._last_run = now

        logger.info("🔄 Source changed; recompiling…")
        try:
            process_uncompiled_directory(**self._paths, **self._flags)  # type: ignore[arg-type]
            logger.info("✅ Recompiled successfully.")
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("❌ Recompilation failed: %s", exc, exc_info=True)


def start_watch(
    *,
    uncompiled_path: Path,
    output_path: Path,
    scripts_path: Path,
    templates_dir: Path,
    output_templates_dir: Path,
    dry_run: bool = False,
    parallelism: int | None = None,
) -> None:
    """
    Start an in-process watchdog that recompiles whenever source files change.

    Blocks forever (Ctrl-C to stop).
    """
    handler = _RecompileHandler(
        uncompiled_path=uncompiled_path,
        output_path=output_path,
        scripts_path=scripts_path,
        templates_dir=templates_dir,
        output_templates_dir=output_templates_dir,
        dry_run=dry_run,
        parallelism=parallelism,
    )

    observer = Observer()
    observer.schedule(handler, str(uncompiled_path), recursive=True)
    if templates_dir != uncompiled_path:
        observer.schedule(handler, str(templates_dir), recursive=True)
    if scripts_path not in (uncompiled_path, templates_dir):
        observer.schedule(handler, str(scripts_path), recursive=True)

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
