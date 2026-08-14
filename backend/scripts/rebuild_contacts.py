"""
Rebuild the contacts aggregate from the messages already cached in SQLite.

Use this if the contacts table ever gets out of sync with messages: it
truncates `contacts` and re-aggregates from scratch by re-parsing the
to_emails column on each message. No Gmail traffic; the cached messages
are the source of truth.

Run from project root:
    python -m backend.scripts.rebuild_contacts
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from email.utils import getaddresses

from backend.config import DB_PATH, get_settings
from backend.clients.gmail import get_credentials, get_my_email
from backend.storage.db import connect, init_db
from backend.utils.logging import get_logger, setup_logging


log = get_logger("rebuild_contacts")


def _empty_row() -> dict:
    return {
        "display_name": None,
        "first_seen_utc": None,
        "last_seen_utc": None,
        "thread_ids": set(),
        "msg_in_count": 0,
        "msg_out_count": 0,
    }


def _parse_addresses(raw: str) -> list[tuple[str, str]]:
    """Same getaddresses-based parser used by gmail.py. Inlined here so
    the script is self-contained and doesn't depend on the ingest module."""
    if not raw:
        return []
    return [(name, addr.lower()) for name, addr in getaddresses([raw]) if addr]


def main() -> None:
    setup_logging("INFO")

    settings = get_settings()
    init_db(DB_PATH)

    # We need my_email to know which side of the conversation each message
    # represents. The token is already cached from earlier runs, so this
    # is silent unless the token expired.
    log.info("resolving authenticated user...")
    creds = get_credentials(settings.google_credentials_path, settings.google_token_path)
    my_email = get_my_email(creds).lower()
    log.info("identifying contacts opposite to %s", my_email)

    contacts: dict[str, dict] = defaultdict(_empty_row)
    message_count = 0

    with connect(DB_PATH) as conn:
        # Walk every message, rebuild aggregate. We re-parse to_emails from
        # the stored comma-joined string because that column may have been
        # written by the buggy splitter. The from_email column is safe; it
        # came from parseaddr() on the From: header, which is reliable.
        rows = conn.execute(
            """
            SELECT id, thread_id, date_utc, subject,
                   from_email, from_name, to_emails, is_outgoing
            FROM messages
            """
        ).fetchall()

        for r in rows:
            message_count += 1
            is_outgoing = bool(r["is_outgoing"])

            # Compute "the other parties" for this message. For incoming
            # mail, that's the sender. For outgoing mail, that's the
            # recipients. We exclude my_email from either side.
            #
            # Important: r["to_emails"] is the buggy comma-joined value, so
            # we run it back through the proper parser to recover from
            # past splitting errors.
            others: list[tuple[str, str]] = []
            if is_outgoing:
                # to_emails was stored as a comma-joined string. The data
                # in there might already be corrupted (bare local-parts
                # from "Vance, Marguerite" splits), but on a re-parse with
                # getaddresses they'll either be recoverable (if the
                # angle-bracket form survived) or silently dropped (if
                # only "green" without an @ remained, which isn't a valid
                # address anyway).
                for _name, addr in _parse_addresses(r["to_emails"] or ""):
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
                row["thread_ids"].add(r["thread_id"])
                if is_outgoing:
                    row["msg_out_count"] += 1
                else:
                    row["msg_in_count"] += 1

        log.info("walked %d messages, %d unique valid contacts", message_count, len(contacts))

        # Truncate and rewrite. Doing this inside the same transaction means
        # we never have a half-rebuilt table.
        conn.execute("DELETE FROM contacts")
        for email, row in contacts.items():
            conn.execute(
                """
                INSERT INTO contacts (
                    email, display_name, first_seen_utc, last_seen_utc,
                    thread_count, msg_in_count, msg_out_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email,
                    row["display_name"],
                    row["first_seen_utc"],
                    row["last_seen_utc"],
                    len(row["thread_ids"]),
                    row["msg_in_count"],
                    row["msg_out_count"],
                ),
            )

    log.info("contacts table rebuilt. quick sanity scan:")

    # Print a top-20 view filtered to contacts with at least one outgoing
    # message. This is the same sanity query the user ran manually but
    # done inline for convenience.
    with connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT email, display_name, thread_count, msg_in_count, msg_out_count
            FROM contacts
            WHERE msg_out_count > 0
            ORDER BY thread_count DESC
            LIMIT 20
            """
        ).fetchall()

    for r in rows:
        label = r["display_name"] or r["email"]
        log.info(
            "  %3d threads  in=%-3d out=%-3d  %s",
            r["thread_count"], r["msg_in_count"], r["msg_out_count"], label[:60],
        )


if __name__ == "__main__":
    main()
