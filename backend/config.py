"""
Application config.

Everything tunable lives here. Anything secret comes from .env (which is
gitignored). Path defaults assume the backend is run from the project root,
which is how main.py is wired up, so cwd-relative paths just work.

I keep this module short on purpose. The day this file starts growing
"helpers" is the day config becomes a hairball.
"""

from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


# Project root is the parent of `backend/`. Resolving once at import time
# means we can pass absolute paths to every subprocess and SQLite without
# worrying about which directory uvicorn was launched from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
DB_PATH = DATA_DIR / "cache.db"
OUTPUT_JSON_PATH = OUTPUT_DIR / "people.json"


class Settings(BaseSettings):
    # Anthropic powers reasoning, summarization, and web research (via the
    # built-in web_search tool). Required to run the pipeline, but we
    # default to empty so the app can boot without it: the first-run
    # setup wizard collects this from the user. /api/start will refuse
    # to run if the key is still empty when the user hits Begin.
    anthropic_api_key: str = ""

    # Google OAuth. Paths default to the project root so the user only needs
    # to drop the JSON file into the repo and the rest works.
    google_credentials_path: str = str(PROJECT_ROOT / "credentials.json")
    google_token_path: str = str(PROJECT_ROOT / "token.json")

    # Whose inbox this is. Threaded into every agent prompt so the model
    # narrates in the right first person. Left empty by default; the
    # pipeline resolves it from the authenticated Google account, and the
    # demo overrides it with its fictional protagonist.
    protagonist_name: str = ""

    # Pipeline tuning. 90-day window captures most active relationships while
    # keeping the first-run ingestion under ~15 minutes. Bump to 180+ for a
    # more thorough ranking pass at the cost of a slower first run.
    top_n_people: int = 10
    ranking_window_days: int = 90
    max_emails_per_person: int = 200

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Lazy, cached settings accessor.

    Cached because parsing .env is non-trivial and we hit get_settings()
    on lots of code paths. Cache is invalidated explicitly by the setup
    wizard after it writes a new key, via get_settings.cache_clear().
    """
    return Settings()


def ensure_dirs() -> None:
    """Create data/ and output/ if they don't exist. Idempotent."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
