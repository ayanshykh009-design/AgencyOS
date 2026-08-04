"""Content-Security-Policy builder — validated and configuration-driven.

The middleware applies the built policy when ``ENABLE_CSP`` is on. Directives
stay restrictive: a JSON API has no business loading third-party scripts or
frames, so the policy pins ``default-src 'self'`` plus hardening directives and
only widens ``connect-src`` for explicitly configured origins (e.g. Supabase,
n8n, or an LLM gateway). ``upgrade-insecure-requests`` is added in production
so a mis-served page cannot downgrade to HTTP.

Config is validated at startup (``app/core/config.py``), so an invalid
``CSP_CONNECT_ORIGINS`` value fails fast at boot rather than at request time.
"""
from __future__ import annotations

import re

from app.core.config import settings

_BASE_POLICY = [
    "default-src 'self'",
    "base-uri 'self'",
    "frame-ancestors 'self'",
    "form-action 'self'",
    "object-src 'none'",
    "frame-src 'none'",
]

# scheme://host(:port)(/path) only — no wildcards, no keywords, no quotes.
_ORIGIN_RE = re.compile(
    r"^(https?|wss?):\/\/"
    r"[A-Za-z0-9.\-]+"
    r"(:\d+)?"
    r"(/[A-Za-z0-9.\-_/]*)?$"
)


def validate_csp_origins(connect_origins: str) -> list[str]:
    """Parse and validate ``CSP_CONNECT_ORIGINS``; raise ValueError if invalid.

    Returns the trimmed origin list (empty when the setting is blank).
    """
    origins = [o.strip() for o in connect_origins.split(",") if o.strip()]
    for origin in origins:
        if not _ORIGIN_RE.fullmatch(origin):
            raise ValueError(f"invalid CSP connect origin: {origin!r}")
    return origins


def build_csp_policy(
    *,
    connect_origins: str | None = None,
    production: bool | None = None,
) -> str:
    """Build the full CSP policy string from configuration.

    Overridable via keyword args for tests; production callers use the
    settings singleton so the policy always matches validated config.
    """
    if connect_origins is None:
        connect_origins = settings.CSP_CONNECT_ORIGINS
    if production is None:
        production = settings.APP_ENV == "production"

    origins = validate_csp_origins(connect_origins)
    directives = list(_BASE_POLICY)
    if origins:
        directives.append("connect-src 'self' " + " ".join(origins))
    if production:
        directives.append("upgrade-insecure-requests")
    return "; ".join(directives)
