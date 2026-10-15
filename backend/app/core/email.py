"""Outbound email delivery for account-security messages.

A single, deliberately tiny surface: :func:`send_email` delivers a plaintext
message over SMTP when it is configured, and otherwise logs (never silently
drops in production — startup validation refuses to boot a mail-dependent
feature without SMTP; see ``Settings.validate_for_production``).

No secrets are logged: recipient addresses are reduced to a short digest.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from hashlib import sha256

from app.core.config import settings

logger = logging.getLogger("agencyos.email")


def _digest(address: str) -> str:
    return sha256(address.strip().lower().encode("utf-8")).hexdigest()[:16]


def send_email(*, to: str, subject: str, body: str) -> bool:
    """Send an email; return True when handed to the SMTP server.

    Returns False (without raising) when SMTP is not configured or delivery
    fails, so callers can decide the user-facing behaviour. The caller is
    responsible for not leaking whether an account exists.
    """
    if not settings.smtp_configured:
        logger.warning(
            "email.not_configured to=%s subject=%s", _digest(to), subject
        )
        return False

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls()
            if settings.SMTP_USERNAME:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)
    except Exception:  # noqa: BLE001 - delivery failure is reported, never raised
        logger.exception("email.send_failed to=%s subject=%s", _digest(to), subject)
        return False
    logger.info("email.sent to=%s subject=%s", _digest(to), subject)
    return True
