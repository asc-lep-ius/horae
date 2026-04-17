import json
import logging
import re
from datetime import datetime, timedelta

import httpx

from horae.config import Settings
from horae.parser import ParseResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_TEMPLATE = (
    "You are a calendar assistant. Extract event details from the user's text.\n"
    "Today's date is {date} ({weekday}).\n"
    "Return ONLY a JSON object with these fields:\n"
    '- "summary": event title (string)\n'
    '- "date": date in YYYY-MM-DD format\n'
    '- "time": time in HH:MM format (24h), or null if not specified\n'
    '- "duration_minutes": estimated duration in minutes (default 60)'
)

_TIMEOUT_SECONDS = 30.0

_CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences that Ollama sometimes wraps around JSON."""
    match = _CODE_BLOCK_RE.search(text)
    return match.group(1) if match else text


async def extract_event_llm(
    text: str,
    reference_date: datetime,
    settings: Settings,
) -> ParseResult | None:
    """Call a local Ollama instance to extract event details from text.

    Returns None on any failure (timeout, bad JSON, missing fields, etc.).
    """
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        date=reference_date.strftime("%Y-%m-%d"),
        weekday=reference_date.strftime("%A"),
    )
    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        "format": "json",
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{settings.ollama_url}/api/chat", json=payload)
            response.raise_for_status()

        raw_content = response.json()["message"]["content"]
        data = json.loads(_strip_code_fences(raw_content))

        summary: str = data["summary"]
        date_str: str = data["date"]
        time_str: str | None = data.get("time")
        duration: int = int(data.get("duration_minutes", settings.default_duration_minutes))

        parsed_date = datetime.strptime(date_str, "%Y-%m-%d")

        if time_str:
            parsed_time = datetime.strptime(time_str, "%H:%M")
            dtstart = parsed_date.replace(hour=parsed_time.hour, minute=parsed_time.minute)
        else:
            dtstart = parsed_date.replace(hour=9, minute=0)

        dtend = dtstart + timedelta(minutes=duration)

        return ParseResult(summary=summary, dtstart=dtstart, dtend=dtend)

    except Exception:
        logger.warning("LLM extraction failed for text: %s", text, exc_info=True)
        return None
