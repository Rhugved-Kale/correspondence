"""
Ranking: pick the top N people from a cache of hundreds of contacts.

The whole point of this module is to compress thousands of contacts down
to maybe ten before we burn any LLM tokens. If we did LLM calls over the
full set, the run would be slow and expensive, and most of the calls
would be wasted on newsletters anyway. So we score deterministically
here with cheap features, then hand only the survivors to the agents.

Design notes for whoever reads this later:

  - The features are all directly observable in SQLite. No need for any
    external service, no risk of nondeterminism. Run it twice on the same
    cache, get the same ranking.
  - Reciprocity is the single most important signal. Someone you've replied
    to is almost certainly a real human you care about. Someone you've
    never replied to is almost certainly a newsletter, alert, or bot.
  - Recency matters but not overwhelmingly. A close collaborator from
    eight months ago is more important than a recruiter you spoke to
    twice yesterday. We use a soft exponential decay, not a hard cutoff.
  - Volume is helpful but log-scaled. Going from 5 threads to 50 threads
    is meaningful. Going from 50 to 500 is not 10x more meaningful, so we
    flatten the curve.
  - Calendar overlap is a small but specific boost. Someone who shows up
    in your calendar in the last 90 days is presumably someone you've
    actually spoken to in real time, which is a strong signal that text
    alone doesn't capture.

  - Weights are tuned by hand against a real inbox. They could be learned
    from feedback in a future iteration, but for a single-user prototype
    that defeats the point of being inspectable.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.storage.db import connect, init_db
from backend.utils.logging import get_logger


log = get_logger(__name__)


# Patterns that hint a sender is automated even when the address itself
# looks human. The ingestion-time filter catches the obvious cases
# (noreply@, notifications@). These catch what slips through.
SUSPICIOUS_LOCAL_PARTS = {
    "alerts", "alert", "info", "support", "team", "hello", "hi",
    "contact", "noreply", "no-reply", "newsletter", "digest", "updates",
    "notification", "notifications", "bot", "system",
    # Patterns we've observed in real testing that the basic list missed:
    "spamdigest", "spam-digest", "notifications-noreply",
    "noreply-comments", "do-not-reply", "newsletters", "alerts-noreply",
    "mailer", "mailer-daemon", "postmaster", "automated",
}

# Domains whose human-named senders are usually mass-mail or transactional.
# We don't hard-exclude them since occasionally a real person emails from
# one of these, but we apply a heavy malus.
SUSPICIOUS_DOMAINS = {
    "linkedin.com", "indeed.com", "ziprecruiter.com", "handshake.com",
    "glassdoor.com", "monster.com", "naukri.com",
    "googlemail.com", "mailer-daemon",
    "redditmail.com", "x.com", "twitter.com", "instagram.com",
    "spotify.com", "airbnb.com", "uber.com", "lyft.com", "doordash.com",
}


@dataclass
class RankedContact:
    """What the ranker returns for each top-N person."""
    email: str
    display_name: str
    score: float
    thread_count: int
    msg_in: int
    msg_out: int
    last_seen_utc: str
    # Sub-scores kept for debuggability. When the ranking surprises us,
    # we want to see why a contact ranked where they did, not just the
    # final number.
    feature_breakdown: dict[str, float]


def rank_contacts(db_path: Path, top_n: int) -> list[RankedContact]:
    """
    Score every contact in the cache and return the top N.

    Returns ranked contacts in descending score order. Also marks the
    chosen contacts in the DB so downstream stages know who to deep-fetch.
    """
    # Defensive: make sure every expected table exists. Cheap no-op if
    # the schema is already current, catches the case where the DB was
    # created against an older schema and a new table was added later.
    init_db(db_path)

    now = datetime.now(timezone.utc)
    calendar_emails = _calendar_attendees(db_path)

    scored: list[RankedContact] = []

    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT email, display_name, thread_count,
                   msg_in_count, msg_out_count,
                   first_seen_utc, last_seen_utc
            FROM contacts
            WHERE msg_in_count + msg_out_count > 0
            """
        ).fetchall()

        for r in rows:
            score, breakdown = _score(r, now, calendar_emails)
            if score <= 0:
                continue
            scored.append(
                RankedContact(
                    email=r["email"],
                    display_name=r["display_name"] or "",
                    score=score,
                    thread_count=r["thread_count"],
                    msg_in=r["msg_in_count"],
                    msg_out=r["msg_out_count"],
                    last_seen_utc=r["last_seen_utc"] or "",
                    feature_breakdown=breakdown,
                )
            )

        scored.sort(key=lambda c: c.score, reverse=True)
        top = scored[:top_n]

        # Persist score for everyone (useful for debugging) and mark selected.
        # One UPDATE per contact is fine at this scale.
        conn.execute("UPDATE contacts SET is_selected = 0")
        for c in scored:
            conn.execute(
                "UPDATE contacts SET score = ? WHERE email = ?",
                (c.score, c.email),
            )
        for c in top:
            conn.execute(
                "UPDATE contacts SET is_selected = 1 WHERE email = ?",
                (c.email,),
            )

    return top


# --- scoring -------------------------------------------------------------------


