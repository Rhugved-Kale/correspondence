"""
Standalone ingestion driver.

Run from the project root:

    python -m backend.scripts.ingest

Pulls recent emails and calendar events into SQLite. Use this to test
the foundation end-to-end before wiring up the rest of the pipeline.

This script is intentionally not part of the FastAPI app. Ingestion is
a long-running operation that we want to be able to invoke from the CLI
during development without spinning up a web server.
"""

from __future__ import annotations

import time

from backend.clients.gmail import get_credentials
from backend.config import DB_PATH, ensure_dirs, get_settings
from backend.storage.db import connect, init_db
from backend.storage.ingest import ingest_calendar, ingest_recent_window
from backend.utils.logging import get_logger, setup_logging


def main() -> None:
    setup_logging("INFO")
    log = get_logger("ingest")

    settings = get_settings()
    ensure_dirs()
    init_db(DB_PATH)

    log.info("authenticating with Google")
    creds = get_credentials(settings.google_credentials_path, settings.google_token_path)

    t0 = time.monotonic()
    log.info("starting ingestion")
    email_stats = ingest_recent_window(creds, settings, DB_PATH)
    event_count = ingest_calendar(creds, DB_PATH)
    elapsed = time.monotonic() - t0

    # Print a small summary so the user can sanity-check what landed in the DB.
    log.info("=" * 50)
    log.info("ingestion complete in %.1fs", elapsed)
    log.info("messages ingested: %d", email_stats["messages_seen"])
    log.info("unique contacts:   %d", email_stats["contacts_seen"])
    log.info("calendar events:   %d", event_count)

    # Show the top 10 contacts by raw thread count, just as a sanity check.
    # The real ranking comes later; this is just "did we pull anything useful?"
    with connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT email, display_name, thread_count, msg_in_count, msg_out_count, last_seen_utc
            FROM contacts
            ORDER BY thread_count DESC
            LIMIT 10
            """
        ).fetchall()

    if rows:
        log.info("")
        log.info("top contacts by thread count (no smart ranking yet):")
        for r in rows:
            label = r["display_name"] or r["email"]
            log.info(
                "  %3d threads  in=%-3d out=%-3d  last=%s  %s",
                r["thread_count"], r["msg_in_count"], r["msg_out_count"],
                (r["last_seen_utc"] or "")[:10], label[:50],
            )


if __name__ == "__main__":
    main()
