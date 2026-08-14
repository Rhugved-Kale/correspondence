"""
Top-level pipeline orchestrator.

Sequence:

  1. Rank contacts (cheap, deterministic) -> top N people.
  2. For each top-N person, deep-fetch their full history from Gmail.
     We do this sequentially because Gmail's API doesn't love concurrent
     bursts and one extra second per person is fine.
  3. Run the per-person agent pipeline for all N people in parallel,
     bounded by a small concurrency cap so we don't pound Anthropic.
  4. Write the result as a JSON array to output/people.json.

The whole run takes roughly:
  - 5 to 15 minutes on first run (deep fetch is the bottleneck)
  - 2 to 5 minutes on a re-run (cache hits, agents only)

This module is the single entry point both the FastAPI app and the CLI
script call. Keep it framework-agnostic.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from google.oauth2.credentials import Credentials

from backend.agents.deep_fetch import deep_fetch_person
from backend.agents.insights import compose_insights
from backend.agents.person_pipeline import build_person_payload
from backend.agents.ranking import RankedContact, rank_contacts
from backend.config import DB_PATH, OUTPUT_JSON_PATH, Settings, ensure_dirs
from backend.utils.logging import get_logger


log = get_logger(__name__)


# On Anthropic Tier 1 (30k input tokens/min, 50 RPM), running multiple
# people in parallel guarantees 429s on the heavier ones. Stay sequential;
# one person at a time is 5-8 minutes total for 10 people, which is fine.
PERSON_CONCURRENCY = 1


def _name_from_email(email: str) -> str:
    """
    "priya.raghunathan@thicket.vet" -> "Priya Raghunathan". Only used when
    nothing better is configured; a rough name beats a hardcoded one.
    """
    import re
    local = re.sub(r"\d+$", "", (email or "").split("@", 1)[0])
    parts = [p for p in re.split(r"[._\-+]+", local) if p]
    return " ".join(p[:1].upper() + p[1:] for p in parts) or "the account owner"


class EmptyInboxError(Exception):
    """
    Raised when ranking finds zero usable contacts. This isn't a bug; it
    means the inbox under analysis is empty or contains only automated
    senders (newsletters, no-reply notifications, etc). The frontend
    surfaces this as a friendly "nothing to summarize yet" state rather
    than the generic crash screen.
    """


async def run_pipeline(
    creds: Credentials,
    settings: Settings,
    db_path: Path = DB_PATH,
    output_path: Path = OUTPUT_JSON_PATH,
    progress_callback=None,
) -> dict:
    """
    Execute the full pipeline. Returns a stats dict for whoever called us
    (CLI prints it, FastAPI returns it). Writes people.json as a side effect.

    progress_callback is an optional sync function the caller can pass to
    receive structured updates. Useful for the frontend progress UI.
    Shape: callback({"stage": "ranking", "current": 0, "total": 10, "message": "..."})
    """
    ensure_dirs()
    t0 = time.monotonic()

    # Resolve the authenticated user's email up front. Used by the
    # insights composer at the end to filter their own messages out of
    # the about-you stats and to anchor calendar-event matching.
    from backend.clients.gmail import get_my_email
    my_email = get_my_email(creds)

    # Whose inbox this is, for the agent prompts. Config wins if the user
    # set it; otherwise derive something usable from the address so the
    # agents at least narrate as a person rather than as a placeholder.
    protagonist = (settings.protagonist_name or "").strip() or _name_from_email(my_email)

    def emit(stage: str, current: int, total: int, message: str) -> None:
        log.info("[%s] %d/%d  %s", stage, current, total, message)
        if progress_callback:
            try:
                progress_callback({
                    "stage": stage, "current": current, "total": total, "message": message,
                })
            except Exception as e:
                log.debug("progress callback raised: %s", e)

    # Stage 1: ranking
    emit("ranking", 0, 1, "scoring contacts")
    top: list[RankedContact] = rank_contacts(db_path, settings.top_n_people)
    if not top:
        # Not a crash; just an honest "your inbox has no humans we can write
        # about." This happens with brand-new accounts, dedicated billing
        # inboxes, or accounts that only receive newsletters. The API layer
        # catches this and shows a friendly screen instead of a stack trace.
        raise EmptyInboxError(
            "We didn't find enough human correspondence in this inbox to build pages. "
            "Try a different account, or come back after you've used this one for real email."
        )
    emit("ranking", 1, 1, f"selected top {len(top)}")

    # Stage 2: deep-fetch each person's full history
    for i, c in enumerate(top, 1):
        emit(
            "deep_fetch", i, len(top),
            f"pulling full history for {c.display_name or c.email}",
        )
        # Deep-fetch is sync (under the hood Gmail calls are sync). Running
        # this in an asyncio.to_thread would let us overlap with ranking
        # work, but ranking is already done. Sequential is fine.
        deep_fetch_person(creds, db_path, c.email, settings.max_emails_per_person)

    # Stage 3: parallel per-person agents
    emit("agents", 0, len(top), "starting agent pipelines")
    sem = asyncio.Semaphore(PERSON_CONCURRENCY)
    completed = 0
    completed_lock = asyncio.Lock()

    async def run_one(c: RankedContact, position: int) -> dict:
        nonlocal completed
        async with sem:
            payload = await build_person_payload(
                db_path=db_path,
                email=c.email,
                rank_score=c.score,
                rank_position=position,
                protagonist_name=protagonist,
            )
        async with completed_lock:
            completed += 1
            emit(
                "agents", completed, len(top),
                f"finished {c.display_name or c.email}",
            )
        return payload

    payloads = await asyncio.gather(
        *(run_one(c, i + 1) for i, c in enumerate(top))
    )

    # Stage 4: write people output
    payloads.sort(key=lambda p: p["rank_position"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payloads, f, indent=2, ensure_ascii=False)

    # Stage 5: compose top-level insights (forgotten threads, upcoming
    # meetings, about-you stats). These power the dashboard surfaces that
    # complement the per-person wiki. Wrapped in try/except so a failure
    # here never invalidates the per-person artifact we just wrote.
    emit("compose", len(top), len(top), "composing insights")
    try:
        insights = compose_insights(
            db_path=db_path,
            payloads=payloads,
            my_email=my_email,
        )
        insights_path = output_path.parent / "insights.json"
        with open(insights_path, "w", encoding="utf-8") as f:
            json.dump(insights, f, indent=2, ensure_ascii=False)
        log.info("wrote insights.json (%d forgotten, %d upcoming)",
                 len(insights.get("forgotten", [])),
                 len(insights.get("upcoming", [])))
    except Exception as e:
        # Insights are a nice-to-have. If anything goes wrong, the wiki
        # still renders and we just don't get the dashboard.
        log.warning("insights composition failed: %s", e)

    elapsed = time.monotonic() - t0
    emit("done", len(top), len(top), f"wrote {output_path.name} in {elapsed:.1f}s")

    return {
        "ok": True,
        "people_count": len(payloads),
        "output_path": str(output_path),
        "elapsed_seconds": round(elapsed, 1),
    }
