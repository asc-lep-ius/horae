import datetime
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from starlette.responses import JSONResponse

from horae.calendar import create_event, list_calendars
from horae.config import Settings
from horae.llm import extract_event_llm
from horae.models import CalendarInfo, EventRequest, EventResponse, SyncStatusResponse
from horae.parser import parse_event_text
from horae.scheduler import SyncScheduler


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    scheduler = SyncScheduler(get_settings())
    _app.state.scheduler = scheduler
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="Horae", description="Natural language calendar event creation", lifespan=lifespan)


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


@app.get("/sync/status")
async def sync_status() -> SyncStatusResponse:
    scheduler: SyncScheduler = app.state.scheduler
    s = scheduler.status
    last_result = None
    if s.last_result is not None:
        last_result = {
            "created": s.last_result.created,
            "updated": s.last_result.updated,
            "unchanged": s.last_result.unchanged,
            "deleted": s.last_result.deleted,
        }
    return SyncStatusResponse(
        last_run=s.last_run,
        last_result=last_result,
        last_error=s.last_error,
        next_run=s.next_run,
        is_running=s.is_running,
    )


@app.post("/sync/trigger", status_code=202)
async def sync_trigger() -> JSONResponse:
    scheduler: SyncScheduler = app.state.scheduler
    scheduler.trigger()
    return JSONResponse(status_code=202, content={"detail": "Sync triggered"})
