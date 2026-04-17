"""TISS iCal feed sync to Radicale via CalDAV.

Fetches the TISS iCal feed, generates stable content-based UIDs
(TISS regenerates UIDs on every fetch), diffs against the target
Radicale calendar, and applies create/update/delete operations.
"""

from __future__ import annotations

import hashlib
import logging
import sys
from dataclasses import dataclass, field
from typing import Any

import caldav
import httpx
import icalendar
from filelock import FileLock, Timeout

from horae.config import Settings

log = logging.getLogger(__name__)

LOCK_PATH = "/tmp/horae-sync.lock"
PRODID = "-//Horae//TISS Sync//EN"


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.created + self.updated + self.unchanged + self.deleted


# ---------------------------------------------------------------------------
# iCal helpers
# ---------------------------------------------------------------------------


def _stable_uid(summary: str, dtstart: str, dtend: str) -> str:
    """Generate a deterministic UID from event content fields."""
    payload = f"{summary}|{dtstart}|{dtend}"
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"horae-{digest}"


def _dt_to_str(dt: Any) -> str:
    """Normalise an icalendar date/datetime to a comparable string."""
    if hasattr(dt, "dt"):
        dt = dt.dt
    return str(dt)


def _extract_timezones(cal: icalendar.Calendar) -> dict[str, icalendar.Component]:
    """Return a {tzid: VTIMEZONE} mapping from the parsed calendar."""
    tzmap: dict[str, icalendar.Component] = {}
    for component in cal.walk("VTIMEZONE"):
        tzid = str(component.get("TZID", ""))
        if tzid:
            tzmap[tzid] = component
    return tzmap


def _event_tzids(vevent: icalendar.Component) -> set[str]:
    """Collect all TZID references from an event's date properties."""
    tzids: set[str] = set()
    for prop_name in ("DTSTART", "DTEND"):
        prop = vevent.get(prop_name)
        if prop and hasattr(prop, "params"):
            tzid = prop.params.get("TZID")
            if tzid:
                tzids.add(str(tzid))
    return tzids


def _build_vcalendar(vevent: icalendar.Component, tzmap: dict[str, icalendar.Component]) -> bytes:
    """Wrap a VEVENT in a standalone VCALENDAR with required VTIMEZONE(s)."""
    cal = icalendar.Calendar()
    cal.add("VERSION", "2.0")
    cal.add("PRODID", PRODID)

    for tzid in _event_tzids(vevent):
        if tzid in tzmap:
            cal.add_component(tzmap[tzid])

    cal.add_component(vevent)
    return cal.to_ical()


# ---------------------------------------------------------------------------
# Feed parsing
# ---------------------------------------------------------------------------


