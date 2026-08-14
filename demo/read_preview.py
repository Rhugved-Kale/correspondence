"""
The Read: vignette iteration harness.

Runs the self-portrait vignette agent against the demo fixture, one person
at a time, and prints what it produced or why it skipped.

    python -m demo.read_preview                # all warranted people + Dane
    python -m demo.read_preview wendy dane

Dane is the negative case. He clears the numeric warrant threshold at 374x
but his two extremes are a live product question and a thread-closing
acknowledgement, which are not different in kind. Correct output for Dane
is silence. If he produces prose, the escape clause is not working.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from backend.agents.self_portrait import compute_signals
from backend.clients import claude
from backend.prompts import templates as T

DEMO_DIR = Path(__file__).resolve().parent


def _dur(h: float) -> str:
    if h < 1:
        return f"{h * 60:.0f} minutes"
    if h < 48:
        return f"{h:.1f} hours"
    return f"{h / 24:.1f} days"


def _alt(h: float) -> str:
    """
    The same duration in the other units a writer might reach for. Handing
    every form over is cheaper than banning conversion: the model reached
    for "a quarter of an hour" and "sixty-two hours" despite an explicit
    prohibition, which is the Stage 2 lesson repeating.
    """
    forms = []
    if h < 1:
        forms.append(f"{h * 60:.0f} minutes")
        if h * 60 >= 45:
            forms.append("about an hour")
    elif h < 48:
        forms.append(f"{h:.0f} hours")
        forms.append(f"{h / 24:.1f} days")
    else:
        forms.append(f"{h / 24:.0f} days")
        forms.append(f"{h:.0f} hours")
        if h / 24 >= 13:
            forms.append(f"{h / 24 / 7:.0f} weeks")
    return ", or ".join(dict.fromkeys(forms))


def _between(a: str, b: str) -> str:
    """Days between the two exchanges, precomputed. The model got this
    wrong as 'five months later' when it was three weeks."""
    from datetime import date
    try:
        d = abs((date.fromisoformat(b) - date.fromisoformat(a)).days)
    except (ValueError, TypeError):
        return "unknown, do not refer to it"
    if d < 14:
        return f"{d} days apart"
    if d < 60:
        return f"{d} days apart, or about {d // 7} weeks"
    return f"{d} days apart, or about {d // 30} months"


async def run_one(row: dict, my_name: str) -> dict:
    user = T.LATENCY_VIGNETTE_USER_TEMPLATE.format(
        my_name=my_name,
        person=row["name"],
        n=row["n"],
        median=_dur(row["median_h"]),
        spread=row["spread_ratio"],
        fastest_time=_dur(row["fastest"]["hours"]),
        fastest_alt=_alt(row["fastest"]["hours"]),
        fastest_when=row["fastest"]["when"],
        fastest_them=row["fastest"]["they_wrote"],
        fastest_me=row["fastest"]["i_wrote"],
        slowest_time=_dur(row["slowest"]["hours"]),
        slowest_alt=_alt(row["slowest"]["hours"]),
        slowest_when=row["slowest"]["when"],
        between=_between(row["fastest"]["when"], row["slowest"]["when"]),
        slowest_them=row["slowest"]["they_wrote"],
        slowest_me=row["slowest"]["i_wrote"],
    )
    system = T.SELF_PORTRAIT_SYSTEM + "\n\n" + T.SELF_PORTRAIT_ESCAPE
    try:
        return await claude.call_json(system=system, user=user, max_tokens=2000)
    except Exception as e:
        return {"__error__": f"{type(e).__name__}: {e}"}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("handles", nargs="*", help="contact handles; default = warranted + dane")
    ap.add_argument("--db", default="data/demo.db")
    args = ap.parse_args()

    contacts = json.loads((DEMO_DIR / "contacts.json").read_text())
    people = contacts["people"]
    my = people[contacts["me"]]
    signals = compute_signals(Path(args.db), my["email"])
    by_email = {r["email"]: r for r in signals["latency"]["by_person"]}

    if args.handles:
        targets = [(h, people[h]["email"]) for h in args.handles if h in people]
    else:
        email_to_handle = {v["email"]: k for k, v in people.items()}
        targets = [
            (email_to_handle.get(r["email"], r["email"]), r["email"])
            for r in signals["latency"]["by_person"] if r["has_warrant"]
        ]

    print(f"{len(targets)} people\n")
    wrote = skipped = 0
    for handle, email in targets:
        row = by_email.get(email)
        if not row:
            print(f"--- {handle}: no reply pairs\n")
            continue

        tag = "warrant" if row["has_warrant"] else "NO WARRANT"
        print("=" * 76)
        print(f"{row['name']}  [{tag}]  spread={row['spread_ratio']}x  n={row['n']}")
        print(f"   fast {_dur(row['fastest']['hours']):>12}  {row['fastest']['they_wrote'][:66]!r}")
        print(f"   slow {_dur(row['slowest']['hours']):>12}  {row['slowest']['they_wrote'][:66]!r}")
        print("=" * 76)

        data = await run_one(row, my["name"].split()[0])
        if "__error__" in data:
            print(f"  ERROR {data['__error__']}\n")
            continue

        v = data.get("vignette")
        if not v:
            skipped += 1
            print(f"  SKIPPED: {data.get('skip_reason', '(no reason given)')}\n")
        else:
            wrote += 1
            print(f"\n  {v.get('headline', '')}\n")
            body = v.get("body", "")
            for i in range(0, len(body), 72):
                print(f"  {body[i:i + 72]}")
            print()
        await asyncio.sleep(1.5)

    print(f"\n{wrote} vignettes, {skipped} skipped")


if __name__ == "__main__":
    asyncio.run(main())
