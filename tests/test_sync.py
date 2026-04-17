"""Tests for horae.sync — TISS iCal feed sync to Radicale via CalDAV."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import icalendar
import pytest
from filelock import Timeout
from pydantic import SecretStr

from horae.config import Settings
from horae.sync import (
    SyncResult,
    _build_vcalendar,
    _content_changed,
    _dt_to_str,
    _event_tzids,
    _extract_timezones,
    _parse_feed,
    _stable_uid,
    main,
    sync_tiss,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feed(*events: tuple[str, str, str]) -> bytes:
    """Build a minimal iCal feed from (summary, dtstart, dtend) tuples."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TISS//Test//EN"]
    for i, (summary, start, end) in enumerate(events):
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:tiss-unstable-{i}@tiss.tuwien.ac.at",
            f"SUMMARY:{summary}",
            f"DTSTART:{start}",
            f"DTEND:{end}",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines).encode()


def _make_tz_feed(tzid: str, event_summary: str, dtstart: str, dtend: str) -> bytes:
    """Build an iCal feed with a VTIMEZONE and timezone-aware event."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//TISS//Test//EN",
        "BEGIN:VTIMEZONE",
        f"TZID:{tzid}",
        "BEGIN:STANDARD",
        "DTSTART:19701025T030000",
        "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU",
        "TZOFFSETFROM:+0200",
        "TZOFFSETTO:+0100",
        "TZNAME:CET",
        "END:STANDARD",
        "BEGIN:DAYLIGHT",
        "DTSTART:19700329T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU",
        "TZOFFSETFROM:+0100",
        "TZOFFSETTO:+0200",
        "TZNAME:CEST",
        "END:DAYLIGHT",
        "END:VTIMEZONE",
        "BEGIN:VEVENT",
        "UID:tiss-tz-0@tiss.tuwien.ac.at",
        f"SUMMARY:{event_summary}",
        f"DTSTART;TZID={tzid}:{dtstart}",
        f"DTEND;TZID={tzid}:{dtend}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines).encode()


def _sync_settings() -> Settings:
    return Settings(
        radicale_url="http://test-radicale:5232",
        radicale_username="testuser",
        radicale_password=SecretStr("testpass"),
        tiss_ical_url="https://tiss.example.com/feed.ics",
        sync_calendar="uni",
        default_calendar="personal",
        default_duration_minutes=60,
        ollama_url="http://test-ollama:11434",
        ollama_model="test-model",
    )


def _make_vevent(summary: str = "Lecture", dtstart: str = "20260401T100000",
                 dtend: str = "20260401T120000", location: str = "",
                 description: str = "") -> icalendar.Event:
    """Build an icalendar VEVENT component."""
    ev = icalendar.Event()
    ev.add("UID", _stable_uid(summary, dtstart, dtend))
    ev.add("SUMMARY", summary)
    ev.add("DTSTART", datetime(2026, 4, 1, 10, 0))
    ev.add("DTEND", datetime(2026, 4, 1, 12, 0))
    if location:
        ev.add("LOCATION", location)
    if description:
        ev.add("DESCRIPTION", description)
    return ev


# ---------------------------------------------------------------------------
# Unit tests — pure functions
# ---------------------------------------------------------------------------


class TestStableUid:
    def test_deterministic(self) -> None:
        uid1 = _stable_uid("Lecture", "20260401T100000", "20260401T120000")
        uid2 = _stable_uid("Lecture", "20260401T100000", "20260401T120000")
        assert uid1 == uid2

    def test_has_horae_prefix(self) -> None:
        uid = _stable_uid("Lecture", "20260401T100000", "20260401T120000")
        assert uid.startswith("horae-")

    def test_different_inputs_produce_different_uids(self) -> None:
        uid_a = _stable_uid("Lecture A", "20260401T100000", "20260401T120000")
        uid_b = _stable_uid("Lecture B", "20260401T100000", "20260401T120000")
        assert uid_a != uid_b

    @pytest.mark.parametrize("summary,dtstart,dtend", [
        ("", "", ""),
        ("X", "20260101T000000", "20260101T010000"),
        ("Long " * 50, "20260601T080000", "20260601T180000"),
    ])
    def test_always_returns_valid_uid(self, summary: str, dtstart: str, dtend: str) -> None:
        uid = _stable_uid(summary, dtstart, dtend)
        assert uid.startswith("horae-")
        assert len(uid) == len("horae-") + 16  # sha256[:16] hex


class TestDtToStr:
    def test_plain_datetime(self) -> None:
        dt = datetime(2026, 4, 1, 10, 0)
        assert _dt_to_str(dt) == "2026-04-01 10:00:00"

    def test_plain_date(self) -> None:
        d = date(2026, 4, 1)
        assert _dt_to_str(d) == "2026-04-01"

    def test_icalendar_vdate(self) -> None:
        vdt = icalendar.vDatetime(datetime(2026, 4, 1, 10, 0))
        assert "2026" in _dt_to_str(vdt)

    def test_icalendar_vdate_date(self) -> None:
        vd = icalendar.vDate(date(2026, 4, 1))
        result = _dt_to_str(vd)
        assert "2026" in result


class TestExtractTimezones:
    def test_extracts_vtimezone(self) -> None:
        feed = _make_tz_feed("Europe/Vienna", "Lecture", "20260401T100000", "20260401T120000")
        cal = icalendar.Calendar.from_ical(feed)
        tzmap = _extract_timezones(cal)
        assert "Europe/Vienna" in tzmap

    def test_empty_calendar_returns_empty(self) -> None:
        cal = icalendar.Calendar()
        assert _extract_timezones(cal) == {}


class TestEventTzids:
    def test_collects_tzid_from_dt_properties(self) -> None:
        feed = _make_tz_feed("Europe/Vienna", "Lecture", "20260401T100000", "20260401T120000")
        cal = icalendar.Calendar.from_ical(feed)
        vevents = list(cal.walk("VEVENT"))
        assert len(vevents) == 1
        tzids = _event_tzids(vevents[0])
        assert "Europe/Vienna" in tzids

    def test_no_tzid_returns_empty(self) -> None:
        ev = icalendar.Event()
        ev.add("DTSTART", datetime(2026, 4, 1, 10, 0))
        ev.add("DTEND", datetime(2026, 4, 1, 12, 0))
        assert _event_tzids(ev) == set()


class TestBuildVcalendar:
    def test_wraps_vevent_in_vcalendar(self) -> None:
        ev = icalendar.Event()
        ev.add("UID", "horae-abc123")
        ev.add("SUMMARY", "Lecture")
        ev.add("DTSTART", datetime(2026, 4, 1, 10, 0))
        result = _build_vcalendar(ev, {})
        text = result.decode()
        assert "BEGIN:VCALENDAR" in text
        assert "BEGIN:VEVENT" in text
        assert "horae-abc123" in text

    def test_includes_needed_timezone(self) -> None:
        feed = _make_tz_feed("Europe/Vienna", "Lecture", "20260401T100000", "20260401T120000")
        cal = icalendar.Calendar.from_ical(feed)
        tzmap = _extract_timezones(cal)
        vevent = next(iter(cal.walk("VEVENT")))
        result = _build_vcalendar(vevent, tzmap)
        text = result.decode()
        assert "VTIMEZONE" in text
        assert "Europe/Vienna" in text


class TestParseFeed:
    def test_parses_multiple_events(self) -> None:
        feed = _make_feed(
            ("Lecture A", "20260401T100000", "20260401T120000"),
            ("Lecture B", "20260402T140000", "20260402T160000"),
        )
        events, _tzmap = _parse_feed(feed)
        assert len(events) == 2

    def test_assigns_stable_uids(self) -> None:
        feed = _make_feed(("Lecture", "20260401T100000", "20260401T120000"))
        events, _ = _parse_feed(feed)
        uid = next(iter(events.keys()))
        assert uid.startswith("horae-")

    def test_same_content_produces_same_uid(self) -> None:
        feed1 = _make_feed(("Lecture", "20260401T100000", "20260401T120000"))
        feed2 = _make_feed(("Lecture", "20260401T100000", "20260401T120000"))
        events1, _ = _parse_feed(feed1)
        events2, _ = _parse_feed(feed2)
        assert set(events1.keys()) == set(events2.keys())

    def test_dedup_identical_events(self) -> None:
        """Duplicate events (same SUMMARY+DTSTART+DTEND) collapse to one UID."""
        feed = _make_feed(
            ("Same", "20260401T100000", "20260401T120000"),
            ("Same", "20260401T100000", "20260401T120000"),
        )
        events, _ = _parse_feed(feed)
        assert len(events) == 1

    def test_event_without_dtend_falls_back_to_dtstart(self) -> None:
        lines = [
            "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TISS//Test//EN",
            "BEGIN:VEVENT",
            "UID:tiss-no-end@tiss.tuwien.ac.at",
            "SUMMARY:All-Day",
            "DTSTART:20260401T100000",
            "END:VEVENT",
            "END:VCALENDAR",
        ]
        feed = "\r\n".join(lines).encode()
        events, _ = _parse_feed(feed)
        assert len(events) == 1

    def test_event_without_summary(self) -> None:
        lines = [
            "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TISS//Test//EN",
            "BEGIN:VEVENT",
            "UID:tiss-no-summary@tiss.tuwien.ac.at",
            "DTSTART:20260401T100000",
            "DTEND:20260401T120000",
            "END:VEVENT",
            "END:VCALENDAR",
        ]
        feed = "\r\n".join(lines).encode()
        events, _ = _parse_feed(feed)
        assert len(events) == 1

    def test_feed_with_timezone(self) -> None:
        feed = _make_tz_feed("Europe/Vienna", "Lecture", "20260401T100000", "20260401T120000")
        events, tzmap = _parse_feed(feed)
        assert len(events) == 1
        assert "Europe/Vienna" in tzmap

    def test_empty_feed(self) -> None:
        feed = b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//TISS//Test//EN\r\nEND:VCALENDAR"
        events, tzmap = _parse_feed(feed)
        assert len(events) == 0
        assert len(tzmap) == 0


class TestContentChanged:
    def _wrap_vevent(self, vevent: icalendar.Event) -> str:
        """Wrap a VEVENT in a VCALENDAR string (simulates existing CalDAV data)."""
        cal = icalendar.Calendar()
        cal.add("VERSION", "2.0")
        cal.add_component(vevent)
        return cal.to_ical().decode()

    def test_identical_events_not_changed(self) -> None:
        ev = icalendar.Event()
        ev.add("SUMMARY", "Lecture")
        ev.add("DTSTART", datetime(2026, 4, 1, 10, 0))
        ev.add("DTEND", datetime(2026, 4, 1, 12, 0))

        existing_data = self._wrap_vevent(ev)
        assert _content_changed(existing_data, ev) is False

    def test_summary_changed(self) -> None:
        old = icalendar.Event()
        old.add("SUMMARY", "Lecture")
        old.add("DTSTART", datetime(2026, 4, 1, 10, 0))
        old.add("DTEND", datetime(2026, 4, 1, 12, 0))

        new = icalendar.Event()
        new.add("SUMMARY", "Updated Lecture")
        new.add("DTSTART", datetime(2026, 4, 1, 10, 0))
        new.add("DTEND", datetime(2026, 4, 1, 12, 0))

        assert _content_changed(self._wrap_vevent(old), new) is True

    def test_location_changed(self) -> None:
        old = icalendar.Event()
        old.add("SUMMARY", "Lecture")
        old.add("DTSTART", datetime(2026, 4, 1, 10, 0))
        old.add("DTEND", datetime(2026, 4, 1, 12, 0))
        old.add("LOCATION", "Room A")

        new = icalendar.Event()
        new.add("SUMMARY", "Lecture")
        new.add("DTSTART", datetime(2026, 4, 1, 10, 0))
        new.add("DTEND", datetime(2026, 4, 1, 12, 0))
        new.add("LOCATION", "Room B")

        assert _content_changed(self._wrap_vevent(old), new) is True

    def test_description_changed(self) -> None:
        old = icalendar.Event()
        old.add("SUMMARY", "Lecture")
        old.add("DTSTART", datetime(2026, 4, 1, 10, 0))
        old.add("DTEND", datetime(2026, 4, 1, 12, 0))
        old.add("DESCRIPTION", "Old desc")

        new = icalendar.Event()
        new.add("SUMMARY", "Lecture")
        new.add("DTSTART", datetime(2026, 4, 1, 10, 0))
        new.add("DTEND", datetime(2026, 4, 1, 12, 0))
        new.add("DESCRIPTION", "New desc")

        assert _content_changed(self._wrap_vevent(old), new) is True

    def test_invalid_existing_data_returns_changed(self) -> None:
        new = icalendar.Event()
        new.add("SUMMARY", "Lecture")
        assert _content_changed("INVALID ICAL DATA", new) is True


class TestSyncResult:
    def test_total(self) -> None:
        r = SyncResult(created=2, updated=1, unchanged=3, deleted=1)
        assert r.total == 7

    def test_defaults_zero(self) -> None:
        r = SyncResult()
        assert r.total == 0
        assert r.errors == []


# ---------------------------------------------------------------------------
# Integration tests — mocked CalDAV + HTTP
# ---------------------------------------------------------------------------


def _mock_caldav_event(uid: str, vevent: icalendar.Component) -> MagicMock:
    """Create a mock CalDAV event with parseable .data."""
    cal = icalendar.Calendar()
    cal.add("VERSION", "2.0")
    cal.add_component(vevent)
    mock_event = MagicMock()
    mock_event.data = cal.to_ical().decode()
    mock_event.url = f"http://test/{uid}.ics"
    return mock_event


class TestSyncTiss:
    """Integration tests for sync_tiss with mocked HTTP + CalDAV."""

    def _setup_mocks(
        self,
        feed_data: bytes,
        existing_events: list[MagicMock] | None = None,
    ) -> tuple[MagicMock, MagicMock]:
        """Wire up mock CalDAV client and httpx.get."""
        mock_calendar = MagicMock()
        mock_calendar.name = "uni"
        mock_calendar.events.return_value = existing_events or []

        mock_principal = MagicMock()
        mock_principal.calendars.return_value = [mock_calendar]

        mock_client = MagicMock()
        mock_client.principal.return_value = mock_principal

        mock_resp = MagicMock()
        mock_resp.content = feed_data
        mock_resp.raise_for_status = MagicMock()

        return mock_client, mock_resp

    @patch("horae.sync.caldav.DAVClient")
    @patch("horae.sync.httpx.get")
    def test_creates_new_events(self, mock_get: MagicMock, mock_dav: MagicMock) -> None:
        feed = _make_feed(("Lecture A", "20260401T100000", "20260401T120000"))
        mock_client, mock_resp = self._setup_mocks(feed)
        mock_get.return_value = mock_resp
        mock_dav.return_value = mock_client

        result = sync_tiss(_sync_settings())

        assert result.created == 1
        assert result.unchanged == 0
        assert result.deleted == 0
        mock_client.principal().calendars()[0].save_event.assert_called_once()

    @patch("horae.sync.caldav.DAVClient")
    @patch("horae.sync.httpx.get")
    def test_skips_unchanged_events(self, mock_get: MagicMock, mock_dav: MagicMock) -> None:
        feed = _make_feed(("Lecture", "20260401T100000", "20260401T120000"))
        events, _ = _parse_feed(feed)
        uid = next(iter(events.keys()))
        vevent = events[uid]

        existing_mock = _mock_caldav_event(uid, vevent)
        mock_client, mock_resp = self._setup_mocks(feed, [existing_mock])
        mock_get.return_value = mock_resp
        mock_dav.return_value = mock_client

        result = sync_tiss(_sync_settings())

        assert result.unchanged == 1
        assert result.created == 0
        assert result.updated == 0

    @patch("horae.sync.caldav.DAVClient")
    @patch("horae.sync.httpx.get")
    def test_updates_changed_events(self, mock_get: MagicMock, mock_dav: MagicMock) -> None:
        feed = _make_feed(("Lecture", "20260401T100000", "20260401T120000"))
        events, _ = _parse_feed(feed)
        uid = next(iter(events.keys()))

        # Existing event has different LOCATION
        old_vevent = icalendar.Event()
        old_vevent.add("UID", uid)
        old_vevent.add("SUMMARY", "Lecture")
        old_vevent.add("DTSTART", datetime(2026, 4, 1, 10, 0))
        old_vevent.add("DTEND", datetime(2026, 4, 1, 12, 0))
        old_vevent.add("LOCATION", "Old Room")

        existing_mock = _mock_caldav_event(uid, old_vevent)
        mock_client, mock_resp = self._setup_mocks(feed, [existing_mock])
        mock_get.return_value = mock_resp
        mock_dav.return_value = mock_client

        result = sync_tiss(_sync_settings())

        assert result.updated == 1
        existing_mock.save.assert_called_once()

    @patch("horae.sync.caldav.DAVClient")
    @patch("horae.sync.httpx.get")
    def test_deletes_removed_horae_events(self, mock_get: MagicMock, mock_dav: MagicMock) -> None:
        feed = _make_feed()  # empty feed
        stale_uid = "horae-deadbeef12345678"

        stale_vevent = icalendar.Event()
        stale_vevent.add("UID", stale_uid)
        stale_vevent.add("SUMMARY", "Old Lecture")
        stale_vevent.add("DTSTART", datetime(2026, 3, 1, 10, 0))
        stale_vevent.add("DTEND", datetime(2026, 3, 1, 12, 0))
        stale_mock = _mock_caldav_event(stale_uid, stale_vevent)

        mock_client, mock_resp = self._setup_mocks(feed, [stale_mock])
        mock_get.return_value = mock_resp
        mock_dav.return_value = mock_client

        result = sync_tiss(_sync_settings())

        assert result.deleted == 1
        stale_mock.delete.assert_called_once()

    @patch("horae.sync.caldav.DAVClient")
    @patch("horae.sync.httpx.get")
    def test_does_not_delete_non_horae_events(self, mock_get: MagicMock, mock_dav: MagicMock) -> None:
        feed = _make_feed()  # empty feed
        foreign_uid = "foreign-event-abc123"

        foreign_vevent = icalendar.Event()
        foreign_vevent.add("UID", foreign_uid)
        foreign_vevent.add("SUMMARY", "Personal Event")
        foreign_vevent.add("DTSTART", datetime(2026, 3, 1, 10, 0))
        foreign_vevent.add("DTEND", datetime(2026, 3, 1, 12, 0))
        foreign_mock = _mock_caldav_event(foreign_uid, foreign_vevent)

        mock_client, mock_resp = self._setup_mocks(feed, [foreign_mock])
        mock_get.return_value = mock_resp
        mock_dav.return_value = mock_client

        result = sync_tiss(_sync_settings())

        assert result.deleted == 0
        foreign_mock.delete.assert_not_called()

    @patch("horae.sync.caldav.DAVClient")
    @patch("horae.sync.httpx.get")
    def test_idempotent_sync(self, mock_get: MagicMock, mock_dav: MagicMock) -> None:
        """Running sync twice with identical feed → 0 creates/updates on second run."""
        feed = _make_feed(("Lecture", "20260401T100000", "20260401T120000"))
        events, _ = _parse_feed(feed)
        uid = next(iter(events.keys()))
        vevent = events[uid]

        existing_mock = _mock_caldav_event(uid, vevent)
        mock_client, mock_resp = self._setup_mocks(feed, [existing_mock])
        mock_get.return_value = mock_resp
        mock_dav.return_value = mock_client

        result = sync_tiss(_sync_settings())

        assert result.created == 0
        assert result.updated == 0
        assert result.unchanged == 1

    @patch("horae.sync.caldav.DAVClient")
    @patch("horae.sync.httpx.get")
    def test_empty_feed_no_errors(self, mock_get: MagicMock, mock_dav: MagicMock) -> None:
        feed = _make_feed()
        mock_client, mock_resp = self._setup_mocks(feed)
        mock_get.return_value = mock_resp
        mock_dav.return_value = mock_client

        result = sync_tiss(_sync_settings())

        assert result.total == 0
        assert result.errors == []

    @patch("horae.sync.caldav.DAVClient")
    @patch("horae.sync.httpx.get")
    def test_save_error_logged_and_continues(self, mock_get: MagicMock, mock_dav: MagicMock) -> None:
        feed = _make_feed(
            ("Lecture A", "20260401T100000", "20260401T120000"),
            ("Lecture B", "20260402T140000", "20260402T160000"),
        )
        mock_client, mock_resp = self._setup_mocks(feed)
        mock_get.return_value = mock_resp
        mock_dav.return_value = mock_client

        calendar_mock = mock_client.principal().calendars()[0]
        calendar_mock.save_event.side_effect = [Exception("CalDAV down"), None]

        result = sync_tiss(_sync_settings())

        assert result.created == 1
        assert len(result.errors) == 1
        assert "CalDAV down" in result.errors[0]

    def test_missing_tiss_url_raises(self) -> None:
        settings = Settings(
            radicale_url="http://test:5232",
            radicale_username="u",
            radicale_password=SecretStr("p"),
            default_calendar="personal",
            default_duration_minutes=60,
            ollama_url="http://test:11434",
            ollama_model="m",
        )
        with pytest.raises(ValueError, match="HORAE_TISS_ICAL_URL"):
            sync_tiss(settings)

    @patch("horae.sync.caldav.DAVClient")
    @patch("horae.sync.httpx.get")
    def test_full_cycle_create_update_delete_unchanged(
        self, mock_get: MagicMock, mock_dav: MagicMock
    ) -> None:
        """Full sync cycle: one new, one unchanged, one updated, one deleted."""
        feed = _make_feed(
            ("New Lecture", "20260405T100000", "20260405T120000"),
            ("Unchanged", "20260401T100000", "20260401T120000"),
            ("Updated", "20260402T100000", "20260402T120000"),
        )
        feed_events, _ = _parse_feed(feed)
        # _parse_feed normalises dates via _dt_to_str before hashing
        uid_unchanged = _stable_uid("Unchanged", "2026-04-01 10:00:00", "2026-04-01 12:00:00")
        uid_updated = _stable_uid("Updated", "2026-04-02 10:00:00", "2026-04-02 12:00:00")
        uid_deleted = "horae-toberemoved00000"
        assert uid_unchanged in feed_events, f"{uid_unchanged} not in {list(feed_events.keys())}"

        # Existing: unchanged (same), updated (different location), deleted (not in feed)
        unchanged_vevent = feed_events[uid_unchanged]
        unchanged_mock = _mock_caldav_event(uid_unchanged, unchanged_vevent)

        old_updated = icalendar.Event()
        old_updated.add("UID", uid_updated)
        old_updated.add("SUMMARY", "Updated")
        old_updated.add("DTSTART", datetime(2026, 4, 2, 10, 0))
        old_updated.add("DTEND", datetime(2026, 4, 2, 12, 0))
        old_updated.add("LOCATION", "Old Room")
        updated_mock = _mock_caldav_event(uid_updated, old_updated)

        deleted_vevent = icalendar.Event()
        deleted_vevent.add("UID", uid_deleted)
        deleted_vevent.add("SUMMARY", "Gone")
        deleted_vevent.add("DTSTART", datetime(2026, 3, 1, 10, 0))
        deleted_vevent.add("DTEND", datetime(2026, 3, 1, 12, 0))
        deleted_mock = _mock_caldav_event(uid_deleted, deleted_vevent)

        mock_client, mock_resp = self._setup_mocks(
            feed, [unchanged_mock, updated_mock, deleted_mock]
        )
        mock_get.return_value = mock_resp
        mock_dav.return_value = mock_client

        result = sync_tiss(_sync_settings())

        assert result.created == 1
        assert result.unchanged == 1
        assert result.updated == 1
        assert result.deleted == 1
        assert result.errors == []


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestMain:
    @patch("horae.sync.sync_tiss")
    @patch("horae.sync.Settings")
    def test_returns_0_on_success(self, mock_settings_cls: MagicMock, mock_sync: MagicMock) -> None:
        mock_sync.return_value = SyncResult(created=1)
        assert main() == 0

    @patch("horae.sync.sync_tiss")
    @patch("horae.sync.Settings")
    def test_returns_1_on_sync_errors(self, mock_settings_cls: MagicMock, mock_sync: MagicMock) -> None:
        mock_sync.return_value = SyncResult(errors=["some error"])
        assert main() == 1

    @patch("horae.sync.Settings", side_effect=Exception("bad config"))
    def test_returns_1_on_config_error(self, mock_settings_cls: MagicMock) -> None:
        assert main() == 1

    @patch("horae.sync.FileLock")
    @patch("horae.sync.Settings")
    def test_returns_2_when_lock_held(self, mock_settings_cls: MagicMock, mock_lock_cls: MagicMock) -> None:
        mock_lock_cls.return_value.__enter__ = MagicMock(side_effect=Timeout("lock"))
        mock_lock_cls.return_value.__exit__ = MagicMock(return_value=False)
        # FileLock raises Timeout before entering context
        mock_lock_cls.side_effect = None
        lock_inst = MagicMock()
        lock_inst.__enter__ = MagicMock(side_effect=Timeout("lock"))
        lock_inst.__exit__ = MagicMock(return_value=False)
        mock_lock_cls.return_value = lock_inst

        assert main() == 2

    @patch("horae.sync.sync_tiss", side_effect=Exception("network down"))
    @patch("horae.sync.Settings")
    def test_returns_1_on_sync_exception(self, mock_settings_cls: MagicMock, mock_sync: MagicMock) -> None:
        assert main() == 1
