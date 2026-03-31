from datetime import datetime, timedelta

import httpx
import pytest
import respx

from horae.config import Settings
from horae.llm import extract_event_llm
from horae.parser import ParseResult

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        radicale_url="http://localhost:5232",
        radicale_username="test",
        radicale_password="test",  # type: ignore[arg-type]
        ollama_url="http://localhost:11434",
        ollama_model="llama3.2",
    )


@pytest.fixture
def reference_date() -> datetime:
    return datetime(2026, 3, 31, 12, 0)


@respx.mock
async def test_successful_extraction(settings: Settings, reference_date: datetime) -> None:
    respx.post(OLLAMA_CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "message": {
                    "content": '{"summary": "Dentist", "date": "2026-04-03", "time": "15:00", "duration_minutes": 60}'
                }
            },
        )
    )

    result = await extract_event_llm("Dentist on April 3", reference_date, settings)

    assert result is not None
    assert result == ParseResult(
        summary="Dentist",
        dtstart=datetime(2026, 4, 3, 15, 0),
        dtend=datetime(2026, 4, 3, 16, 0),
    )


@respx.mock
async def test_malformed_json_returns_none(settings: Settings, reference_date: datetime) -> None:
    respx.post(OLLAMA_CHAT_URL).mock(
        return_value=httpx.Response(200, json={"message": {"content": "I don't understand"}}),
    )

    result = await extract_event_llm("gibberish input", reference_date, settings)

    assert result is None


@respx.mock
async def test_timeout_returns_none(settings: Settings, reference_date: datetime) -> None:
    respx.post(OLLAMA_CHAT_URL).mock(side_effect=httpx.ReadTimeout("timed out"))

    result = await extract_event_llm("Dentist tomorrow", reference_date, settings)

    assert result is None


@respx.mock
async def test_missing_fields_returns_none(settings: Settings, reference_date: datetime) -> None:
    respx.post(OLLAMA_CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            json={"message": {"content": '{"title": "something"}'}},
        ),
    )

    result = await extract_event_llm("something", reference_date, settings)

    assert result is None


@respx.mock
async def test_connection_error_returns_none(settings: Settings, reference_date: datetime) -> None:
    respx.post(OLLAMA_CHAT_URL).mock(side_effect=httpx.ConnectError("connection refused"))

    result = await extract_event_llm("Dentist tomorrow", reference_date, settings)

    assert result is None


@respx.mock
async def test_null_time_defaults_to_0900(settings: Settings, reference_date: datetime) -> None:
    respx.post(OLLAMA_CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "message": {
                    "content": '{"summary": "Team meeting", "date": "2026-04-01", "time": null, "duration_minutes": 90}'
                }
            },
        )
    )

    result = await extract_event_llm("Team meeting on April 1", reference_date, settings)

    assert result is not None
    assert result.summary == "Team meeting"
    assert result.dtstart == datetime(2026, 4, 1, 9, 0)
    assert result.dtend - result.dtstart == timedelta(minutes=90)
