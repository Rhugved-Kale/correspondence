"""
Signal computation for The Read.

This module computes facts about how the user actually uses email. It does
not write prose and it does not interpret. Every number the vignette agent
prints comes from here, because a number the model derives is a number the
model can get wrong, and Stage 2 established that at some cost.

The design rule, stated once: anything derivable from the data is computed
here and handed to the agent as input. The agent's only job is to write
sentences around values it was given.

What makes this different from the stats dashboard it replaces: the old
about_you answered "how much". These signals answer "what do you do", and
several of them are things the user cannot see about themselves because
they require comparing their behaviour across relationships.

Selection matters as much as computation. We compute everything and let
the composer pick the extremes, so two different inboxes produce different
pages. A page that says the same thing for everybody is a template, and a
template is not worth sharing.
"""

from __future__ import annotations

import re
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.utils.logging import get_logger


log = get_logger(__name__)


# A reply counts as a reply if it lands in the same thread after an
# inbound message. Anything past this is a new conversation, not an
# answer, and folding it in would inflate every median.
MAX_REPLY_WINDOW_HOURS = 24 * 30

# Forward commitments: "let me look", "I'll send", "this week". The
# deferral finding depends on this list, and it counts distinct messages
# rather than phrase hits because one message often carries two.
DEFERRAL_RE = re.compile(
    r"(let me (look|think|check|see|get back)"
    r"|i'?ll (venmo|ping|send|look|check|get back|have|write|figure)"
    r"|this week|next week|give me a few days|in a few days"
    r"|when i (get|have) a|i'?ll figure)",
    re.IGNORECASE,
)

# --- composition rules -------------------------------------------------------
#
# Three rules the composer must obey. They are constants here so the
# thresholds are inspectable rather than buried in prose.
#
# WARRANT. A vignette needs an extreme signal, not merely a present one.
# Josiah's reply latency varies 3x, which is the honest reading of a
# relationship with no context-dependence, and writing the "you answer
# what is easy to face" vignette about him would be forcing it. When a
# signal lacks warrant the person does not get that vignette and another
# finding takes the slot. This is the anti-template discipline: not every
# finding fires for every person, and a page that says the same thing for
# everybody is not worth sharing.
MIN_SPREAD_FOR_VIGNETTE = 20      # within-person fastest:slowest ratio
MIN_PAIRS_FOR_VIGNETTE = 4        # below this a median is noise

# COOLING NEEDS A RELATIONSHIP. Someone you traded five terse
# acknowledgements with was never warm enough to cool.
MIN_COOLING_REPLIES = 4
MIN_COOLING_WORDS = 20            # median words in the early replies

# DEDUPE BY EVIDENCE, NOT BY FINDING CLASS. Marguerite's latency
# inflection and her latency spread are the same fact seen twice: her
# easy thread came first and her hard one came later. Selecting both
# would print one observation as two vignettes. The composer compares the
# underlying data a finding rests on, not its label.


# Sign-offs, longest first so "thanks so much" wins over "thanks".
SIGNOFFS = [
    "love you", "thanks so much", "many thanks", "best regards", "all the best",
    "talk soon", "speak soon", "cheers", "thanks", "thx", "best", "regards",
    "sincerely", "warmly", "yours",
]


# Addresses that are machines or bulk senders. The Read is about how the
# user treats people, so a calendar invite containing a question mark is
# not question debt and a billing robot is not a relationship. Reuses the
# ranker's list so the two agree on what counts as a human.
_MACHINE_LOCALS = {
    "no-reply", "noreply", "do-not-reply", "notifications", "notification",
    "alerts", "alert", "receipts", "billing", "dispatch", "cfp", "outreach",
    "mailer", "mailer-daemon", "postmaster", "automated", "newsletter",
    "digest", "updates", "support", "info", "team",
}


