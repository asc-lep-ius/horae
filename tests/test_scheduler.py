"""Tests for the SyncScheduler background sync manager."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from horae.config import Settings
from horae.scheduler import SyncScheduler, SyncStatus
from horae.sync import SyncResult


@pytest.fixture
def sync_settings() -> Settings:
    return Settings(
        radicale_url="http://test:5232",
        radicale_username="test",
        radicale_password=SecretStr("test"),
        tiss_ical_url="https://tiss.example.com/feed.ics",
        sync_calendar="uni",
        sync_interval_minutes=60,
        sync_enabled=True,
    )


@pytest.fixture
def disabled_settings() -> Settings:
    return Settings(
        radicale_url="http://test:5232",
        radicale_username="test",
        radicale_password=SecretStr("test"),
        tiss_ical_url="https://tiss.example.com/feed.ics",
        sync_calendar="uni",
        sync_interval_minutes=60,
        sync_enabled=False,
    )


@pytest.fixture
def no_url_settings() -> Settings:
    return Settings(
        radicale_url="http://test:5232",
        radicale_username="test",
        radicale_password=SecretStr("test"),
        tiss_ical_url="",
        sync_calendar="uni",
        sync_interval_minutes=60,
        sync_enabled=True,
    )


class TestSyncSchedulerStart:
    def test_start_begins_scheduler_when_configured(self, sync_settings: Settings) -> None:
        scheduler = SyncScheduler(sync_settings)
        try:
            scheduler.start()
            assert scheduler._scheduler.running
        finally:
            scheduler.stop()

    def test_start_does_not_start_when_url_empty(self, no_url_settings: Settings) -> None:
        scheduler = SyncScheduler(no_url_settings)
        scheduler.start()
        assert not scheduler._scheduler.running

    def test_start_does_not_start_when_disabled(self, disabled_settings: Settings) -> None:
        scheduler = SyncScheduler(disabled_settings)
        scheduler.start()
        assert not scheduler._scheduler.running


class TestSyncSchedulerStop:
    def test_stop_shuts_down_gracefully(self, sync_settings: Settings) -> None:
        scheduler = SyncScheduler(sync_settings)
        scheduler.start()
        scheduler.stop()
        assert not scheduler._scheduler.running

    def test_stop_safe_when_not_running(self, sync_settings: Settings) -> None:
        scheduler = SyncScheduler(sync_settings)
        scheduler.stop()  # should not raise


class TestSyncSchedulerTrigger:
    @patch("horae.scheduler.sync_tiss")
    def test_trigger_calls_sync_in_background(
        self, mock_sync: MagicMock, sync_settings: Settings
    ) -> None:
        mock_sync.return_value = SyncResult(created=1)
        scheduler = SyncScheduler(sync_settings)

        with patch("threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            scheduler.trigger()

            mock_thread_cls.assert_called_once_with(target=scheduler._run_sync, daemon=True)
            mock_thread.start.assert_called_once()

    @patch("horae.scheduler.sync_tiss")
    def test_trigger_noop_when_already_running(
        self, mock_sync: MagicMock, sync_settings: Settings
    ) -> None:
        scheduler = SyncScheduler(sync_settings)
        scheduler._status.is_running = True

        with patch("threading.Thread") as mock_thread_cls:
            scheduler.trigger()
            mock_thread_cls.assert_not_called()


class TestRunSync:
    @patch("horae.scheduler.sync_tiss")
    def test_updates_last_run_and_result_on_success(
        self, mock_sync: MagicMock, sync_settings: Settings
    ) -> None:
        result = SyncResult(created=2, updated=1, unchanged=5, deleted=0)
        mock_sync.return_value = result
        scheduler = SyncScheduler(sync_settings)

        scheduler._run_sync()

        assert scheduler._status.last_result is result
        assert scheduler._status.last_run is not None
        assert scheduler._status.last_error is None
        assert scheduler._status.is_running is False

    @patch("horae.scheduler.sync_tiss")
    def test_sets_last_error_on_sync_errors(
        self, mock_sync: MagicMock, sync_settings: Settings
    ) -> None:
        result = SyncResult(created=1, errors=["bad event", "connection lost"])
        mock_sync.return_value = result
        scheduler = SyncScheduler(sync_settings)

        scheduler._run_sync()

        assert scheduler._status.last_result is result
        assert scheduler._status.last_error == "2 error(s) during sync"

    @patch("horae.scheduler.sync_tiss")
    def test_sets_last_error_and_clears_result_on_exception(
        self, mock_sync: MagicMock, sync_settings: Settings
    ) -> None:
        mock_sync.side_effect = RuntimeError("connection refused")
        scheduler = SyncScheduler(sync_settings)

        scheduler._run_sync()

        assert scheduler._status.last_result is None
        assert scheduler._status.last_error == "connection refused"
        assert scheduler._status.last_run is not None

    @patch("horae.scheduler.sync_tiss")
    def test_never_raises(self, mock_sync: MagicMock, sync_settings: Settings) -> None:
        mock_sync.side_effect = Exception("catastrophic failure")
        scheduler = SyncScheduler(sync_settings)

        scheduler._run_sync()  # should not raise

        assert scheduler._status.last_error == "catastrophic failure"

    @patch("horae.scheduler.sync_tiss")
    def test_is_running_true_during_execution(
        self, mock_sync: MagicMock, sync_settings: Settings
    ) -> None:
        observed_running: list[bool] = []

        def capture_running(settings: Settings) -> SyncResult:
            observed_running.append(scheduler._status.is_running)
            return SyncResult()

        mock_sync.side_effect = capture_running
        scheduler = SyncScheduler(sync_settings)

        scheduler._run_sync()

        assert observed_running == [True]
        assert scheduler._status.is_running is False

    @patch("horae.scheduler.sync_tiss")
    def test_is_running_false_after_exception(
        self, mock_sync: MagicMock, sync_settings: Settings
    ) -> None:
        mock_sync.side_effect = RuntimeError("boom")
        scheduler = SyncScheduler(sync_settings)

        scheduler._run_sync()

        assert scheduler._status.is_running is False

    @patch("horae.scheduler.sync_tiss")
    def test_skips_when_already_running(
        self, mock_sync: MagicMock, sync_settings: Settings
    ) -> None:
        scheduler = SyncScheduler(sync_settings)
        scheduler._status.is_running = True

        scheduler._run_sync()

        mock_sync.assert_not_called()


class TestSyncStatus:
    def test_status_returns_sync_status(self, sync_settings: Settings) -> None:
        scheduler = SyncScheduler(sync_settings)
        status = scheduler.status
        assert isinstance(status, SyncStatus)

    def test_status_next_run_populated_after_start(self, sync_settings: Settings) -> None:
        scheduler = SyncScheduler(sync_settings)
        try:
            scheduler.start()
            status = scheduler.status
            assert status.next_run is not None
        finally:
            scheduler.stop()

    def test_status_next_run_none_when_not_started(self, sync_settings: Settings) -> None:
        scheduler = SyncScheduler(sync_settings)
        status = scheduler.status
        assert status.next_run is None

    @patch("horae.scheduler.sync_tiss")
    def test_status_reflects_last_result(
        self, mock_sync: MagicMock, sync_settings: Settings
    ) -> None:
        result = SyncResult(created=3, updated=2)
        mock_sync.return_value = result
        scheduler = SyncScheduler(sync_settings)

        scheduler._run_sync()
        status = scheduler.status

        assert status.last_result is result
        assert status.last_run is not None


class TestSyncStatusDataclass:
    def test_defaults(self) -> None:
        status = SyncStatus()
        assert status.last_run is None
        assert status.last_result is None
        assert status.last_error is None
        assert status.next_run is None
        assert status.is_running is False
