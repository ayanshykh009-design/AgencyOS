"""Delivery provider registry + lookup helpers (M6).

Providers implement the contract in ``app/communication/contract.py`` and
register their channel class here; :func:`get_provider` returns a session-bound
provider for a channel or raises :class:`DeliveryProviderUnavailable` for
channels whose providers have not shipped yet (fail closed).

M6 ships the ``dashboard`` provider only; ``email``/``whatsapp``/``push`` stay
unavailable until their providers land in later milestones.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.communication.contract import DeliveryProvider
from app.communication.inapp_provider import InAppProvider
from app.models.enums import DeliveryChannel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class DeliveryProviderUnavailable(RuntimeError):
    """Raised when no provider is registered for a delivery channel."""


class DeliveryProviderRegistry:
    """Channel -> provider class mapping; registered at import time."""

    _providers: dict[DeliveryChannel, type[DeliveryProvider]] = {}

    @classmethod
    def register(cls, provider: type[DeliveryProvider]) -> None:
        cls._providers[provider.channel] = provider

    @classmethod
    def available(cls) -> set[DeliveryChannel]:
        return set(cls._providers)

    @classmethod
    def get(
        cls, channel: DeliveryChannel, session: AsyncSession
    ) -> DeliveryProvider:
        provider_cls = cls._providers.get(channel)
        if provider_cls is None:
            raise DeliveryProviderUnavailable(
                f"No delivery provider registered for channel '{channel.value}'"
            )
        return provider_cls(session)


# Register the shipped providers. New providers register themselves here when
# they land (email/whatsapp/push remain unavailable until then).
DeliveryProviderRegistry.register(InAppProvider)


def get_provider(
    channel: DeliveryChannel, session: AsyncSession
) -> DeliveryProvider:
    """Return a session-bound provider for ``channel`` (fail closed)."""
    return DeliveryProviderRegistry.get(channel, session)


def provider_available(channel: DeliveryChannel) -> bool:
    """Whether a provider is registered for ``channel``."""
    return channel in DeliveryProviderRegistry.available()


def sanitize_error(exc: Exception) -> str:
    """Short, safe error text for persistence (no stack traces/secrets)."""
    text = str(exc).strip() or exc.__class__.__name__
    return text[:500]
