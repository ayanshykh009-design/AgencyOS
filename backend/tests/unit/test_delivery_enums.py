"""Unit tests for the M6 delivery enums (must match the frozen plan)."""
from __future__ import annotations

from app.models.enums import DeliveryChannel, DeliveryEventType, DeliveryStatus


def test_delivery_channel_values() -> None:
    assert set(DeliveryChannel) == {"dashboard", "email", "whatsapp", "push"}


def test_delivery_status_values() -> None:
    assert set(DeliveryStatus) == {
        "queued",
        "processing",
        "delivered",
        "retrying",
        "failed",
        "cancelled",
    }


def test_delivery_event_type_values() -> None:
    assert set(DeliveryEventType) == {
        "queued",
        "claimed",
        "provider_dispatched",
        "provider_returned",
        "delivered",
        "retrying",
        "failed",
        "cancelled",
        "timed_out",
        "recovery_guard",
        "superseded",
    }
