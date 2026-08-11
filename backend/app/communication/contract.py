"""Delivery provider contract (M6).

Channel adapters implement :class:`DeliveryProvider` against this contract and
are registered in the :class:`DeliveryProviderRegistry` (``app/communication/
providers.py``). The contract is deliberately transport-agnostic so the same
outbox semantics hold for dashboard, email, whatsapp, and push providers.

Error semantics:

- :class:`RetryableDeliveryError`  — transient; the delivery worker schedules
  a retry (subject to ``max_attempts``/backoff).
- :class:`PermanentDeliveryError` — will never succeed (e.g. ``provider.
  not_configured``); the worker marks the delivery FAILED immediately without
  burning retries.

Idempotency: the worker drains at-least-once. A provider may be asked to send
the same ``delivery_id``/``idempotency_key`` again after a worker crash (the
crash rolls the transaction back, so any side effect the provider wrote is
also rolled back). Providers must therefore be safe to call for the same
delivery more than once and return a consistent result.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.models.enums import DeliveryChannel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class DeliveryError(Exception):
    """Base class for provider failures, carrying a stable error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"{self.__class__.__name__}({self.code!r}, {self.message!r})"


class RetryableDeliveryError(DeliveryError):
    """Transient failure: safe to retry (subject to the retry policy)."""


class PermanentDeliveryError(DeliveryError):
    """Permanent failure: retrying will never succeed; mark the delivery FAILED.

    The canonical example is ``provider.not_configured`` — a channel whose
    provider has not shipped. It must never be retried.
    """


@dataclass(frozen=True)
class DeliveryMessage:
    """Everything a provider needs to send one delivery.

    ``delivery_id``/``idempotency_key`` are the correlation + idempotency
    handles; ``metadata`` is the structured payload (never secrets or PII
    beyond what the recipient already owns).
    """

    delivery_id: uuid.UUID
    idempotency_key: str | None
    organization_id: uuid.UUID
    recipient_user_id: uuid.UUID | None
    subject: str
    body: str
    action_url: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeliveryResult:
    """Outcome of one provider attempt.

    ``ok=True`` means the provider accepted the message; the worker persists
    ``provider_metadata`` and marks the delivery DELIVERED. Expected failures
    are returned as ``ok=False`` (with ``error``), never raised — raising is
    reserved for ``DeliveryError`` subclasses and programming errors.
    """

    ok: bool
    provider_metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class DeliveryProvider(ABC):
    """Contract every channel adapter implements.

    Providers are constructed per use with an :class:`AsyncSession` so they can
    write side effects (e.g. an inbox row) inside the worker's transaction.
    """

    channel: DeliveryChannel

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @abstractmethod
    async def deliver(self, message: DeliveryMessage) -> DeliveryResult:
        """Attempt delivery.

        - success            -> ``DeliveryResult(ok=True, provider_metadata=...)``
        - expected failure   -> ``DeliveryResult(ok=False, error=...)``
        - retryable failure  -> raise :class:`RetryableDeliveryError`
        - permanent failure  -> raise :class:`PermanentDeliveryError`
        """
