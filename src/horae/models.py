from datetime import datetime

from pydantic import BaseModel


class EventRequest(BaseModel):
    text: str
    calendar: str | None = None


class EventResponse(BaseModel):
    summary: str
    dtstart: datetime
    dtend: datetime
    calendar: str
    uid: str


class CalendarInfo(BaseModel):
    name: str
    path: str


class HealthResponse(BaseModel):
    status: str
