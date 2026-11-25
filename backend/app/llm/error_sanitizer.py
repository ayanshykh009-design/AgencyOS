"""Sanitization boundary for errors that cross into client-visible state.

Low-level provider/transport exceptions (``httpx``, vendor SDKs) can embed
request URLs, bodies, headers or credentials in their string form. Their text
must never be returned to a client or persisted in an assistant message.

This module centralises the boundary: callers pass the raw exception or error
string plus a stable public message. Raw detail is discarded after classification;
only non-sensitive metadata (label, request id, exception type) is logged, and
the stable message is returned.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("agencyos")


def safe_error(detail: Any, *, public: str, log_label: str) -> str:
    """Discard ``detail`` and return the stable ``public`` message.

    ``detail`` may be an exception, a tool/executor error string, or ``None``.
    Neither the returned string nor the log record contains text derived from
    ``detail``: provider/transport strings can embed URLs, bodies or secrets.
    Only the stable label, current request id and exception class name are
    logged, which keeps server-side diagnostics without leaking raw detail.
    """
    from app.core.contextvars import request_id_var

    if detail is not None:
        logger.warning(
            "%s [request_id=%s] sanitized upstream failure (type=%s)",
            log_label,
            request_id_var.get(),
            type(detail).__name__,
        )
    return public
