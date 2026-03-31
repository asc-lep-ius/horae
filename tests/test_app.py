from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx

from horae.models import CalendarInfo
from horae.parser import ParseResult


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
