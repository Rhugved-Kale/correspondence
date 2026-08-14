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

# Bounded concurrency, unlike the per-person agents which run strictly
# sequentially. That rule exists because those calls carry a whole
# correspondence, around 200k tokens, and firing four at once guarantees
# a 429 on Tier 1. A gate call carries one vignette and a roster: about
# 2.4k tokens. Three in flight is 7.2k against a 30k-per-minute budget,
# which is not close to anything.
#
# It matters because the gate runs inline in the pipeline now. Sequential
# put it at just over thirty seconds, which is enough to make someone
# think about skipping it. Three at a time puts it around ten.
GATE_CONCURRENCY = 3

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
    sem = asyncio.Semaphore(GATE_CONCURRENCY)

    async def gate(v: dict) -> dict:
        user = T.CARD_USER_TEMPLATE.format(
            headline=v.get("headline", ""),
            body=v.get("body", ""),
            roster=roster,
        )
        async with sem:
            try:
                data = await claude.call_json(
                    system=T.CARD_SYSTEM, user=user, max_tokens=1200
                )
            except Exception as e:
                log.warning("card gate failed for %s: %s", v.get("kind"), e)
                return {"rejected": {"kind": v.get("kind"),
                                     "headline": v.get("headline", ""),
                                     "reason": f"error: {e}"}}

            card = data.get("card")
            if not card or not card.get("quote"):
                reason = data.get("skip_reason", "no reason given")
                log.info("CARD reject kind=%s reason=%s", v.get("kind"), reason)
                return {"rejected": {"kind": v.get("kind"),
                                     "headline": v.get("headline", ""),
                                     "reason": reason}}

            # Length is a canvas constraint, never a proxy for what
            # deserves to be on it. A finding that cleared the gate gets a
            # trim attempt rather than being discarded for two words.
            n = len(card["quote"].split())
            if n > MAX_QUOTE_WORDS:
                log.info("CARD trim kind=%s %d words", v.get("kind"), n)
                try:
                    retry = await claude.call_json(
                        system=T.CARD_SYSTEM,
                        user=user + (
                            f"\n\nYour previous quote ran to {n} words, which "
                            f"does not fit. Return the same finding in "
                            f"{MAX_QUOTE_WORDS} words or fewer. Cut detail, "
                            f"do not cut the observation."
                        ),
                        max_tokens=1200,
                    )
                    if retry.get("card", {}).get("quote"):
                        card = retry["card"]
                        n = len(card["quote"].split())
                except Exception as e:
                    log.warning("card trim failed for %s: %s", v.get("kind"), e)

        if not (MIN_QUOTE_WORDS <= n <= MAX_QUOTE_WORDS):
            log.info("CARD reject kind=%s reason=length %d words", v.get("kind"), n)
            return {"rejected": {"kind": v.get("kind"),
                                 "headline": v.get("headline", ""),
                                 "reason": f"{n} words, outside "
                                           f"{MIN_QUOTE_WORDS}-{MAX_QUOTE_WORDS}"}}

        return {"card": {"kind": v.get("kind"),
                         "kicker": card.get("kicker", ""),
                         "quote": card["quote"],
                         "core": data.get("core", ""),
                         "source_headline": v.get("headline", "")}}

    # gather preserves order, so cards stay in composer priority.
    outcomes = await asyncio.gather(*(gate(v) for v in vignettes))
    cards = [o["card"] for o in outcomes if o.get("card")]
    rejected = [o["rejected"] for o in outcomes if o.get("rejected")]

    log.info("CARD summary: %d of %d survived anonymisation",
             len(cards), len(vignettes))
    return {"cards": cards, "rejected": rejected, "considered": len(vignettes)}