def is_person(email: str, out_count: int = 1) -> bool:
    """
    Whether an address belongs to someone the user actually corresponds
    with. Requires at least one reply from the user, which is the same
    reciprocity test the ranker uses: no reply, no relationship.
    """
    if not email or "@" not in email:
        return False
    if out_count < 1:
        return False
    local = email.split("@", 1)[0].lower()
    if local in _MACHINE_LOCALS:
        return False
    return not any(local.startswith(p) for p in ("no-reply", "noreply", "notifications"))


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _words(s: str | None) -> int:
    return len((s or "").split())


# A salutation is not content. Formal correspondents open with "Priya,"
# on its own line, and taking the first non-empty line hands the agent
# the word "Priya," as the thing it is supposed to characterise.
_SALUTATION = re.compile(
    r"^(hi|hey|hello|dear|good (morning|afternoon|evening))?\s*"
    r"[A-Z][a-z]+([\s,]|$)|^[A-Z][a-z]+,\s*$",
)


def _first_line(body: str) -> str:
    """First line that actually carries content, skipping the greeting."""
    lines = [ln.strip() for ln in (body or "").splitlines() if ln.strip()]
    for ln in lines:
        # Short lines that are only a greeting or a name get skipped. The
        # length bound matters: "Priya, we have a problem" is content and
        # must survive, "Priya," alone must not.
        if len(ln.split()) <= 3 and _SALUTATION.match(ln) and ln.endswith(","):
            continue
        if ln.lower().rstrip(",.! ") in {
            "hi", "hey", "hello", "dear", "thanks", "thank you",
        }:
            continue
        return ln
    return lines[0] if lines else ""


def _excerpt(body: str, limit: int = 400) -> str:
    """
    Enough of a message for the agent to know what it is about.

    The first content line alone was too thin, and the failure was not
    truncation but gap-filling: given only "Bumping the radio thing... $135"
    the model decided the radio thing was an advertisement, and given only
    a bump it decided someone had already spent the money. Neither was in
    the text. A wider window removes the gap rather than forbidding the
    fill.

    It also strengthens the escape clause, which has to judge whether two
    messages differ in kind. That judgement is only as good as how much of
    each message it can see.
    """
    lines = [ln.strip() for ln in (body or "").splitlines() if ln.strip()]
    out: list[str] = []
    total = 0
    for ln in lines:
        if not out:
            # Reuse the salutation skip for the opening line only.
            if len(ln.split()) <= 3 and _SALUTATION.match(ln) and ln.endswith(","):
                continue
            if ln.lower().rstrip(",.! ") in {"hi", "hey", "hello", "dear"}:
                continue
        if total + len(ln) > limit:
            remaining = limit - total
            if remaining > 40:
                out.append(ln[:remaining].rsplit(" ", 1)[0] + "...")
            break
        out.append(ln)
        total += len(ln) + 1
    return " ".join(out) if out else (lines[0][:limit] if lines else "")


def _last_line(body: str) -> str:
    lines = [ln.strip() for ln in (body or "").splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def _load(db_path: Path, my_email: str) -> tuple[list[dict], dict[str, str]]:
    """Every message plus a display-name lookup, ordered by thread and time."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, thread_id, date_utc, subject, from_email, from_name,
                   to_emails, body, is_outgoing
            FROM messages
            ORDER BY thread_id, date_utc
            """
        ).fetchall()
        names = {
            r["email"]: (r["display_name"] or r["email"].split("@", 1)[0])
            for r in conn.execute("SELECT email, display_name FROM contacts")
        }

    msgs = []
    for r in rows:
        dt = _parse(r["date_utc"])
        if not dt:
            continue
        msgs.append({
            "thread_id": r["thread_id"],
            "dt": dt,
            "subject": r["subject"] or "",
            "body": r["body"] or "",
            "from_email": (r["from_email"] or "").lower(),
            "to_emails": (r["to_emails"] or "").lower(),
            "is_outgoing": bool(r["is_outgoing"]),
        })
    return msgs, names


def _counterparty(m: dict, my_email: str) -> str:
    """Who the message is with, from the user's point of view."""
    if m["is_outgoing"]:
        for e in m["to_emails"].split(","):
            e = e.strip()
            if e and e != my_email:
                return e
        return ""
    return m["from_email"]


