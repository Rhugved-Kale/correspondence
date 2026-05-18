"""
Calendar client.

Smaller than Gmail because Calendar's data shape is already clean. We pull
two windows of events:

  - Past 90 days, for co-attendance signal during ranking. Someone you've
    been in three meetings with this quarter is more important than someone
    whose only thread is a years-old reply chain.
  - Future 30 days, for the "upcoming meeting prep" feature surfaced in the
    artifact. We'll wire that into the agents later.

We deliberately don't pull years of calendar history. The signal/noise gets
worse and the data volume doesn't reward the effort.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from backend.utils.logging import get_logger


log = get_logger(__name__)


@dataclass
class CalendarEvent:
    id: str
    summary: str
    start_utc: str
    end_utc: str
    attendees: list[str]   # email addresses, lowercased, organizer included
    is_past: bool


def fetch_events(
    creds: Credentials,
    past_days: int = 90,
    future_days: int = 30,
) -> list[CalendarEvent]:
    """
    Pull events in a [now - past_days, now + future_days] window from the
    primary calendar. Recurring events are expanded (`singleEvents=True`)
    so each occurrence shows up once.
    """
    service = build("calendar", "v3", credentials=creds)
    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=past_days)).isoformat()
    time_max = (now + timedelta(days=future_days)).isoformat()

    events: list[CalendarEvent] = []
    page_token: str | None = None

    while True:
        try:
            resp = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=250,
                    pageToken=page_token,
                )
                .execute()
            )
        except HttpError as e:
            log.error("Calendar list error: %s", e)
            return events

        for ev in resp.get("items", []) or []:
            normalized = _normalize_event(ev, now)
            if normalized:
                events.append(normalized)

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return events


def _normalize_event(ev: dict, now: datetime) -> CalendarEvent | None:
    """Pick out the fields we care about, drop all-day or malformed entries gracefully."""
    start = ev.get("start", {})
    end = ev.get("end", {})

    # All-day events use 'date' instead of 'dateTime'. For our purposes a
    # date-only event still has signal (someone scheduled time around you),
    # so we coerce to midnight UTC.
    start_str = start.get("dateTime") or start.get("date")
    end_str = end.get("dateTime") or end.get("date")
    if not start_str:
        return None

    try:
        start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
    except ValueError:
        return None

    # All-day events come through as date-only strings (e.g. "2026-05-18")
    # which parse as naive datetimes. Comparing a naive datetime to our
    # offset-aware `now` raises TypeError. Attach UTC explicitly so the
    # comparison below is well-defined. For an all-day event, "midnight UTC
    # on that day" is a reasonable anchor; we're using this purely to
    # bucket past vs future, not to display.
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)

    attendees = [
        a["email"].lower()
        for a in ev.get("attendees", []) or []
        if a.get("email") and not a.get("resource")
    ]

    return CalendarEvent(
        id=ev.get("id", ""),
        summary=ev.get("summary", "") or "(no title)",
        start_utc=start_str,
        end_utc=end_str or start_str,
        attendees=attendees,
        is_past=start_dt < now,
    )
