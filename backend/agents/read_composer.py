"""
Compose The Read.

Takes the computed signals, runs the vignette agent over each candidate,
keeps what it wrote, and decides what makes the page.

Three rules govern selection, all of them anti-template. A page that says
the same thing about everybody is not worth sharing, so the composer's
job is as much refusal as it is assembly.

  WARRANT. A vignette needs an extreme signal, not merely a present one.
  Numeric warrant is checked here; semantic warrant is checked by the
  agent, which returns nothing when two things are not different in kind.
  A skip is a correct outcome and is not retried.

  DEDUPE BY EVIDENCE. Marguerite's latency spread and her latency
  inflection are one fact seen twice. Two vignettes resting on the same
  person and the same underlying measure would print one observation
  twice, so the higher-priority one wins and the other is dropped.

  CAP. Six at most, and no more than two of any one kind. Evidence-level
  dedupe is not enough on its own: four latency vignettes about four
  different people all pass it, and the page then makes the same
  observation four times with different names in it. That is the template
  failure wearing a disguise.

Order is fixed rather than scored: the opening vignette is the sharpest
latency contrast if one exists, because that finding (reply speed tracks
how answerable a question is, and the slowest-answered questions are the
easiest ones) is the one that carries the page. The deferral vignette
follows it, because it is the mechanism behind the first.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from backend.agents import phrasing as ph
from backend.agents.self_portrait import compute_signals
from backend.clients import claude
from backend.prompts import templates as T
from backend.utils.logging import get_logger


log = get_logger(__name__)

MAX_VIGNETTES = 6
INTER_CALL_SLEEP = 1.5

# At most this many of any one kind, counted on what is kept rather than
# what is attempted. Latency gets two because the finding is strong enough
# to bear repeating once with a different relationship; nothing gets more.
KIND_CAP = {"latency": 2}
DEFAULT_KIND_CAP = 1

# Fixed priority. Lower sorts earlier on the page. Cooling sits above the
# rest of the latency candidates because "you slowed down first" is a
# scarcer and sharper finding than another fast-versus-slow contrast, and
# when both exist for the same person the cooling one should win the
# evidence collision.
PRIORITY = {
    "latency": 0, "deferral": 1, "cooling": 2, "question_debt": 3,
    "hours": 4, "signoff": 5, "length": 6, "last_word": 7,
}


def _system() -> str:
    return T.SELF_PORTRAIT_SYSTEM + "\n\n" + T.SELF_PORTRAIT_ESCAPE


def _candidates(signals: dict, me: str, as_of: str) -> list[dict]:
    """
    Every vignette worth asking the agent about, with its evidence key.
    Numeric warrant is applied here; anything without it never costs a
    call.
    """
    out: list[dict] = []

    # One person gets one vignette, and where a cooling finding exists it is
    # the richer frame for that relationship. Letting the latency candidate
    # claim the evidence key first would lock out "you slowed down first",
    # which is scarcer and says more.
    cooling_emails = {c["email"] for c in signals.get("cooling", [])}

    for r in signals["latency"]["by_person"]:
        if not r.get("has_warrant") or r["email"] in cooling_emails:
            continue
        out.append({
            "kind": "latency",
            "evidence": f"latency:{r['email']}",
            # Ranked by how slow the relationship runs overall, not by raw
            # spread. Callum's 4825x comes from one 26-day invoice thread
            # against a median of 2.6 hours: he is fast with an outlier.
            # Wendy's median is 88 hours, and that is the finding.
            "sort": -r["median_h"],
            "prompt": T.LATENCY_VIGNETTE_USER_TEMPLATE.format(
                my_name=me, person=r["name"], n=r["n"],
                median=ph.duration(r["median_h"]), spread=r["spread_ratio"],
                fastest_time=ph.duration(r["fastest"]["hours"]),
                fastest_alt=ph.duration_forms(r["fastest"]["hours"]),
                fastest_when=r["fastest"]["when"],
                fastest_them=r["fastest"]["they_wrote"],
                fastest_me=r["fastest"]["i_wrote"],
                slowest_time=ph.duration(r["slowest"]["hours"]),
                slowest_alt=ph.duration_forms(r["slowest"]["hours"]),
                slowest_when=r["slowest"]["when"],
                slowest_them=r["slowest"]["they_wrote"],
                slowest_me=r["slowest"]["i_wrote"],
                between=ph.gap_between(r["fastest"]["when"], r["slowest"]["when"]),
            ),
        })

    d = signals["deferrals"]
    if d["count"] >= 2:
        rows = "\n".join(
            f'  {e["when"]}  to {e["person"]}: said "{e["phrase"]}"'
            f'{"" if e["followed_up"] else f"  [no further message from {me} in that thread]"}\n'
            f'      full line: "{e["excerpt"][:200]}"'
            for e in d["examples"][:10]
        )
        corr = (
            'One of them said so directly. Marguerite Vance wrote: "you have now '
            'told me twice that you will have a real answer after a conversation '
            'that has not yet been scheduled." When someone in the inbox names '
            "the pattern themselves, quote them rather than asserting it."
            if any("Marguerite" in e["person"] for e in d["examples"]) else ""
        )
        out.append({
            "kind": "deferral", "evidence": "deferral:all", "sort": -d["count"],
            "prompt": T.DEFERRAL_VIGNETTE_USER_TEMPLATE.format(
                my_name=me, count=d["count"], people=d["people"],
                unkept=d["unkept"], examples=rows, corroboration=corr,
            ),
        })

    for c in signals["cooling"]:
        out.append({
            "kind": "cooling", "evidence": f"latency:{c['email']}", "sort": 0,
            "prompt": T.COOLING_VIGNETTE_USER_TEMPLATE.format(
                my_name=me, person=c["name"],
                my_inflection=c["my_inflection"], their_inflection=c["their_inflection"],
                mover=c["moved_first"],
                my_hours=ph.hours_list(c["my_reply_hours"]),
                my_words=c["my_reply_words"],
                their_hours=ph.hours_list(c["their_reply_hours"]),
                their_longest=ph.duration_pair(max(c["their_reply_hours"] or [0])),
                last_from=c["last_message_from"], last_on=c["last_message_on"],
                sitting_for=ph.days_since(c["last_message_on"], as_of),
                last_text=c.get("last_text", "(not supplied)"),
            ),
        })

    q = signals["question_debt"]
    if q["count"] >= 2:
        rows = "\n".join(
            f'  {e["when"]}  {e["person"]} asked, in "{e["subject"]}":\n'
            + "\n".join(f'      "{x}"' for x in e["questions"])
            for e in q["examples"]
        )
        out.append({
            "kind": "question_debt", "evidence": "questions:all", "sort": -q["count"],
            "prompt": T.QUESTION_DEBT_VIGNETTE_USER_TEMPLATE.format(
                my_name=me, count=q["count"], people=q["people"], examples=rows,
            ),
        })

    h = signals.get("hours") or {}
    if h.get("total_sent"):
        lm = h.get("latest_message") or {}
        out.append({
            "kind": "hours", "evidence": "hours:all", "sort": 0,
            "prompt": T.HOURS_VIGNETTE_USER_TEMPLATE.format(
                my_name=me, total=h["total_sent"],
                day_n=h["day_n"], evening_n=h["evening_n"],
                late_n=h["late_n"], dead_n=h["dead_n"],
                window_days=ph.window_span(signals["window"]["days"]),
                day_pct=ph.percent_forms(h["day_pct"]),
                evening_pct=ph.percent_forms(h["evening_pct"]),
                late_pct=ph.percent_forms(h["late_pct"]),
                dead_pct=ph.percent_forms(h["dead_pct"]),
                latest_at=ph.clock(lm.get("at", "")),
                latest_when=lm.get("when", "?"),
                latest_ago=ph.days_since(lm.get("when", as_of), as_of),
                latest_subject=lm.get("subject", ""),
                latest_excerpt=lm.get("excerpt", ""),
            ),
        })

    rows = signals["length_by_person"]
    if len(rows) >= 3:
        top, bottom = rows[0], rows[-1]
        table = "\n".join(
            f'  {r["name"]:<26} {r["median_words"]:>4} words   (over {r["n"]} messages)'
            for r in rows
        )
        out.append({
            "kind": "length", "evidence": "length:all", "sort": 0,
            "prompt": T.LENGTH_VIGNETTE_USER_TEMPLATE.format(
                my_name=me, table=table,
                top_name=top["name"], top_words=top["median_words"],
                bottom_name=bottom["name"], bottom_words=bottom["median_words"],
                spread=ph.ratio(top["median_words"], bottom["median_words"]),
            ),
        })

    sg = signals["signoffs"]
    if len(sg) >= 3:
        table = "\n".join(f'  {r["name"]:<26} "{r["signoff"]}"  ({r["n"]}x)' for r in sg)
        openers = "\n".join(
            f'  "{o["phrase"]}"  {o["n"]}x' for o in signals["openers"]
        ) or "  (none recurring)"
        out.append({
            "kind": "signoff", "evidence": "signoff:all", "sort": 0,
            "prompt": T.SIGNOFF_VIGNETTE_USER_TEMPLATE.format(
                my_name=me, table=table, openers=openers,
                signoff_total=sum(r["n"] for r in sg), signoff_people=len(sg),
            ),
        })

    lw = signals["last_word"]
    if lw["threads"] >= 8:
        hanging = "\n".join(
            f'  {r["name"]:<26} {r["threads"]} threads' for r in lw["left_hanging"]
        ) or "  (none)"
        out.append({
            "kind": "last_word", "evidence": "lastword:all", "sort": 0,
            "prompt": T.LAST_WORD_VIGNETTE_USER_TEMPLATE.format(
                my_name=me, threads=lw["threads"], i_ended=lw["i_ended"],
                they_ended=lw["they_ended"],
                i_ended_pct=ph.percent_forms(lw["i_ended_pct"]),
                left_hanging=hanging,
            ),
        })

    # Rank latency candidates so only the two sharpest compete for the cap,
    # and push the rest below cooling. Without this, a mid-ranked latency
    # vignette can claim a person's evidence key and lock out the stronger
    # cooling finding about the same relationship.
    seen_latency = 0
    for c in sorted([x for x in out if x["kind"] == "latency"], key=lambda x: x["sort"]):
        seen_latency += 1
        if seen_latency > KIND_CAP["latency"]:
            c["_demoted"] = True

    out.sort(key=lambda c: (
        PRIORITY[c["kind"]] + (10 if c.get("_demoted") else 0),
        c["sort"],
    ))
    return out


async def compose_read(
    db_path: Path, my_email: str, my_name: str, as_of: str
) -> dict:
    """
    Run every candidate and return the page. Skips are expected and are
    not errors; a page with four vignettes is better than one with six
    where two were forced.
    """
    signals = compute_signals(db_path, my_email)
    if signals.get("error"):
        return {"vignettes": [], "error": signals["error"]}

    first_name = my_name.split()[0] if my_name else "you"
    cands = _candidates(signals, first_name, as_of)
    log.info("The Read: %d candidates with numeric warrant", len(cands))

    kept: list[dict] = []
    used_evidence: set[str] = set()
    kind_counts: dict[str, int] = {}
    skipped = 0

    for c in cands:
        if len(kept) >= MAX_VIGNETTES:
            break
        cap = KIND_CAP.get(c["kind"], DEFAULT_KIND_CAP)
        if kind_counts.get(c["kind"], 0) >= cap:
            log.info("The Read: %s dropped, already have %d of that kind",
                     c["kind"], cap)
            continue
        # Dedupe before spending a call, not after.
        if c["evidence"] in used_evidence:
            log.info("The Read: %s dropped, evidence %s already used",
                     c["kind"], c["evidence"])
            continue
        try:
            data = await claude.call_json(
                system=_system(), user=c["prompt"], max_tokens=2000
            )
        except Exception as e:
            log.warning("The Read: %s failed (%s)", c["kind"], e)
            continue

        v = data.get("vignette")
        if not v or not v.get("body"):
            skipped += 1
            log.info("The Read: %s skipped (%s)", c["kind"],
                     data.get("skip_reason", "no reason"))
        else:
            kept.append({
                "kind": c["kind"],
                "headline": v.get("headline", ""),
                "body": v["body"],
            })
            used_evidence.add(c["evidence"])
            kind_counts[c["kind"]] = kind_counts.get(c["kind"], 0) + 1
        await asyncio.sleep(INTER_CALL_SLEEP)

    log.info("The Read: %d vignettes kept, %d skipped", len(kept), skipped)
    return {
        "vignettes": kept,
        "window": signals["window"],
        "volume": signals["volume"],
        "considered": len(cands),
        "skipped": skipped,
    }
