from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from horae.calendar import create_event, list_calendars
from horae.config import Settings
from horae.models import CalendarInfo
from horae.parser import ParseResult


@pytest.fixture
def settings() -> Settings:
    return Settings(
        radicale_username="test",
        radicale_password="test",  # type: ignore[arg-type]
    )


def _make_mock_calendar(name: str, url: str = "/user/cal/") -> MagicMock:
    cal = MagicMock()
    cal.name = name
    cal.url = url
    return cal


@patch("horae.calendar.caldav.DAVClient")
def test_create_event_returns_uid_and_saves(mock_client_cls: MagicMock, settings: Settings) -> None:
    mock_cal = _make_mock_calendar("personal")
    mock_client_cls.return_value.principal.return_value.calendars.return_value = [mock_cal]

    result = ParseResult(summary="Dentist", dtstart=datetime(2026, 4, 10, 14, 0), dtend=datetime(2026, 4, 10, 15, 0))
    uid = create_event(result, "personal", settings)

    assert isinstance(uid, str)
    assert len(uid) > 0
    mock_cal.save_event.assert_called_once()
    ical_data = mock_cal.save_event.call_args[0][0]
    assert "SUMMARY:Dentist" in ical_data


@patch("horae.calendar.caldav.DAVClient")
def test_create_event_unknown_calendar_raises(mock_client_cls: MagicMock, settings: Settings) -> None:
    mock_client_cls.return_value.principal.return_value.calendars.return_value = [
        _make_mock_calendar("personal"),
    ]

    result = ParseResult(summary="Test", dtstart=datetime(2026, 4, 10, 14, 0), dtend=datetime(2026, 4, 10, 15, 0))

    with pytest.raises(ValueError, match="not found"):
        create_event(result, "nonexistent", settings)


@patch("horae.calendar.caldav.DAVClient")
def test_create_event_ical_format(mock_client_cls: MagicMock, settings: Settings) -> None:
    mock_cal = _make_mock_calendar("work")
    mock_client_cls.return_value.principal.return_value.calendars.return_value = [mock_cal]

    result = ParseResult(summary="Standup", dtstart=datetime(2026, 5, 1, 9, 0), dtend=datetime(2026, 5, 1, 9, 30))
    create_event(result, "work", settings)

    ical_data: str = mock_cal.save_event.call_args[0][0]
    assert ical_data.startswith("BEGIN:VCALENDAR")
    assert "VERSION:2.0" in ical_data
    assert "PRODID:-//Horae//EN" in ical_data
    assert "BEGIN:VEVENT" in ical_data
    assert "UID:" in ical_data
    assert "DTSTART:20260501T090000" in ical_data
    assert "DTEND:20260501T093000" in ical_data
    assert "SUMMARY:Standup" in ical_data
    assert "END:VEVENT" in ical_data
    assert ical_data.rstrip().endswith("END:VCALENDAR")


@patch("horae.calendar.caldav.DAVClient")
def test_list_calendars_returns_calendar_info(mock_client_cls: MagicMock, settings: Settings) -> None:
    mock_client_cls.return_value.principal.return_value.calendars.return_value = [
        _make_mock_calendar("Personal", "/asclepius/personal/"),
        _make_mock_calendar("Work", "/asclepius/work/"),
    ]

    result = list_calendars(settings)

    assert len(result) == 2
    assert all(isinstance(c, CalendarInfo) for c in result)
    assert result[0].name == "Personal"
    assert result[0].path == "/asclepius/personal/"
    assert result[1].name == "Work"
    assert result[1].path == "/asclepius/work/"


@patch("horae.calendar.caldav.DAVClient")
def test_create_event_case_insensitive_match(mock_client_cls: MagicMock, settings: Settings) -> None:
    mock_cal = _make_mock_calendar("Personal")
    mock_client_cls.return_value.principal.return_value.calendars.return_value = [mock_cal]

    result = ParseResult(summary="Lunch", dtstart=datetime(2026, 4, 15, 12, 0), dtend=datetime(2026, 4, 15, 13, 0))
    uid = create_event(result, "personal", settings)

    assert isinstance(uid, str)
    mock_cal.save_event.assert_called_once()


@patch("horae.calendar.caldav.DAVClient")
def test_create_event_propagates_connection_error(mock_client_cls: MagicMock, settings: Settings) -> None:
    mock_client_cls.return_value.principal.side_effect = ConnectionError("refused")

    result = ParseResult(summary="Meeting", dtstart=datetime(2026, 4, 10, 10, 0), dtend=datetime(2026, 4, 10, 11, 0))

    with pytest.raises(ConnectionError, match="refused"):
        create_event(result, "personal", settings)
