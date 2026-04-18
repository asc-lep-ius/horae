from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from horae.calendar import (
    create_calendar,
    create_event,
    delete_calendar,
    import_ics,
    list_calendars,
    list_events,
)
from horae.config import Settings
from horae.models import CalendarInfo, EventInfo
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


# ---------------------------------------------------------------------------
# create_calendar tests
# ---------------------------------------------------------------------------


@patch("horae.calendar.caldav.DAVClient")
def test_create_calendar_success(mock_client_cls: MagicMock, settings: Settings) -> None:
    mock_principal = mock_client_cls.return_value.principal.return_value
    mock_principal.calendars.return_value = []
    new_cal = _make_mock_calendar("work", "/user/work/")
    mock_principal.make_calendar.return_value = new_cal

    result = create_calendar("work", settings)

    assert result.name == "work"
    assert result.path == "/user/work/"
    mock_principal.make_calendar.assert_called_once_with(name="work")


@patch("horae.calendar.caldav.DAVClient")
def test_create_calendar_already_exists_raises(mock_client_cls: MagicMock, settings: Settings) -> None:
    mock_principal = mock_client_cls.return_value.principal.return_value
    mock_principal.calendars.return_value = [_make_mock_calendar("work")]

    with pytest.raises(ValueError, match="already exists"):
        create_calendar("Work", settings)


# ---------------------------------------------------------------------------
# delete_calendar tests
# ---------------------------------------------------------------------------


@patch("horae.calendar.caldav.DAVClient")
def test_delete_calendar_success(mock_client_cls: MagicMock, settings: Settings) -> None:
    mock_cal = _make_mock_calendar("work")
    mock_principal = mock_client_cls.return_value.principal.return_value
    mock_principal.calendars.return_value = [mock_cal]

    delete_calendar("work", settings)

    mock_cal.delete.assert_called_once()


@patch("horae.calendar.caldav.DAVClient")
def test_delete_calendar_not_found_raises(mock_client_cls: MagicMock, settings: Settings) -> None:
    mock_principal = mock_client_cls.return_value.principal.return_value
    mock_principal.calendars.return_value = []

    with pytest.raises(ValueError, match="not found"):
        delete_calendar("nonexistent", settings)


# ---------------------------------------------------------------------------
# list_events tests
# ---------------------------------------------------------------------------


def _make_mock_event(uid: str, summary: str, dtstart: datetime, dtend: datetime) -> MagicMock:
    event = MagicMock()
    vcal = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTART:{dtstart.strftime('%Y%m%dT%H%M%S')}\r\n"
        f"DTEND:{dtend.strftime('%Y%m%dT%H%M%S')}\r\n"
        f"SUMMARY:{summary}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR"
    )
    event.data = vcal
    return event


@patch("horae.calendar.caldav.DAVClient")
def test_list_events_returns_events(mock_client_cls: MagicMock, settings: Settings) -> None:
    mock_cal = _make_mock_calendar("personal")
    mock_cal.events.return_value = [
        _make_mock_event("uid-1", "Dentist", datetime(2026, 4, 10, 14, 0), datetime(2026, 4, 10, 15, 0)),
        _make_mock_event("uid-2", "Lunch", datetime(2026, 4, 10, 12, 0), datetime(2026, 4, 10, 13, 0)),
    ]
    mock_client_cls.return_value.principal.return_value.calendars.return_value = [mock_cal]

    result = list_events("personal", settings)

    assert len(result) == 2
    assert all(isinstance(e, EventInfo) for e in result)
    assert result[0].uid == "uid-1"
    assert result[0].summary == "Dentist"
    assert result[1].uid == "uid-2"


@patch("horae.calendar.caldav.DAVClient")
def test_list_events_empty_calendar(mock_client_cls: MagicMock, settings: Settings) -> None:
    mock_cal = _make_mock_calendar("personal")
    mock_cal.events.return_value = []
    mock_client_cls.return_value.principal.return_value.calendars.return_value = [mock_cal]

    result = list_events("personal", settings)

    assert result == []


@patch("horae.calendar.caldav.DAVClient")
def test_list_events_calendar_not_found(mock_client_cls: MagicMock, settings: Settings) -> None:
    mock_client_cls.return_value.principal.return_value.calendars.return_value = []

    with pytest.raises(ValueError, match="not found"):
        list_events("nonexistent", settings)


# ---------------------------------------------------------------------------
# import_ics tests
# ---------------------------------------------------------------------------

_TWO_EVENT_ICS = (
    "BEGIN:VCALENDAR\r\n"
    "VERSION:2.0\r\n"
    "BEGIN:VEVENT\r\n"
    "UID:import-1\r\n"
    "DTSTART:20260501T090000\r\n"
    "SUMMARY:Morning\r\n"
    "END:VEVENT\r\n"
    "BEGIN:VEVENT\r\n"
    "UID:import-2\r\n"
    "DTSTART:20260501T140000\r\n"
    "SUMMARY:Afternoon\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR"
)


@patch("horae.calendar.caldav.DAVClient")
def test_import_ics_success(mock_client_cls: MagicMock, settings: Settings) -> None:
    mock_cal = _make_mock_calendar("personal")
    mock_client_cls.return_value.principal.return_value.calendars.return_value = [mock_cal]

    count = import_ics("personal", _TWO_EVENT_ICS, settings)

    assert count == 2
    assert mock_cal.save_event.call_count == 2


@patch("horae.calendar.caldav.DAVClient")
def test_import_ics_invalid_data_raises(mock_client_cls: MagicMock, settings: Settings) -> None:
    mock_cal = _make_mock_calendar("personal")
    mock_client_cls.return_value.principal.return_value.calendars.return_value = [mock_cal]

    with pytest.raises(ValueError, match=r"[Ii]nvalid"):
        import_ics("personal", "not valid ics data", settings)


@patch("horae.calendar.caldav.DAVClient")
def test_import_ics_calendar_not_found(mock_client_cls: MagicMock, settings: Settings) -> None:
    mock_client_cls.return_value.principal.return_value.calendars.return_value = []

    with pytest.raises(ValueError, match="not found"):
        import_ics("nonexistent", _TWO_EVENT_ICS, settings)
