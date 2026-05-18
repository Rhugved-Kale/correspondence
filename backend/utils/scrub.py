"""
Secret scrubbing for email bodies.

People email each other API keys all the time. Without this, we'd cheerfully
forward those keys to Anthropic and Perplexity in our prompts. That's bad
both for the user (key exposed in third-party logs) and for us (potential
abuse if a bad actor pastes keys into someone's inbox expecting us to log
them somewhere).

The patterns below cover the keys we're most likely to see in tech-adjacent
inboxes. The placeholder string is intentionally long and obvious so it's
visible in any debug output, and it's not a substring of common English
words so it won't accidentally match real content downstream.
"""

import re
from typing import Pattern


# Each pattern matches a known secret format. I anchored on the prefix
# (sk-, AKIA, ghp_, etc.) because those are far more discriminating than
# the body of the string. False positives on entropy-only detectors are
# noisy and unhelpful.
_PATTERNS: list[Pattern[str]] = [
    re.compile(r"sk-[a-zA-Z0-9_-]{20,}"),                       # OpenAI / Anthropic
    re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}"),                   # Anthropic explicit
    re.compile(r"AKIA[0-9A-Z]{16}"),                            # AWS access key id
    re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9])"),  # AWS secret-key-shape
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),                        # GitHub personal token
    re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),                # GitHub fine-grained token
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"),                # Slack tokens
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),                       # Google API key
    re.compile(r"ya29\.[0-9A-Za-z_-]{20,}"),                    # Google OAuth access token
]

_PLACEHOLDER = "[REDACTED_SECRET]"


def scrub_secrets(text: str) -> str:
    """
    Run every pattern over the text and replace matches with a placeholder.
    Returns the scrubbed text. Safe to call on None or empty inputs.

    Order doesn't matter because the patterns are non-overlapping in practice;
    if two ever did overlap, whichever ran first would win, which is fine.
    """
    if not text:
        return text
    out = text
    for pattern in _PATTERNS:
        out = pattern.sub(_PLACEHOLDER, out)
    return out
