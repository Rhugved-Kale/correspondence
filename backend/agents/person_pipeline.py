"""
Per-person agent pipeline.

For one person, this module:

  1. Pulls their full email history from cache (deep_fetch already ran).
  2. Builds a compact "messages block" string to feed Claude.
  3. Runs five agents SEQUENTIALLY (with a small sleep between):
       - Timeline
       - Stories
       - About them (with web search)
       - Forgotten threads
       - Prep card
  4. Composes the final per-person object in the shape the frontend wants.

Why sequential and not parallel: my Anthropic account is on Tier 1
(30k input tokens/min, 50 req/min). A heavy person like Karen has 177
cached messages; trying to fire four 200k-token requests in parallel
gets every one of them 429'd. Going sequential plus aggressive input
trimming keeps us comfortably inside both limits.

Wall-clock cost: roughly 30-45 seconds per person, so 5-8 minutes for
ten people. Slower than I'd like, but the rate-limit budget pays for it.

Input trimming: a person can have hundreds of cached emails. The agents
don't need all of them. We keep the 10 oldest (to anchor the start of
the relationship) and the most recent 30, then truncate bodies to 400
chars. For 99% of people this fits comfortably under one rate-limit
window. The Karens of the world get a slightly thinner view than they
would with everything, but the resulting outputs are still strong.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from backend.agents import grounding
from backend.agents.deep_fetch import PersonMessages, load_person_messages
from backend.clients import claude
from backend.prompts import templates as T
from backend.utils.logging import get_logger


log = get_logger(__name__)


MAX_BODY_CHARS = 400

# How many messages to include in the agent prompt. We keep the oldest few
# (so timeline can recognize the start of the relationship) and the most
# recent ones (where the actionable signal lives). If a person has fewer
# than HEAD+TAIL total messages, we include everything.
HEAD_MESSAGES = 10
TAIL_MESSAGES = 30

# Pause between sequential agent calls within one person. Mostly insurance
# against 429s when many short messages happen in quick succession; the
# token-per-minute budget is the harder constraint, but RPM matters too.
INTER_AGENT_SLEEP_SECONDS = 1.5


async def build_person_payload(
    db_path: Path,
    email: str,
    rank_score: float,
    rank_position: int,
) -> dict:
    """
    Run the full agent pipeline for one person and return the composed
    payload, ready to drop into the people.json array.

    Errors from individual agents are logged and don't kill the run; the
    affected section just gets a sensible default. We prefer to ship a
    person with one missing section than to fail the whole run for one
    bad agent.
    """
    pm = load_person_messages(db_path, email)
    if not pm.messages:
        log.warning("no cached messages for %s; skipping", email)
        return _empty_payload(email)

    messages_block = _format_messages_block(pm)
    context_block = _format_context_block(pm)
    calendar_stats = _calendar_stats_for(db_path, pm.email)
    name = _label(pm)

    log.info("agents starting for %s (%d msgs, sampled to fit)", name, len(pm.messages))

    # Sequential, with a short sleep between calls. Slower but never 429s.
    timeline_data = await _safe_call(
        "timeline",
        claude.call_json(
            system=T.TIMELINE_SYSTEM,
            user=T.TIMELINE_USER_TEMPLATE.format(
                display_name=name,
                email=pm.email,
                message_count=len(pm.messages),
                first_date=pm.first_date[:10],
                last_date=pm.last_date[:10],
                messages_block=messages_block,
                gaps_block=_format_gaps_block(pm),
                hero_facts=_format_hero_facts(pm, calendar_stats),
            ),
        ),
        default={"events": []},
    )
    await asyncio.sleep(INTER_AGENT_SLEEP_SECONDS)

    stories_data = await _safe_call(
        "stories",
        claude.call_json(
            system=T.STORIES_SYSTEM,
            user=T.STORIES_USER_TEMPLATE.format(
                display_name=name,
                email=pm.email,
                messages_block=messages_block,
            ),
        ),
        default={"stories": []},
    )
    await asyncio.sleep(INTER_AGENT_SLEEP_SECONDS)

    forgotten_data = await _safe_call(
        "forgotten",
        claude.call_json(
            system=T.FORGOTTEN_SYSTEM,
            user=T.FORGOTTEN_USER_TEMPLATE.format(
                display_name=name,
                email=pm.email,
                messages_block=messages_block,
            ),
        ),
        default={"forgotten": []},
    )
    await asyncio.sleep(INTER_AGENT_SLEEP_SECONDS)

    # About uses web search and a small context block, so its input cost
    # is much lower than the others. Still keep it sequential to be safe.
    about_data = await _safe_call(
        "about",
        claude.call_json_with_web_search(
            system=T.ABOUT_SYSTEM,
            user=T.ABOUT_USER_TEMPLATE.format(
                display_name=name,
                email=pm.email,
                context_block=context_block,
            ),
        ),
        default=_empty_about(),
    )
    await asyncio.sleep(INTER_AGENT_SLEEP_SECONDS)

    prep_data = await _safe_call(
        "prep",
        claude.call_json(
            system=T.PREP_SYSTEM,
            user=T.PREP_USER_TEMPLATE.format(
                display_name=name,
                email=pm.email,
                messages_block=messages_block,
            ),
        ),
        default=_empty_prep(),
    )

    # Check quotes before composing. The agents are told an empty field
    # beats an invented one; this enforces it rather than trusting it,
    # because `evidence` renders as a verbatim quote directly under the
    # claim it supports and a paraphrase there reads as a fabrication to
    # anyone who knows the thread.
    grounding.verify_payload(
        messages=pm.messages,
        timeline_events=timeline_data.get("events") or [],
        stories=stories_data.get("stories") or [],
        person=pm.email,
    )

    payload = _compose_payload(
        email=pm.email,
        display_name=name,
        rank_score=rank_score,
        rank_position=rank_position,
        timeline_data=timeline_data,
        stories_data=stories_data,
        about_data=about_data,
        forgotten_data=forgotten_data,
        prep_data=prep_data,
        calendar_stats=calendar_stats,
    )

    log.info("agents done for %s", name)
    return payload


# --- helpers -------------------------------------------------------------------


def _label(pm: PersonMessages) -> str:
    """
    Best display label we have for this person, normalized for readability.

    Three cases:
      1. "Last, First" academic format -> "First Last".
      2. A real display name present  -> keep it, just trimmed.
      3. No display name at all       -> derive a friendly form from the
         email local-part. "yugandharak21@gmail.com" becomes "Yugandhara K"
         instead of showing the raw email as the heading.
    """
    name = (pm.display_name or "").strip()
    if name:
        # "Ryu, Angela" -> "Angela Ryu". Only do this when there's exactly
        # one comma with names on both sides; we don't want to mangle
        # legitimate comma-bearing names like "Smith, Jr.".
        if "," in name and name.count(",") == 1:
            last, _, first = name.partition(",")
            last = last.strip()
            first = first.strip()
            # Defensive: both parts must look like names (letters present
            # and not just initials or suffixes).
            if last and first and len(first) >= 2:
                return f"{first} {last}"
        return name

    # Derive a display name from the email's local-part. Strip trailing
    # digits, replace separators with spaces, title-case. Best-effort;
    # if it looks bad it's still better than showing the email as a page
    # title.
    local = pm.email.split("@", 1)[0]
    # Strip trailing run of digits ("yugandhara21" -> "yugandhara")
    import re
    cleaned = re.sub(r"\d+$", "", local)
    # Split on common separators
    parts = re.split(r"[._\-+]+", cleaned)
    parts = [p for p in parts if p]
    if not parts:
        return pm.email  # bail to email if local-part is unusable
    return " ".join(p[:1].upper() + p[1:] for p in parts)


def _sample_messages(messages: list[dict]) -> list[dict]:
    """
    Trim a possibly-huge message list to head+tail. Returns at most
    HEAD_MESSAGES + TAIL_MESSAGES total, in chronological order, deduped.
    If the total is already small, return everything.
    """
    if len(messages) <= HEAD_MESSAGES + TAIL_MESSAGES:
        return messages

    head = messages[:HEAD_MESSAGES]
    tail = messages[-TAIL_MESSAGES:]
    seen = {m["id"] for m in head}
    combined = list(head)
    for m in tail:
        if m["id"] not in seen:
            combined.append(m)
            seen.add(m["id"])
    return combined


def _format_messages_block(pm: PersonMessages) -> str:
    """
    Build the chronological message block Claude reads. Each message is
    a compact header plus a body excerpt. We sample down to head+tail if
    the full set would blow our token budget.
    """
    sampled = _sample_messages(pm.messages)
    skipped = len(pm.messages) - len(sampled)

    parts = []
    if skipped > 0:
        # Let Claude know there's a gap so it doesn't claim full coverage
        # of a thread it only saw the endpoints of.
        parts.append(
            f"[NOTE: showing the oldest {HEAD_MESSAGES} and most recent "
            f"{TAIL_MESSAGES} of {len(pm.messages)} total messages. "
            f"The middle {skipped} are omitted for brevity.]"
        )

    for i, m in enumerate(sampled, 1):
        direction = "ME -> THEM" if m["is_outgoing"] else "THEM -> ME"
        date = m["date_utc"][:10]
        body = m["body"] or m["snippet"] or ""
        if len(body) > MAX_BODY_CHARS:
            body = body[:MAX_BODY_CHARS] + "  [...truncated]"
        parts.append(
            f"--- Message {i}: {date} ({direction}) ---\n"
            f"Subject: {m['subject']}\n"
            f"Body:\n{body}"
        )
    return "\n\n".join(parts)


MIN_GAP_DAYS = 10


def _format_hero_facts(pm: PersonMessages, calendar: dict, as_of=None) -> str:
    """
    The handful of numbers the hero line is composed from.

    The old hero was four stat tiles, one of which ("Milestones") counted
    how many events the timeline agent chose to emit: a statistic about
    the artifact rather than the person. These are the facts worth
    keeping, handed over precomputed so the sentence around them cannot
    get them wrong.
    """
    from datetime import datetime, timezone
    from backend.agents import phrasing as ph

    now = as_of or datetime.now(timezone.utc)
    rows = [f"- Messages exchanged: {len(pm.messages)}"]

    try:
        first = datetime.fromisoformat(pm.first_date.replace("Z", "+00:00"))
        last = datetime.fromisoformat(pm.last_date.replace("Z", "+00:00"))
        rows.append(f"- Span of the relationship: {ph.window_span((last - first).days)}")
        rows.append(
            f"- Time since the last message: "
            f"{ph.days_since(pm.last_date[:10], now.date().isoformat())}"
        )
    except (ValueError, AttributeError, TypeError):
        pass

    n = (calendar or {}).get("count") or 0
    rows.append(
        f"- Meetings on the calendar together: {n}" if n
        else "- Meetings on the calendar together: none, do not mention meetings"
    )
    return "\n".join(rows)


def _format_gaps_block(pm: PersonMessages) -> str:
    """
    Precompute notable silences and hand them to the timeline agent as
    facts.

    The silence event is the most valuable thing the timeline produces and
    its most quotable element is the number of days, which is exactly the
    thing the model gets wrong: given both dates it still miscounted 23 as
    24, and drifted on which date to file the event under. Date arithmetic
    is derivable from data we already hold, so we derive it. The agent
    writes prose around these numbers instead of computing them.

    Also records who fell silent and who spoke first afterward, because
    "they went quiet" and "I went quiet" are different events and the
    direction is not always obvious from a message list.
    """
    msgs = pm.messages
    if len(msgs) < 2:
        return "None."

    from datetime import datetime

    rows: list[str] = []
    for prev, cur in zip(msgs, msgs[1:]):
        try:
            a = datetime.fromisoformat(prev["date_utc"])
            b = datetime.fromisoformat(cur["date_utc"])
        except (ValueError, TypeError, KeyError):
            continue
        days = (b - a).days
        if days < MIN_GAP_DAYS:
            continue

        # "I" must stay capitalised mid-sentence, so build the clause from
        # explicit forms rather than case-folding a pronoun.
        if prev["is_outgoing"] and cur["is_outgoing"]:
            direction = "I sent the last message before it and I broke it too, so they never replied at all"
        elif prev["is_outgoing"]:
            direction = "I sent the last message before it, they broke the silence"
        elif cur["is_outgoing"]:
            direction = "They sent the last message before it, I broke the silence"
        else:
            direction = "They sent the last message before it and they broke it too, so I never replied at all"

        rows.append(
            f"- {a.date().isoformat()} to {b.date().isoformat()}: {days} days "
            f"of silence. {direction}."
        )

    if not rows:
        return "None."
    return "\n".join(rows)


def _format_context_block(pm: PersonMessages) -> str:
    """
    A much smaller summary for the About agent. The About agent doesn't
    need the full thread, just enough to know how I know this person
    (their domain, the topics that come up). Web search will fill in
    the rest.
    """
    if not pm.messages:
        return f"No prior emails with {pm.email}."

    subjects = []
    seen = set()
    for m in pm.messages:
        s = (m["subject"] or "").strip()
        if s and s.lower() not in seen:
            subjects.append(s)
            seen.add(s.lower())
        if len(subjects) >= 6:
            break

    return (
        f"Email domain: {pm.email}\n"
        f"Number of emails exchanged: {len(pm.messages)}\n"
        f"Date range: {pm.first_date[:10]} to {pm.last_date[:10]}\n"
        f"Display name as seen in their emails: {pm.display_name or '(none)'}\n"
        f"Subject lines from our exchange (sample):\n"
        + "\n".join(f"  - {s}" for s in subjects)
    )


async def _safe_call(name: str, coro, default: dict) -> dict:
    """
    Wrap an agent call so any exception logs a warning and returns the
    default shape, keeping the rest of the pipeline alive.
    """
    try:
        return await coro
    except Exception as e:
        log.warning("agent %s failed: %s. using default.", name, e)
        return default


def _compose_payload(
    email: str,
    display_name: str,
    rank_score: float,
    rank_position: int,
    timeline_data: dict,
    stories_data: dict,
    about_data: dict,
    forgotten_data: dict,
    prep_data: dict,
    calendar_stats: dict | None = None,
) -> dict:
    """
    Glue the agent outputs into the exact shape PeopleWiki.jsx expects.
    Defensive about missing keys so a partial failure doesn't crash the
    composer.
    """
    one_line = (about_data.get("one_line") or "").strip()
    role_hint = one_line if one_line else display_name
    cal = calendar_stats or {"count": 0, "most_recent_utc": None}

    return {
        "id": _slug_from_email(email),
        "name": display_name,
        "email": email,
        "rank_position": rank_position,
        "rank_score": round(rank_score, 3),
        "role_hint": role_hint,
        "about": {
            "one_line": about_data.get("one_line") or "",
            "current_focus": about_data.get("current_focus") or "",
            "background": about_data.get("background") or "",
            "three_things_to_know": about_data.get("three_things_to_know") or [],
        },
        "hero_line": (timeline_data.get("hero_line") or "").strip(),
        "timeline": timeline_data.get("events") or [],
        "stories": stories_data.get("stories") or [],
        "forgotten": forgotten_data.get("forgotten") or [],
        "prep": {
            "last_substantive_interaction": prep_data.get("last_substantive_interaction") or "",
            "open_threads": prep_data.get("open_threads") or [],
            "three_talking_points": prep_data.get("three_talking_points") or [],
            "something_personal": prep_data.get("something_personal") or "",
        },
        "meetings": {
            "count": cal["count"],
            "most_recent_utc": cal["most_recent_utc"],
        },
    }


def _calendar_stats_for(db_path: Path, email: str) -> dict:
    """
    How many calendar events did the user share with this person, and when
    was the most recent? Used by the frontend to render "We've met 6 times,
    most recently 3 weeks ago" on the person's page.

    Attendees are stored as a JSON list in the calendar_events table. We
    use SQLite's LIKE because the email is matched as a substring of the
    serialized list; this is good enough at our scale (a few hundred events
    max) and avoids forcing a schema change.
    """
    import sqlite3
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT COUNT(*) AS n, MAX(start_utc) AS recent
                FROM calendar_events
                WHERE LOWER(attendees) LIKE ?
                """,
                (f"%{email.lower()}%",),
            ).fetchone()
            return {
                "count": int(row["n"] or 0),
                "most_recent_utc": row["recent"],
            }
    except sqlite3.Error:
        # Calendar table might not exist on a very old cache; treat as zero.
        return {"count": 0, "most_recent_utc": None}


def _slug_from_email(email: str) -> str:
    """A stable, human-readable id derived from the email local-part."""
    return email.split("@", 1)[0].lower().replace(".", "-").replace("+", "-")


def _empty_payload(email: str) -> dict:
    """For the rare case where we have no cached messages at all."""
    return {
        "id": _slug_from_email(email),
        "name": email,
        "email": email,
        "rank_position": 0,
        "rank_score": 0.0,
        "role_hint": email,
        "about": _empty_about(),
        "hero_line": "",
        "timeline": [],
        "stories": [],
        "forgotten": [],
        "prep": _empty_prep(),
        "meetings": {"count": 0, "most_recent_utc": None},
    }


def _empty_about() -> dict:
    return {
        "one_line": "",
        "current_focus": "",
        "background": "",
        "three_things_to_know": [],
    }


def _empty_prep() -> dict:
    return {
        "last_substantive_interaction": "",
        "open_threads": [],
        "three_talking_points": [],
        "something_personal": "",
    }
