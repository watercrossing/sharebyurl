"""Human-friendly durations, as accepted by ``--expiry``.

A duration is a positive integer and a single unit suffix (``7d``, ``12h``,
``4w``), or one of the words meaning "no expiry at all". Compound forms like
``1w2d`` are deliberately not supported -- they buy nothing here and make the
error messages worse.
"""

from __future__ import annotations

import re
from datetime import timedelta

# 'm' is minutes, never months: a calendar month is not a fixed timedelta, and
# silently picking one interpretation over the other is how people lose files.
UNITS: dict[str, timedelta] = {
    "m": timedelta(minutes=1),
    "h": timedelta(hours=1),
    "d": timedelta(days=1),
    "w": timedelta(weeks=1),
    "y": timedelta(days=365),
}

NEVER_WORDS = frozenset({"never", "none", "forever"})

_PATTERN = re.compile(r"^(\d+)\s*([a-z]+)$")


class DurationError(ValueError):
    """Raised when a duration string cannot be parsed."""


def parse_duration(text: str) -> timedelta | None:
    """Parse ``text`` into a timedelta, or ``None`` meaning "never expires".

    Raises DurationError with a message suitable for showing to the user.
    """
    cleaned = text.strip().lower()
    if not cleaned:
        raise DurationError("Empty duration. Use something like '7d', or 'never'.")

    if cleaned in NEVER_WORDS:
        return None

    # Legacy: config files written by version 0.3 stored the expiry as an
    # integer, and -1 was its sentinel for "never".
    if cleaned.lstrip("-").isdigit() and cleaned.startswith("-"):
        return None

    match = _PATTERN.match(cleaned)
    if not match:
        raise DurationError(
            f"Cannot understand the duration {text!r}. "
            f"Expected a number and a unit, one of {_units_help()} -- for example '7d'. "
            f"Use 'never' for a share that should not expire."
        )

    amount, unit = match.groups()
    if unit not in UNITS:
        raise DurationError(
            f"Unknown unit {unit!r} in {text!r}. Expected one of {_units_help()}. "
            f"Note that 'm' means minutes; months are not supported."
        )

    if int(amount) == 0:
        raise DurationError(
            f"{text!r} is a zero-length duration, which would expire the share "
            f"immediately. Use 'never' if you meant a share that never expires."
        )

    return int(amount) * UNITS[unit]


def _units_help() -> str:
    return ", ".join(f"'{u}'" for u in UNITS)


def format_delta(delta: timedelta) -> str:
    """Render a timedelta the way ``--list`` wants it: coarse and readable."""
    seconds = int(abs(delta).total_seconds())
    for unit, label in (("w", "week"), ("d", "day"), ("h", "hour"), ("m", "minute")):
        size = int(UNITS[unit].total_seconds())
        if seconds >= size:
            count = seconds // size
            return f"{count} {label}{'s' if count != 1 else ''}"
    return "less than a minute"
