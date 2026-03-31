import datetime
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException

from horae.calendar import create_event, list_calendars
from horae.config import Settings
from horae.llm import extract_event_llm
from horae.models import CalendarInfo, EventRequest, EventResponse
from horae.parser import parse_event_text

app = FastAPI(title="Horae", description="Natural language calendar event creation")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/events", status_code=201)
async def post_event(
    request: EventRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> EventResponse:
    now = datetime.datetime.now(datetime.UTC)

    result = parse_event_text(
        request.text,
        reference_date=now,
        default_duration_minutes=settings.default_duration_minutes,
    )
    if result is None:
        result = await extract_event_llm(request.text, reference_date=now, settings=settings)
    if result is None:
        raise HTTPException(422, "Could not parse event from text")

    calendar_name = request.calendar or settings.default_calendar
    try:
        uid = create_event(result, calendar_name=calendar_name, settings=settings)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc

    return EventResponse(
        summary=result.summary,
        dtstart=result.dtstart,
        dtend=result.dtend,
        calendar=calendar_name,
        uid=uid,
    )


@app.get("/calendars")
async def get_calendars(
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[CalendarInfo]:
    return list_calendars(settings)
