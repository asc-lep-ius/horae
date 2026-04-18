import datetime
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile
from starlette.responses import JSONResponse

from horae.calendar import create_calendar, create_event, delete_calendar, import_ics, list_calendars, list_events
from horae.config import Settings
from horae.llm import extract_event_llm
from horae.models import (
    CalendarCreate,
    CalendarInfo,
    EventInfo,
    EventRequest,
    EventResponse,
    ImportResult,
    SyncStatusResponse,
)
from horae.parser import parse_event_text
from horae.scheduler import SyncScheduler


def get_scheduler(request: Request) -> SyncScheduler:
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        raise HTTPException(503, "Scheduler not initialized")
    return scheduler


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


@app.post("/calendars", status_code=201)
async def post_calendar(
    body: CalendarCreate,
    settings: Annotated[Settings, Depends(get_settings)],
) -> CalendarInfo:
    try:
        return create_calendar(body.name, settings)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.delete("/calendars/{name}", status_code=204)
async def remove_calendar(
    name: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    try:
        delete_calendar(name, settings)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(status_code=204)


@app.get("/calendars/{name}/events")
async def get_calendar_events(
    name: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[EventInfo]:
    try:
        return list_events(name, settings)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/calendars/{name}/import", status_code=201)
async def post_import_ics(
    name: str,
    file: UploadFile,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ImportResult:
    ics_data = (await file.read()).decode()
    try:
        count = import_ics(name, ics_data, settings)
    except ValueError as exc:
        detail = str(exc)
        if "not found" in detail.lower():
            raise HTTPException(404, detail) from exc
        raise HTTPException(422, detail) from exc
    return ImportResult(imported=count)


@app.get("/sync/status")
async def sync_status(
    scheduler: Annotated[SyncScheduler, Depends(get_scheduler)],
) -> SyncStatusResponse:
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
async def sync_trigger(
    scheduler: Annotated[SyncScheduler, Depends(get_scheduler)],
) -> JSONResponse:
    scheduler.trigger()
    return JSONResponse(status_code=202, content={"detail": "Sync triggered"})
