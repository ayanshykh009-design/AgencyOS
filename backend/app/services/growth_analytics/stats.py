"""Deterministic statistical helpers for the growth analytics engines.

Small, pure, dependency-free math used across the M7 engines. Everything here
is deterministic: same inputs in, same outputs out. No external statistics
library is required.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import TypeVar

T = TypeVar("T")


def to_float(value: Decimal | float | int | None, default: float = 0.0) -> float:
    """Coerce a Decimal/float/int to float, with a fallback for None."""
    if value is None:
        return default
    return float(value)


def mean(xs: Sequence[float]) -> float:
    """Arithmetic mean of a sequence (0.0 when empty)."""
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


def sample_stdev(xs: Sequence[float]) -> float:
    """Sample standard deviation (0.0 when fewer than two points)."""
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    variance = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(variance)


def zscore(x: float, m: float, std: float) -> float:
    """Standard score; 0.0 when the spread is zero."""
    if std == 0:
        return 0.0
    return (x - m) / std


def clamp(value: float, low: float, high: float) -> float:
    """Clamp ``value`` into ``[low, high]``."""
    return max(low, min(high, value))


def pct_change(old: float, new: float) -> float:
    """Relative change (old -> new) as a fraction; 0 when old is 0."""
    if old == 0:
        return 0.0
    return (new - old) / abs(old)


def lerp_band(value: float, zero_at: float, hundred_at: float) -> float:
    """Map ``value`` linearly so ``zero_at`` -> 0 and ``hundred_at`` -> 100.

    Values below ``zero_at`` clamp to 0, above ``hundred_at`` clamp to 100.
    """
    span = hundred_at - zero_at
    if span == 0:
        return 100.0 if value >= hundred_at else 0.0
    return clamp((value - zero_at) / span * 100.0, 0.0, 100.0)


def linear_fit(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float, float, list[float]]:
    """Least-squares fit: (slope, intercept, r_squared, residuals).

    Returns slope=0, intercept=mean(ys), r2=0 with empty residuals when there
    are fewer than two distinct x values.
    """
    n = len(xs)
    if n < 2 or n != len(ys):
        return 0.0, mean(ys), 0.0, []
    x_mean = mean(xs)
    y_mean = mean(ys)
    sxx = sum((x - x_mean) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, y_mean, 0.0, []
    sxy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True))
    slope = sxy / sxx
    intercept = y_mean - slope * x_mean
    residuals = [y - (slope * x + intercept) for x, y in zip(xs, ys, strict=True)]
    y_var = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum(r * r for r in residuals)
    r2 = 1.0 - (ss_res / y_var) if y_var else 0.0
    return slope, intercept, r2, residuals


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion (default 95% confidence).

    Returns ``(lower, upper)`` proportions. Degenerates to ``(0, 0)`` for no
    trials and ``(1, 1)`` for all-success single-trial.
    """
    if trials <= 0:
        return 0.0, 0.0
    p = successes / trials
    z2 = z * z
    denom = 1 + z2 / trials
    centre = (p + z2 / (2 * trials)) / denom
    margin = z * math.sqrt((p * (1 - p) + z2 / (4 * trials)) / trials) / denom
    return clamp(centre - margin, 0.0, 1.0), clamp(centre + margin, 0.0, 1.0)


def sum_decimal(values: Iterable[Decimal | float | int | None]) -> Decimal:
    """Sum values as Decimal, skipping None."""
    total = Decimal("0")
    for value in values:
        if value is None:
            continue
        if isinstance(value, Decimal):
            total += value
        else:
            total += Decimal(str(value))
    return total


def quantize(value: Decimal | float, places: int = 4) -> Decimal:
    """Round a Decimal/float to ``places`` decimal places (numeric-18,6-safe)."""
    return Decimal(str(round(float(value), places)))
