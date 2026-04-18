from __future__ import annotations

from typing import Any
from uuid import uuid4

import caldav
import icalendar

from horae.config import Settings
from horae.models import CalendarInfo, EventInfo
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


def create_calendar(name: str, settings: Settings) -> CalendarInfo:
    """Create a new calendar. Raises ValueError if it already exists."""
    client = _connect(settings)
    principal = client.principal()
    for cal in principal.calendars():
        if cal.name.lower() == name.lower():
            raise ValueError(f"Calendar '{name}' already exists")
    new_cal = principal.make_calendar(name=name)
    return CalendarInfo(name=new_cal.name, path=str(new_cal.url))


def delete_calendar(name: str, settings: Settings) -> None:
    """Delete a calendar by name. Raises ValueError if not found."""
    client = _connect(settings)
    principal = client.principal()
    calendar = _find_calendar(principal, name)
    calendar.delete()


def list_events(calendar_name: str, settings: Settings) -> list[EventInfo]:
    """List all events in a calendar. Raises ValueError if calendar not found."""
    client = _connect(settings)
    principal = client.principal()
    calendar = _find_calendar(principal, calendar_name)
    events: list[EventInfo] = []
    for event in calendar.events():
        cal = icalendar.Calendar.from_ical(event.data)
        for component in cal.walk():
            if component.name == "VEVENT":
                dtstart = component.get("dtstart")
                dtend = component.get("dtend")
                events.append(
                    EventInfo(
                        uid=str(component.get("uid", "")),
                        summary=str(component.get("summary", "")),
                        dtstart=dtstart.dt if dtstart else None,
                        dtend=dtend.dt if dtend else None,
                    )
                )
    return events


def import_ics(calendar_name: str, ics_data: str, settings: Settings) -> int:
    """Import events from an ICS string. Returns count of imported events."""
    client = _connect(settings)
    principal = client.principal()
    calendar = _find_calendar(principal, calendar_name)
    try:
        cal = icalendar.Calendar.from_ical(ics_data)
    except Exception as exc:
        raise ValueError("Invalid ICS data") from exc
    count = 0
    for component in cal.walk():
        if component.name == "VEVENT":
            calendar.save_event(component.to_ical().decode())
            count += 1
    if count == 0:
        raise ValueError("Invalid ICS data: no events found")
    return count