# --- reply pairs -------------------------------------------------------------


def _reply_pairs(msgs: list[dict], my_email: str) -> list[dict]:
    """
    Every (their message, my reply) pair inside a thread, with the latency
    and enough context to say what kind of message was being answered.

    Context class is the load-bearing part. Constraint 1 in the Stage 3
    notes exists because a single per-person median hides the finding: the
    same person gets 42 minutes on an easy message and 61 hours on a hard
    one. So each pair records whether the inbound asked a question, which
    is the closest deterministic proxy we have for "this one costs
    something to answer".
    """
    by_thread: dict[str, list[dict]] = defaultdict(list)
    for m in msgs:
        by_thread[m["thread_id"]].append(m)

    pairs = []
    for tid, thread in by_thread.items():
        thread.sort(key=lambda m: m["dt"])
        for i, m in enumerate(thread):
            # Both directions. The user's replies are the subject of most
            # findings, but constraint 2 needs the counterparty's trend
            # too: naming who moved first is impossible with one side.
            reply = next(
                (x for x in thread[i + 1:] if x["is_outgoing"] != m["is_outgoing"]),
                None,
            )
            if not reply:
                continue
            hours = (reply["dt"] - m["dt"]).total_seconds() / 3600
            if hours < 0 or hours > MAX_REPLY_WINDOW_HOURS:
                continue
            pairs.append({
                "thread_id": tid,
                "person": _counterparty(m, my_email),
                "hours": hours,
                "reply_outgoing": reply["is_outgoing"],
                "asked_question": "?" in m["body"],
                "prompt_words": _words(m["body"]),
                "reply_words": _words(reply["body"]),
                "subject": m["subject"],
                "they_wrote": _excerpt(m["body"], 400),
                "i_wrote": _excerpt(reply["body"], 400),
                "when": m["dt"].date().isoformat(),
                "_ts": m["dt"],
            })

    # Chronological, not thread order. Every trend computed downstream
    # depends on this and the bug it hides is silent: messages arrive
    # grouped by thread_id, so Nkechi's May equity thread sorted ahead of
    # her April intro thread and her steepest cooling in the corpus read
    # as a relationship warming up.
    pairs.sort(key=lambda p: p["_ts"])
    return pairs


def _latency_by_person(
    pairs: list[dict], names: dict[str, str], people: set[str]
) -> list[dict]:
    """
    The user's reply latency per person, with the fastest and slowest
    exchange carried as text.

    The text is the point. Constraint 1 says a latency finding must name
    the class of message it describes, and the first implementation tried
    to do that with a question-mark proxy, which does not work: at four or
    five samples the median is noise, and "did it contain a question" does
    not separate a message that is easy to answer from one that is easy to
    face. Wendy's fastest reply is seventeen minutes to "look what turned
    up" and her slowest is five days to a bump about money. Both are
    questions.

    So we hand over the extremes with what the person actually wrote, and
    the agent names the class by reading it. That is reading, not
    deriving, and it is the thing a language model is for.
    """
    by: dict[str, list[dict]] = defaultdict(list)
    for p in pairs:
        if p["reply_outgoing"] and p["person"] in people:
            by[p["person"]].append(p)

    out = []
    for email, ps in by.items():
        fastest = min(ps, key=lambda p: p["hours"])
        slowest = max(ps, key=lambda p: p["hours"])
        spread = (
            round(slowest["hours"] / fastest["hours"])
            if fastest["hours"] > 0.01 else None
        )
        out.append({
            "email": email,
            "name": names.get(email, email.split("@", 1)[0]),
            "n": len(ps),
            "median_h": round(statistics.median([p["hours"] for p in ps]), 2),
            # The within-person spread is the constraint-1 evidence: when
            # one relationship contains both a 17-minute reply and a
            # 5-day one, no single median describes it honestly.
            "spread_ratio": spread,
            "has_warrant": bool(
                spread and spread >= MIN_SPREAD_FOR_VIGNETTE
                and len(ps) >= MIN_PAIRS_FOR_VIGNETTE
            ),
            "fastest": {
                "hours": round(fastest["hours"], 3),
                "subject": fastest["subject"],
                "they_wrote": fastest["they_wrote"],
                "i_wrote": fastest["i_wrote"],
                "when": fastest["when"],
            },
            "slowest": {
                "hours": round(slowest["hours"], 2),
                "subject": slowest["subject"],
                "they_wrote": slowest["they_wrote"],
                "i_wrote": slowest["i_wrote"],
                "when": slowest["when"],
            },
        })
    out.sort(key=lambda r: r["median_h"])
    return out


