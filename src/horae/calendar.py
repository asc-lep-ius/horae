from __future__ import annotations

from typing import Any
from uuid import uuid4

import caldav

from horae.config import Settings
from horae.models import CalendarInfo
from horae.parser import ParseResult

_VCALENDAR_TEMPLATE = (
    "BEGIN:VCALENDAR\r\n"
    "VERSION:2.0\r\n"
    "PRODID:-//Horae//EN\r\n"
    "BEGIN:VEVENT\r\n"
    "UID:{uid}\r\n"
    "DTSTART:{dtstart}\r\n"
    "DTEND:{dtend}\r\n"
    "SUMMARY:{summary}\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR"
)


def _connect(settings: Settings) -> Any:
    return caldav.DAVClient(  # pyright: ignore[reportCallIssue]
        url=settings.radicale_url,
        username=settings.radicale_username,
        password=settings.radicale_password.get_secret_value(),
    )


def _find_calendar(principal: Any, name: str) -> Any:
    for cal in principal.calendars():
        if cal.name.lower() == name.lower():
            return cal
    raise ValueError(f"Calendar '{name}' not found")


def create_event(result: ParseResult, calendar_name: str, settings: Settings) -> str:
    """Create a CalDAV event. Returns the UID of the created event."""
    client = _connect(settings)
    principal = client.principal()
    calendar = _find_calendar(principal, calendar_name)

    uid = str(uuid4())
    ical_data = _VCALENDAR_TEMPLATE.format(
        uid=uid,
        dtstart=result.dtstart.strftime("%Y%m%dT%H%M%S"),
        dtend=result.dtend.strftime("%Y%m%dT%H%M%S"),
        summary=result.summary,
    )
    calendar.save_event(ical_data)
    return uid


def list_calendars(settings: Settings) -> list[CalendarInfo]:
    """List all accessible calendars from Radicale."""
    client = _connect(settings)
    principal = client.principal()
    return [CalendarInfo(name=cal.name, path=str(cal.url)) for cal in principal.calendars()]
