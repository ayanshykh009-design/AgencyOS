"""Lightweight monotonic counters for schedule-dispatch telemetry.

Reuses the existing observability stack: when ``OTEL_ENABLED=true`` the
counters also mirror into real OpenTelemetry metrics (the opentelemetry SDK is
already a dependency). A thread-safe in-process fallback is always maintained
so the worker works without an exporter and tests can read counter values.

Public API:

- ``get_counter(name, description, unit)`` — return a counter handle.
- ``read_counter(name)`` — current in-process value (0 if never incremented).
- ``reset()`` — zero all in-process counters (test helper).
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

logger = logging.getLogger("agencyos.telemetry")


class _FallbackCounter:
    """Thread-safe in-process counter used when OTel is not exported."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._lock = threading.Lock()
        self._value = 0

    def add(self, value: int = 1) -> None:
        with self._lock:
            self._value += value

    def reset(self) -> None:
        with self._lock:
            self._value = 0

    @property
    def value(self) -> int:
        with self._lock:
            return self._value


class Counter:
    """Monotonic counter that records to OTel (when enabled) and in-process."""

    def __init__(self, name: str, description: str, unit: str) -> None:
        self._name = name
        self._fallback = _FallbackCounter(name)
        self._otel = _build_otel_counter(name, description, unit)

    def add(self, value: int = 1, attributes: Mapping[str, Any] | None = None) -> None:
        self._fallback.add(value)
        if self._otel is not None:
            self._otel.add(value, attributes=attributes or {})

    @property
    def value(self) -> int:
        return self._fallback.value

    def reset(self) -> None:
        self._fallback.reset()


def _build_otel_counter(name: str, description: str, unit: str) -> Any | None:
    """Build a real OTel counter when metrics are enabled, else None."""
    if not settings.OTEL_ENABLED:
        return None
    try:
        from opentelemetry import metrics as otel_metrics

        meter = otel_metrics.get_meter_provider().get_meter(
            "agencyos.automation.schedule", "0.1.0"
        )
        return meter.create_counter(name, description=description, unit=unit)
    except Exception:  # pragma: no cover - depends on exporter availability
        logger.warning("OpenTelemetry metrics unavailable; using in-process counters")
        return None


_counters: dict[str, Counter] = {}
_registry_lock = threading.Lock()


def get_counter(name: str, description: str = "", unit: str = "1") -> Counter:
    """Return a shared monotonic counter for ``name`` (created on first use)."""
    with _registry_lock:
        counter = _counters.get(name)
        if counter is None:
            counter = Counter(name, description, unit)
            _counters[name] = counter
        return counter


def read_counter(name: str) -> int:
    """Return the current in-process value of a counter (0 if never used)."""
    with _registry_lock:
        counter = _counters.get(name)
        return counter.value if counter is not None else 0


def reset() -> None:
    """Zero all in-process counters (test helper)."""
    with _registry_lock:
        for counter in _counters.values():
            counter.reset()
