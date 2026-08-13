"""Delivery provider test doubles (M6).

Deterministic fake providers for the unit/integration suite: success, retryable
failure, permanent failure, hang (active-timeout), and crash. Constructed with
``session=None`` so tests can use them without a database session.
"""

from __future__ import annotations

import asyncio

from app.communication.contract import (
    DeliveryMessage,
    DeliveryProvider,
    DeliveryResult,
    PermanentDeliveryError,
    RetryableDeliveryError,
)
from app.models.enums import DeliveryChannel


class StubProvider(DeliveryProvider):
    """Always succeeds; records every received message for assertions."""

    channel = DeliveryChannel.DASHBOARD

    def __init__(self, session=None) -> None:  # type: ignore[assignment]
        super().__init__(session)  # type: ignore[arg-type]
        self.calls: list[DeliveryMessage] = []
        self._metadata: dict = {}

    async def deliver(self, message: DeliveryMessage) -> DeliveryResult:
        self.calls.append(message)
        return DeliveryResult(
            ok=True,
            provider_metadata={"stub": True, **self._metadata},
        )


class FailureProvider(DeliveryProvider):
    """Always fails with a retryable error (drives the retry policy)."""

    channel = DeliveryChannel.EMAIL

    def __init__(self, session=None, *, error_code: str = "provider.unavailable") -> None:
        super().__init__(session)  # type: ignore[arg-type]
        self.error_code = error_code
        self.calls: list[DeliveryMessage] = []

    async def deliver(self, message: DeliveryMessage) -> DeliveryResult:
        self.calls.append(message)
        raise RetryableDeliveryError(self.error_code, "provider temporarily unavailable")


class PermanentFailureProvider(DeliveryProvider):
    """Fails permanently (e.g. ``provider.not_configured``); never retried."""

    channel = DeliveryChannel.WHATSAPP

    def __init__(self, session=None, *, error_code: str = "provider.not_configured") -> None:
        super().__init__(session)  # type: ignore[arg-type]
        self.error_code = error_code
        self.calls: list[DeliveryMessage] = []

    async def deliver(self, message: DeliveryMessage) -> DeliveryResult:
        self.calls.append(message)
        raise PermanentDeliveryError(self.error_code, "provider is not configured")


class TimeoutProvider(DeliveryProvider):
    """Hangs past the active provider timeout (drives timed_out)."""

    channel = DeliveryChannel.PUSH

    def __init__(self, session=None, *, delay_seconds: float = 3600) -> None:
        super().__init__(session)  # type: ignore[arg-type]
        self.delay_seconds = delay_seconds

    async def deliver(self, message: DeliveryMessage) -> DeliveryResult:
        await asyncio.sleep(self.delay_seconds)
        return DeliveryResult(ok=True, provider_metadata={})  # pragma: no cover


class CrashedProvider(DeliveryProvider):
    """Blows up with an unexpected exception (unhandled provider bug)."""

    channel = DeliveryChannel.DASHBOARD

    def __init__(self, session=None) -> None:  # type: ignore[assignment]
        super().__init__(session)  # type: ignore[arg-type]
        self.calls: list[DeliveryMessage] = []

    async def deliver(self, message: DeliveryMessage) -> DeliveryResult:
        self.calls.append(message)
        raise RuntimeError("provider exploded")
