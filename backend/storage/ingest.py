"""
Ingestion: pull email and calendar into SQLite.

This is the boring-but-important phase. Two passes:

  Pass 1 (recency window): pull message ids in the last RANKING_WINDOW_DAYS,
         fetch each, write to messages, update contacts aggregate. This is
         what the ranking pass will score over.

  Pass 2 (deep history per person): runs later, after ranking. For each of
         the top N people, pull their full history up to MAX_EMAILS_PER_PERSON
         and ingest those too. That data feeds the agent pipeline.

Why split: ranking only needs recent signal, not 10 years of email. Doing
the deep pull only for the people who actually get featured saves a lot
of API calls and a lot of cache space.

Idempotency: messages.id is the primary key, so re-running is an upsert.
Calling ingest twice in a row produces the same DB state as calling once.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from google.oauth2.credentials import Credentials

from backend.clients import gmail as gmail_client
from backend.clients import calendar_client
from backend.config import Settings
from backend.storage.db import connect, init_db
from backend.utils.logging import get_logger


log = get_logger(__name__)


# Gmail has a strict per-user-per-minute quota (3,000 query units, where
# messages.get costs 5 units = 600 reads/min ceiling). Going parallel runs
# right into that ceiling on a moderately-sized inbox: 8 workers at ~300ms
# latency = ~26 req/s = ~1,600/min, well over the limit. We tried 20 and
# 8 workers with per-worker retry; both produced data loss because all
# workers share one quota and backing off one worker doesn't help if seven
# others keep slamming it.
#
# The right answer in this codebase is sequential fetching. It's slower
# (~300ms per message vs ~40ms theoretical parallel ceiling) but it cannot
# overrun the quota and cannot drop messages. First-run takes longer; every
# subsequent run is fast because the cache check skips already-fetched ids.
# This is a take-home build, so correctness matters more than first-run latency.
#
# A proper shared token-bucket rate limiter could let us go parallel at
# ~40 req/s sustainable, cutting first-run by ~5x. That's deferred work.
FETCH_WORKERS = 1


def ingest_recent_window(creds: Credentials, settings: Settings, db_path: Path) -> dict:
    """
    Pull every non-noise message in the recency window and ingest into SQLite.
    Returns a stats dict (messages_seen, contacts_seen) for the caller to log.

    Two passes:
      1. Enumerate message ids (cheap, paginated, single-threaded).
      2. Fetch the bodies for ids not already cached, in parallel.

    Re-running on the same cache only fetches new mail; the cache check
    between passes means we skip the network for messages we already have.
    """
    init_db(db_path)
    my_email = gmail_client.get_my_email(creds)
    log.info("ingesting recent window for %s", my_email)

    # Gmail query operators are the same as the web search box. We exclude
    # promotional and social tabs because they're 95% noise. `-in:chats`
    # drops Hangouts/Chat messages which aren't relevant.
    query = (
        f"newer_than:{settings.ranking_window_days}d "
        f"-category:promotions -category:social -in:chats"
    )

    # Pass 1: enumerate ids. This is fast (one paginated listing) and
    # serves as the master set of "messages that should be in the window."
    log.info("enumerating message ids in Gmail...")
    all_ids: list[str] = []
    for msg_id, _thread_id in gmail_client.list_message_ids(creds, query):
        all_ids.append(msg_id)
    log.info("found %d message ids in window", len(all_ids))

    # Cache check: only fetch ids we don't have yet. This is the difference
    # between "5 minutes" and "5 seconds" on re-ingestion.
    with connect(db_path) as conn:
        rows = conn.execute("SELECT id FROM messages").fetchall()
        cached_ids = {r["id"] for r in rows}
    to_fetch = [mid for mid in all_ids if mid not in cached_ids]
    already_cached = len(set(all_ids) & cached_ids)
    log.info("%d already cached, %d to fetch", already_cached, len(to_fetch))

    # Pass 2: parallel fetch. Each worker hits Gmail's messages.get for
    # one id. The googleapiclient is synchronous, so we use threads, not
    # asyncio. Threads work because the bottleneck is network I/O, where
    # the GIL is released during socket waits.
    contacts: dict[str, dict] = defaultdict(_empty_contact_row)
    fetched_count = 0

    if to_fetch:
        log.info("fetching %d messages with %d parallel workers", len(to_fetch), FETCH_WORKERS)
        # Hook into the API's status file so the frontend progress bar can
        # update while we fetch. We import locally to avoid a cycle when
        # this module is loaded from the CLI script (which doesn't need it).
        try:
            from backend.utils.progress import write_status, Phase
            _has_progress = True
        except ImportError:
            _has_progress = False

        with connect(db_path) as conn:
            with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
                futures = {
                    pool.submit(gmail_client.fetch_message, creds, mid, my_email): mid
                    for mid in to_fetch
                }
                for fut in as_completed(futures):
                    fetched_count += 1
                    if fetched_count % 100 == 0:
                        log.info("  fetched %d/%d...", fetched_count, len(to_fetch))
                        if _has_progress:
                            write_status(
                                phase=Phase.INGEST.value,
                                message=f"Reading emails ({fetched_count} of {len(to_fetch)})...",
                                current=fetched_count,
                                total=len(to_fetch),
                            )
                    try:
                        msg = fut.result()
                    except Exception as e:
                        log.warning("worker error: %s", e)
                        continue
                    if msg is None:
                        continue
                    # Writes happen here on the main thread, which holds the
                    # only DB connection. Workers do the network round-trips
                    # in parallel; the main thread serializes the writes.
                    # That's fine: writes are microseconds, fetches are ~300ms.
                    _upsert_message(conn, msg)
                    _accumulate_contact(contacts, msg, my_email)
            _flush_contacts(conn, contacts)

    # When everything was already cached, the contacts aggregate may be stale
    # (older runs of the pipeline may have left it in a partial state). Do a
    # quick rebuild from the messages table to be safe.
    if not to_fetch and cached_ids:
        log.info("nothing new; rebuilding contacts aggregate from cache")
        _rebuild_contacts_from_cache(db_path, my_email)

    # Read back the contact count for the summary, since the contacts dict
    # in memory only reflects what we accumulated in this run (which is
    # zero when nothing new was fetched).
    with connect(db_path) as conn:
        contacts_total = conn.execute("SELECT COUNT(*) AS n FROM contacts").fetchone()["n"]

    total_in_window = already_cached + fetched_count
    log.info(
        "done. %d total in window (%d new, %d cached)",
        total_in_window, fetched_count, already_cached,
    )
    return {"messages_seen": total_in_window, "contacts_seen": contacts_total}


def ingest_calendar(creds: Credentials, db_path: Path) -> int:
    """Pull recent + upcoming calendar events into SQLite. Returns event count."""
    init_db(db_path)
    events = calendar_client.fetch_events(creds, past_days=90, future_days=30)

    with connect(db_path) as conn:
        for ev in events:
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
                    ev.id,
                    ev.summary,
                    ev.start_utc,
                    ev.end_utc,
                    ",".join(ev.attendees),
                    1 if ev.is_past else 0,
                ),
            )

    log.info("ingested %d calendar events", len(events))
    return len(events)


# --- internals -----------------------------------------------------------------


def _empty_contact_row() -> dict:
    return {
        "display_name": None,
        "first_seen_utc": None,
        "last_seen_utc": None,
        "thread_count_set": set(),     # thread ids, deduped here, sized at flush
        "msg_in_count": 0,
        "msg_out_count": 0,
    }


def _upsert_message(conn: sqlite3.Connection, msg: gmail_client.GmailMessage) -> None:
    """Insert or update. ON CONFLICT keeps the latest body (in case format=full changed)."""
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
            msg.id,
            msg.thread_id,
            msg.date_utc,
            msg.subject,
            msg.from_email,
            msg.from_name,
            ",".join(msg.to_emails),
            msg.body,
            msg.snippet,
            1 if msg.is_outgoing else 0,
        ),
    )


def _accumulate_contact(
    contacts: dict[str, dict],
    msg: gmail_client.GmailMessage,
    my_email: str,
) -> None:
    """
    Update the in-memory aggregate for every non-me address attached to this
    message. We always treat the *other* party as the contact, so we don't
    count messages to/from yourself.
    """
    # When outgoing: contacts are the recipients.
    # When incoming: the contact is the sender.
    others: list[tuple[str, str]] = []  # (email, display_name)
    if msg.is_outgoing:
        for addr in msg.to_emails:
            if addr and addr != my_email:
                others.append((addr, ""))
    else:
        if msg.from_email and msg.from_email != my_email:
            others.append((msg.from_email, msg.from_name))

    for email, display_name in others:
        row = contacts[email]
        if display_name and not row["display_name"]:
            row["display_name"] = display_name
        if row["first_seen_utc"] is None or msg.date_utc < row["first_seen_utc"]:
            row["first_seen_utc"] = msg.date_utc
        if row["last_seen_utc"] is None or msg.date_utc > row["last_seen_utc"]:
            row["last_seen_utc"] = msg.date_utc
        row["thread_count_set"].add(msg.thread_id)
        if msg.is_outgoing:
            row["msg_out_count"] += 1
        else:
            row["msg_in_count"] += 1


def _flush_contacts(conn: sqlite3.Connection, contacts: dict[str, dict]) -> None:
    """Write the accumulated contacts dict to the contacts table."""
    for email, row in contacts.items():
        conn.execute(
            """
            INSERT INTO contacts (
                email, display_name, first_seen_utc, last_seen_utc,
                thread_count, msg_in_count, msg_out_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                display_name = COALESCE(excluded.display_name, contacts.display_name),
                first_seen_utc = MIN(contacts.first_seen_utc, excluded.first_seen_utc),
                last_seen_utc  = MAX(contacts.last_seen_utc,  excluded.last_seen_utc),
                thread_count   = excluded.thread_count,
                msg_in_count   = excluded.msg_in_count,
                msg_out_count  = excluded.msg_out_count
            """,
            (
                email,
                row["display_name"],
                row["first_seen_utc"],
                row["last_seen_utc"],
                len(row["thread_count_set"]),
                row["msg_in_count"],
                row["msg_out_count"],
            ),
        )


def _rebuild_contacts_from_cache(db_path: Path, my_email: str) -> None:
    """
    Recompute the contacts aggregate by walking the messages table from
    scratch. Used when the cache is already fully populated but we suspect
    the contacts table is stale from earlier partial runs.

    Cheap because messages is keyed on id and the walk is in-memory.
    """
    from email.utils import getaddresses  # local import: only needed here

    contacts: dict[str, dict] = defaultdict(_empty_contact_row)

    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT thread_id, date_utc, from_email, from_name,
                   to_emails, is_outgoing
            FROM messages
            """
        ).fetchall()

        for r in rows:
            is_outgoing = bool(r["is_outgoing"])
            others: list[tuple[str, str]] = []
            if is_outgoing:
                # Re-parse to_emails defensively in case any legacy rows
                # were written by the old buggy splitter.
                for _name, addr in getaddresses([r["to_emails"] or ""]):
                    addr = (addr or "").lower()
                    if addr and addr != my_email and "@" in addr:
                        others.append((addr, ""))
            else:
                addr = (r["from_email"] or "").lower()
                if addr and addr != my_email and "@" in addr:
                    others.append((addr, r["from_name"] or ""))

            for email, display_name in others:
                row = contacts[email]
                if display_name and not row["display_name"]:
                    row["display_name"] = display_name
                if row["first_seen_utc"] is None or r["date_utc"] < row["first_seen_utc"]:
                    row["first_seen_utc"] = r["date_utc"]
                if row["last_seen_utc"] is None or r["date_utc"] > row["last_seen_utc"]:
                    row["last_seen_utc"] = r["date_utc"]
                row["thread_count_set"].add(r["thread_id"])
                if is_outgoing:
                    row["msg_out_count"] += 1
                else:
                    row["msg_in_count"] += 1

        conn.execute("DELETE FROM contacts")
        _flush_contacts(conn, contacts)
