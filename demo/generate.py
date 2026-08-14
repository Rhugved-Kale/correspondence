"""
Demo corpus generator.

Reads the world spec, the contact registry, and the thread plan, then
generates the threads that aren't hand-written. Hand-written anchors are
fed in as few-shot examples so the generated bulk inherits their texture
instead of drifting into competent email-shaped mush.

Run it:

    python -m demo.generate --plan              show what would run, no API calls
    python -m demo.generate --only dane-standup-april
    python -m demo.generate --run               everything not already written

Key handling: this module never reads, prints, or stores the API key. It
calls backend.clients.claude, which loads it through pydantic Settings
from .env, which is gitignored. Nothing here logs request objects, and
the failure path prints an exception type and message only.

Run artifacts (raw model output, cost log) are written outside the repo,
to DEMO_ARTIFACT_DIR or a system temp directory. The corpus is source and
gets committed. The machinery that produced it does not.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from backend.clients import claude


DEMO_DIR = Path(__file__).resolve().parent
THREADS_DIR = DEMO_DIR / "threads"

# Run artifacts live outside the repo by default. Override with
# DEMO_ARTIFACT_DIR if you want them somewhere you can watch.
ARTIFACT_DIR = Path(
    os.environ.get("DEMO_ARTIFACT_DIR")
    or Path(tempfile.gettempdir()) / "correspondence-demo-artifacts"
)

# Threads this long need room. A 16-message thread at ~80 words a message
# plus JSON overhead runs past the 2000 default and gets truncated
# mid-object, which fails parsing rather than producing something short.
MAX_TOKENS = 8000


# --- prompt construction ----------------------------------------------------


SYSTEM = """You write realistic email threads for a fictional corpus. You are given a world, two people with specific writing styles, and a set of beats. You produce the thread as JSON.

The single most important thing: this must not read like generated email. Generated email is uniform in length, uniformly polite, uniformly complete, and every message is a finished thought. Real email is none of those things.

Specifically:

- Message length should vary wildly inside one thread. A 200-word message and a two-word message belong in the same exchange.
- People do not restate context they both have. Real threads are full of references that would be unclear to an outsider. That is correct and you should write it.
- Not every message advances anything. Some are acknowledgements. Some are jokes that do not land.
- People write badly when they are tired, annoyed, or in a hurry. Typos, missing words, a sentence that changes direction halfway.
- Nobody summarizes a thread at the end of it.
- Do not have characters explain their own feelings. Let the behavior carry it.

Match each person's documented style exactly. The styles are the point. If one person writes in lowercase fragments and the other writes in full paragraphs, that contrast should be visible in every single exchange.

Return ONLY a valid JSON object. First character is an opening brace. No prose, no code fences."""


USER_TEMPLATE = """# The world

{world}

# The two people

## {me_name} (the account owner, writes as "me")
{me_style}

## {them_name}
{them_style}

# Examples of correctly written threads in this corpus

These are hand-written. Match their texture, not their content.

{examples}

# The thread to write

Subject: {subject}
Date range: {start} to {end}
Number of messages: {count}
Time-of-day: {hours_rule}

## Beats

{beats}

## Hard constraints

{constraints}

# Output shape

{{
  "messages": [
    {{
      "from": "{me_handle}" or "{them_handle}",
      "date_utc": "YYYY-MM-DDTHH:MM:SS-07:00",
      "subject": "...",
      "body": "..."
    }}
  ]
}}

