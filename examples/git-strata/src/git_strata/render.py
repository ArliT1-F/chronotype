"""Small text helpers for the terminal output."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

_SPARKS = "▁▂▃▄▅▆▇█"
_EIGHTHS = " ▏▎▍▌▋▊▉"


def sparkline(values: Sequence[float]) -> str:
    """A one-line chart of ``values`` (scaled from 0, so flat lines sit low, not in the middle)."""
    if not values:
        return ""
    top = max(values)
    if top <= 0:
        return _SPARKS[0] * len(values)
    steps = len(_SPARKS) - 1
    return "".join(_SPARKS[min(steps, int(v / top * steps + 0.5))] for v in values)


def bar(fraction: float, width: int = 24) -> str:
    """A horizontal bar ``width`` cells wide for ``fraction`` in [0, 1], in eighths of a cell."""
    eighths = round(max(0.0, min(1.0, fraction)) * width * 8)
    full, rest = divmod(eighths, 8)
    return ("█" * full + (_EIGHTHS[rest] if rest else "")).ljust(width)


def number(n: int) -> str:
    return f"{n:,}"


def plural(n: int, word: str) -> str:
    """'1 file', '2 files'."""
    return f"{n:,} {word}{'s' * (n != 1)}"


def signed(n: int) -> str:
    if n > 0:
        return f"+{n:,}"
    if n < 0:
        return f"−{-n:,}"
    return "0"


def percent(fraction: float) -> str:
    return f"{fraction * 100:.0f}%"


def day(when: datetime) -> str:
    return when.strftime("%Y-%m-%d")


def moment(when: datetime) -> str:
    return when.strftime("%Y-%m-%d %H:%M UTC")


def short(sha: str) -> str:
    return sha[:8]


def span(delta: timedelta) -> str:
    """A rough human length of time: '3 years, 2 months', '5 weeks', '2 days'."""
    days = delta.days
    if days >= 365:
        years, rest = divmod(days, 365)
        months = rest // 30
        text = f"{years} year{'s' * (years != 1)}"
        return text + (f", {months} month{'s' * (months != 1)}" if months else "")
    if days >= 60:
        return f"{days // 30} months"
    if days >= 14:
        return f"{days // 7} weeks"
    if days >= 1:
        return f"{days} day{'s' * (days != 1)}"
    hours = delta.seconds // 3600
    return f"{hours} hour{'s' * (hours != 1)}" if hours else "less than an hour"


def people(names: Sequence[str], limit: int = 3) -> str:
    """'alice, bob, carol +2'."""
    shown = ", ".join(names[:limit])
    return shown + (f" +{len(names) - limit}" if len(names) > limit else "")
