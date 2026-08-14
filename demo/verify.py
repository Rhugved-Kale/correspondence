"""
Verify the demo corpus against its planted findings.

The corpus is built on one rule: we author the world, we do not author the
conclusions. The Read is supposed to discover the reply-latency gap
because the gap is genuinely present in the timestamps, not because
anyone wrote it down.

That rule is only real if it is checkable, which is what this script is
for. Every planted finding in world.md gets an assertion here. If a
regeneration quietly breaks one, this says so.

    python -m demo.verify

Exit code is non-zero if any check fails, so it can gate a regeneration.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent
THREADS_DIR = DEMO_DIR / "threads"

PASS, FAIL, WARN = "pass", "FAIL", "warn"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str, soft: bool = False) -> None:
    results.append((PASS if ok else (WARN if soft else FAIL), name, detail))


def _load() -> tuple[list[dict], dict]:
    contacts = json.loads((DEMO_DIR / "contacts.json").read_text())
    threads = [json.loads(p.read_text()) for p in sorted(THREADS_DIR.glob("*.json"))]
    return threads, contacts


def _dt(m: dict) -> datetime:
    return datetime.fromisoformat(m["date_utc"])


def main() -> int:
    threads, contacts = _load()
    me = contacts["me"]

    msgs = [(t, m) for t in threads for m in t["messages"]]
    mine = [m for _, m in msgs if m["from"] == me]

    # --- volume -----------------------------------------------------------
    check(
        "corpus volume",
        380 <= len(msgs) <= 480,
        f"{len(msgs)} messages across {len(threads)} threads",
    )

    # --- second shift -----------------------------------------------------
    # The signal is the shape, not the ratio. A first pass checked "what
    # percent lands after 22:00" and failed at 21%, which was the wrong
    # question: 21% after 22:00 alongside a dead evening is a much clearer
    # second shift than 35% smeared evenly from 18:00 onward.
    #
    # What actually makes it a second shift is the gap. Work, stop for
    # dinner and life, come back late. So we assert two populated bands
    # with an empty trough between them.
    hours = [_dt(m).hour for m in mine]
    n = len(hours) or 1
    day = sum(1 for h in hours if 9 <= h < 18) / n
    evening = sum(1 for h in hours if 18 <= h < 22) / n
    late = sum(1 for h in hours if h >= 22 or h < 2) / n

    check(
        "second shift: day band",
        day >= 0.50,
        f"{day * 100:.0f}% between 09:00 and 18:00",
    )
    check(
        "second shift: late band",
        late >= 0.15,
        f"{late * 100:.0f}% between 22:00 and 02:00",
    )
    check(
        "second shift: evening trough",
        evening <= 0.06,
        f"{evening * 100:.0f}% between 18:00 and 22:00 (the gap is the finding)",
    )

    # --- reply latency and word count per person --------------------------
    lat: dict[str, list[float]] = defaultdict(list)
    words: dict[str, list[int]] = defaultdict(list)
    for t, m in msgs:
        if m["from"] != me:
            continue
        others = [p for p in t["participants"] if p != me]
        if not others:
            continue
        words[others[0]].append(len(m["body"].split()))
    for t in threads:
        others = [p for p in t["participants"] if p != me]
        if not others:
            continue
        ms = t["messages"]
        for i, m in enumerate(ms):
            if m["from"] == me and i > 0 and ms[i - 1]["from"] != me:
                lat[others[0]].append((_dt(m) - _dt(ms[i - 1])).total_seconds() / 3600)

    def med_lat(p: str) -> float:
        return statistics.median(lat[p]) if lat.get(p) else float("nan")

    def med_words(p: str) -> float:
        return statistics.median(words[p]) if words.get(p) else float("nan")

    dane_l, wendy_l = med_lat("dane"), med_lat("wendy")
    check(
        "Dane reply floor",
        dane_l * 60 <= 30,
        f"median {dane_l * 60:.0f} min",
    )
    check(
        "Wendy reply gap",
        wendy_l / 24 >= 2.5,
        f"median {wendy_l / 24:.1f} days",
    )
    check(
        "the headline ratio",
        wendy_l / dane_l >= 100,
        f"Wendy/Dane = {wendy_l / dane_l:.0f}x",
    )

    check(
        "length inverse to closeness",
        med_words("wendy") < med_words("dane") * 4 < med_words("marguerite"),
        f"Wendy {med_words('wendy'):.0f}w, Dane {med_words('dane'):.0f}w, "
        f"Marguerite {med_words('marguerite'):.0f}w",
    )

    # --- context class, not person ---------------------------------------
    # The finding that survives is "latency tracks the question," so the
    # same person must show a wide spread across question types. If this
    # collapses, constraint 1 in notes/stage3-self-portrait.md loses its
    # evidence.
    def thread_lat(tid: str) -> float:
        t = next((x for x in threads if x["thread_id"] == tid), None)
        if not t:
            return float("nan")
        ms = t["messages"]
        v = [
            (_dt(m) - _dt(ms[i - 1])).total_seconds() / 3600
            for i, m in enumerate(ms)
            if m["from"] == me and i > 0 and ms[i - 1]["from"] != me
        ]
        return statistics.median(v) if v else float("nan")

    easy, hard = thread_lat("t-marguerite-close"), thread_lat("t-marguerite-metrics")
    check(
        "same person, different question",
        hard / easy >= 20,
        f"Marguerite: {easy:.1f}h on the close, {hard:.1f}h on the metrics = {hard / easy:.0f}x",
    )

    ros_crisis = thread_lat("t-ros-double-booking")
    check(
        "crisis floor is not a general rate",
        med_lat("rosalind") > 24,
        f"Rosalind median {med_lat('rosalind') / 24:.1f}d despite a 17-min crisis reply",
    )

    # --- who moved first --------------------------------------------------
    nk = next(x for x in threads if x["thread_id"] == "t-nkechi-equity")
    ms = nk["messages"]
    my_gaps = [
        (_dt(m) - _dt(ms[i - 1])).total_seconds() / 86400
        for i, m in enumerate(ms) if m["from"] == me and i > 0
    ]
    my_words = [len(m["body"].split()) for m in ms if m["from"] == me]
    check(
        "Nkechi: user cools first",
        my_gaps == sorted(my_gaps) and my_words == sorted(my_words, reverse=True),
        f"Priya gaps {[f'{g:.1f}d' for g in my_gaps]}, words {my_words}",
    )

    # --- unanswered threads (the Forgotten plants) ------------------------
    unanswered = [
        t["thread_id"] for t in threads
        if t["messages"][-1]["from"] != me and len(t["participants"]) == 2
        and t["participants"][0] != "__noise__"
    ]
    for tid in ("t-wendy-birthday", "t-josiah-intro", "t-nkechi-equity", "t-ros-day-sheet"):
        check(f"unanswered: {tid}", tid in unanswered, "ends on them, no reply")

    # --- last word --------------------------------------------------------
    ezra = [t for t in threads if "ezra" in t["participants"]]
    check(
        "Ezra gets the last word",
        all(t["messages"][-1]["from"] == "ezra" for t in ezra) and len(ezra) >= 3,
        f"{len(ezra)} threads, all ending on Ezra",
    )

    # --- question debt ----------------------------------------------------
    # Inbound messages containing a question that were never followed by a
    # reply from the user in that thread.
    debt = 0
    for t in threads:
        ms = t["messages"]
        for i, m in enumerate(ms):
            if m["from"] == me or "?" not in m["body"]:
                continue
            if not any(x["from"] == me for x in ms[i + 1:]):
                debt += 1
    check("question debt", debt >= 8, f"{debt} unanswered messages containing a question")

    # --- the deferral pattern --------------------------------------------
    # "This week" as a way of saying no without saying no. Counts distinct
    # messages, not phrase matches: one message often carries two phrases
    # ("I'll venmo you this week") and counting matches inflates it by
    # about 60%.
    import re
    defer = re.compile(
        r"(let me (look|think|check|see)|i'?ll (venmo|ping|send|look|get back|have)"
        r"|this week|next week|give me a few days)", re.I
    )
    deferrals: set[tuple[str, str]] = set()
    for t in threads:
        others = [p for p in t["participants"] if p != me]
        if not others:
            continue
        for m in t["messages"]:
            if m["from"] == me and defer.search(m["body"]):
                deferrals.add((others[0], m["date_utc"]))
    people_deferred = {p for p, _ in deferrals}
    check(
        "deferral pattern",
        len(deferrals) >= 10 and len(people_deferred) >= 6,
        f"{len(deferrals)} deferral messages across {len(people_deferred)} relationships",
    )

    # The corroboration. A finding a person in the inbox names out loud is
    # worth more than one the agent infers, and it is a share-card
    # candidate, so assert the line survives regeneration.
    marg = next((x for x in threads if x["thread_id"] == "t-marguerite-metrics"), None)
    named = bool(marg) and any(
        "told me twice" in m["body"] for m in marg["messages"]
    )
    check("deferral named in-corpus", named, "Marguerite calls out the pattern in June")

    # --- report -----------------------------------------------------------
    width = max(len(n) for _, n, _ in results) + 2
    failed = 0
    for status, name, detail in results:
        if status == FAIL:
            failed += 1
        print(f"[{status:>4}] {name:<{width}} {detail}")

    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