Timestamps must be strictly increasing, inside the date range, and obey the time-of-day rule. Use -07:00 throughout. Reply gaps should be irregular: some minutes, some days. Write exactly {count} messages."""


HOURS_RULES = {
    "business": (
        "Every message between 09:00 and 18:00 on a weekday. This is routine "
        "traffic and routine traffic happens during the day. Do not put these "
        "messages late at night."
    ),
    "late": (
        "Messages from the account owner land between 22:30 and 01:30. The "
        "other person replies during normal hours."
    ),
    "mixed": (
        "Vary it. Most messages during the day, and one or two from the "
        "account owner after 22:30 where the beats suggest avoidance or "
        "thinking out loud."
    ),
}


def _load_examples(handles: list[str], limit: int = 2) -> str:
    """
    Pull hand-written anchors as few-shot examples. Prefer anchors involving
    the same person, since voice consistency across threads matters more
    than variety here. Falls back to any anchor.
    """
    anchors = []
    for p in sorted(THREADS_DIR.glob("*.json")):
        d = json.loads(p.read_text())
        if d.get("anchor"):
            anchors.append(d)

    same = [a for a in anchors if any(h in a["participants"] for h in handles)]
    chosen = (same or anchors)[:limit]

    out = []
    for a in chosen:
        msgs = [
            {"from": m["from"], "date_utc": m["date_utc"], "body": m["body"]}
            for m in a["messages"]
        ]
        out.append(json.dumps({"subject": a["subject"], "messages": msgs}, indent=2))
    return "\n\n".join(out)


def _build_prompt(spec: dict, world: str, contacts: dict) -> tuple[str, str]:
    people = contacts["people"]
    me = contacts["me"]
    them = spec["with"]

    if them == "__noise__":
        them_name = spec["sender"]
        them_style = (
            "An automated or bulk sender. Template voice, no personality, "
            "consistent formatting across every message."
        )
        them_handle = spec["sender"]
    else:
        them_name = people[them]["name"]
        them_style = people[them]["style_note"]
        them_handle = them

    user = USER_TEMPLATE.format(
        world=world,
        me_name=people[me]["name"],
        me_style=people[me]["style_note"],
        them_name=them_name,
        them_style=them_style,
        examples=_load_examples([them]),
        subject=spec["subject"],
        start=spec["range"][0],
        end=spec["range"][1],
        count=spec["messages"],
        hours_rule=HOURS_RULES[spec["hours"]],
        beats=spec["beats"],
        constraints="\n".join(f"- {c}" for c in spec.get("constraints", [])),
        me_handle=me,
        them_handle=them_handle,
    )
    return SYSTEM, user


# --- validation -------------------------------------------------------------


def _validate(spec: dict, data: dict) -> list[str]:
    """
    Check the generated thread against the spec. Returns a list of problems;
    empty means it passed. We validate rather than trust because the most
    common failure is subtle: timestamps that drift outside the window, or
    a "business hours" thread that quietly lands at 2am and wrecks the
    second-shift ratio.
    """
    problems: list[str] = []
    msgs = data.get("messages") or []

    if not msgs:
        return ["no messages returned"]

    want = spec["messages"]
    if abs(len(msgs) - want) > max(2, want * 0.2):
        problems.append(f"wanted ~{want} messages, got {len(msgs)}")

    start = datetime.fromisoformat(spec["range"][0] + "T00:00:00-07:00")
    end = datetime.fromisoformat(spec["range"][1] + "T23:59:59-07:00")

    prev = None
    for i, m in enumerate(msgs):
        for field in ("from", "date_utc", "body"):
            if not m.get(field):
                problems.append(f"message {i}: missing {field}")
        try:
            dt = datetime.fromisoformat(m["date_utc"])
        except (ValueError, KeyError, TypeError):
            problems.append(f"message {i}: unparseable date {m.get('date_utc')!r}")
            continue

        if not (start <= dt <= end):
            problems.append(f"message {i}: {dt.date()} outside {spec['range']}")
        if prev and dt < prev:
            problems.append(f"message {i}: timestamp goes backwards")
        prev = dt

        if spec["hours"] == "business" and not (9 <= dt.hour < 18):
            problems.append(f"message {i}: {dt.strftime('%H:%M')} outside business hours")

    # Day spread. A thread that should be lumpy across a month and instead
    # lands on four consecutive Thursdays is the clearest tell that a
    # corpus was generated, so where the plan asks for spread we enforce it
    # rather than hoping the model honored the constraint.
    min_days = spec.get("min_days")
    if min_days:
        dates = {
            datetime.fromisoformat(m["date_utc"]).date()
            for m in msgs if m.get("date_utc")
        }
        if len(dates) < min_days:
            problems.append(f"spans {len(dates)} distinct days, need at least {min_days}")

        # The weekday check exists to catch human traffic that fakes a
        # rhythm. Genuinely scheduled senders (a weekly newsletter, a
        # monthly invoice) are supposed to land on the same weekday, so
        # exempt anything the plan marks periodic. Without this the check
        # rejects a newsletter for behaving like a newsletter.
        if not spec.get("periodic"):
            weekdays = {d.weekday() for d in dates}
            if len(dates) >= 4 and len(weekdays) < 3:
                problems.append(
                    f"only {len(weekdays)} distinct weekday(s) across {len(dates)} days; "
                    "traffic is landing on a weekly rhythm"
                )

    return problems


# --- generation -------------------------------------------------------------


async def generate_one(spec: dict, world: str, contacts: dict, retries: int = 2) -> dict | None:
    system, user = _build_prompt(spec, world, contacts)
    tid = spec["id"]

    for attempt in range(retries + 1):
        try:
            data = await claude.call_json(system=system, user=user, max_tokens=MAX_TOKENS)
        except Exception as e:
            # Type and message only. Never the request, which would carry
            # headers.
            print(f"  {tid}: call failed ({type(e).__name__}: {e})")
            if attempt == retries:
                return None
            await asyncio.sleep(3)
            continue

        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        (ARTIFACT_DIR / f"{tid}.attempt{attempt}.raw.json").write_text(
            json.dumps(data, indent=2)
        )

        problems = _validate(spec, data)
        if not problems:
            return data

        print(f"  {tid}: attempt {attempt + 1} rejected")
        for p in problems[:5]:
            print(f"    - {p}")
        if attempt == retries:
            print(f"  {tid}: giving up after {retries + 1} attempts")
            return None

        user += (
            "\n\n# Your previous attempt was rejected\n\nFix these and "
            "regenerate the whole thread:\n"
            + "\n".join(f"- {p}" for p in problems)
        )

    return None


def _write_thread(spec: dict, data: dict, contacts: dict) -> Path:
    them = spec["with"]
    participants = (
        [contacts["me"], spec["sender"]] if them == "__noise__"
        else [contacts["me"], them]
    )
    out = {
        "thread_id": f"t-{spec['id']}",
        "anchor": False,
        "_note": f"Generated from thread_plan.json entry '{spec['id']}'. Beats are hand-authored; prose is not.",
        "participants": participants,
        "subject": spec["subject"],
        "messages": data["messages"],
    }
    path = THREADS_DIR / f"{spec['id']}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    return path


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true", help="show what would run, no API calls")
    ap.add_argument("--run", action="store_true", help="generate everything missing")
    ap.add_argument("--only", help="generate a single thread id")
    ap.add_argument("--force", action="store_true", help="regenerate even if the file exists")
    args = ap.parse_args()

    world = (DEMO_DIR / "world.md").read_text()
    contacts = json.loads((DEMO_DIR / "contacts.json").read_text())
    plan = json.loads((DEMO_DIR / "thread_plan.json").read_text())

    specs = plan["threads"]
    if args.only:
        specs = [s for s in specs if s["id"] == args.only]
        if not specs:
            raise SystemExit(f"no thread with id {args.only!r}")

    pending = [
        s for s in specs
        if args.force or not (THREADS_DIR / f"{s['id']}.json").exists()
    ]

    if args.plan or not (args.run or args.only):
        total = sum(s["messages"] for s in pending)
        print(f"{len(pending)} threads pending, {total} messages\n")
        for s in pending:
            print(f"  {s['id']:<28} {s['messages']:>3} msgs  {s['hours']:<9} {s['with']}")
        print(f"\nartifacts -> {ARTIFACT_DIR}")
        return

    print(f"generating {len(pending)} threads -> {THREADS_DIR}")
    print(f"artifacts  -> {ARTIFACT_DIR}\n")

    ok, failed = 0, []
    for s in pending:
        print(f"{s['id']} ({s['messages']} msgs)")
        data = await generate_one(s, world, contacts)
        if data is None:
            failed.append(s["id"])
            continue
        path = _write_thread(s, data, contacts)
        print(f"  wrote {path.name} ({len(data['messages'])} messages)")
        ok += 1
        # Tier 1 headroom. The generator is not in a hurry.
        await asyncio.sleep(2)

    print(f"\n{ok} written, {len(failed)} failed")
    for f in failed:
        print(f"  failed: {f}")


if __name__ == "__main__":
    random.seed(11)
    asyncio.run(main())
