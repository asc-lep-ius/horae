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


class CalendarCreate(BaseModel):
    name: str


class EventInfo(BaseModel):
    uid: str
    summary: str
    dtstart: datetime | None = None
    dtend: datetime | None = None


class ImportResult(BaseModel):
    imported: int


class HealthResponse(BaseModel):
    status: str


class SyncStatusResponse(BaseModel):
    last_run: datetime | None = None
    last_result: dict[str, int] | None = None
    last_error: str | None = None
    next_run: datetime | None = None
    is_running: bool = False
