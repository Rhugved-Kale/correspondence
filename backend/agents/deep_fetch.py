"""
Deep history fetcher.

Once ranking picks the top N people, we go back to Gmail and pull each one's
full history (up to MAX_EMAILS_PER_PERSON). The general ingestion pass only
covers the last RANKING_WINDOW_DAYS (180 by default) so it's good for finding
who's important, but bad for telling their story. A relationship that started
in 2022 needs the 2022 emails to produce a real timeline.

This module is intentionally a thin wrapper around the gmail client:

  - Build a per-person Gmail query (`from:X OR to:X`)
  - Page through up to MAX_EMAILS_PER_PERSON message ids
  - For ids not already cached, fetch and upsert
  - Return the full set of messages for that person, sorted chronologically

Idempotency: re-running on the same cache produces the same result without
re-fetching messages we already have. This matters because we'll iterate
during development and don't want to burn Gmail quota each time.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from google.oauth2.credentials import Credentials

from backend.clients import gmail as gmail_client
from backend.storage.db import connect
from backend.storage.ingest import _upsert_message
from backend.utils.logging import get_logger


log = get_logger(__name__)


@dataclass
class PersonMessages:
    """All cached messages for one person, plus a few derived stats."""
    email: str
    display_name: str
    messages: list[dict]   # sorted oldest -> newest
    first_date: str        # ISO-8601
    last_date: str         # ISO-8601


def deep_fetch_person(
    creds: Credentials,
    db_path: Path,
    email: str,
    max_emails: int,
) -> PersonMessages:
    """
    Pull this person's full email history (up to max_emails). Caches new
    messages into SQLite. Returns the full set sorted chronologically.

    We always query Gmail in case there are messages outside our previous
    ingestion window. The cache means we never re-fetch ids we already have.
    """
    my_email = gmail_client.get_my_email(creds)
    query = f"from:{email} OR to:{email}"

    # Page through ids, deduping against what's already cached.
    already_cached = _cached_ids_for(db_path, email)
    new_ids: list[str] = []

    for msg_id, _thread_id in gmail_client.list_message_ids(creds, query, max_results=max_emails):
        if msg_id not in already_cached:
            new_ids.append(msg_id)
        if len(new_ids) + len(already_cached) >= max_emails:
            break

    if new_ids:
        log.info("fetching %d new messages for %s", len(new_ids), email)
    else:
        log.info("no new messages for %s; %d already cached", email, len(already_cached))

    # Fetch the new ones and write them into the messages cache. Note: we
    # deliberately do NOT update the contacts table here. The contacts
    # aggregate is built during full ingestion (where we see all messages),
    # and deep_fetch only sees one person's history in isolation. If we
    # tried to upsert per-person aggregates here, we'd overwrite the
    # authoritative counts with partial ones, breaking ranking on the
    # next run. Just cache the new messages and move on; load_person_messages
    # below will read what we need straight from the messages table.
    with connect(db_path) as conn:
        for msg_id in new_ids:
            msg = gmail_client.fetch_message(creds, msg_id, my_email)
            if msg is None:
                continue
            _upsert_message(conn, msg)

    # Now pull the full set back out of the cache, normalized.
    return load_person_messages(db_path, email)


def load_person_messages(db_path: Path, email: str) -> PersonMessages:
    """Read this person's cached messages, sorted oldest to newest."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, thread_id, date_utc, subject, from_email, from_name,
                   to_emails, body, snippet, is_outgoing
            FROM messages
            WHERE from_email = ? OR to_emails LIKE ?
            ORDER BY date_utc ASC
            """,
            (email, f"%{email}%"),
        ).fetchall()

    messages: list[dict] = []
    display_name = ""
    first_date = ""
    last_date = ""

    for r in rows:
        # Filter out cases where the LIKE match was a substring inside a
        # longer address (e.g. searching for "joe@x.com" matched "vjoe@x.com").
        # Re-check the to_emails comma list properly.
        if r["from_email"] != email:
            to_list = (r["to_emails"] or "").split(",")
            if email not in [t.strip() for t in to_list]:
                continue

        if not display_name and r["from_email"] == email and r["from_name"]:
            display_name = r["from_name"]

        msg = {
            "id": r["id"],
            "thread_id": r["thread_id"],
            "date_utc": r["date_utc"],
            "subject": r["subject"] or "",
            "from_email": r["from_email"],
            "from_name": r["from_name"] or "",
            "body": r["body"] or "",
            "snippet": r["snippet"] or "",
            "is_outgoing": bool(r["is_outgoing"]),
        }
        messages.append(msg)
        if not first_date:
            first_date = msg["date_utc"]
        last_date = msg["date_utc"]

    return PersonMessages(
        email=email,
        display_name=display_name,
        messages=messages,
        first_date=first_date,
        last_date=last_date,
    )


# --- internals -----------------------------------------------------------------


def _cached_ids_for(db_path: Path, email: str) -> set[str]:
    """Set of message ids already cached for this email (either side)."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id FROM messages
            WHERE from_email = ? OR to_emails LIKE ?
            """,
            (email, f"%{email}%"),
        ).fetchall()
    return {r["id"] for r in rows}