# --- unanswered questions ----------------------------------------------------


def _question_debt(msgs: list[dict], my_email: str, names: dict[str, str],
                   people: set[str]) -> dict:
    """
    Inbound messages containing a question that the user never replied to
    in that thread. The count is the finding; the examples are what make
    it land, so we keep the actual sentences.
    """
    by_thread: dict[str, list[dict]] = defaultdict(list)
    for m in msgs:
        by_thread[m["thread_id"]].append(m)

    items = []
    for tid, thread in by_thread.items():
        thread.sort(key=lambda m: m["dt"])
        for i, m in enumerate(thread):
            if m["is_outgoing"] or "?" not in m["body"]:
                continue
            if any(x["is_outgoing"] for x in thread[i + 1:]):
                continue
            person = _counterparty(m, my_email)
            # A calendar invite with a question mark is not question debt.
            if person not in people:
                continue
            sentences = [
                s.strip() for s in re.split(r"(?<=[.?!])\s+", m["body"])
                if s.strip().endswith("?")
            ]
            items.append({
                "person": names.get(person, person.split("@", 1)[0]),
                "when": m["dt"].date().isoformat(),
                "subject": m["subject"],
                "questions": sentences[:3],
            })

    items.sort(key=lambda x: x["when"])
    return {
        "count": len(items),
        "people": len({i["person"] for i in items}),
        "examples": items,
    }


# --- deferrals ---------------------------------------------------------------


def _deferrals(msgs: list[dict], my_email: str, names: dict[str, str],
               people: set[str]) -> dict:
    """
    Outgoing messages that promise a future action. Counts distinct
    messages, not phrase hits: "I'll venmo you this week" is one deferral
    and matches twice, and counting matches inflates the figure by about
    sixty percent.

    A deferral is marked unkept when the user sent nothing further in that
    thread. That under-counts (a promise can be broken while the thread
    continues) which is the correct direction to be wrong in.
    """
    by_thread: dict[str, list[dict]] = defaultdict(list)
    for m in msgs:
        by_thread[m["thread_id"]].append(m)

    items = []
    for tid, thread in by_thread.items():
        thread.sort(key=lambda m: m["dt"])
        for i, m in enumerate(thread):
            if not m["is_outgoing"]:
                continue
            hit = DEFERRAL_RE.search(m["body"])
            if not hit:
                continue
            person = _counterparty(m, my_email)
            if person not in people:
                continue
            later_from_me = any(x["is_outgoing"] for x in thread[i + 1:])
            items.append({
                "person": names.get(person, person.split("@", 1)[0]),
                "when": m["dt"].date().isoformat(),
                "subject": m["subject"],
                "phrase": hit.group(0),
                "excerpt": _excerpt(m["body"], 300),
                "followed_up": later_from_me,
            })

    return {
        "count": len(items),
        "people": len({i["person"] for i in items}),
        "unkept": sum(1 for i in items if not i["followed_up"]),
        "examples": items,
    }


# --- hours -------------------------------------------------------------------


