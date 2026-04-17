"""Background sync scheduler for TISS calendar sync."""

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from horae.config import Settings
from horae.sync import SyncResult, sync_tiss

log = logging.getLogger(__name__)


@dataclass
class SyncStatus:
    last_run: datetime | None = None
    last_result: SyncResult | None = None
    last_error: str | None = None
    next_run: datetime | None = None
    is_running: bool = False


class SyncScheduler:
    """Manages periodic TISS sync as a background job."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._scheduler = BackgroundScheduler()
        self._status = SyncStatus()
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the scheduler with configured interval."""
        if not self._settings.tiss_ical_url:
            log.warning("TISS sync disabled — HORAE_TISS_ICAL_URL not configured")
            return
        if not self._settings.sync_enabled:
            log.info("TISS sync disabled via HORAE_SYNC_ENABLED=false")
            return

        first_run = datetime.now(UTC) + timedelta(minutes=self._settings.sync_interval_minutes)
        self._scheduler.add_job(
            self._run_sync,
            "interval",
            minutes=self._settings.sync_interval_minutes,
            id="tiss_sync",
            next_run_time=first_run,
        )
        self._scheduler.start()
        self._refresh_next_run()
        log.info("Sync scheduler started (interval: %d min)", self._settings.sync_interval_minutes)

    def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            log.info("Sync scheduler stopped")

    def trigger(self) -> None:
        """Trigger an immediate sync in a background thread."""
        if self._status.is_running:
            log.warning("Sync already in progress, skipping trigger")
            return
        thread = threading.Thread(target=self._run_sync, daemon=True)
        thread.start()

    @property
    def status(self) -> SyncStatus:
        self._refresh_next_run()
        return self._status

    def _refresh_next_run(self) -> None:
        if self._scheduler.running:
            job = self._scheduler.get_job("tiss_sync")
            if job:
                self._status.next_run = job.next_run_time

    def _run_sync(self) -> None:
        """Execute sync with error handling. Never raises."""
        with self._lock:
            if self._status.is_running:
                log.warning("Sync already in progress, skipping")
                return
            self._status.is_running = True

        try:
            log.info("Starting scheduled TISS sync")
            result = sync_tiss(self._settings)
            self._status.last_result = result
            self._status.last_error = None
            if result.errors:
                self._status.last_error = f"{len(result.errors)} error(s) during sync"
        except Exception as exc:
            log.exception("Scheduled sync failed: %s", exc)
            self._status.last_error = str(exc)
            self._status.last_result = None
        finally:
            self._status.last_run = datetime.now(UTC)
            self._status.is_running = False
