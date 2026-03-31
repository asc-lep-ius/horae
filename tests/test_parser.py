from datetime import datetime, timedelta

import pytest

from horae.parser import ParseResult, parse_event_text

REF_DATE = datetime(2026, 3, 30, 12, 0)


class TestParseEventText:
    """Core parsing: date extraction + title extraction."""

    @pytest.mark.parametrize(
        ("text", "expected_summary_substr", "expected_hour"),
        [
            ("dentist Friday 3pm", "dentist", 15),
            ("lunch 2pm", "lunch", 14),
            ("meeting tomorrow at 10:00", "meeting", 10),
        ],
        ids=["english-day-time", "english-time-only", "english-tomorrow"],
    )
    def test_english_dates(self, text: str, expected_summary_substr: str, expected_hour: int) -> None:
        result = parse_event_text(text, reference_date=REF_DATE)

        assert result is not None
        assert expected_summary_substr.lower() in result.summary.lower()
        assert result.dtstart.hour == expected_hour

    @pytest.mark.parametrize(
        ("text", "expected_summary_substr", "expected_hour"),
        [
            pytest.param(
                "Zahnarzt Freitag 15 Uhr",
                "Zahnarzt",
                15,
                marks=pytest.mark.xfail(reason="dateparser German support"),
                id="german-day-time",
            ),
            pytest.param(
                "Abendessen morgen um 19 Uhr",
                "Abendessen",
                19,
                marks=pytest.mark.xfail(reason="dateparser German support"),
                id="german-tomorrow",
            ),
        ],
    )
    def test_german_dates(self, text: str, expected_summary_substr: str, expected_hour: int) -> None:
        result = parse_event_text(text, reference_date=REF_DATE)

        assert result is not None
        assert expected_summary_substr.lower() in result.summary.lower()
        assert result.dtstart.hour == expected_hour


class TestParseEventTextEdgeCases:
    """No-date, empty, date-only inputs."""

    @pytest.mark.parametrize(
        "text",
        ["buy groceries", ""],
        ids=["no-date", "empty-string"],
    )
    def test_returns_none_when_no_date(self, text: str) -> None:
        assert parse_event_text(text, reference_date=REF_DATE) is None

    def test_date_only_returns_parse_result(self) -> None:
        result = parse_event_text("Friday", reference_date=REF_DATE)

        assert result is not None
        assert isinstance(result, ParseResult)
        assert result.summary  # non-empty (may be "Event" fallback)


class TestDuration:
    """dtend = dtstart + duration."""

    def test_default_duration_60_minutes(self) -> None:
        result = parse_event_text("dentist Friday 3pm", reference_date=REF_DATE)

        assert result is not None
        assert result.dtend == result.dtstart + timedelta(minutes=60)

    def test_custom_duration(self) -> None:
        result = parse_event_text("dentist Friday 3pm", reference_date=REF_DATE, default_duration_minutes=30)

        assert result is not None
        assert result.dtend == result.dtstart + timedelta(minutes=30)


class TestParseResultImmutability:
    """ParseResult is a frozen dataclass."""

    def test_frozen(self) -> None:
        result = parse_event_text("dentist Friday 3pm", reference_date=REF_DATE)
        assert result is not None

        with pytest.raises(AttributeError):
            result.summary = "hacked"  # type: ignore[misc]