def _hours(msgs: list[dict]) -> dict:
    """
    The shape, not the ratio. A first pass measured "percent after 22:00"
    and it was the wrong question: 21% after ten alongside a dead evening
    is a much clearer second shift than 35% smeared from six onward. The
    finding is the trough between two populated bands.
    """
    sent = [m for m in msgs if m["is_outgoing"]]
    if not sent:
        return {}

    n = len(sent)
    hrs = [m["dt"].hour for m in sent]
    band = lambda lo, hi: sum(1 for h in hrs if lo <= h < hi) / n
    late = sum(1 for h in hrs if h >= 22 or h < 2) / n

    latest = max(
        (m for m in sent if m["dt"].hour >= 22 or m["dt"].hour < 4),
        key=lambda m: (m["dt"].hour if m["dt"].hour < 4 else m["dt"].hour - 24),
        default=None,
    )
    return {
        "total_sent": n,
        "day_n": sum(1 for h in hrs if 9 <= h < 18),
        "evening_n": sum(1 for h in hrs if 18 <= h < 22),
        "late_n": sum(1 for h in hrs if h >= 22 or h < 2),
        "dead_n": sum(1 for h in hrs if 2 <= h < 9),
        "day_pct": round(band(9, 18) * 100),
        "evening_pct": round(band(18, 22) * 100),
        "late_pct": round(late * 100),
        "dead_pct": round(band(2, 9) * 100),
        "has_second_shift": band(9, 18) >= 0.4 and late >= 0.12 and band(18, 22) <= 0.10,
        "latest_message": {
            "at": latest["dt"].strftime("%H:%M"),
            "when": latest["dt"].date().isoformat(),
            "subject": latest["subject"],
            "excerpt": _excerpt(latest["body"], 300),
        } if latest else None,
    }


# --- length, sign-offs, openers ----------------------------------------------


def _length_by_person(msgs: list[dict], my_email: str, names: dict[str, str],
                      people: set[str]) -> list[dict]:
    by: dict[str, list[int]] = defaultdict(list)
    for m in msgs:
        if not m["is_outgoing"]:
            continue
        p = _counterparty(m, my_email)
        if p in people:
            by[p].append(_words(m["body"]))
    out = [
        {"name": names.get(e, e.split("@", 1)[0]), "email": e,
         "median_words": round(statistics.median(v)), "n": len(v)}
        for e, v in by.items() if len(v) >= 2
    ]
    out.sort(key=lambda r: -r["median_words"])
    return out


def _signoffs(msgs: list[dict], my_email: str, names: dict[str, str],
              people: set[str]) -> list[dict]:
    """Which closing the user uses for whom. Invisible to the writer."""
    by: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for m in msgs:
        if not m["is_outgoing"]:
            continue
        tail = _last_line(m["body"]).lower().strip(" ,.-!")
        # A bare name is the signature, so look one line up for the closing.
        lines = [ln.strip() for ln in m["body"].splitlines() if ln.strip()]
        candidates = [ln.lower().strip(" ,.-!") for ln in lines[-2:]]
        for s in SIGNOFFS:
            if any(c == s or c.startswith(s + ",") for c in candidates):
                cp = _counterparty(m, my_email)
                if cp in people:
                    by[cp][s] += 1
                break

    out = []
    for email, counts in by.items():
        top = max(counts.items(), key=lambda kv: kv[1])
        out.append({
            "name": names.get(email, email.split("@", 1)[0]),
            "signoff": top[0], "n": top[1],
        })
    return sorted(out, key=lambda r: -r["n"])


def _openers(msgs: list[dict]) -> list[dict]:
    counts: dict[str, int] = defaultdict(int)
    for m in msgs:
        if not m["is_outgoing"]:
            continue
        first = _first_line(m["body"]).lower()
        words = re.findall(r"[a-z']+", first)[:3]
        if len(words) == 3:
            counts[" ".join(words)] += 1
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:5]
    return [{"phrase": p, "n": n} for p, n in top if n >= 2]


# --- who moved first ---------------------------------------------------------


