"""
Anthropic (Claude) client wrapper.

The rest of the codebase doesn't talk to the Anthropic SDK directly. It
asks this module for two things:

  - call_json(): plain text -> structured JSON via Claude.
  - call_json_with_web_search(): same, but Claude has the web_search tool
    available. Used for the public bio research agent.

Why a wrapper:

  1. JSON parsing is fragile. Claude sometimes wraps its output in ```json
     fences, sometimes prefixes with prose. We strip both here so callers
     just get a dict.
  2. Web search is a multi-turn flow under the hood (Claude requests,
     server runs the search, returns results, Claude composes). The SDK
     handles it, but we still want a single "ask for an answer" surface.
  3. Retries on 429/500 should be a property of the client, not duplicated
     across every agent.

We use Claude Sonnet 4 by default. Opus would produce slightly better
prose but at ~5x the cost and 2-3x the latency. Sonnet is the right call
for the volume of calls we're making (4 per person x 10 people = 40 calls
per run).
"""

from __future__ import annotations

import asyncio
import json
import re

import anthropic
from anthropic import AsyncAnthropic

from backend.config import get_settings
from backend.utils.logging import get_logger


log = get_logger(__name__)


# Model selection. Sonnet 4.x is the right balance of quality and cost for
# the per-person agent loop. The exact pinned identifier matters for
# reproducibility; bumping it should be a deliberate decision.
MODEL = "claude-sonnet-4-5-20250929"

# Token caps. The agents produce structured JSON, not essays. 1500 tokens
# is enough for a 9-event timeline with evidence quotes. Web research can
# need a bit more since it summarizes a tool result.
DEFAULT_MAX_TOKENS = 2000
WEB_SEARCH_MAX_TOKENS = 3000

# Retry policy. Exponential backoff for 429 and 5xx. Three attempts is
# enough; if Anthropic is genuinely down we want to fail fast rather than
# keep the user waiting forever.
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 2.0


_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def call_json(
    system: str,
    user: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict:
    """
    Ask Claude for a JSON object. Returns the parsed dict.

    Raises ValueError if Claude returns malformed JSON that can't be
    repaired. The caller decides what to do (usually: log it and substitute
    a default shape so the pipeline keeps moving).
    """
    text = await _call_with_retry(
        system=system,
        user=user,
        max_tokens=max_tokens,
        tools=None,
    )
    return _parse_json(text)


async def call_json_with_web_search(
    system: str,
    user: str,
    max_tokens: int = WEB_SEARCH_MAX_TOKENS,
    max_uses: int = 3,
) -> dict:
    """
    Same as call_json, but Claude has the built-in web_search tool available.
    Claude decides whether to invoke it. `max_uses` caps how many searches
    it can make per call, which bounds cost.

    Returns the parsed dict from Claude's final text response after any
    searches have been performed.
    """
    tools = [
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": max_uses,
        }
    ]
    text = await _call_with_retry(
        system=system,
        user=user,
        max_tokens=max_tokens,
        tools=tools,
    )
    return _parse_json(text)


# --- internals -----------------------------------------------------------------


async def _call_with_retry(
    system: str,
    user: str,
    max_tokens: int,
    tools: list | None,
) -> str:
    """Make the API call with exponential backoff on retriable errors."""
    client = _get_client()
    backoff = INITIAL_BACKOFF_SECONDS
    last_exc: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            kwargs = {
                "model": MODEL,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }
            if tools:
                kwargs["tools"] = tools

            resp = await client.messages.create(**kwargs)
            return _extract_text(resp)

        except (anthropic.RateLimitError, anthropic.APIStatusError) as e:
            # 429 and 5xx are retriable. Anything else (400, auth) is not.
            status = getattr(e, "status_code", None)
            if status and status < 500 and status != 429:
                raise
            last_exc = e
            if attempt < MAX_RETRIES:
                log.warning("Claude API %s, retrying in %.1fs (attempt %d)", status, backoff, attempt)
                await asyncio.sleep(backoff)
                backoff *= 2
        except anthropic.APIConnectionError as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                log.warning("Claude connection error, retrying in %.1fs", backoff)
                await asyncio.sleep(backoff)
                backoff *= 2

    raise RuntimeError(f"Claude API failed after {MAX_RETRIES} attempts: {last_exc}")


def _extract_text(resp) -> str:
    """
    Pull the text out of an Anthropic response. Responses with web search
    have multiple content blocks (text + tool_use + tool_result + final text);
    we want the last text block, which is Claude's composed answer.
    """
    text_parts = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)
    if not text_parts:
        return ""
    # The final text block is the answer; earlier ones are intermediate
    # narration that Claude sometimes does between tool calls.
    return text_parts[-1]


_CODE_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

# Claude's web-search responses sometimes include <cite index="X-Y">...</cite>
# tags inside the structured JSON output. These are infrastructure leakage
# (the search tool uses them to track which claims came from which source)
# and are not meant to appear in the final text. We strip them aggressively
# here so they never reach the frontend or the agent composer.
#
# Subtlety: when the tags appear inside a JSON string value, the quotes
# get backslash-escaped. So the raw text we receive can contain either
# <cite index="1-1"> (raw) or <cite index=\"1-1\"> (inside a JSON string).
# The optional \\? before each quote covers both forms.
_CITE_OPEN = re.compile(r'<cite\s+index=\\?["\'][^"\'\\]*\\?["\']\s*>')
_CITE_CLOSE = re.compile(r"</cite>")


def _strip_citations(text: str) -> str:
    """Remove web-search citation tags. Keeps the inner content intact."""
    text = _CITE_OPEN.sub("", text)
    text = _CITE_CLOSE.sub("", text)
    return text


def _parse_json(text: str) -> dict:
    """
    Parse JSON out of Claude's response. Handles a few common formats:
      - Bare JSON (most common)
      - JSON wrapped in ```json ... ``` fences
      - JSON preceded by a sentence of preamble

    If parsing fails completely, raises ValueError with the offending text.
    """
    # Strip code fences AND citation tags before any parsing. Citation tags
    # are the bigger risk because they appear inside string values, where
    # the JSON parser would happily accept them and leak them to the UI.
    cleaned = _strip_citations(text)
    cleaned = _CODE_FENCE.sub("", cleaned).strip()

    # Direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try to find the outermost {...} or [...] span and parse that
    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        end = cleaned.rfind(closer)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue

    raise ValueError(f"could not parse JSON from Claude response: {text[:400]}")
