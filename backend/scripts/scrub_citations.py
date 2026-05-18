"""
Post-hoc citation tag scrubber.

Run this on an existing output/people.json to strip any leaked
<cite index="..."> ... </cite> tags. Useful when the citation regex was
fixed after a pipeline run and you don't want to spend another 12 minutes
and $1 just to clean tags out.

    python -m backend.scripts.scrub_citations

The script overwrites output/people.json in place. A copy of the original
is saved to output/people.json.before-scrub for safety.
"""

from __future__ import annotations

import json
import re
import shutil

from backend.config import OUTPUT_JSON_PATH
from backend.utils.logging import get_logger, setup_logging


# Same regex as the one in clients/claude.py. Duplicated here so this
# script is self-contained, but if the canonical one changes we should
# remember to update both.
_CITE_OPEN = re.compile(r'<cite\s+index=\\?["\'][^"\'\\]*\\?["\']\s*>')
_CITE_CLOSE = re.compile(r"</cite>")


def _strip(text: str) -> str:
    if not isinstance(text, str):
        return text
    text = _CITE_OPEN.sub("", text)
    text = _CITE_CLOSE.sub("", text)
    return text


def _walk(obj):
    """Recursively scrub every string value in a nested JSON structure."""
    if isinstance(obj, str):
        return _strip(obj)
    if isinstance(obj, list):
        return [_walk(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _walk(v) for k, v in obj.items()}
    return obj


def main() -> None:
    setup_logging("INFO")
    log = get_logger("scrub_citations")

    if not OUTPUT_JSON_PATH.exists():
        log.error("no output/people.json found at %s", OUTPUT_JSON_PATH)
        return

    backup = OUTPUT_JSON_PATH.with_suffix(".json.before-scrub")
    shutil.copy(OUTPUT_JSON_PATH, backup)
    log.info("backed up to %s", backup)

    with open(OUTPUT_JSON_PATH) as f:
        data = json.load(f)

    scrubbed = _walk(data)

    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(scrubbed, f, indent=2, ensure_ascii=False)

    log.info("scrubbed %s in place", OUTPUT_JSON_PATH.name)


if __name__ == "__main__":
    main()
