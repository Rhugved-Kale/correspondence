"""
Progress reporting utilities. The pipeline writes its current state to
output/status.json after every phase change; the API reads it back to
serve /api/status. Centralizing the shape here means we never get a
mismatched key between writer and reader.

This is a deliberately tiny module. Resist the urge to grow it into a
"progress manager" with classes and methods; one file with two functions
and an enum is exactly enough for what this app needs.
"""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import Any

from backend.config import OUTPUT_DIR


STATUS_PATH = OUTPUT_DIR / "status.json"
PEOPLE_PATH = OUTPUT_DIR / "people.json"


class Phase(str, Enum):
    """
    Coarse-grained pipeline phases. The frontend uses these to pick the
    right copy and progress bar style; the strings flow directly into the
    JSON response, so don't rename them without updating the frontend.
    """
    IDLE = "idle"
    STARTING = "starting"
    AUTH = "auth"
    INGEST = "ingest"
    GENERATE = "generate"      # ranking + deep_fetch + per-person agents
    DONE = "done"
    ERROR = "error"


def write_status(
    phase: str,
    message: str = "",
    current: int = 0,
    total: int = 0,
    started_at: float | None = None,
    finished_at: float | None = None,
    error: str | None = None,
    **extra: Any,
) -> None:
    """
    Write the current status atomically. We merge with the previous status
    so callers can update one field (e.g. just the message) without losing
    started_at or other fields written earlier.

    Atomicity matters because the API might be reading the file at exactly
    the moment we write. Writing to a temp file and renaming guarantees
    the reader always sees a valid JSON document, never half a write.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    prev: dict[str, Any] = {}
    if STATUS_PATH.exists():
        try:
            with open(STATUS_PATH) as f:
                prev = json.load(f)
        except (json.JSONDecodeError, OSError):
            # Corrupted or empty status file; start fresh.
            prev = {}

    new = {
        **prev,
        "phase": phase,
        "message": message or prev.get("message", ""),
        "current": current,
        "total": total,
    }
    if started_at is not None:
        new["started_at"] = started_at
    if finished_at is not None:
        new["finished_at"] = finished_at
    if error is not None:
        new["error"] = error
    else:
        # Clear any stale error from a previous run.
        new["error"] = None

    new.update(extra)

    tmp = STATUS_PATH.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(new, f, indent=2)
    os.replace(tmp, STATUS_PATH)


def read_status() -> dict[str, Any] | None:
    """Return the current status, or None if none has been written yet."""
    if not STATUS_PATH.exists():
        return None
    try:
        with open(STATUS_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
