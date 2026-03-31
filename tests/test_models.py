from datetime import UTC, datetime

from horae.models import CalendarInfo, EventRequest, EventResponse, HealthResponse


class TestEventRequest:
    def test_text_is_required(self) -> None:
        req = EventRequest(text="Lunch with Alice tomorrow at noon")

        assert req.text == "Lunch with Alice tomorrow at noon"

    def test_calendar_defaults_to_none(self) -> None:
        req = EventRequest(text="standup")

        assert req.calendar is None

    def test_calendar_can_be_set(self) -> None:
        req = EventRequest(text="standup", calendar="work")

        assert req.calendar == "work"

    def test_empty_text_is_valid(self) -> None:
        req = EventRequest(text="")

        assert req.text == ""


class TestEventResponse:
    def test_round_trip_serialization(self) -> None:
        start = datetime(2026, 4, 1, 10, 0, tzinfo=UTC)
        end = datetime(2026, 4, 1, 11, 0, tzinfo=UTC)

        resp = EventResponse(
            summary="Team standup",
            dtstart=start,
            dtend=end,
            calendar="work",
            uid="abc-123",
        )

        data = resp.model_dump(mode="json")
        restored = EventResponse.model_validate(data)

        assert restored.summary == "Team standup"
        assert restored.dtstart == start
        assert restored.dtend == end
        assert restored.calendar == "work"
        assert restored.uid == "abc-123"

    def test_iso8601_in_json(self) -> None:
        start = datetime(2026, 4, 1, 10, 0, tzinfo=UTC)
        end = datetime(2026, 4, 1, 11, 0, tzinfo=UTC)

        resp = EventResponse(
            summary="meeting",
            dtstart=start,
            dtend=end,
            calendar="personal",
            uid="xyz",
        )

        data = resp.model_dump(mode="json")

        assert isinstance(data["dtstart"], str)
        assert "2026-04-01" in data["dtstart"]


class TestCalendarInfo:
    def test_name_and_path_required(self) -> None:
        info = CalendarInfo(name="Work", path="/user/work/")

        assert info.name == "Work"
        assert info.path == "/user/work/"


class TestHealthResponse:
    def test_status_field(self) -> None:
        resp = HealthResponse(status="ok")

        assert resp.status == "ok"
