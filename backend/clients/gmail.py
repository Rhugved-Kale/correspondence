"""
Gmail client.

Wraps the raw googleapiclient calls in something the rest of the pipeline
can actually use: an iterable of normalized message dicts with cleaned
bodies. The Gmail API itself is fine but the message format it returns is
a recursive MIME tree with base64url-encoded parts, and every consumer in
the codebase shouldn't have to deal with that.

Three things I learned the hard way that this module handles:

1. Some messages have no `text/plain` part, only `text/html`. We fall
   back to HTML and strip it.
2. Reply chains in Gmail include the original message body again, leading
   to massive duplication. We trim at the first quoted-line marker.
3. Many "messages" are auto-generated noise (LinkedIn digests, calendar
   invites, GitHub notifications). We filter at ingestion time using From
   headers and a small noise list, so they never pollute the cache.
"""

from __future__ import annotations

import base64
import os.path
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from typing import Iterable, Iterator

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from backend.utils.logging import get_logger
from backend.utils.scrub import scrub_secrets


log = get_logger(__name__)


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


# Domains and address patterns that almost never produce signal. Filtering
# at ingestion time is cheaper than scoring them out later. Keep this list
# tight; aggressive filtering can hide real conversations from less-common
# transactional senders.
NOISE_FROM_PATTERNS = [
    re.compile(r"^no[-_.]?reply", re.IGNORECASE),
    re.compile(r"^notifications?@", re.IGNORECASE),
    re.compile(r"^digest@", re.IGNORECASE),
    re.compile(r"^donotreply", re.IGNORECASE),
    re.compile(r"@.*\bmailer\b", re.IGNORECASE),
    re.compile(r"@.*bounces?\.", re.IGNORECASE),
]


@dataclass
class GmailMessage:
    """Normalized message shape. This is what the rest of the pipeline consumes."""
    id: str
    thread_id: str
    date_utc: str          # ISO-8601 with timezone
    subject: str
    from_email: str        # lowercased
    from_name: str
    to_emails: list[str]   # lowercased
    body: str              # plain text, secret-scrubbed, reply-trimmed
    snippet: str
    is_outgoing: bool


# Per-thread cache of googleapiclient service objects. The service object
# wraps an httplib2.Http instance which is NOT safe to share across threads
# (https://googleapis.github.io/google-api-python-client/docs/thread_safety.html).
# Each worker gets its own service via thread-local storage, built once on
# first access, reused for the lifetime of the thread. Saves ~50ms per
# fetch on a parallel pool compared to building per call.
_tls = threading.local()


def _gmail_service(creds: Credentials):
    """Get this thread's cached Gmail service, building on first access."""
    svc = getattr(_tls, "gmail", None)
    if svc is None:
        # cache_discovery=False skips an extra HTTP round-trip for the
        # discovery document; we don't need the file cache for a single run.
        svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
        _tls.gmail = svc
    return svc


def get_credentials(credentials_path: str, token_path: str) -> Credentials:
    """
    Resolve Google credentials. Wraps the OAuth flow so the rest of the
    codebase can ask for credentials without knowing about consent
    screens or token caching.

    On first run this opens a browser window for the OAuth consent. On
    subsequent runs it loads the cached token from disk and silently
    refreshes if expired.
    """
    creds: Credentials | None = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            log.info("refreshing expired OAuth token")
            creds.refresh(Request())
        else:
            log.info("running OAuth flow, browser will open")
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return creds


def get_my_email(creds: Credentials) -> str:
    """Resolve the authenticated user's email. We use this to mark messages as outgoing."""
    service = build("oauth2", "v2", credentials=creds)
    return service.userinfo().get().execute()["email"].lower()


def list_message_ids(
    creds: Credentials,
    query: str,
    max_results: int | None = None,
) -> Iterator[tuple[str, str]]:
    """
    Page through message ids matching `query`. Returns (message_id, thread_id) pairs.

    Gmail's `q=` parameter supports the same operators as the search box,
    e.g. `newer_than:180d -category:promotions`. Keeping this generic so
    callers (ranking pass vs deep history pull) can use different queries.

    If max_results is None we exhaust pagination. Otherwise we stop early.
    """
    service = _gmail_service(creds)
    page_token: str | None = None
    yielded = 0

    while True:
        page_size = 500  # Gmail max
        if max_results is not None:
            page_size = min(page_size, max_results - yielded)
            if page_size <= 0:
                return

        try:
            resp = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=page_size, pageToken=page_token)
                .execute()
            )
        except HttpError as e:
            log.error("Gmail list error: %s", e)
            return

        for m in resp.get("messages", []) or []:
            yield (m["id"], m["threadId"])
            yielded += 1

        page_token = resp.get("nextPageToken")
        if not page_token:
            return


