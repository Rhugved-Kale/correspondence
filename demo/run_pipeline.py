"""
Run the per-person agent pipeline against the demo fixture.

Same code path a real inbox takes, with one substitution: the About agent
web-searches each person, and these people do not exist, so it would
correctly return empty for all ten and every page would render missing a
third of its content. The authored blocks in demo/about_blocks.json stand
in for it. Everything else -- timeline, stories, forgotten, prep, the
grounding guard -- runs for real.

    python -m demo.run_pipeline
    python -m demo.run_pipeline --limit 2
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from backend.agents.person_pipeline import build_person_payload
from backend.agents.ranking import rank_contacts

DEMO_DIR = Path(__file__).resolve().parent


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/demo.db")
    ap.add_argument("--out", default="output/people.json")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    contacts = json.loads((DEMO_DIR / "contacts.json").read_text())
    blocks = json.loads((DEMO_DIR / "about_blocks.json").read_text())["blocks"]
    email2handle = {v["email"]: k for k, v in contacts["people"].items()}

    db = Path(args.db)
    top = rank_contacts(db, args.limit)
    print(f"{len(top)} people\n")

    async def fake_about(*, system: str, user: str, **kw) -> dict:
        """Stand in for the web-search agent, matched on the email in the prompt."""
        for email, handle in email2handle.items():
            if email in user:
                return blocks.get(handle) or {
                    "one_line": "", "current_focus": "",
                    "background": "", "three_things_to_know": [],
                }
        return {"one_line": "", "current_focus": "",
                "background": "", "three_things_to_know": []}

    payloads = []
    with patch("backend.clients.claude.call_json_with_web_search", new=fake_about):
        for i, c in enumerate(top, 1):
            name = c.display_name or c.email
            print(f"[{i}/{len(top)}] {name}")
            p = await build_person_payload(
                db_path=db, email=c.email,
                rank_score=c.score, rank_position=i,
                protagonist_name=contacts["people"][contacts["me"]]["name"],
                # The corpus is frozen. Without this the hero line says
                # "seven weeks" from the real clock while the recency
                # marker beside it says "7 days" from demo_as_of: two
                # clocks contradicting each other on the same page.
                as_of=datetime.fromisoformat(contacts["demo_as_of"] + "T12:00:00-07:00"),
            )
            print(f"      {len(p['timeline'])} events, {len(p['stories'])} stories, "
                  f"{len(p['forgotten'])} forgotten, "
                  f"{len(p['prep']['three_talking_points'])} talking points")
            payloads.append(p)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payloads, indent=2, ensure_ascii=False))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
