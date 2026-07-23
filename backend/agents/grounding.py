"""
Verify that quotes the agents attribute to emails actually appear in them.

The prompts tell every agent that an empty field beats an invented one, and
mostly they comply. But `evidence` is the field most likely to be
fabricated and the worst one to get wrong: the frontend renders it inside
quotation marks, directly under the claim it supports, styled as a
verbatim quote. A plausible paraphrase there reads as a lie to anyone who
knows the thread.

So we check it rather than trusting it. This is the same principle as the
hallucination guard in the prompts, enforced deterministically instead of
asked for politely.

Two levels, deliberately different:

  Timeline `evidence` is a dedicated field, so a failure clears the field
  and keeps the event. A good event with a bad quote is still a good
  event, and the UI already renders events with empty evidence because
  that was always a legitimate agent output.

  Story quotes are embedded mid-prose, where excising one would leave
  mangled text. Those are logged and left alone. The log is the point:
  it measures how often it happens without damaging the artifact.

Every drop is logged as a single greppable line so the rate can be tracked
over time on real inboxes, not just during prompt iteration:

    GROUNDING drop person=<email> agent=timeline field=evidence text=<...>
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.utils.logging import get_logger


log = get_logger(__name__)


# Quoted spans shorter than this are things like "no" or "ok" and match
# almost any corpus by accident, so checking them is noise.
MIN_QUOTE_WORDS = 4


def _normalize(s: str) -> str:
    """
    Fold the differences that don't mean anything: smart quotes, unicode
    dashes, collapsed whitespace, case. Agents routinely reformat a quote
    while keeping every word, and that should count as verbatim.
    """
    if not s:
        return ""
    s = (
        s.replace("’", "'").replace("‘", "'")
        # Inner quote marks vary freely: a source saying A simple "agreed"
        # gets re-rendered with single quotes when the model nests it in
        # its own sentence. The words are identical, so fold both forms to
        # one rather than reporting a fabrication.
        .replace("“", '"').replace("”", '"').replace("'", '"')
        .replace("—", "-").replace("–", "-")
        .replace("…", "...")
    )
    s = re.sub(r"\s+", " ", s)
    s = s.strip().strip('"\'').lower()
    # Terminal punctuation the model adds when embedding a fragment in its
    # own sentence. Without stripping it, an accurate quote reads as a
    # fabrication: five of six flags in a full pipeline run were a quote
    # that was right except for a full stop the source did not have. The
    # log is meant to measure hallucination rate on real inboxes, so a
    # false-positive class this large would make the metric useless.
    return s.rstrip(".,;:!?").strip()


def _strip_ellipsis(s: str) -> list[str]:
    """
    Agents elide the middle of a long quote. Treat "a ... b" as two
    fragments that must each appear, rather than one that never will.
    """
    parts = re.split(r"\s*\.\.\.\s*|\s*\[\.\.\.\]\s*", s)
    return [p for p in (x.strip() for x in parts) if p]


@dataclass
class GroundingReport:
    """What the guard did, for logging and for the caller to inspect."""
    checked: int = 0
    dropped: int = 0
    flagged: int = 0          # story quotes: logged, not modified
    counts_fixed: int = 0     # "four words" corrected or removed
    derived_durations: int = 0  # "three weeks later" the model worked out
    drops: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (self.dropped == 0 and self.flagged == 0
                and self.counts_fixed == 0 and self.derived_durations == 0)


def build_haystack(messages: list[dict]) -> str:
    """One normalized blob of everything the agent was allowed to read."""
    return _normalize(" \n ".join(
        (m.get("body") or "") + " " + (m.get("subject") or "")
        for m in messages
    ))


def is_grounded(quote: str, haystack: str) -> bool:
    """True when every fragment of the quote appears in the source."""
    frags = _strip_ellipsis(_normalize(quote))
    if not frags:
        return False
    return all(f in haystack for f in frags)


def verify_timeline(events: list[dict], haystack: str, person: str) -> GroundingReport:
    """
    Clear `evidence` on any event whose quote isn't in the source. Mutates
    the events in place and returns what happened.

    Field-level, not event-level: dropping the whole event would throw away
    a real observation because one sub-field was wrong, which is punitive
    rather than proportionate.
    """
    rep = GroundingReport()
    for i, ev in enumerate(events):
        quote = (ev.get("evidence") or "").strip()
        if not quote:
            continue  # silence events legitimately have none
        rep.checked += 1
        if is_grounded(quote, haystack):
            continue

        rep.dropped += 1
        rep.drops.append({
            "agent": "timeline", "field": "evidence",
            "index": i, "title": ev.get("title", ""), "text": quote,
        })
        log.warning(
            "GROUNDING drop person=%s agent=timeline field=evidence "
            "event=%r text=%r",
            person, ev.get("title", "")[:60], quote,
        )
        ev["evidence"] = ""
    return rep


def verify_stories(stories: list[dict], haystack: str, person: str) -> GroundingReport:
    """
    Check quoted spans inside story prose. Logs only, never edits: cutting
    a quote out of the middle of a sentence produces worse output than
    leaving an imperfect one in. The log is what makes the rate visible.
    """
    rep = GroundingReport()
    for i, s in enumerate(stories):
        moment = s.get("moment") or ""
        for quote in re.findall(r'"([^"]{4,200})"|“([^”]{4,200})”', moment):
            q = (quote[0] or quote[1]).strip()
            if len(q.split()) < MIN_QUOTE_WORDS:
                continue
            rep.checked += 1
            if is_grounded(q, haystack):
                continue

            rep.flagged += 1
            rep.drops.append({
                "agent": "stories", "field": "moment",
                "index": i, "title": s.get("title", ""), "text": q,
            })
            log.warning(
                "GROUNDING flag person=%s agent=stories field=moment "
                "story=%r text=%r",
                person, s.get("title", "")[:60], q,
            )
    return rep


# --- count claims ------------------------------------------------------------
#
# The agents keep writing "he replied with four words" and getting the
# number wrong, with the quote printed directly underneath. Two rounds of
# prompt prohibitions failed to stop it, which is the expected outcome:
# "four words" is a rhetorically attractive construction and the model
# reaches for it faster than it consults a ban.
#
# So we stop asking. The count is derivable from the quote sitting right
# there, so we derive it: substitute the real number when we can find the
# thing being counted, and delete the claim when we cannot.

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_WORD_FOR = {v: k for k, v in _NUMBER_WORDS.items()}

# The leading preposition is captured so a removal takes the whole phrase.
# Without it, deleting "four words" from "ended the argument with four
# words and neither of us wrote" leaves "with and", which is worse than
# the error we set out to fix.
_COUNT_CLAIM = re.compile(
    r"(?P<lead>\b(?:with|in|of|to|was|were)\s+)?"
    r"\b(?P<num>one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)"
    r"[\s-](?P<unit>word|line|sentence)s?\b",
    re.IGNORECASE,
)

# A quoted span near the claim is the thing being counted.
_NEARBY_QUOTE = re.compile(r'"([^"]{2,300})"|“([^”]{2,300})”')


def _count_units(text: str, unit: str) -> int:
    if unit == "word":
        return len(text.split())
    if unit == "line":
        return len([ln for ln in text.splitlines() if ln.strip()]) or 1
    return len([s for s in re.split(r"[.!?]+", text) if s.strip()]) or 1


def strip_count_claims(text: str) -> tuple[str, list[dict]]:
    """
    Correct or remove model-asserted counts. Returns (text, corrections).

    Looks for a quoted span within a window after the claim, then before
    it. Substitutes the real count when found. When no quote is nearby
    there is nothing to check against, so the claim is deleted rather than
    left as an unverifiable assertion.
    """
    corrections: list[dict] = []

    def resolve(m: re.Match) -> str:
        claimed_raw = m.group("num").lower()
        claimed = _NUMBER_WORDS.get(claimed_raw)
        if claimed is None:
            try:
                claimed = int(claimed_raw)
            except ValueError:
                return m.group(0)
        unit = m.group("unit").lower()

        after = text[m.end(): m.end() + 160]
        before = text[max(0, m.start() - 160): m.start()]
        q = _NEARBY_QUOTE.search(after) or _NEARBY_QUOTE.search(before)

        if not q:
            corrections.append({"claim": m.group(0), "action": "removed",
                                "reason": "no quote nearby to count"})
            return ""

        quoted = (q.group(1) or q.group(2)).strip()
        actual = _count_units(quoted, unit)
        if actual == claimed:
            return m.group(0)

        lead = m.group("lead") or ""
        replacement = (
            f"{lead}{_WORD_FOR.get(actual, actual)} {unit}"
            f"{'s' if actual != 1 else ''}"
        )
        corrections.append({"claim": m.group(0).strip(), "action": "corrected",
                            "to": replacement.strip(), "quote": quoted[:60]})
        return replacement

    out = _COUNT_CLAIM.sub(resolve, text)
    # A dropped claim can leave a dangling colon or doubled space. Removing
    # "with four words" from "...back with four words: \"quote\"" should
    # yield "...back: \"quote\"", not "...back : \"quote\"".
    out = re.sub(r"\s+([,:;.])", r"\1", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip(), corrections


def fix_counts_in_place(obj: dict, fields: list[str], person: str, agent: str) -> int:
    """Apply strip_count_claims to named string fields on a dict."""
    n = 0
    for f in fields:
        val = obj.get(f)
        if not isinstance(val, str) or not val:
            continue
        fixed, corr = strip_count_claims(val)
        if corr:
            obj[f] = fixed
            n += len(corr)
            for c in corr:
                log.warning(
                    "GROUNDING count person=%s agent=%s field=%s claim=%r action=%s",
                    person, agent, f, c["claim"], c["action"],
                )
    return n


# --- derived durations -------------------------------------------------------
#
# Stories are told not to state elapsed time as a figure, because the model
# gets it wrong ("nine days before" when it was twenty-three). A duration
# that appears in the source is a fact and may be repeated; one the model
# worked out from two dates is a calculation and should not be there.
#
# Prompt prohibitions failed twice this stage, so this measures compliance
# rather than assuming it. Log-only: excising a duration mid-sentence would
# damage prose, and the prompt is the right place to fix the cause.

_DURATION = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
    r"|thirteen|fourteen|fifteen|twenty|thirty|\d+)[\s-]"
    r"(?:day|week|month|year)s?\b",
    re.IGNORECASE,
)


def check_derived_durations(
    stories: list[dict], haystack: str, person: str
) -> list[dict]:
    """
    Flag numeric durations in story prose that don't appear in the source.
    A match in the haystack means the figure came from an email, which is
    allowed. A miss means the model computed it.
    """
    found: list[dict] = []
    for i, s in enumerate(stories):
        for f in ("moment", "why_it_matters"):
            text = s.get(f) or ""
            for m in _DURATION.finditer(text):
                phrase = m.group(0)
                if _normalize(phrase) in haystack:
                    continue  # stated in an email, not derived
                found.append({
                    "agent": "stories", "field": f, "index": i,
                    "title": s.get("title", ""), "text": phrase,
                })
                log.warning(
                    "GROUNDING duration person=%s agent=stories field=%s "
                    "story=%r text=%r (not in source, likely computed)",
                    person, f, s.get("title", "")[:60], phrase,
                )
    return found


def verify_payload(
    messages: list[dict],
    timeline_events: list[dict],
    stories: list[dict],
    person: str,
) -> GroundingReport:
    """Run both checks against one person's cached messages."""
    haystack = build_haystack(messages)
    a = verify_timeline(timeline_events, haystack, person)
    b = verify_stories(stories, haystack, person)

    durations = check_derived_durations(stories, haystack, person)

    counts = 0
    for ev in timeline_events:
        counts += fix_counts_in_place(ev, ["title", "description"], person, "timeline")
    for s in stories:
        counts += fix_counts_in_place(s, ["moment", "why_it_matters"], person, "stories")

    total = GroundingReport(
        checked=a.checked + b.checked,
        dropped=a.dropped,
        flagged=b.flagged,
        counts_fixed=counts,
        derived_durations=len(durations),
        drops=a.drops + b.drops + durations,
    )
    if total.checked:
        log.info(
            "GROUNDING summary person=%s checked=%d dropped=%d flagged=%d",
            person, total.checked, total.dropped, total.flagged,
        )
    return total
