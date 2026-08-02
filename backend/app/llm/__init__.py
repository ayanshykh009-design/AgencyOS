"""AI provider layer for AgencyOS.

A future-proof, provider-agnostic abstraction over large-language-model APIs.

Public surface:

    LLMService  — facade exposing ``chat``, ``stream`` and ``embeddings``.
                  Provider is selected at runtime from configuration; all usage
                  is recorded through the existing ``ProviderUsage`` accounting.

The only symbols callers should touch are ``LLMService`` (business entry point)
and the data containers in :mod:`app.llm.models`. Provider SDKs are imported
lazily inside their client modules so an unconfigured provider never slows
startup or raises at import time.
"""

from __future__ import annotations

from app.llm.models import (
    ChatResult,
    EmbedResult,
    LLMMessage,
    LLMUsage,
    ProviderType,
)
from app.llm.service import LLMService

__all__ = [
    "ChatResult",
    "EmbedResult",
    "LLMMessage",
    "LLMService",
    "LLMUsage",
    "ProviderType",
]
