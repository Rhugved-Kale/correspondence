"""
Pre-formatted phrasings for anything the vignette agent might restate.

This module exists because of a specific, repeated failure: the agent
converts. Given 62.4 hours it writes "two and a half days"; given 116 and
2 it writes "the gap is 58x"; given a date and nothing else it writes
"eleven months" for eighteen days.

Prohibiting conversion did not work, twice. So every figure is supplied in
every form a writer might reach for, and the prompt only has to say "use
what you were given".

One module, used by every vignette. Building this for one template and
leaving the other seven without it is exactly the mistake that produced
the fabricated timeframe, so it lives in one place on purpose.
"""

from __future__ import annotations

from datetime import date, datetime


def _plural(n: float, unit: str, decimals: int = 0) -> str:
    """`1 week` not `1 weeks`, and `2.6 days` not a rounded `3 days`."""
    val = f"{n:.{decimals}f}"
    return f"{val} {unit}" if val in ("1", "1.0") else f"{val} {unit}s"


def duration(hours: float) -> str:
    """Primary phrasing for an elapsed time."""
    if hours < 1:
        return _plural(hours * 60, "minute")
    if hours < 48:
        return _plural(hours, "hour")
    days = hours / 24
    # Rounding 2.6 days to "3 days" is a quiet falsehood, so keep a
    # decimal until the number is large enough for it not to matter.
    return _plural(days, "day", 1 if days < 10 else 0)


def duration_forms(hours: float) -> str:
    """
    Every phrasing of the same duration, so any one the agent picks is one
    it was handed. Deduped and ordered from most to least natural.
    """
    forms: list[str] = []
    mins, days, weeks = hours * 60, hours / 24, hours / 24 / 7

    if hours < 1:
        forms += [_plural(mins, "minute")]
        if mins >= 40:
            forms.append("under an hour")
    elif hours < 48:
        forms += [_plural(hours, "hour")]
        if days >= 1:
            forms.append(_plural(days, "day", 1))
        if 20 <= hours <= 28:
            forms.append("about a day")
    else:
        forms += [
            _plural(days, "day", 1 if days < 10 else 0),
            _plural(hours, "hour"),
        ]
        if weeks >= 1:
            forms.append(_plural(weeks, "week", 1 if weeks < 3 else 0))
        if 1.3 <= weeks <= 1.7:
            forms.append("a week and a half")
        if 4 <= weeks <= 5:
            forms.append("about a month")
    return ", or ".join(dict.fromkeys(forms))


def duration_pair(hours: float) -> str:
    """`17 minutes (also: 0.3 hours)` for inline use in a template."""
    return f"{duration(hours)}  (also stateable as: {duration_forms(hours)})"


def ratio(a: float, b: float) -> str:
    """Supplied so the agent never divides. It gets this wrong."""
    if not b:
        return "not comparable"
    r = max(a, b) / min(a, b)
    if r >= 10:
        return f"{r:.0f}x"
    return f"{r:.1f}x"


def clock(hhmm: str) -> str:
    """
    24-hour to spoken form. The agent read 00:47 and wrote "ten to one",
    which is wrong by three minutes and reads as invented precision.
    """
    try:
        h, m = (int(x) for x in hhmm.split(":"))
    except (ValueError, AttributeError):
        return hhmm
    suffix = "am" if h < 12 else "pm"
    display_h = h % 12 or 12
    return f"{display_h}:{m:02d}{suffix}"


def window_span(days: int) -> str:
    """
    A date range in days and weeks. Floor division reads as a lie here:
    90 days is 12.9 weeks, and "about 12 weeks" is further from the truth
    than "about 13". Rounding is the honest operation for an approximation
    introduced by the word "about".
    """
    if days < 14:
        return f"{days} days"
    weeks = round(days / 7)
    return f"{days} days, or about {weeks} week{'' if weeks == 1 else 's'}"


def days_since(when: str, as_of: str) -> str:
    """
    How long something has been sitting. Never let the agent work this out
    from a bare date: it produced "eleven months" for eighteen days.
    """
    try:
        a = date.fromisoformat(when[:10])
        b = date.fromisoformat(as_of[:10])
    except (ValueError, TypeError, AttributeError):
        return "unknown, do not refer to it"
    d = (b - a).days
    if d < 0:
        return "in the future, do not refer to it"
    if d < 14:
        return f"{d} days"
    if d < 60:
        w = round(d / 7)
        return f"{d} days, or about {w} week{'' if w == 1 else 's'}"
    m = round(d / 30)
    return f"{d} days, or about {m} month{'' if m == 1 else 's'}"


def gap_between(a: str, b: str) -> str:
    """Distance between two dates, in both units."""
    try:
        d = abs((date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days)
    except (ValueError, TypeError, AttributeError):
        return "unknown, do not refer to it"
    if d < 14:
        return f"{d} days apart"
    if d < 60:
        w = round(d / 7)
        return f"{d} days apart, or about {w} week{'' if w == 1 else 's'}"
    m = round(d / 30)
    return f"{d} days apart, or about {m} month{'' if m == 1 else 's'}"


def hours_list(values: list[float]) -> str:
    """A sequence of latencies with each one pre-phrased."""
    return ", then ".join(duration(v) for v in values)


def percent_forms(pct: int) -> str:
    """`21% (also: about one in five)`."""
    forms = [f"{pct}%"]
    for denom, phrase in ((2, "half"), (3, "one in three"), (4, "one in four"),
                          (5, "one in five"), (10, "one in ten")):
        if abs(pct - 100 / denom) <= 3:
            forms.append(f"about {phrase}")
            break
    return ", or ".join(forms)
