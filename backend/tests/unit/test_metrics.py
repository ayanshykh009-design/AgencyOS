"""Unit tests: lightweight metrics counters (app.core.metrics)."""
from __future__ import annotations

from app.core.metrics import get_counter, read_counter, reset


def test_counter_starts_at_zero() -> None:
    reset()
    assert read_counter("test.never_incremented") == 0


def test_counter_increments() -> None:
    reset()
    counter = get_counter("test.dispatch")
    counter.add()
    counter.add()
    assert read_counter("test.dispatch") == 2


def test_counter_shares_singleton_per_name() -> None:
    reset()
    get_counter("test.singleton").add(3)
    assert get_counter("test.singleton") is get_counter("test.singleton")
    assert read_counter("test.singleton") == 3


def test_counter_accepts_value_and_attributes() -> None:
    reset()
    get_counter("test.attr").add(5, {"trigger_id": "x"})
    assert read_counter("test.attr") == 5


def test_reset_zeroes_all_counters() -> None:
    reset()
    get_counter("test.a").add(2)
    get_counter("test.b").add(1)
    reset()
    assert read_counter("test.a") == 0
    assert read_counter("test.b") == 0


def test_schedule_metric_names_registered() -> None:
    reset()
    for name in (
        "schedule_dispatch_success",
        "schedule_dispatch_failure",
        "schedule_dispatch_skip",
        "reservation_conflict",
        "queue_success",
        "queue_failure",
    ):
        assert read_counter(name) == 0
