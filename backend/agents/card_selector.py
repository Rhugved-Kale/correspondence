"""
Select and build share cards.

A stricter composer than the one behind The Read, and deliberately a
separate module rather than a flag on that one. The two answer different
questions. The Read asks "is this worth telling the reader about
themselves", in a private view where naming the people in their life is
fine. The card asks "would the reader post this in public", which brings
in a constraint The Read never has to think about: the card names someone
who never agreed to appear on anyone's timeline.

Anonymisation is therefore a selection gate rather than a formatting step.
Every vignette is tried with the names removed. What still means something
becomes a card. What collapses stays in The Read.

The gate has a useful bias built into it. Findings about the reader's own
behaviour survive without names, because the reader is the subject.
Findings about one particular relationship usually do not. So the card set
skews toward the self-portrait and away from the person page, which is the
argument for where share weight belongs, enforced rather than hoped for.

Consequence to expect: fewer cards than vignettes. That is the gate
working.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.clients import claude
from backend.prompts import templates as T
from backend.utils.logging import get_logger


log = get_logger(__name__)

INTER_CALL_SLEEP = 1.5

# A card is one thought. Past this it stops being a card and starts being
# a paragraph on a coloured background, which is what v1 shipped.
# What physically sets on a 1080px canvas in Fraunces at a readable size.
# This is a canvas constraint and nothing else: a finding that survived
# the gate must never be discarded for being two words long, which would
# be length quietly acting as a quality filter. Over-length gets one
# trim attempt before it is dropped.
MAX_QUOTE_WORDS = 48
MIN_QUOTE_WORDS = 12


def _roster(people: list[dict]) -> str:
    """
    Who each named person is, so the gate can replace a name with an
    accurate relationship instead of guessing one. Without this it invents
    a plausible role, which is a fabrication in the one place the card
    cannot afford one.
    """
    lines = []
    for p in people:
        role = (p.get("role_hint") or "").strip()
        if role and role != p.get("name"):
            lines.append(f"  {p['name']}: {role}")
        else:
            # Empty About block is the correct outcome for a private
            # person, and it means we genuinely do not know who they are.
            # Saying so is what stops the gate from guessing: it called a
            # sister "a friend" and a bookkeeper "an angel investor" when
            # this line read as an absence rather than a prohibition.
            lines.append(f"  {p['name']}: NO KNOWN RELATIONSHIP - do not guess one")
    lines.append(
        "  Anyone not listed above: NO KNOWN RELATIONSHIP - do not guess one"
    )
    return "\n".join(lines)


async def build_cards(read: dict, people: list[dict]) -> dict:
    """
    Run every kept vignette through the gate. Returns the cards that
    survived plus the ones that did not, because which findings collapse
    is worth seeing rather than silently dropping.
    """
    vignettes = read.get("vignettes") or []
    if not vignettes:
        return {"cards": [], "rejected": [], "considered": 0}

    roster = _roster(people)
    cards: list[dict] = []
    rejected: list[dict] = []

    for v in vignettes:
        user = T.CARD_USER_TEMPLATE.format(
            headline=v.get("headline", ""),
            body=v.get("body", ""),
            roster=roster,
        )
        try:
            data = await claude.call_json(
                system=T.CARD_SYSTEM, user=user, max_tokens=1200
            )
        except Exception as e:
            log.warning("card gate failed for %s: %s", v.get("kind"), e)
            rejected.append({"kind": v.get("kind"), "reason": f"error: {e}"})
            continue

        card = data.get("card")
        if not card or not card.get("quote"):
            reason = data.get("skip_reason", "no reason given")
            log.info("CARD reject kind=%s reason=%s", v.get("kind"), reason)
            rejected.append({
                "kind": v.get("kind"),
                "headline": v.get("headline", ""),
                "reason": reason,
            })
            await asyncio.sleep(INTER_CALL_SLEEP)
            continue

        # Length is a hard constraint on what fits the canvas, never a
        # proxy for what deserves to be on it. Selection already happened
        # upstream; this only rejects text that physically will not set.
        n = len(card["quote"].split())
        if n > MAX_QUOTE_WORDS:
            # Ask for a trim rather than discarding. The finding already
            # cleared the gate; this is a typesetting problem.
            log.info("CARD trim kind=%s %d words", v.get("kind"), n)
            try:
                retry = await claude.call_json(
                    system=T.CARD_SYSTEM,
                    user=user + (
                        f"\n\nYour previous quote ran to {n} words, which does not "
                        f"fit. Return the same finding in {MAX_QUOTE_WORDS} words or "
                        f"fewer. Cut detail, do not cut the observation."
                    ),
                    max_tokens=1200,
                )
                if retry.get("card", {}).get("quote"):
                    card = retry["card"]
                    n = len(card["quote"].split())
            except Exception as e:
                log.warning("card trim failed for %s: %s", v.get("kind"), e)
            await asyncio.sleep(INTER_CALL_SLEEP)

        if not (MIN_QUOTE_WORDS <= n <= MAX_QUOTE_WORDS):
            log.info("CARD reject kind=%s reason=length %d words", v.get("kind"), n)
            rejected.append({
                "kind": v.get("kind"),
                "headline": v.get("headline", ""),
                "reason": f"{n} words, outside {MIN_QUOTE_WORDS}-{MAX_QUOTE_WORDS}",
            })
            await asyncio.sleep(INTER_CALL_SLEEP)
            continue

        cards.append({
            "kind": v.get("kind"),
            "kicker": card.get("kicker", ""),
            "quote": card["quote"],
            "core": data.get("core", ""),
            "source_headline": v.get("headline", ""),
        })
        await asyncio.sleep(INTER_CALL_SLEEP)

    log.info("CARD summary: %d of %d survived anonymisation",
             len(cards), len(vignettes))
    return {
        "cards": cards,
        "rejected": rejected,
        "considered": len(vignettes),
    }
