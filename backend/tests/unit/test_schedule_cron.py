"""Unit tests: minimal 5-field cron evaluator (app.services.schedule_cron)."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.services.schedule_cron import previous_fire, validate_cron


def _dt(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


@pytest.mark.parametrize(
    "expression",
    [
        "* * * * *",
        "0 9 * * MON-FRI",
        "*/15 8-18 * * *",
        "0,30 9-17 * * ?",
        "0 0 1 * *",
        "0 0 29 2 *",
        "30 6 * * 1-5",
        "0 9 * JAN,MAR *",
        "15 10 ? * SUN-SAT",
        "0 0 * * 7",
        "0 22 * * 1-5",
    ],
)
def test_validate_cron_accepts_valid_expressions(expression: str) -> None:
    validate_cron(expression)


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "   ",
        "0 9 * *",
        "0 9 * * * extra",
        "60 * * * *",
        "* 24 * * *",
        "0 0 0 * *",
        "0 0 * 13 *",
        "0 0 * * 8",
        "0 0 * * MONDAY",
        "0 9 * * */0",
        "0 9 * * 9-1",
        "0 9 * *, *",
        "*/x * * * *",
    ],
)
def test_validate_cron_rejects_invalid_expressions(expression: str) -> None:
    with pytest.raises(ValueError):
        validate_cron(expression)


def test_validate_cron_rejects_non_string() -> None:
    with pytest.raises(ValueError):
        validate_cron(None)  # type: ignore[arg-type]


def test_previous_fire_every_minute_is_now_truncated() -> None:
    now = _dt(2026, 8, 4, 10, 30, 45)
    assert previous_fire("* * * * *", now) == _dt(2026, 8, 4, 10, 30)


def test_previous_fire_daily_at_midnight() -> None:
    now = _dt(2026, 8, 4, 10, 0)
    assert previous_fire("0 0 * * *", now) == _dt(2026, 8, 4, 0, 0)


def test_previous_fire_skips_to_previous_day() -> None:
    now = _dt(2026, 8, 4, 0, 30)
    assert previous_fire("0 0 * * *", now) == _dt(2026, 8, 4, 0, 0)
    assert previous_fire("30 23 * * *", now) == _dt(2026, 8, 3, 23, 30)


def test_previous_fire_step_field() -> None:
    now = _dt(2026, 8, 4, 10, 17)
    assert previous_fire("*/5 * * * *", now) == _dt(2026, 8, 4, 10, 15)


def test_previous_fire_weekday_restriction() -> None:
    # 2026-08-04 is a Tuesday; Monday 2026-08-03 09:00 is the last fire.
    now = _dt(2026, 8, 4, 12, 0)
    assert previous_fire("0 9 * * MON-FRI", now) == _dt(2026, 8, 4, 9, 0)


def test_previous_fire_skips_weekend() -> None:
    # 2026-08-08 is a Saturday; last weekday fire is Friday 2026-08-07 09:00.
    now = _dt(2026, 8, 8, 12, 0)
    assert previous_fire("0 9 * * MON-FRI", now) == _dt(2026, 8, 7, 9, 0)


def test_previous_fire_sunday_alias_7() -> None:
    # 2026-08-09 is a Sunday.
    now = _dt(2026, 8, 10, 12, 0)
    assert previous_fire("0 9 * * 7", now) == _dt(2026, 8, 9, 9, 0)


def test_previous_fire_leap_day() -> None:
    # Feb 29 only exists in leap years; 2028 is the next leap year.
    now = _dt(2028, 3, 1, 12, 0)
    assert previous_fire("0 0 29 2 *", now) == _dt(2028, 2, 29, 0, 0)


def test_previous_fire_impossible_date_returns_none() -> None:
    # Feb 31 never exists -> no fire within the lookback window.
    now = _dt(2026, 8, 4, 12, 0)
    assert previous_fire("0 0 31 2 *", now) is None


def test_previous_fire_matches_exact_minute() -> None:
    now = _dt(2026, 8, 4, 10, 30)
    assert previous_fire("30 10 * * *", now) == now


def test_previous_fire_range_list() -> None:
    now = _dt(2026, 8, 4, 9, 0)
    assert previous_fire("0,30 9-17 * * *", now) == now
    assert previous_fire("15,45 * * * *", _dt(2026, 8, 4, 9, 16)) == _dt(2026, 8, 4, 9, 15)


def test_previous_fire_question_mark_as_wildcard() -> None:
    now = _dt(2026, 8, 4, 9, 16)
    assert previous_fire("15 9 * * ?", now) == _dt(2026, 8, 4, 9, 15)
