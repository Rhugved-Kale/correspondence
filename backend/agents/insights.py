"""
Insights composer.

After the per-person agent pipeline finishes, this module composes
three top-level surfaces that complement the per-person wiki:

  1. Forgotten threads: open threads across all top-10 people, ranked
     by how stale the relationship has gotten. The point is to make
     the user say "huh, I should follow up on that."

  2. Upcoming meetings: the next handful of calendar events. Each
     event gets a small prep blurb if any attendee appears in our
     top-10 list; without a match it still shows up but without prep.
     The point is for "Upcoming" to mirror the user's real calendar,
     with prep as a bonus rather than a gate.

  3. About-you stats: aggregate signals about how the user uses email
     in their inbox. The "what this AI found about me that I didn't
     even know" surface from the brief. All numeric, no LLM
     hallucinations.

All three are deterministic. The narrative bits already come out of
the per-person LLM stage; this module is pure aggregation and ranking
over the existing data.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def compose_insights(
    db_path: Path,
    payloads: list[dict],
    my_email: str,
) -> dict:
    """
    Build the top-level dashboard insights from the per-person payloads
    and the SQLite cache. Returns a dict ready to serialize as
    insights.json.

    Shape:
      {
        "generated_at_utc": str,
        "my_email": str,
        "forgotten": [ ... up to 10 entries ... ],
        "upcoming": [ ... up to 5 entries ... ],
        "about_you": { ... aggregate stats ... }
      }

    Each section can be empty independently if there's no relevant data
    (e.g. no upcoming meetings on the calendar). The frontend renders
    only the sections that have content.
    """
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "my_email": my_email,
        "forgotten": _compose_forgotten(payloads),
        "upcoming": _compose_upcoming(db_path, payloads, my_email),
        "about_you": _compose_about_you(db_path, my_email),
    }


# --- Forgotten threads ----------------------------------------------------


def _compose_forgotten(payloads: list[dict]) -> list[dict]:
    """
    Flatten open_threads across all people and rank by staleness.

    Staleness signal: how long since the user's last substantive
    interaction with the person who owns this thread. We compute this
    from the per-person timeline's last event date. People we haven't
    talked to in months bubble up. Highly-active relationships sink.

    Each output entry has the thread text, the person it belongs to,
    and a human-readable freshness label so the frontend doesn't have
    to redo the date math.
    """
    entries: list[dict] = []
    now = datetime.now(timezone.utc)

    for p in payloads:
        person_id = p.get("id")
        person_name = p.get("name") or p.get("email", "")
        threads = (p.get("prep") or {}).get("open_threads") or []
        if not threads:
            continue

        # Use the most recent timeline event date as proxy for "last
        # substantive contact." Falls back to None if the timeline is
        # empty, in which case we treat the threads as maximally stale.
        last_contact_date = _latest_timeline_date(p)
        days_since = (now - last_contact_date).days if last_contact_date else 9999

        for thread_text in threads:
            entries.append({
                "person_id": person_id,
                "person_name": person_name,
                "thread": thread_text,
                "days_since_last_contact": days_since,
                "freshness_label": _freshness_label(days_since),
            })

    # Oldest first. Ties broken by person rank (already implicit in the
    # order payloads come in). Cap at 10 entries to keep the surface
    # focused; this is the "10 most important you forgot" framing the
    # brief called out.
    entries.sort(key=lambda e: -e["days_since_last_contact"])
    return entries[:10]


def _latest_timeline_date(payload: dict) -> datetime | None:
    """Most recent date across a person's timeline events, parsed as UTC."""
    timeline = payload.get("timeline") or []
    latest: datetime | None = None
    for ev in timeline:
        d = ev.get("date")
        if not d:
            continue
        try:
            # Timeline dates come as YYYY-MM-DD from the agent. Treat as UTC midnight.
            dt = datetime.fromisoformat(d).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if latest is None or dt > latest:
            latest = dt
    return latest


def _freshness_label(days_since: int) -> str:
    """Convert a day count to friendly relative-time text."""
    if days_since < 7:
        return f"{days_since} days ago"
    if days_since < 30:
        weeks = days_since // 7
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    if days_since < 365:
        months = days_since // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = days_since // 365
    return f"{years} year{'s' if years != 1 else ''} ago"


