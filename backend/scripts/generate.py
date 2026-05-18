"""
End-to-end pipeline driver.

Run from the project root:

    python -m backend.scripts.generate

Assumes ingestion has already run (data/cache.db exists with messages).
Will rank, deep-fetch the top N, run the agent pipeline, and write
output/people.json.

Use this during development. The FastAPI app uses the same backend.pipeline
module so the production path matches.
"""

from __future__ import annotations

import asyncio

from backend.clients.gmail import get_credentials
from backend.config import get_settings
from backend.pipeline import run_pipeline
from backend.utils.logging import get_logger, setup_logging


def main() -> None:
    setup_logging("INFO")
    log = get_logger("generate")

    settings = get_settings()
    log.info("starting pipeline")

    creds = get_credentials(settings.google_credentials_path, settings.google_token_path)
    result = asyncio.run(run_pipeline(creds=creds, settings=settings))

    log.info("=" * 50)
    if result.get("ok"):
        log.info("pipeline complete in %.1fs", result["elapsed_seconds"])
        log.info("wrote %d people to %s", result["people_count"], result["output_path"])
    else:
        log.error("pipeline failed: %s", result.get("reason"))


if __name__ == "__main__":
    main()
