"""
Load the demo corpus into SQLite.

Takes the hand-written and generated threads plus the calendar fixture and
writes them into the same schema Gmail ingestion writes into, so everything
downstream (ranking, deep fetch, the agent pipeline, insights) runs against
the fixture without knowing it isn't a real inbox.

    python -m demo.load                    # writes to data/demo.db
    python -m demo.load --db data/cache.db # overwrite the real cache instead

The important property: this module fabricates messages and calendar events
and nothing else. The contacts aggregate, which is what ranking actually
scores, is rebuilt by ingest._rebuild_contacts_from_cache, the same function
a real run uses. If the fixture computed its own contact stats we would be
testing the fixture rather than the pipeline.

Message ids are deterministic (a hash of thread id plus position), so
reloading is an upsert and reruns are stable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from backend.storage.db import connect, init_db
from backend.storage.ingest import _rebuild_contacts_from_cache


DEMO_DIR = Path(__file__).resolve().parent
THREADS_DIR = DEMO_DIR / "threads"

WEEKDAYS = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}


def _msg_id(thread_id: str, index: int) -> str:
    return hashlib.sha1(f"{thread_id}:{index}".encode()).hexdigest()[:16]


def _resolve(handle: str, people: dict) -> tuple[str, str]:
    """handle -> (email, display_name). Noise senders arrive already as addresses."""
    if handle in people:
        return people[handle]["email"], people[handle]["name"]
    return handle, ""


def load_messages(db_path: Path, contacts: dict) -> int:
    people = contacts["people"]
    me_email = people[contacts["me"]]["email"]

    files = sorted(THREADS_DIR.glob("*.json"))
    if not files:
        raise SystemExit(f"no thread files in {THREADS_DIR}")

    total = 0
    with connect(db_path) as conn:
        for path in files:
            thread = json.loads(path.read_text())
            tid = thread["thread_id"]

            for i, m in enumerate(thread["messages"]):
                from_email, from_name = _resolve(m["from"], people)
                is_outgoing = from_email == me_email

                # Recipient is the other participant. These threads are all
                # two-party, which is a simplification the corpus commits to
                # deliberately: group threads would complicate the ranker's
                # reciprocity signal without making the artifact any better.
                others = [
                    _resolve(p, people)[0]
                    for p in thread["participants"]
                    if _resolve(p, people)[0] != from_email
                ]
                to_emails = ",".join(others) if others else me_email

                body = m["body"]
                conn.execute(
                    """
                    INSERT INTO messages (
                        id, thread_id, date_utc, subject, from_email, from_name,
                        to_emails, body, snippet, is_outgoing
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        body=excluded.body,
                        snippet=excluded.snippet
                    """,
                    (
                        _msg_id(tid, i),
                        tid,
                        m["date_utc"],
                        m.get("subject") or thread.get("subject") or "",
                        from_email,
                        from_name,
                        to_emails,
                        body,
                        body[:180].replace("\n", " "),
                        1 if is_outgoing else 0,
                    ),
                )
                total += 1

    return total


def _expand_calendar(cal: dict, contacts: dict, as_of: datetime) -> list[dict]:
    people = contacts["people"]
    me_email = people[contacts["me"]]["email"]
    events: list[dict] = []

    def emails(handles: list[str]) -> str:
        addrs = [me_email] + [people[h]["email"] for h in handles if h in people]
        return ",".join(addrs)

    for rule in cal.get("recurring", []):
        start = datetime.fromisoformat(rule["from"] + "T00:00:00-07:00")
        end = datetime.fromisoformat(rule["to"] + "T00:00:00-07:00")
        wanted = {WEEKDAYS[d] for d in rule["weekdays"]}
        skip = set(rule.get("skip", []))
        hh, mm = (int(x) for x in rule["time"].split(":"))

        day = start
        while day <= end:
            if day.weekday() in wanted and day.strftime("%Y-%m-%d") not in skip:
                s = day.replace(hour=hh, minute=mm)
                events.append({
                    "id": _msg_id(rule["summary"], int(s.timestamp())),
                    "summary": rule["summary"],
                    "start": s,
                    "end": s + timedelta(minutes=rule["duration_min"]),
                    "attendees": emails(rule["attendees"]),
                })
            day += timedelta(days=1)

    for ev in cal.get("one_off", []):
        # A cancelled meeting leaves no event on a real calendar. It is in
        # the fixture so the world stays legible to a human reading it, but
        # it must not reach the database or the pipeline will count a
        # meeting that never happened.
        if ev.get("cancelled"):
            continue
        s = datetime.fromisoformat(ev["start"])
        events.append({
            "id": _msg_id(ev["summary"], int(s.timestamp())),
            "summary": ev["summary"],
            "start": s,
            "end": s + timedelta(minutes=ev["duration_min"]),
            "attendees": emails(ev.get("attendees", [])),
        })

    for e in events:
        e["is_past"] = 1 if e["start"] < as_of else 0
    return events


def load_calendar(db_path: Path, contacts: dict, cal: dict, as_of: datetime) -> int:
    events = _expand_calendar(cal, contacts, as_of)
    with connect(db_path) as conn:
        for e in events:
            conn.execute(
                """
                INSERT INTO calendar_events (id, summary, start_utc, end_utc, attendees, is_past)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    summary=excluded.summary,
                    start_utc=excluded.start_utc,
                    end_utc=excluded.end_utc,
                    attendees=excluded.attendees,
                    is_past=excluded.is_past
                """,
                (
                    e["id"], e["summary"],
                    e["start"].isoformat(), e["end"].isoformat(),
                    e["attendees"], e["is_past"],
                ),
            )
    return len(events)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/demo.db")
    ap.add_argument("--fresh", action="store_true", help="delete the db first")
    args = ap.parse_args()

    db_path = Path(args.db)
    if args.fresh and db_path.exists():
        db_path.unlink()
        for suffix in ("-wal", "-shm"):
            extra = db_path.with_name(db_path.name + suffix)
            if extra.exists():
                extra.unlink()

    contacts = json.loads((DEMO_DIR / "contacts.json").read_text())
    cal = json.loads((DEMO_DIR / "calendar.json").read_text())
    as_of = datetime.fromisoformat(contacts["demo_as_of"] + "T23:59:59-07:00")
    me_email = contacts["people"][contacts["me"]]["email"]

    init_db(db_path)
    n_msgs = load_messages(db_path, contacts)
    n_events = load_calendar(db_path, contacts, cal, as_of)

    # Derived state comes from the real ingestion code, never from here.
    _rebuild_contacts_from_cache(db_path, me_email)

    with connect(db_path) as conn:
        n_contacts = conn.execute("SELECT COUNT(*) AS n FROM contacts").fetchone()["n"]
        n_reciprocal = conn.execute(
            "SELECT COUNT(*) AS n FROM contacts WHERE msg_out_count > 0"
        ).fetchone()["n"]
        upcoming = conn.execute(
            "SELECT COUNT(*) AS n FROM calendar_events WHERE is_past = 0"
        ).fetchone()["n"]

    print(f"db          {db_path}")
    print(f"messages    {n_msgs}")
    print(f"contacts    {n_contacts} ({n_reciprocal} with a reply from Priya)")
    print(f"events      {n_events} ({upcoming} after {contacts['demo_as_of']})")


if __name__ == "__main__":
    main()