def _fetch_feed(url: str) -> bytes:
    """Download the iCal feed."""
    resp = httpx.get(url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def _parse_feed(raw: bytes) -> tuple[dict[str, icalendar.Component], dict[str, icalendar.Component]]:
    """Parse the iCal feed into {stable_uid: VEVENT} and timezone map.

    TISS UIDs are unstable (regenerated on every fetch). We group events
    by their original UID first (to associate RECURRENCE-ID overrides with
    the correct series), then compute a stable content-hash UID for each
    individual occurrence.
    """
    cal = icalendar.Calendar.from_ical(raw)
    tzmap = _extract_timezones(cal)

    # Group raw VEVENTs by original UID (handles recurring series)
    uid_groups: dict[str, list[icalendar.Component]] = {}
    for component in cal.walk("VEVENT"):
        original_uid = str(component.get("UID", ""))
        uid_groups.setdefault(original_uid, []).append(component)

    events: dict[str, icalendar.Component] = {}
    for _original_uid, group in uid_groups.items():
        for vevent in group:
            summary = str(vevent.get("SUMMARY", ""))
            dtstart = _dt_to_str(vevent.get("DTSTART"))
            dtend = _dt_to_str(vevent.get("DTEND", vevent.get("DTSTART")))
            stable = _stable_uid(summary, dtstart, dtend)

            # Replace the UID in the component so CalDAV stores it
            vevent["UID"] = stable
            events[stable] = vevent

    return events, tzmap


# ---------------------------------------------------------------------------
# CalDAV interaction
# ---------------------------------------------------------------------------


def _connect(settings: Settings) -> Any:
    return caldav.DAVClient(  # pyright: ignore[reportCallIssue]
        url=settings.radicale_url,
        username=settings.radicale_username,
        password=settings.radicale_password.get_secret_value(),
    )


def _find_calendar(principal: Any, name: str) -> Any:
    for cal in principal.calendars():
        if cal.name.lower() == name.lower():
            return cal
    raise ValueError(f"Calendar '{name}' not found")


def _existing_uids(calendar: Any) -> dict[str, Any]:
    """Return {uid: caldav_event} for all events in the calendar."""
    mapping: dict[str, Any] = {}
    for event in calendar.events():
        try:
            parsed = icalendar.Calendar.from_ical(event.data)
            for component in parsed.walk("VEVENT"):
                uid = str(component.get("UID", ""))
                if uid:
                    mapping[uid] = event
                    break
        except Exception:
            log.warning("Failed to parse existing event, skipping: %s", event.url)
    return mapping


# ---------------------------------------------------------------------------
# Core sync
# ---------------------------------------------------------------------------


def sync_tiss(settings: Settings) -> SyncResult:
    """Fetch TISS feed and sync to Radicale. Returns sync statistics."""
    if not settings.tiss_ical_url:
        raise ValueError("HORAE_TISS_ICAL_URL is not configured")

    result = SyncResult()

    log.info("Fetching TISS feed from %s", settings.tiss_ical_url)
    raw = _fetch_feed(settings.tiss_ical_url)
    feed_events, tzmap = _parse_feed(raw)
    log.info("Parsed %d events from feed", len(feed_events))

    client = _connect(settings)
    principal = client.principal()  # pyright: ignore[reportAttributeAccessIssue]
    calendar = _find_calendar(principal, settings.sync_calendar)

    existing = _existing_uids(calendar)
    log.info("Found %d existing events in calendar '%s'", len(existing), settings.sync_calendar)

    feed_uids = set(feed_events.keys())
    existing_uids_set = set(existing.keys())

    # Create or update
    for uid, vevent in feed_events.items():
        ical_data = _build_vcalendar(vevent, tzmap)
        if uid not in existing_uids_set:
            try:
                calendar.save_event(ical_data)
                result.created += 1
                log.debug("Created: %s (%s)", vevent.get("SUMMARY", ""), uid)
            except Exception as exc:
                log.error("Failed to create event %s: %s", uid, exc)
                result.errors.append(f"create {uid}: {exc}")
        else:
            # Compare raw ical content to decide if update is needed
            existing_event = existing[uid]
            existing_data = existing_event.data
            if _content_changed(existing_data, vevent):
                try:
                    existing_event.data = ical_data.decode()
                    existing_event.save()
                    result.updated += 1
                    log.debug("Updated: %s (%s)", vevent.get("SUMMARY", ""), uid)
                except Exception as exc:
                    log.error("Failed to update event %s: %s", uid, exc)
                    result.errors.append(f"update {uid}: {exc}")
            else:
                result.unchanged += 1

    # Delete events no longer in feed
    for uid in existing_uids_set - feed_uids:
        # Only delete events we manage (horae- prefix)
        if not uid.startswith("horae-"):
            continue
        try:
            existing[uid].delete()
            result.deleted += 1
            log.debug("Deleted: %s", uid)
        except Exception as exc:
            log.error("Failed to delete event %s: %s", uid, exc)
            result.errors.append(f"delete {uid}: {exc}")

    log.info(
        "Sync complete — created: %d, updated: %d, unchanged: %d, deleted: %d",
        result.created,
        result.updated,
        result.unchanged,
        result.deleted,
    )
    return result


def _content_changed(existing_data: str, new_vevent: icalendar.Component) -> bool:
    """Check if an event's meaningful content has changed."""
    try:
        existing_cal = icalendar.Calendar.from_ical(existing_data)
        for component in existing_cal.walk("VEVENT"):
            for prop in ("SUMMARY", "DTSTART", "DTEND", "LOCATION", "DESCRIPTION"):
                old_val = str(component.get(prop, ""))
                new_val = str(new_vevent.get(prop, ""))
                if old_val != new_val:
                    return True
            return False
    except Exception:
        log.debug("Failed to compare existing event data, treating as changed", exc_info=True)
        return True
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    """CLI entrypoint. Returns exit code: 0=success, 1=error, 2=lock held."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        settings = Settings()  # pyright: ignore[reportCallIssue]
    except Exception as exc:
        log.error("Configuration error: %s", exc)
        return 1

    try:
        lock = FileLock(LOCK_PATH, timeout=0)
        with lock:
            result = sync_tiss(settings)
            if result.errors:
                log.warning("Sync finished with %d error(s)", len(result.errors))
                return 1
            return 0
    except Timeout:
        log.warning("Another sync is already running (lock: %s)", LOCK_PATH)
        return 2
    except Exception as exc:
        log.error("Sync failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
