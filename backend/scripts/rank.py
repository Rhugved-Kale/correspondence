"""
Standalone ranking driver.

Run from project root:

    python -m backend.scripts.rank

Walks the cached contacts table, computes scores, and prints the top N
with their feature breakdowns. No external API calls, runs in seconds.

Use this to sanity-check the ranking heuristic before kicking off the
expensive per-person agent pipeline. If the top 10 here doesn't look
like the people you'd actually want to feature in the artifact, tune
the weights in agents/ranking.py and re-run.
"""

from __future__ import annotations

from backend.agents.ranking import rank_contacts
from backend.config import DB_PATH, get_settings
from backend.utils.logging import get_logger, setup_logging


def main() -> None:
    setup_logging("INFO")
    log = get_logger("rank")

    settings = get_settings()
    log.info("ranking contacts (top_n=%d)", settings.top_n_people)

    top = rank_contacts(DB_PATH, settings.top_n_people)

    if not top:
        log.warning("no contacts ranked. is the cache empty?")
        return

    log.info("")
    log.info("%-3s  %-7s  %-7s  %-6s  %-5s  %s", "#", "score", "threads", "in/out", "last", "who")
    log.info("-" * 92)
    for i, c in enumerate(top, 1):
        label = c.display_name or c.email
        last = (c.last_seen_utc or "")[:10]
        log.info(
            "%-3d  %-7.3f  %-7d  %3d/%-3d  %s  %s",
            i, c.score, c.thread_count, c.msg_in, c.msg_out, last, label[:50],
        )

    # Optional: show the feature breakdown for the top 3 so the user can
    # see why those three landed where they did. Useful when tuning weights.
    log.info("")
    log.info("feature breakdown for top 3:")
    for c in top[:3]:
        log.info("  %s", c.display_name or c.email)
        for feat, val in c.feature_breakdown.items():
            log.info("    %-20s  %+.3f", feat, val)


if __name__ == "__main__":
    main()
