"""Time parsing utilities — convert relative strings to ISO8601 for the Sumo Logic API."""

import re
from datetime import datetime, timedelta, timezone


_RELATIVE_RE = re.compile(
    r"^-(\d+)\s*(s|sec|second|seconds|m|min|minute|minutes|h|hr|hour|hours|d|day|days|w|week|weeks)$",
    re.IGNORECASE,
)

_UNIT_TO_SECONDS = {
    "s": 1, "sec": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
    "w": 604800, "week": 604800, "weeks": 604800,
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: str) -> str:
    """Parse a time expression to ISO8601 UTC string.

    Accepts:
    - "now"              → current UTC time
    - "-3h", "-30m"      → relative offsets from now
    - ISO8601 strings    → passed through unchanged
    - Unix ms timestamps → converted to ISO8601
    """
    v = value.strip()

    if v.lower() == "now":
        return _now_utc().strftime("%Y-%m-%dT%H:%M:%S+00:00")

    m = _RELATIVE_RE.match(v)
    if m:
        amount = int(m.group(1))
        unit = m.group(2).lower()
        seconds = _UNIT_TO_SECONDS[unit] * amount
        dt = _now_utc() - timedelta(seconds=seconds)
        return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    # Unix millisecond timestamp (13 digits)
    if re.match(r"^\d{13}$", v):
        dt = datetime.fromtimestamp(int(v) / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    # Already looks like ISO8601 — pass through
    return v