def _score(
    row: sqlite3.Row,
    now: datetime,
    calendar_emails: set[str],
) -> tuple[float, dict[str, float]]:
    """
    Combine the individual signals into one score. Returns (score, breakdown)
    so callers can inspect why a contact landed where they did.

    The component weights are deliberately exposed as constants below.
    Tuning them is faster than re-running ingestion.
    """
    breakdown: dict[str, float] = {}

    # 1. Reciprocity. The most important signal in principle, but we have
    # to guard against the "single round-trip" trap: a one-email exchange
    # where you replied once looks perfectly 1:1, but it's not a real
    # relationship. We damp the reciprocity signal for contacts with very
    # few threads, ramping up to full weight only past ~5 threads.
    in_count = row["msg_in_count"]
    out_count = row["msg_out_count"]
    if in_count + out_count == 0:
        return 0.0, breakdown

    # Hard rule: if you have never replied to this person, they are not
    # a relationship worth featuring. Every contact in the top 10 of our
    # earlier test that had out=0 was either a newsletter, an automated
    # alert, or a transactional service that slipped through the noise
    # filter. The previous "0.05 floor" let them score 2.8+ on volume
    # alone and crack the top 10. The right answer is: no reply, no
    # relationship. Group-thread edge cases lose here, but in a 4,500-
    # message inbox the false-negative rate is acceptable.
    if out_count == 0:
        return 0.0, breakdown

    if max(in_count, out_count) > 0:
        ratio = min(in_count, out_count) / max(in_count, out_count)
    else:
        ratio = 0.0
    # Damp by thread count using a smooth ramp: 0 threads = 0% credit,
    # 5+ threads = 100% credit, in between scales linearly. Without this,
    # a single round-trip exchange (1 in, 1 out) reads as perfect
    # reciprocity but tells us nothing about whether the contact is a
    # real ongoing relationship.
    thread_count = row["thread_count"]
    volume_damper = min(1.0, thread_count / 5.0)
    reciprocity_signal = ratio * volume_damper
    breakdown["reciprocity"] = reciprocity_signal * W_RECIPROCITY

    # 2. Volume, log-scaled. Going from 1 to 10 threads is a big deal;
    # going from 100 to 200 is not. log1p flattens the curve cleanly.
    # We normalize against log1p(50) so a contact with 50 threads
    # contributes ~1.0 of the volume signal, since real heavy-traffic
    # collaborators in a personal inbox typically max out in this range.
    volume_signal = math.log1p(thread_count) / math.log1p(50)
    volume_signal = min(volume_signal, 1.0)
    breakdown["volume"] = volume_signal * W_VOLUME

    # 3. Recency. Soft exponential decay: a contact whose last_seen is
    # today is at full weight, dropping to ~0.5 at 60 days, ~0.1 at
    # 180 days. This rewards active relationships without erasing
    # important older ones.
    last_seen = _parse_iso(row["last_seen_utc"])
    if last_seen:
        days_ago = max(0.0, (now - last_seen).days)
        recency_signal = math.exp(-days_ago / 90.0)
    else:
        recency_signal = 0.0
    breakdown["recency"] = recency_signal * W_RECENCY

    # 4. Calendar co-attendance. Binary: a person who shows up in your
    # calendar at all gets a flat boost. We don't try to count meetings
    # since a single recurring 1:1 would dominate.
    on_calendar = row["email"] in calendar_emails
    breakdown["calendar"] = (1.0 if on_calendar else 0.0) * W_CALENDAR

    # 5. Suspicious sender penalty. Local-parts like "alerts" or
    # "noreply" that slipped through the ingestion filter, and known
    # mass-mail domains. This is a malus, not a multiplier, so it can
    # cancel out a high volume signal but won't reverse a good one.
    suspicious_penalty = 0.0
    local, _, domain = row["email"].partition("@")
    if local.lower() in SUSPICIOUS_LOCAL_PARTS:
        suspicious_penalty += W_SUSPICIOUS_LOCAL
    if domain.lower() in SUSPICIOUS_DOMAINS:
        suspicious_penalty += W_SUSPICIOUS_DOMAIN
    # The penalty is recorded as a negative number so callers reading
    # the breakdown can see "ah, this contact lost 0.5 here."
    breakdown["suspicious_penalty"] = -suspicious_penalty

    score = (
        breakdown["reciprocity"]
        + breakdown["volume"]
        + breakdown["recency"]
        + breakdown["calendar"]
        + breakdown["suspicious_penalty"]
    )

    return max(score, 0.0), breakdown


# Weights. Tuned by inspection against a real inbox. Adjust here, not
# inline. Reciprocity stays the strongest signal but volume is now close
# enough that a sustained collaboration outranks a one-off perfect-balance
# exchange.
W_RECIPROCITY = 1.6
W_VOLUME = 1.8
W_RECENCY = 1.0
W_CALENDAR = 0.5
W_SUSPICIOUS_LOCAL = 1.5
W_SUSPICIOUS_DOMAIN = 1.0


# --- helpers -------------------------------------------------------------------


def _parse_iso(s: str | None) -> datetime | None:
    """Tolerant ISO-8601 parser; returns None on garbage rather than raising."""
    if not s:
        return None
    try:
        # SQLite stores both 'Z' and '+00:00'; fromisoformat handles the latter.
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _calendar_attendees(db_path: Path) -> set[str]:
    """Pull every email address that appears as a calendar attendee."""
    out: set[str] = set()
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT attendees FROM calendar_events WHERE attendees != ''"
        ).fetchall()
        for r in rows:
            for email in (r["attendees"] or "").split(","):
                email = email.strip().lower()
                if email:
                    out.add(email)
    return out
