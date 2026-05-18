"""
SQLite schema and connection helpers.

Three tables:

  messages   one row per Gmail message we've ingested. Includes metadata
             (date, subject, from/to) and the cleaned plain-text body.
             The Gmail message id is the primary key, so re-ingestion is
             a free upsert.

  contacts   one row per unique email address. Aggregated stats are kept
             here (thread count, last contact date, etc.) so the ranking
             pass doesn't have to re-scan all of messages every time.

  runs       a small audit table. One row per pipeline run. Useful for
             debugging and for showing the user something honest like
             "last run took 12m 04s, processed 1,847 messages".

Connections are short-lived. We open a connection per logical operation
and close it. SQLite handles concurrent reads fine but only one writer
at a time, and our pipeline is single-process anyway, so this is
deliberately boring and predictable.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,           -- Gmail message id
    thread_id       TEXT NOT NULL,
    date_utc        TEXT NOT NULL,              -- ISO-8601, e.g. 2026-02-11T15:32:00+00:00
    subject         TEXT,
    from_email      TEXT NOT NULL,              -- normalized, lowercased
    from_name       TEXT,                       -- display name if Gmail parsed one
    to_emails       TEXT,                       -- comma-separated, normalized
    body            TEXT,                       -- cleaned plain text, secret-scrubbed
    snippet         TEXT,                       -- Gmail's own short preview, kept as fallback
    is_outgoing     INTEGER NOT NULL,           -- 1 if you sent it, 0 if you received it
    ingested_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(date_utc);
CREATE INDEX IF NOT EXISTS idx_messages_from ON messages(from_email);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);

CREATE TABLE IF NOT EXISTS contacts (
    email           TEXT PRIMARY KEY,           -- normalized, lowercased
    display_name    TEXT,
    first_seen_utc  TEXT,
    last_seen_utc   TEXT,
    thread_count    INTEGER NOT NULL DEFAULT 0,
    msg_in_count    INTEGER NOT NULL DEFAULT 0, -- messages received from them
    msg_out_count   INTEGER NOT NULL DEFAULT 0, -- messages you sent to them
    score           REAL,                       -- populated by the ranking pass
    is_selected     INTEGER NOT NULL DEFAULT 0  -- 1 if in the top N for this run
);

CREATE INDEX IF NOT EXISTS idx_contacts_score ON contacts(score DESC);

CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at     TEXT,
    status          TEXT NOT NULL DEFAULT 'running',  -- running | ok | error
    messages_seen   INTEGER,
    contacts_seen   INTEGER,
    error_text      TEXT
);

CREATE TABLE IF NOT EXISTS calendar_events (
    id              TEXT PRIMARY KEY,
    summary         TEXT,
    start_utc       TEXT,
    end_utc         TEXT,
    attendees       TEXT,                       -- comma-separated emails
    is_past         INTEGER NOT NULL            -- 1 if event is in the past
);

CREATE INDEX IF NOT EXISTS idx_calendar_start ON calendar_events(start_utc);
"""


def init_db(db_path: Path) -> None:
    """Create tables and indexes if they don't exist. Safe to call repeatedly."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    """
    Context-managed connection with sensible defaults. Returns rows as
    dict-like objects so callers can do row["subject"] instead of row[3].
    """
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    # Foreign keys aren't used yet but enabling now is cheap insurance.
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL mode is friendlier when a writer and reader overlap. We don't have
    # that today but it's the standard recommendation and costs nothing.
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
