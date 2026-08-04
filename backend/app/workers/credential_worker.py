"""Credential rekey worker: re-encrypt stale credentials with the current key.

Enables master-key rotation: while ``CREDENTIALS_ENC_KEY_PREVIOUS`` keeps old
rows readable (dual-read), this worker re-encrypts everything under the new
``CREDENTIALS_ENC_KEY`` and retires the previous version once no stale rows
remain.

Restart-safety: per-row work is idempotent (decrypt → re-encrypt with the
current version), batches are bounded, and state (``key_version``) is
persisted per row, so a crash mid-sweep leaves no partial progress — the next
tick picks up where it stopped. Rows that fail to decrypt are logged and
skipped (never re-encrypted into garbage).

Runs as a standalone loop (``python -m app.workers.credential_worker``).
"""
from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.kms import get_kms_provider
from app.core.metrics import get_counter
from app.services.base import utcnow
from app.services.credential_service import CredentialService

logger = logging.getLogger("agencyos.automation.credential_worker")


class CredentialWorker:
    """Re-encrypt stale credentials in small, idempotent batches."""

    @classmethod
    async def rekey_tick(cls) -> dict[str, int]:
        """Run one rekey sweep. Returns ``{"rekeyed": n, "stale": n}``."""
        if not settings.CREDENTIAL_REKEY_ENABLED:
            return {"rekeyed": 0, "stale": 0}
        provider = get_kms_provider()
        current = provider.current_key_version()

        async with async_session_factory() as session:
            service = CredentialService(session)
            await service.upsert_key_version(
                current, provider.key_fingerprint(current)
            )
            previous = provider.previous_key_version()
            if previous is not None:
                await service.upsert_key_version(
                    previous, provider.key_fingerprint(previous)
                )

            batch = await service.list_stale_key(
                current, settings.CREDENTIAL_REKEY_BATCH
            )
            rekeyed = 0
            for credential in batch:
                try:
                    plaintext = provider.decrypt_secret(
                        credential.encrypted_value,
                        key_version=credential.key_version,
                    )
                except Exception:
                    get_counter("credential_rekey_failed").add(1)
                    logger.exception(
                        "rekey: skipping credential %s (key version %s) — decrypt failed",
                        credential.id,
                        credential.key_version,
                    )
                    continue
                credential.encrypted_value = provider.encrypt_secret(plaintext)
                credential.key_version = current
                credential.last_rotated_at = utcnow()
                rekeyed += 1
            await session.commit()

            stale = await service.count_stale_key(current)
            if stale == 0 and previous is not None:
                if await service.retire_key_version(previous):
                    logger.info("rekey: retired key version %s", previous)
                await session.commit()

            get_counter("credential_rekey_processed").add(rekeyed)
            logger.info(
                "credential rekey sweep: rekeyed=%s stale=%s",
                rekeyed,
                stale,
            )
            return {"rekeyed": rekeyed, "stale": stale}

    @classmethod
    async def run_loop(cls) -> None:
        """Poll forever: the standalone rekey worker entrypoint."""
        interval = settings.CREDENTIAL_REKEY_INTERVAL_SECONDS
        logger.info("credential rekey worker starting (every %ss)", interval)
        try:
            while True:
                try:
                    stats = await cls.rekey_tick()
                    if stats["rekeyed"] or stats["stale"]:
                        logger.info("credential rekey sweep stats: %s", stats)
                except Exception:
                    logger.exception("credential rekey tick failed")
                await asyncio.sleep(interval)
        except (KeyboardInterrupt, SystemExit):
            logger.info("credential rekey worker stopped")
            raise


def _worker_entrypoint() -> None:
    """Entrypoint for ``python -m app.workers.credential_worker``."""
    asyncio.run(CredentialWorker.run_loop())


if __name__ == "__main__":
    _worker_entrypoint()