def fetch_message(creds: Credentials, message_id: str, my_email: str) -> GmailMessage | None:
    """
    Fetch a single message by id and normalize it. Returns None if the message
    is filtered as noise or fails to parse cleanly. We don't raise on per-message
    errors; one bad email shouldn't stop ingestion.

    Safe to call from worker threads: uses a thread-local service object so
    the underlying httplib2.Http is never shared across threads.

    Retries on transient quota errors (403 rateLimitExceeded, 429) with
    exponential backoff. Gmail's per-minute quota can fire even when the
    per-second budget is healthy, especially during big bursts; the retry
    gives the worker a few seconds to clear the window instead of dropping
    the message permanently.
    """
    service = _gmail_service(creds)

    raw = None
    backoff = 2.0
    for attempt in range(1, 5):
        try:
            raw = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
            break
        except HttpError as e:
            status = getattr(e.resp, "status", None)
            # 429 = explicit rate limit. 403 with rateLimitExceeded reason
            # is Gmail's per-minute quota signal; the body looks like a
            # generic forbidden but the reason is transient.
            is_transient = (
                status == 429
                or (status == 403 and "rateLimitExceeded" in str(e))
            )
            if is_transient and attempt < 4:
                import time as _time
                _time.sleep(backoff)
                backoff *= 2
                continue
            log.warning("failed to fetch %s: %s", message_id, e)
            return None

    if raw is None:
        return None

    headers = {h["name"].lower(): h["value"] for h in raw.get("payload", {}).get("headers", [])}

    from_raw = headers.get("from", "")
    from_name, from_email = parseaddr(from_raw)
    from_email = from_email.lower()
    if not from_email or _is_noise_sender(from_email):
        return None

    to_raw = headers.get("to", "")
    to_emails = [addr.lower() for _, addr in _parseaddr_list(to_raw) if addr]

    subject = headers.get("subject", "") or ""
    date_utc = _parse_date(headers.get("date", ""))
    body = _extract_body(raw.get("payload", {}))
    body = _trim_quoted_reply(body)
    body = scrub_secrets(body).strip()

    is_outgoing = from_email == my_email.lower()

    return GmailMessage(
        id=raw["id"],
        thread_id=raw["threadId"],
        date_utc=date_utc,
        subject=subject,
        from_email=from_email,
        from_name=from_name or "",
        to_emails=to_emails,
        body=body,
        snippet=raw.get("snippet", "") or "",
        is_outgoing=is_outgoing,
    )


# --- internals -----------------------------------------------------------------


def _parseaddr_list(raw: str) -> Iterable[tuple[str, str]]:
    """
    Parse a comma-separated address list correctly, including the common
    academic case where display names are "Last, First" with a literal comma
    inside the quoted name. stdlib's `getaddresses` handles RFC 2822 quoting
    properly; a naive `.split(",")` does not, and the resulting bug splits
    one contact into two corrupted rows that pollute downstream ranking.

    `getaddresses` expects a list of header values, so we wrap the raw string
    in a single-element list.
    """
    if not raw:
        return
    for name, addr in getaddresses([raw]):
        if addr:
            yield (name, addr)


def _parse_date(raw: str) -> str:
    """
    RFC 2822 date in headers, normalized to ISO-8601 UTC. If parsing fails,
    fall back to 'now' rather than dropping the message; we'd rather have
    slightly wrong dates than missing messages.
    """
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).isoformat()


def _is_noise_sender(from_email: str) -> bool:
    local = from_email.split("@", 1)[0]
    return any(p.search(from_email) or p.search(local) for p in NOISE_FROM_PATTERNS)


def _extract_body(payload: dict) -> str:
    """
    Walk the MIME tree and return the first usable text representation.
    Preference: text/plain > text/html (stripped). Returns empty string if
    neither is available.
    """
    plain = _walk_for_mime(payload, "text/plain")
    if plain:
        return plain
    html = _walk_for_mime(payload, "text/html")
    if html:
        return _strip_html(html)
    return ""


def _walk_for_mime(payload: dict, mime: str) -> str:
    """Depth-first search for the first part with the given mimeType."""
    if payload.get("mimeType") == mime:
        data = payload.get("body", {}).get("data")
        if data:
            return _decode(data)
    for part in payload.get("parts", []) or []:
        found = _walk_for_mime(part, mime)
        if found:
            return found
    return ""


def _decode(data: str) -> str:
    """Gmail uses base64url with padding stripped. Decode tolerantly."""
    try:
        padding = 4 - (len(data) % 4)
        if padding != 4:
            data += "=" * padding
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _strip_html(html: str) -> str:
    """Convert HTML to plain text. BeautifulSoup handles nested tags better than regex."""
    try:
        soup = BeautifulSoup(html, "lxml")
        # Drop scripts and styles, they otherwise show up as literal text.
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        # Collapse runs of whitespace and blank lines.
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    except Exception:
        return html


# Common markers Gmail or email clients insert before quoted reply chains.
# Trimming here is the difference between a 500-char useful body and a
# 5,000-char body where 90% is the same conversation repeated.
_QUOTE_MARKERS = [
    re.compile(r"^On .+ wrote:\s*$", re.MULTILINE),
    re.compile(r"^From:\s.+$", re.MULTILINE),
    re.compile(r"^-+ ?Original Message ?-+$", re.MULTILINE),
    re.compile(r"^_{4,}\s*$", re.MULTILINE),
]


def _trim_quoted_reply(body: str) -> str:
    """
    Cut the body at the first quoted-reply marker. We lose some context but
    gain a lot of signal density. The first 1-2 paragraphs are almost always
    what the sender actually wrote in this round of the exchange.
    """
    earliest = len(body)
    for pat in _QUOTE_MARKERS:
        m = pat.search(body)
        if m and m.start() < earliest:
            earliest = m.start()
    return body[:earliest].rstrip()
