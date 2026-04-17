from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from pydantic import SecretStr

from horae.app import app, get_settings
from horae.config import Settings


@pytest.fixture
def settings_override() -> Iterator[Settings]:
    settings = Settings(
        radicale_url="http://test-radicale:5232",
        radicale_username="testuser",
        radicale_password=SecretStr("testpass"),
        default_calendar="personal",
        default_duration_minutes=60,
        ollama_url="http://test-ollama:11434",
        ollama_model="test-model",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings
    app.dependency_overrides.clear()


@pytest.fixture
async def async_client(settings_override: Settings) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
