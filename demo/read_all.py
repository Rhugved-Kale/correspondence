"""
Run every Read vignette against the demo fixture.

    python -m demo.read_all
    python -m demo.read_all --only deferral hours

Prints what each vignette produced, or why it declined. A skip is a
correct outcome, not a failure: the escape clause exists so the page says
nothing rather than manufacturing a distinction to fill a slot.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from backend.agents import phrasing as ph
from backend.agents.self_portrait import compute_signals
from backend.clients import claude
from backend.prompts import templates as T

DEMO_DIR = Path(__file__).resolve().parent


AS_OF = "2026-06-30"   # demo window close; real runs pass today


def build(kind: str, s: dict, me: str) -> str | None:
    """Format one vignette's precomputed slice, or None if there's no data."""
    if kind == "deferral":
        d = s["deferrals"]
        if d["count"] < 2:
            return None
        rows = "\n".join(
            f'  {e["when"]}  to {e["person"]}: said "{e["phrase"]}"'
            f'{"" if e["followed_up"] else "  [no further message from " + me + " in that thread]"}\n'
            f'      full line: "{e["excerpt"][:200]}"'
            for e in d["examples"][:10]
        )
        corr = (
            "One of them said so directly. Marguerite Vance wrote: \"you have "
            "now told me twice that you will have a real answer after a "
            "conversation that has not yet been scheduled.\" When someone in "
            "the inbox names the pattern themselves, quote them rather than "
            "asserting it."
            if any("Marguerite" in e["person"] for e in d["examples"]) else ""
        )
        return T.DEFERRAL_VIGNETTE_USER_TEMPLATE.format(
            my_name=me, count=d["count"], people=d["people"],
            unkept=d["unkept"], examples=rows, corroboration=corr,
        )

    if kind == "cooling":
        if not s["cooling"]:
            return None
        c = s["cooling"][0]
        return T.COOLING_VIGNETTE_USER_TEMPLATE.format(
            my_name=me, person=c["name"],
            my_inflection=c["my_inflection"], their_inflection=c["their_inflection"],
            mover=c["moved_first"],
            my_hours=ph.hours_list(c["my_reply_hours"]),
            my_words=c["my_reply_words"],
            their_hours=ph.hours_list(c["their_reply_hours"]),
            their_longest=ph.duration_pair(max(c["their_reply_hours"] or [0])),
            last_from=c["last_message_from"], last_on=c["last_message_on"],
            sitting_for=ph.days_since(c["last_message_on"], AS_OF),
            last_text=c.get("last_text", "(not supplied)"),
        )

    if kind == "question_debt":
        q = s["question_debt"]
        if q["count"] < 2:
            return None
        rows = "\n".join(
            f'  {e["when"]}  {e["person"]} asked, in "{e["subject"]}":\n'
            + "\n".join(f'      "{x}"' for x in e["questions"])
            for e in q["examples"]
        )
        return T.QUESTION_DEBT_VIGNETTE_USER_TEMPLATE.format(
            my_name=me, count=q["count"], people=q["people"], examples=rows,
        )

    if kind == "hours":
        h = s["hours"]
        lm = h.get("latest_message") or {}
        return T.HOURS_VIGNETTE_USER_TEMPLATE.format(
            my_name=me, total=h["total_sent"],
            day_n=h["day_n"], evening_n=h["evening_n"],
            late_n=h["late_n"], dead_n=h["dead_n"],
            window_days=f'{s["window"]["days"]} days, or about {s["window"]["days"]//7} weeks',
            day_pct=ph.percent_forms(h["day_pct"]),
            evening_pct=ph.percent_forms(h["evening_pct"]),
            late_pct=ph.percent_forms(h["late_pct"]),
            dead_pct=ph.percent_forms(h["dead_pct"]),
            latest_at=ph.clock(lm.get("at", "")),
            latest_when=lm.get("when", "?"),
            latest_ago=ph.days_since(lm.get("when", AS_OF), AS_OF),
            latest_subject=lm.get("subject", ""),
            latest_excerpt=lm.get("excerpt", ""),
        )

    if kind == "length":
        rows = s["length_by_person"]
        if len(rows) < 3:
            return None
        table = "\n".join(
            f'  {r["name"]:<26} {r["median_words"]:>4} words   (over {r["n"]} messages)'
            for r in rows
        )
        top, bottom = rows[0], rows[-1]
        return T.LENGTH_VIGNETTE_USER_TEMPLATE.format(
            my_name=me, table=table,
            top_name=top["name"], top_words=top["median_words"],
            bottom_name=bottom["name"], bottom_words=bottom["median_words"],
            spread=ph.ratio(top["median_words"], bottom["median_words"]),
        )

    if kind == "signoff":
        rows = s["signoffs"]
        if len(rows) < 3:
            return None
        table = "\n".join(f'  {r["name"]:<26} "{r["signoff"]}"  ({r["n"]}x)' for r in rows)
        openers = "\n".join(f'  "{o["phrase"]}"  {o["n"]}x' for o in s["openers"]) or "  (none recurring)"
        return T.SIGNOFF_VIGNETTE_USER_TEMPLATE.format(
            my_name=me, table=table, openers=openers,
            signoff_total=sum(r["n"] for r in rows),
            signoff_people=len(rows),
        )

    if kind == "last_word":
        lw = s["last_word"]
        hanging = "\n".join(
            f'  {r["name"]:<26} {r["threads"]} threads' for r in lw["left_hanging"]
        ) or "  (none)"
        return T.LAST_WORD_VIGNETTE_USER_TEMPLATE.format(
            my_name=me, threads=lw["threads"], i_ended=lw["i_ended"],
            they_ended=lw["they_ended"],
            i_ended_pct=ph.percent_forms(lw["i_ended_pct"]),
            left_hanging=hanging,
        )
    return None


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="vignette kinds to run")
    ap.add_argument("--db", default="data/demo.db")
    args = ap.parse_args()

    contacts = json.loads((DEMO_DIR / "contacts.json").read_text())
    my = contacts["people"][contacts["me"]]
    me = my["name"].split()[0]
    s = compute_signals(Path(args.db), my["email"])

    kinds = args.only or [
        "deferral", "cooling", "question_debt", "hours",
        "length", "signoff", "last_word",
    ]
    system = T.SELF_PORTRAIT_SYSTEM + "\n\n" + T.SELF_PORTRAIT_ESCAPE

    wrote = skipped = nodata = 0
    for kind in kinds:
        user = build(kind, s, me)
        print("=" * 76)
        print(kind.upper().replace("_", " "))
        print("=" * 76)
        if user is None:
            nodata += 1
            print("  no data for this vignette\n")
            continue
        try:
            data = await claude.call_json(system=system, user=user, max_tokens=2000)
        except Exception as e:
            print(f"  ERROR {type(e).__name__}: {e}\n")
            continue

        v = data.get("vignette")
        if not v:
            skipped += 1
            print(f"  SKIPPED: {data.get('skip_reason', '(none)')}\n")
        else:
            wrote += 1
            print(f"\n  {v.get('headline','')}\n")
            b = v.get("body", "")
            for i in range(0, len(b), 72):
                print(f"  {b[i:i+72]}")
            print()
        await asyncio.sleep(1.5)

    print(f"\n{wrote} written, {skipped} skipped, {nodata} no data")


if __name__ == "__main__":
    asyncio.run(main())
