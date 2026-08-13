"""Minimal 5-field cron evaluator (Python standard library only).

Schedule triggers store a cron expression that the schedule dispatcher
evaluates against UTC wall time (the convention for infrastructure cron; it
also sidesteps DST ambiguity). This module is intentionally dependency-free:
the supported syntax covers the standard 5-field subset:

*       any value
?       synonym for * (Quartz-style)
n       single value
a-b     inclusive range
a-b/n   range with step
*/n     any value with step
a,b,c   comma-separated list of the above

Month names (JAN..DEC) and weekday names (SUN..SAT; 0-6 or 7 for Sunday) are
accepted where applicable. Values are bounds-checked per field.

Day-of-month / day-of-week matching follows vixie-cron: when both fields are
restricted a day matches when *either* matches; when one is a wildcard the
other governs. ``previous_fire`` walks backward minute-by-minute within the
current day, then day-by-day (bounded by a ~4-year lookback that covers
Feb-29 cadences), so evaluation cost is bounded and predictable.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta

_MONTH_NAMES: dict[str, int] = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}
_DAY_NAMES: dict[str, int] = {
    "SUN": 0,
    "MON": 1,
    "TUE": 2,
    "WED": 3,
    "THU": 4,
    "FRI": 5,
    "SAT": 6,
}

# (field name, inclusive lower bound, inclusive upper bound)
_FIELDS: tuple[tuple[str, int, int], ...] = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day-of-month", 1, 31),
    ("month", 1, 12),
    ("day-of-week", 0, 6),
)

# ~4 years of days: covers every Feb-29 cadence within any leap cycle.
_LOOKBACK_DAYS = 1462
_MINUTES_PER_DAY = 1440


def _names_for(field_name: str) -> Mapping[str, int] | None:
    if field_name == "month":
        return _MONTH_NAMES
    if field_name == "day-of-week":
        return _DAY_NAMES
    return None


def _coerce_item(
    token: str, field_name: str, lo: int, hi: int, names: Mapping[str, int] | None
) -> int:
    """Convert a single cron token (number or name) to its value."""
    if names is not None and token in names:
        value = names[token]
    elif token.isdigit():
        value = int(token)
        # vixie-cron allows 7 as an alias for Sunday.
        if field_name == "day-of-week" and value == 7:
            value = 0
    else:
        raise ValueError(f"invalid {field_name} value: {token!r}")
    if not lo <= value <= hi:
        raise ValueError(f"{field_name} value {value} out of range {lo}-{hi}")
    return value


def _parse_field(
    value: str, field_name: str, lo: int, hi: int, names: Mapping[str, int] | None
) -> set[int] | None:
    """Parse one cron field. Returns None for a ``*``/``?`` wildcard."""
    if value.strip() in ("*", "?"):
        return None
    allowed: set[int] = set()
    for item in value.split(","):
        item = item.strip().upper()
        if not item:
            raise ValueError(f"empty value in {field_name} field")
        if item in ("*", "?"):
            raise ValueError(f"'{item}' cannot be combined with other values in {field_name} field")

        step = 1
        if "/" in item:
            base, _, step_raw = item.partition("/")
            if not step_raw.isdigit() or int(step_raw) < 1:
                raise ValueError(f"invalid step in {field_name} field: {item!r}")
            step = int(step_raw)
            item = base

        if "-" in item:
            start_raw, _, end_raw = item.partition("-")
            start = _coerce_item(start_raw, field_name, lo, hi, names)
            end = _coerce_item(end_raw, field_name, lo, hi, names)
            if start > end:
                raise ValueError(f"{field_name} range start exceeds end: {item!r}")
            allowed.update(range(start, end + 1, step))
        elif item == "*":
            allowed.update(range(lo, hi + 1, step))
        else:
            allowed.add(_coerce_item(item, field_name, lo, hi, names))
    return allowed


def validate_cron(expression: str) -> None:
    """Validate a 5-field cron expression; raise ValueError on invalid input."""
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("cron expression must be a non-empty string")
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError(
            "cron expression must have exactly 5 fields "
            "(minute hour day-of-month month day-of-week)"
        )
    for (field_name, lo, hi), value in zip(_FIELDS, fields, strict=True):
        _parse_field(value, field_name, lo, hi, _names_for(field_name))


def _fields_from(expression: str) -> tuple[set[int] | None, ...]:
    return tuple(
        _parse_field(value, field_name, lo, hi, _names_for(field_name))
        for (field_name, lo, hi), value in zip(_FIELDS, expression.split(), strict=True)
    )


def _matches_minute(fields: tuple[set[int] | None, ...], dt: datetime) -> bool:
    minute_set, hour_set = fields[0], fields[1]
    if hour_set is not None and dt.hour not in hour_set:
        return False
    if minute_set is not None and dt.minute not in minute_set:
        return False
    return True


def _day_matches(fields: tuple[set[int] | None, ...], day: date) -> bool:
    dom_set, month_set, dow_set = fields[2], fields[3], fields[4]
    if month_set is not None and day.month not in month_set:
        return False
    dom_ok = dom_set is None or day.day in dom_set
    # Convert Python's weekday (Mon=0) to cron's (Sun=0) before comparing.
    cron_weekday = (day.weekday() + 1) % 7
    dow_ok = dow_set is None or cron_weekday in dow_set
    if dom_set is not None and dow_set is not None:
        return dom_ok or dow_ok
    if dom_set is not None:
        return dom_ok
    if dow_set is not None:
        return dow_ok
    return True


def previous_fire(expression: str, now: datetime) -> datetime | None:
    """Return the most recent fire time (UTC, minute precision) at or before ``now``.

    Returns None when the expression never matches within the lookback window
    (e.g. an impossible date like Feb 31).
    """
    validate_cron(expression)
    fields = _fields_from(expression)
    now = now.astimezone(UTC).replace(second=0, microsecond=0)

    # 1) Walk the current day backward (bounded by a single day).
    start_of_day = datetime.combine(now.date(), time(0, 0), tzinfo=UTC)
    cursor = now
    while cursor >= start_of_day:
        if _matches_minute(fields, cursor) and _day_matches(fields, cursor):
            return cursor
        cursor -= timedelta(minutes=1)

    # 2) Walk previous days; only scan matching days in full.
    day = now.date()
    for _ in range(_LOOKBACK_DAYS):
        day -= timedelta(days=1)
        if not _day_matches(fields, day):
            continue
        base = datetime.combine(day, time(0, 0), tzinfo=UTC)
        for minute in range(_MINUTES_PER_DAY - 1, -1, -1):
            candidate = base + timedelta(minutes=minute)
            if _matches_minute(fields, candidate):
                return candidate
    return None
