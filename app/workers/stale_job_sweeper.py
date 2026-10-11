"""A background thread that fails jobs which never finished.

It calls ``FileService.fail_stale_jobs`` every ``interval_seconds``. It lives
in ``workers/`` because it is a background mechanism; the rule for what counts
as stale stays in the service. A sweep that raises is logged and the loop
carries on, so one bad sweep never stops future ones.
"""

from __future__ import annotations

import logging
import threading

from app.services.file_service import FileService

logger = logging.getLogger(__name__)


class StaleJobSweeper:
    def __init__(
        self,
        service: FileService,
        *,
        max_age_seconds: float,
        interval_seconds: float,
    ) -> None:
        if max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be greater than 0")
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than 0")
        self._service = service
        self._max_age_seconds = max_age_seconds
        self._interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def run_once(self) -> int:
        """Do one sweep now. Returns how many jobs were failed."""
        return self._service.fail_stale_jobs(max_age_seconds=self._max_age_seconds)

    def start(self) -> None:
        """Start the background thread. Does nothing if it is already running."""
        with self._lock:
            if self.is_running:
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._loop, name="stale-job-sweeper", daemon=True
            )
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Ask the thread to stop and wait for it. Safe to call twice."""
        with self._lock:
            thread = self._thread
            self._stop_event.set()
        if thread is not None:
            thread.join(timeout)

    def _loop(self) -> None:
        # wait() returns True when stop() was called, so the loop ends at once
        # instead of sleeping out the whole interval.
        while not self._stop_event.wait(self._interval_seconds):
            try:
                failed = self.run_once()
                if failed:
                    logger.info("stale_sweep_finished", extra={"failed": failed})
            except Exception:  # noqa: BLE001 - a bad sweep must not end the loop
                logger.exception("stale_sweep_error")