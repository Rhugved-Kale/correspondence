"""Run the card gate against the demo fixture and print what survived."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.agents.card_selector import build_cards

DEMO = Path(__file__).resolve().parent


async def main() -> None:
    read = json.loads((Path("output/insights.json")).read_text())["the_read"]
    people = json.loads(Path("output/people.json").read_text())
    out = await build_cards(read, people)

    print(f"{len(out['cards'])} of {out['considered']} survived anonymisation\n")
    print("=" * 74)
    print("SURVIVED")
    print("=" * 74)
    for c in out["cards"]:
        print(f"\n[{c['kind']}]  {c['kicker']}")
        q = c["quote"]
        for i in range(0, len(q), 68):
            print(f"  {q[i:i+68]}")
    print()
    print("=" * 74)
    print("COLLAPSED (stay in The Read only)")
    print("=" * 74)
    for r in out["rejected"]:
        print(f"\n[{r['kind']}]  {r.get('headline','')}")
        print(f"  -> {r['reason']}")

    Path("output/cards.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\nwrote output/cards.json")


if __name__ == "__main__":
    asyncio.run(main())
