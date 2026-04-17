from dataclasses import dataclass
from datetime import datetime, timedelta

from dateparser.search import search_dates

DATEPARSER_SETTINGS: dict[str, object] = {
    "PREFER_DATES_FROM": "future",
    "RETURN_AS_TIMEZONE_AWARE": False,
}


@dataclass(frozen=True)
class ParseResult:
    summary: str
    dtstart: datetime
    dtend: datetime


def parse_event_text(
    text: str,
    reference_date: datetime | None = None,
    default_duration_minutes: int = 60,
) -> ParseResult | None:
    """Extract a calendar event from natural language text."""
    if not text.strip():
        return None

    settings = dict(DATEPARSER_SETTINGS)
    if reference_date is not None:
        settings["RELATIVE_BASE"] = reference_date

    matches = search_dates(text, languages=["en", "de"], settings=settings)
    if not matches:
        return None

    # Take the last match — typically the most specific date fragment
    matched_text, dtstart = matches[-1]

    # Title: remove matched date span, clean up
    title = text.replace(matched_text, "", 1).strip()
    title = "Event" if not title else title[0].upper() + title[1:]

    dtend = dtstart + timedelta(minutes=default_duration_minutes)

    return ParseResult(summary=title, dtstart=dtstart, dtend=dtend)
