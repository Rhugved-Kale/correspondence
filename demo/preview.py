"""
Prompt iteration harness.

Runs the voice-carrying agents (timeline, stories, prep) for one person
against the demo fixture and prints the output in a readable form. Skips
the About agent, which web-searches and would burn time confirming that
fictional people do not exist.

    python -m demo.preview theo
    python -m demo.preview theo --agent stories
    python -m demo.preview theo --save before

    python -m demo.preview --diff before after

The point is a tight loop. A full pipeline run is 50 calls; this is one to
three, against threads whose content is already known, so a prompt change
can be judged in under a minute.

Saved runs go to the scratch artifact dir, not the repo. Prompt output is
a working artifact, not source.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
from pathlib import Path

from backend.agents.deep_fetch import load_person_messages
from backend.agents.person_pipeline import (
    _format_gaps_block,
    _format_messages_block,
    _label,
)
from backend.agents import grounding
from backend.clients import claude
from backend.prompts import templates as T

DEMO_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = Path(
    os.environ.get("DEMO_ARTIFACT_DIR")
    or Path(tempfile.gettempdir()) / "correspondence-demo-artifacts"
)

AGENTS = {
    "timeline": (T.TIMELINE_SYSTEM, T.TIMELINE_USER_TEMPLATE, {"events": []}),
    "stories": (T.STORIES_SYSTEM, T.STORIES_USER_TEMPLATE, {"stories": []}),
    "prep": (T.PREP_SYSTEM, T.PREP_USER_TEMPLATE, {}),
}


async def run_agent(name: str, pm, block: str, label: str) -> dict:
    system, template, default = AGENTS[name]
    fields = {
        "display_name": label,
        "email": pm.email,
        "messages_block": block,
        "message_count": len(pm.messages),
        "first_date": pm.first_date[:10],
        "last_date": pm.last_date[:10],
        "gaps_block": _format_gaps_block(pm),
    }
    # Templates take different subsets; pass only what each one declares.
    import string
    needed = {
        f for _, f, _, _ in string.Formatter().parse(template) if f
    }
    user = template.format(**{k: v for k, v in fields.items() if k in needed})
    try:
        return await claude.call_json(system=system, user=user, max_tokens=3000)
    except Exception as e:
        return {"__error__": f"{type(e).__name__}: {e}"}


def render(name: str, data: dict) -> str:
    out = [f"\n{'=' * 76}\n{name.upper()}\n{'=' * 76}"]
    if "__error__" in data:
        return "\n".join(out + [f"  ERROR: {data['__error__']}"])

    if name == "timeline":
        for ev in data.get("events", []):
            out.append(f"\n  {ev.get('date','?')}  {ev.get('title','')}")
            out.append(f"    {ev.get('description','')}")
            out.append(f"    “{ev.get('evidence','')}”")
    elif name == "stories":
        for s in data.get("stories", []):
            out.append(f"\n  [{s.get('when','')}]  {s.get('title','')}")
            out.append(f"    {s.get('moment','')}")
            out.append(f"    -> {s.get('why_it_matters','')}")
    elif name == "prep":
        out.append(f"\n  last: {data.get('last_substantive_interaction','')}")
        out.append("  open threads:")
        for t in data.get("open_threads", []):
            out.append(f"    - {t}")
        out.append("  talking points:")
        for t in data.get("three_talking_points", []):
            out.append(f"    - {t}")
        out.append(f"  personal: {data.get('something_personal','')}")
    return "\n".join(out)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("handle", nargs="?", help="contact handle, e.g. theo")
    ap.add_argument("--db", default="data/demo.db")
    ap.add_argument("--agent", action="append", choices=list(AGENTS),
                    help="repeatable; defaults to all three")
    ap.add_argument("--save", help="save this run under a label for later diffing")
    ap.add_argument("--diff", nargs=2, metavar=("A", "B"), help="compare two saved runs")
    args = ap.parse_args()

    if args.diff:
        a, b = (ARTIFACT_DIR / f"preview-{x}.txt" for x in args.diff)
        for p in (a, b):
            if not p.exists():
                raise SystemExit(f"no saved run at {p}")
        print(f"--- {args.diff[0]}\n+++ {args.diff[1]}\n")
        import difflib
        for line in difflib.unified_diff(
            a.read_text().splitlines(), b.read_text().splitlines(),
            lineterm="", n=2,
        ):
            print(line)
        return

    if not args.handle:
        raise SystemExit("need a contact handle, or --diff A B")

    contacts = json.loads((DEMO_DIR / "contacts.json").read_text())
    person = contacts["people"].get(args.handle)
    if not person:
        raise SystemExit(f"unknown handle {args.handle!r}")

    pm = load_person_messages(Path(args.db), person["email"])
    if not pm.messages:
        raise SystemExit(f"no cached messages for {person['email']}; run demo.load first")

    block = _format_messages_block(pm)
    label = _label(pm)
    names = args.agent or list(AGENTS)

    # The harness has to run the same guard the pipeline runs. An earlier
    # version called the agents directly and skipped verify_payload, which
    # meant every prompt change during iteration was being judged against
    # unguarded output while the shipped path was guarded. Two different
    # artifacts, one of them invisible.

    header = (
        f"{label} <{pm.email}>  |  {len(pm.messages)} messages  "
        f"|  {pm.first_date[:10]} to {pm.last_date[:10]}\n"
        f"prompt input: {len(block)} chars"
    )
    print(header)

    chunks = [header]
    outputs: dict[str, dict] = {}
    for n in names:
        outputs[n] = await run_agent(n, pm, block, label)
        await asyncio.sleep(1.5)

    report = grounding.verify_payload(
        messages=pm.messages,
        timeline_events=outputs.get("timeline", {}).get("events") or [],
        stories=outputs.get("stories", {}).get("stories") or [],
        person=pm.email,
    )
    guard = (
        f"\nGUARD  checked={report.checked}  evidence_dropped={report.dropped}  "
        f"story_quotes_flagged={report.flagged}  counts_fixed={report.counts_fixed}  "
        f"derived_durations={report.derived_durations}"
    )
    for d in report.drops:
        guard += f"\n  {d['agent']}.{d['field']}: {d['text'][:70]!r}"
    print(guard)
    chunks.append(guard)

    for n in names:
        text = render(n, outputs[n])
        print(text)
        chunks.append(text)

    if args.save:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        path = ARTIFACT_DIR / f"preview-{args.save}.txt"
        path.write_text("\n".join(chunks))
        print(f"\nsaved -> {path}")


if __name__ == "__main__":
    asyncio.run(main())