# --- Upcoming meetings ----------------------------------------------------


def _compose_upcoming(
    db_path: Path,
    payloads: list[dict],
    my_email: str,
) -> list[dict]:
    """
    Find calendar events in the next 14 days and surface them, with
    prep context attached when at least one attendee matches our top-10
    people.

    We show meetings even when no attendee is in the top-10 because
    the user expects "Upcoming" to reflect their actual calendar; an
    empty view when they clearly have meetings would feel broken. The
    prep blurb is the bonus, not the gate.

    14-day window cap because the user is unlikely to care about prep
    for a meeting three months out, and the brief asked specifically for
    the next handful of meetings.
    """
    by_email = {p["email"].lower(): p for p in payloads if p.get("email")}

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=14)

    # We pull all events and filter in Python rather than using a SQL
    # range query on start_utc. The stored timestamps come straight from
    # Google as ISO 8601 with the user's local timezone offset (e.g.
    # "...T15:30:00-07:00"). Naive string comparison breaks across
    # different offsets because "-07:00" sorts before "+00:00" lexically.
    # Parsing into aware datetimes is the only correct way to compare.
    upcoming: list[dict] = []
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, summary, start_utc, end_utc, attendees
                FROM calendar_events
                ORDER BY start_utc ASC
                """
            ).fetchall()
    except sqlite3.Error as e:
        log.warning("could not read calendar_events: %s", e)
        return []

    for row in rows:
        # Parse start time as timezone-aware. If parsing fails for any
        # reason (corrupted row, unexpected format), skip the event
        # rather than crashing the whole composer.
        start_raw = row["start_utc"]
        if not start_raw:
            continue
        try:
            start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
            if start_dt.tzinfo is None:
                # All-day events come as date strings; treat as UTC midnight.
                start_dt = start_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        if start_dt < now or start_dt > horizon:
            continue

        # Attendees stored as a comma-separated string of emails. The
        # ingest layer chose this format because the calendar table is
        # small and we never query into the list, just read it whole.
        attendees_raw = row["attendees"] or ""
        attendees = [a.strip() for a in attendees_raw.split(",") if a.strip()]

        # Lowercase + skip yourself + drop empties.
        attendee_emails = [
            a.lower() for a in attendees
            if a.lower() != my_email.lower()
        ]

        # Look for a top-10 match to anchor a prep blurb. The meeting
        # still shows up even with no match; we just won't have anything
        # to say about it beyond title + time.
        matched_people = [by_email[e] for e in attendee_emails if e in by_email]
        anchor = (
            min(matched_people, key=lambda p: p.get("rank_position", 99))
            if matched_people else None
        )
        anchor_prep = (anchor.get("prep") or {}) if anchor else {}

        upcoming.append({
            "event_id": row["id"],
            "summary": row["summary"] or "(no title)",
            "start_utc": row["start_utc"],
            "end_utc": row["end_utc"],
            "location": "",
            "anchor_person_id": anchor["id"] if anchor else None,
            "anchor_person_name": (anchor.get("name") or anchor["email"]) if anchor else None,
            "other_attendees_count": max(0, len(attendee_emails) - (1 if anchor else 0)),
            "prep_blurb": anchor_prep.get("last_substantive_interaction", "") if anchor else "",
            "talking_points": (anchor_prep.get("three_talking_points") or [])[:2] if anchor else [],
        })

        if len(upcoming) >= 5:
            break

    return upcoming


# --- About you ------------------------------------------------------------


def _compose_about_you(db_path: Path, my_email: str) -> dict:
    """
    Aggregate stats about how the user uses email. These are the
    "things you didn't know about yourself" insights the brief flagged
    as worth surfacing for sharing.

    All deterministic SQL. No LLM, no risk of hallucination. Each
    number can be defended by re-running the query.
    """
    stats: dict[str, Any] = {}

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Total messages in the ingestion window.
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM messages"
            ).fetchone()
            stats["total_messages"] = int(row["n"] or 0)

            # Sent vs received split.
            sent_row = conn.execute(
                "SELECT COUNT(*) AS n FROM messages WHERE is_outgoing = 1"
            ).fetchone()
            stats["sent_messages"] = int(sent_row["n"] or 0)
            stats["received_messages"] = stats["total_messages"] - stats["sent_messages"]

            # Number of distinct correspondents we have any back-and-forth with.
            # "Correspondent" = anyone with at least one message in either direction.
            row = conn.execute(
                """
                SELECT COUNT(*) AS n FROM contacts
                WHERE msg_in_count + msg_out_count > 0
                """
            ).fetchone()
            stats["distinct_correspondents"] = int(row["n"] or 0)

            # People you actually replied to (gives the "real conversations" count).
            row = conn.execute(
                """
                SELECT COUNT(*) AS n FROM contacts
                WHERE msg_out_count > 0
                """
            ).fetchone()
            stats["people_you_replied_to"] = int(row["n"] or 0)

            # Window covered (days from first to last message in cache).
            row = conn.execute(
                """
                SELECT MIN(date_utc) AS first, MAX(date_utc) AS last
                FROM messages
                """
            ).fetchone()
            if row and row["first"] and row["last"]:
                try:
                    first = datetime.fromisoformat(row["first"].replace("Z", "+00:00"))
                    last = datetime.fromisoformat(row["last"].replace("Z", "+00:00"))
                    stats["window_days"] = max(1, (last - first).days)
                    stats["window_start_utc"] = row["first"]
                    stats["window_end_utc"] = row["last"]
                except (ValueError, AttributeError):
                    stats["window_days"] = None

            # Most active week. SQLite doesn't have a clean strftime for
            # "year-week" but '%Y-%W' is close enough for our purposes.
            row = conn.execute(
                """
                SELECT strftime('%Y-%W', date_utc) AS week, COUNT(*) AS n
                FROM messages
                WHERE date_utc IS NOT NULL
                GROUP BY week
                ORDER BY n DESC
                LIMIT 1
                """
            ).fetchone()
            if row and row["week"]:
                stats["busiest_week"] = {
                    "week_id": row["week"],
                    "message_count": int(row["n"]),
                    "human_label": _human_week_label(row["week"]),
                }

            # Top 3 senders (so you can call out who you hear from most).
            # Skip yourself and skip anyone with zero outgoing from you,
            # which filters out newsletter-only relationships.
            rows = conn.execute(
                """
                SELECT email, display_name, msg_in_count
                FROM contacts
                WHERE LOWER(email) != ?
                  AND msg_in_count > 0
                  AND msg_out_count > 0
                ORDER BY msg_in_count DESC
                LIMIT 3
                """,
                (my_email.lower(),),
            ).fetchall()
            stats["top_senders"] = [
                {
                    "email": r["email"],
                    "name": r["display_name"] or r["email"].split("@", 1)[0],
                    "count": int(r["msg_in_count"]),
                }
                for r in rows
            ]

            # Domains: count unique non-personal domains among contacts.
            # Rough proxy for "how many orgs touched your inbox."
            row = conn.execute(
                """
                SELECT COUNT(DISTINCT LOWER(SUBSTR(email, INSTR(email, '@') + 1))) AS n
                FROM contacts
                WHERE msg_in_count + msg_out_count > 0
                """
            ).fetchone()
            stats["distinct_domains"] = int(row["n"] or 0)

    except sqlite3.Error as e:
        log.warning("about_you stats failed: %s", e)
        return {"error": "stats unavailable"}

    return stats


def _human_week_label(week_id: str) -> str:
    """
    Convert "2026-15" (year-week, ISO-ish via strftime) into a friendly
    label like "week of Apr 6, 2026". Approximate; we anchor to the
    Monday of that week.
    """
    try:
        year_str, week_str = week_id.split("-")
        year = int(year_str)
        week = int(week_str)
        # strftime %W counts Mondays from the first Monday of the year.
        # Compute the date of the Monday in that week.
        jan1 = datetime(year, 1, 1, tzinfo=timezone.utc)
        # Days until first Monday (0 if jan1 is Monday).
        days_to_first_monday = (7 - jan1.weekday()) % 7
        first_monday = jan1 + timedelta(days=days_to_first_monday)
        target = first_monday + timedelta(weeks=week - 1)
        return f"week of {target.strftime('%b %-d, %Y')}"
    except (ValueError, AttributeError):
        return week_id
