from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from horae.models import CalendarInfo, EventInfo
from horae.parser import ParseResult
from horae.scheduler import SyncScheduler, SyncStatus
from horae.sync import SyncResult


async def test_health_returns_ok(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_create_event_dateparser_success(async_client: httpx.AsyncClient) -> None:
    now = datetime(2026, 3, 31, 10, 0)
    result = ParseResult(
        summary="Meeting",
        dtstart=now,
        dtend=now + timedelta(hours=1),
    )
    with (
        patch("horae.app.parse_event_text", return_value=result) as mock_parse,
        patch("horae.app.create_event", return_value="uid-123") as mock_create,
    ):
        response = await async_client.post("/events", json={"text": "meeting tomorrow at 10am"})

    assert response.status_code == 201
    body = response.json()
    assert body["summary"] == "Meeting"
    assert body["uid"] == "uid-123"
    assert body["calendar"] == "personal"
    mock_parse.assert_called_once()
    mock_create.assert_called_once()


async def test_create_event_llm_fallback(async_client: httpx.AsyncClient) -> None:
    now = datetime(2026, 3, 31, 10, 0)
    result = ParseResult(
        summary="Dentist",
        dtstart=now,
        dtend=now + timedelta(hours=1),
    )
    with (
        patch("horae.app.parse_event_text", return_value=None),
        patch("horae.app.extract_event_llm", new_callable=AsyncMock, return_value=result),
        patch("horae.app.create_event", return_value="uid-456"),
    ):
        response = await async_client.post("/events", json={"text": "dentist next week"})

    assert response.status_code == 201
    assert response.json()["summary"] == "Dentist"
    assert response.json()["uid"] == "uid-456"


async def test_create_event_both_fail(async_client: httpx.AsyncClient) -> None:
    with (
        patch("horae.app.parse_event_text", return_value=None),
        patch("horae.app.extract_event_llm", new_callable=AsyncMock, return_value=None),
    ):
        response = await async_client.post("/events", json={"text": "something vague"})

    assert response.status_code == 422


async def test_create_event_custom_calendar(async_client: httpx.AsyncClient) -> None:
    now = datetime(2026, 3, 31, 10, 0)
    result = ParseResult(summary="Standup", dtstart=now, dtend=now + timedelta(hours=1))
    with (
        patch("horae.app.parse_event_text", return_value=result),
        patch("horae.app.create_event", return_value="uid-789") as mock_create,
    ):
        response = await async_client.post("/events", json={"text": "standup at 10am", "calendar": "work"})

    assert response.status_code == 201
    assert response.json()["calendar"] == "work"
    _, kwargs = mock_create.call_args
    assert kwargs["calendar_name"] == "work"


async def test_create_event_empty_text(async_client: httpx.AsyncClient) -> None:
    with (
        patch("horae.app.parse_event_text", return_value=None),
        patch("horae.app.extract_event_llm", new_callable=AsyncMock, return_value=None),
    ):
        response = await async_client.post("/events", json={"text": ""})

    assert response.status_code == 422


async def test_list_calendars(async_client: httpx.AsyncClient) -> None:
    calendars = [
        CalendarInfo(name="personal", path="/user/personal/"),
        CalendarInfo(name="work", path="/user/work/"),
    ]
    with patch("horae.app.list_calendars", return_value=calendars):
        response = await async_client.get("/calendars")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "personal"
    assert data[1]["name"] == "work"


async def test_create_event_caldav_error(async_client: httpx.AsyncClient) -> None:
    now = datetime(2026, 3, 31, 10, 0)
    result = ParseResult(summary="Event", dtstart=now, dtend=now + timedelta(hours=1))
    with (
        patch("horae.app.parse_event_text", return_value=result),
        patch("horae.app.create_event", side_effect=ValueError("Calendar not found")),
    ):
        response = await async_client.post("/events", json={"text": "event at 10am"})

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Sync endpoint tests
# ---------------------------------------------------------------------------


async def test_sync_status_returns_200(async_client: httpx.AsyncClient) -> None:
    from horae.app import app

    mock_scheduler = MagicMock(spec=SyncScheduler)
    mock_scheduler.status = SyncStatus()
    app.state.scheduler = mock_scheduler
    try:
        response = await async_client.get("/sync/status")
        assert response.status_code == 200
        data = response.json()
        assert data["is_running"] is False
        assert data["last_run"] is None
        assert data["last_result"] is None
        assert data["last_error"] is None
        assert data["next_run"] is None
    finally:
        del app.state.scheduler


async def test_sync_status_returns_503_without_scheduler(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/sync/status")
    assert response.status_code == 503


async def test_sync_trigger_returns_202(async_client: httpx.AsyncClient) -> None:
    from horae.app import app

    mock_scheduler = MagicMock(spec=SyncScheduler)
    app.state.scheduler = mock_scheduler
    try:
        response = await async_client.post("/sync/trigger")
        assert response.status_code == 202
        assert response.json() == {"detail": "Sync triggered"}
        mock_scheduler.trigger.assert_called_once()
    finally:
        del app.state.scheduler


async def test_sync_trigger_returns_503_without_scheduler(async_client: httpx.AsyncClient) -> None:
    response = await async_client.post("/sync/trigger")
    assert response.status_code == 503


async def test_sync_status_reflects_last_result(async_client: httpx.AsyncClient) -> None:
    from horae.app import app

    result = SyncResult(created=3, updated=1, unchanged=10, deleted=2)
    status = SyncStatus(
        last_run=datetime(2026, 4, 17, 12, 0),
        last_result=result,
        is_running=False,
    )
    mock_scheduler = MagicMock(spec=SyncScheduler)
    mock_scheduler.status = status
    app.state.scheduler = mock_scheduler
    try:
        response = await async_client.get("/sync/status")
        assert response.status_code == 200
        data = response.json()
        assert data["last_result"] == {
            "created": 3,
            "updated": 1,
            "unchanged": 10,
            "deleted": 2,
        }
        assert data["last_run"] is not None
        assert data["is_running"] is False
    finally:
        del app.state.scheduler


# ---------------------------------------------------------------------------
# Calendar management endpoint tests
# ---------------------------------------------------------------------------


async def test_create_calendar_success(async_client: httpx.AsyncClient) -> None:
    cal_info = CalendarInfo(name="work", path="/user/work/")
    with patch("horae.app.create_calendar", return_value=cal_info):
        response = await async_client.post("/calendars", json={"name": "work"})

    assert response.status_code == 201
    assert response.json()["name"] == "work"
    assert response.json()["path"] == "/user/work/"


async def test_create_calendar_conflict(async_client: httpx.AsyncClient) -> None:
    with patch("horae.app.create_calendar", side_effect=ValueError("already exists")):
        response = await async_client.post("/calendars", json={"name": "work"})

    assert response.status_code == 409


async def test_delete_calendar_success(async_client: httpx.AsyncClient) -> None:
    with patch("horae.app.delete_calendar"):
        response = await async_client.delete("/calendars/work")

    assert response.status_code == 204


async def test_delete_calendar_not_found(async_client: httpx.AsyncClient) -> None:
    with patch("horae.app.delete_calendar", side_effect=ValueError("not found")):
        response = await async_client.delete("/calendars/nonexistent")

    assert response.status_code == 404


async def test_list_events_success(async_client: httpx.AsyncClient) -> None:
    events = [
        EventInfo(
            uid="uid-1",
            summary="Dentist",
            dtstart=datetime(2026, 4, 10, 14, 0),
            dtend=datetime(2026, 4, 10, 15, 0),
        ),
        EventInfo(uid="uid-2", summary="Lunch"),
    ]
    with patch("horae.app.list_events", return_value=events):
        response = await async_client.get("/calendars/personal/events")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["uid"] == "uid-1"
    assert data[1]["summary"] == "Lunch"


async def test_list_events_not_found(async_client: httpx.AsyncClient) -> None:
    with patch("horae.app.list_events", side_effect=ValueError("not found")):
        response = await async_client.get("/calendars/nonexistent/events")

    assert response.status_code == 404


async def test_import_ics_success(async_client: httpx.AsyncClient) -> None:
    with patch("horae.app.import_ics", return_value=3):
        response = await async_client.post(
            "/calendars/personal/import",
            files={"file": ("events.ics", b"BEGIN:VCALENDAR\r\nEND:VCALENDAR", "text/calendar")},
        )

    assert response.status_code == 201
    assert response.json()["imported"] == 3


async def test_import_ics_not_found(async_client: httpx.AsyncClient) -> None:
    with patch("horae.app.import_ics", side_effect=ValueError("Calendar 'bad' not found")):
        response = await async_client.post(
            "/calendars/bad/import",
            files={"file": ("events.ics", b"BEGIN:VCALENDAR\r\nEND:VCALENDAR", "text/calendar")},
        )

    assert response.status_code == 404


async def test_import_ics_invalid_data(async_client: httpx.AsyncClient) -> None:
    with patch("horae.app.import_ics", side_effect=ValueError("Invalid ICS data")):
        response = await async_client.post(
            "/calendars/personal/import",
            files={"file": ("events.ics", b"not ics", "text/calendar")},
        )

    assert response.status_code == 422
