"""
Logging setup.

Stdlib logging with a custom format. Two reasons not to reach for structlog
or loguru here: (1) one less dependency to vet during code review, (2) Python's
built-in logging is more than enough for a single-machine pipeline.

The format prints time, level, and a short module name. Long enough to be
useful, short enough that lines don't wrap on a 100-column terminal.
"""

import logging
import sys


_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    """
    Call once at startup. Calling again is a no-op (FastAPI sometimes
    re-imports modules during reload and we don't want duplicate handlers).
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s  %(levelname)-7s  %(name)-22s  %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # Quiet down libraries that log at INFO for every retry or HTTP call.
    # We still see warnings and errors from them.
    for noisy in ("httpx", "httpcore", "googleapiclient", "google.auth", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Module-level logger. Use the module's __name__ for `name`."""
    return logging.getLogger(name)