def _cooling(pairs: list[dict], msgs: list[dict], my_email: str,
             names: dict[str, str], people: set[str]) -> list[dict]:
    """
    Relationships that went cold, and which side moved first.

    Constraint 2 exists because "the candidate went cold" is the reading
    the person living it has, and it is usually wrong. The honest version
    names who moved first.

    A first implementation looked at message rate and missed the case the
    constraint was written for: Nkechi's message count barely changed
    (six in twenty-eight days, then six in thirty-three) while her replies
    went from 2.6 days and eighty words to 6.6 days and eighteen. Rate was
    the wrong signal. What decays in a cooling relationship is how fast
    and how fully each side answers, so that is what we measure.

    Both sides get the same treatment, and if their trends move together
    we say so rather than picking a mover.
    """
    def side(person: str, outgoing: bool) -> list[dict]:
        """One side's replies, oldest first. Pairs are already sorted."""
        return [
            p for p in pairs
            if p["person"] == person and p["reply_outgoing"] == outgoing
        ]

    def inflection(seq: list[dict]) -> datetime | None:
        """
        When this side's replies started taking materially longer. Returns
        the timestamp, not the index, because the two sides have different
        numbers of replies and only timestamps are comparable between them.
        """
        if len(seq) < 3:
            return None
        base = statistics.median([p["hours"] for p in seq[:2]])
        if base <= 0:
            base = 0.1
        for p in seq[2:]:
            if p["hours"] > base * 3:
                return p["_ts"]
        return None

    def decayed(seq: list[dict]) -> bool:
        """
        The relationship actually ended up slower, not just one spike. A
        single long gap mid-thread is an argument or a holiday; sustained
        decay is what cooling means.
        """
        if len(seq) < 4:
            return False
        third = max(1, len(seq) // 3)
        early = statistics.median([p["hours"] for p in seq[:third]])
        late = statistics.median([p["hours"] for p in seq[-third:]])
        return late > max(early * 3, 24.0)

    out = []
    for email in people:
        mine, theirs = side(email, True), side(email, False)

        # The relationship has to have mattered before it can cool. Five
        # terse acknowledgements traded with a landlord over ten weeks is
        # a plumbing thread, not a relationship in decline, and calling it
        # one is the kind of finding that makes a reader stop trusting the
        # page.
        if len(mine) < MIN_COOLING_REPLIES or len(theirs) < 3:
            continue
        words = [p["reply_words"] for p in mine]
        early_words = statistics.median(words[: max(1, len(words) // 2)])
        if early_words < MIN_COOLING_WORDS:
            continue

        if not decayed(mine):
            continue  # only the user's own decay makes this The Read's business

        # The documented signature is monotonic in BOTH latency and
        # length. Requiring both is what separates a relationship going
        # quiet from one where the answer just happened to be hard: a
        # person whose replies get slower but stay long is still engaged.
        shrinking = (
            len(words) >= 3
            and early_words
            > statistics.median(words[len(words) // 2:]) * 1.5
        )
        if not shrinking:
            continue

        # Constraint 2: name who moved first, by comparing when each side
        # inflected. "The candidate went cold" is the reading the person
        # living it has, and it is usually backwards.
        mi, ti = inflection(mine), inflection(theirs)
        if mi and (ti is None or mi < ti):
            mover = "user"
        elif ti and (mi is None or ti < mi):
            mover = "them"
        else:
            mover = "unclear"

        ms = [m for m in msgs if _counterparty(m, my_email) == email]
        ms.sort(key=lambda m: m["dt"])
        out.append({
            "name": names.get(email, email.split("@", 1)[0]),
            "email": email,
            "my_reply_hours": [round(p["hours"], 1) for p in mine],
            "their_reply_hours": [round(p["hours"], 1) for p in theirs],
            "my_inflection": mi.date().isoformat() if mi else None,
            "their_inflection": ti.date().isoformat() if ti else None,
            "my_reply_words": words,
            "my_replies_shrinking": shrinking,
            "moved_first": mover,
            "last_message_from": "me" if ms and ms[-1]["is_outgoing"] else "them",
            "last_message_on": ms[-1]["dt"].date().isoformat() if ms else None,
        })
    return out


# --- last word ---------------------------------------------------------------


def _last_word(msgs: list[dict], my_email: str, names: dict[str, str],
               people: set[str]) -> dict:
    by_thread: dict[str, list[dict]] = defaultdict(list)
    for m in msgs:
        by_thread[m["thread_id"]].append(m)

    mine = theirs = 0
    ended_on_them: dict[str, int] = defaultdict(int)
    for thread in by_thread.values():
        thread.sort(key=lambda m: m["dt"])
        last = thread[-1]
        if last["is_outgoing"]:
            mine += 1
        else:
            theirs += 1
            p = _counterparty(last, my_email)
            if p in people:
                ended_on_them[p] += 1

    total = mine + theirs or 1
    top = sorted(ended_on_them.items(), key=lambda kv: -kv[1])[:5]
    return {
        "threads": total,
        "i_ended": mine,
        "they_ended": theirs,
        "i_ended_pct": round(mine / total * 100),
        "left_hanging": [
            {"name": names.get(e, e.split("@", 1)[0]), "threads": n}
            for e, n in top if n >= 2
        ],
    }


# --- entry point -------------------------------------------------------------


def compute_signals(db_path: Path, my_email: str) -> dict[str, Any]:
    """
    Everything The Read is allowed to say, as numbers. The vignette agent
    receives this and writes prose around it; it derives nothing itself.
    """
    my_email = (my_email or "").lower()
    msgs, names = _load(db_path, my_email)
    if not msgs:
        return {"error": "no messages"}

    # Who counts as a person. Everything downstream filters on this, so a
    # calendar robot never appears in a finding about how the user treats
    # the people in their life.
    out_counts: dict[str, int] = defaultdict(int)
    for m in msgs:
        if m["is_outgoing"]:
            cp = _counterparty(m, my_email)
            if cp:
                out_counts[cp] += 1
    people = {e for e in out_counts if is_person(e, out_counts[e])}

    pairs = _reply_pairs(msgs, my_email)
    latency = _latency_by_person(pairs, names, people)
    my_pairs = [p for p in pairs if p["reply_outgoing"] and p["person"] in people]

    sent = [m for m in msgs if m["is_outgoing"]]
    signals = {
        "window": {
            "first": min(m["dt"] for m in msgs).date().isoformat(),
            "last": max(m["dt"] for m in msgs).date().isoformat(),
            "days": (max(m["dt"] for m in msgs) - min(m["dt"] for m in msgs)).days or 1,
        },
        "volume": {
            "total": len(msgs),
            "sent": len(sent),
            "received": len(msgs) - len(sent),
            "threads": len({m["thread_id"] for m in msgs}),
        },
        "latency": {
            "overall_median_h": round(statistics.median([p["hours"] for p in my_pairs]), 2)
            if my_pairs else None,
            "by_person": latency,
            "fastest_overall": min(my_pairs, key=lambda p: p["hours"]) if my_pairs else None,
            "slowest_overall": max(my_pairs, key=lambda p: p["hours"]) if my_pairs else None,
            "question_vs_not": {
                "median_h_question": round(statistics.median(
                    [p["hours"] for p in my_pairs if p["asked_question"]]), 2)
                if any(p["asked_question"] for p in my_pairs) else None,
                "median_h_no_question": round(statistics.median(
                    [p["hours"] for p in my_pairs if not p["asked_question"]]), 2)
                if any(not p["asked_question"] for p in my_pairs) else None,
            },
        },
        "question_debt": _question_debt(msgs, my_email, names, people),
        "deferrals": _deferrals(msgs, my_email, names, people),
        "hours": _hours(msgs),
        "length_by_person": _length_by_person(msgs, my_email, names, people),
        "signoffs": _signoffs(msgs, my_email, names, people),
        "openers": _openers(msgs),
        "cooling": _cooling(pairs, msgs, my_email, names, people),
        "last_word": _last_word(msgs, my_email, names, people),
    }

    # Drop non-JSON-safe datetimes that rode along on the extremes.
    for key in ("fastest_overall", "slowest_overall"):
        v = signals["latency"].get(key)
        if v:
            signals["latency"][key] = {
                k: val for k, val in v.items() if not k.startswith("_")
            }

    log.info(
        "self-portrait signals: %d pairs, %d deferrals, %d unanswered questions",
        len(my_pairs), signals["deferrals"]["count"],
        signals["question_debt"]["count"],
    )
    return signals
