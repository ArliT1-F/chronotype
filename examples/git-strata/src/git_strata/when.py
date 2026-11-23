"""Turn command-line time arguments into UTC datetimes."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from git_strata.gitlog import Git, GitError

_RELATIVE = re.compile(
    r"(?P<n>\d+)\s*(?P<unit>d|w|m|y|days?|weeks?|months?|years?)(?:\s+ago)?", re.IGNORECASE
)
_YEAR = re.compile(r"\d{4}")
_MONTH = re.compile(r"(\d{4})-(\d{1,2})")


def months_before(when: datetime, months: int) -> datetime:
    """The same day ``months`` calendar months earlier (clamped to the end of shorter months)."""
    index = when.year * 12 + when.month - 1 - months
    year, month = divmod(index, 12)
    for day in range(when.day, 0, -1):
        try:
            return when.replace(year=year, month=month + 1, day=day)
        except ValueError:
            continue
    raise AssertionError("unreachable")


def parse_when(text: str, git: Git | None = None, now: datetime | None = None) -> datetime:
    """
    Parse a point in time.

    Accepts ``now``; ISO dates and times (``2023-04-01``, ``2023-04-01T12:30``,
    with an optional offset or ``Z``; times without one are UTC); ``2023-04``
    and ``2023`` (the start of that month or year); relative times
    (``90d``, ``6 months ago``, ``2y``); and, with ``git``, any revision such
    as a tag, branch or commit id (its commit time).
    """
    now = now or datetime.now(timezone.utc)
    value = text.strip()
    lowered = value.lower()
    if lowered in ("now", "today"):
        return now

    match = _RELATIVE.fullmatch(lowered)
    if match:
        n, unit = int(match["n"]), match["unit"][0]
        if unit == "d":
            return now - timedelta(days=n)
        if unit == "w":
            return now - timedelta(weeks=n)
        return months_before(now, n * (12 if unit == "y" else 1))

    if _YEAR.fullmatch(value):
        return datetime(int(value), 1, 1, tzinfo=timezone.utc)
    match = _MONTH.fullmatch(value)
    if match and 1 <= int(match[2]) <= 12:
        return datetime(int(match[1]), int(match[2]), 1, tzinfo=timezone.utc)

    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        pass
    else:
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    if git is not None:
        try:
            return git.commit_time(value)
        except GitError:
            pass
    raise ValueError(
        f"can't read {text!r} as a time: use a date (2023-04-01), a month (2023-04), "
        "a year, 'now', a relative time (90d, 6 months ago) or a git revision"
    )
