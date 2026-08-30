"""Delivery worker: drains the delivery outbox.

The worker sweeps the global delivery outbox on a polling loop:

- recovers stale PROCESSING rows (attempts stuck past
  ``DELIVERY_RECOVERY_SECONDS``) after stamping ``recovery_guard`` +
  ``timed_out`` events,
- promotes due RETRYING rows back to QUEUED,
- fair-drains due QUEUED deliveries through the channel provider:
  QUEUED -> PROCESSING (claim) -> DELIVERED | FAILED, or -> RETRYING,
- honours cooperative cancellation (a successful send always wins),
- upserts a heartbeat row per loop.

It owns a session per phase and is safe to run on multiple instances (state
transitions are optimistic — only one runner moves a delivery out of
QUEUED/RETRYING/PROCESSING). Each delivery is processed in its own
transaction, so a crash mid-send rolls back the claim, provider side effect
and events together.

Runs as a standalone loop (``python -m app.workers.delivery_worker``) or as a
single sweep from a scheduler.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.communication.contract import (
    DeliveryMessage,
    DeliveryResult,
    PermanentDeliveryError,
    RetryableDeliveryError,
)
from app.communication.providers import get_provider, sanitize_error
from app.core.config import settings
from app.core.database import async_session_factory
from app.core.metrics import get_counter, get_histogram
from app.core.observability import span
from app.models.delivery import Delivery
from app.models.delivery_event import DeliveryEvent
from app.models.enums import DeliveryEventType
from app.repositories.delivery import DeliveryRepository
from app.repositories.delivery_event import DeliveryEventRepository
from app.services.monitoring_service import WorkerHealthService

logger = logging.getLogger("agencyos.communication.delivery")

# Identity for this worker instance, stable across the process lifetime so the
# heartbeat upsert always targets one row per (worker_type, instance_id).
INSTANCE_ID = uuid.uuid4()

_HEARTBEAT_COUNTERS = (
    "delivery_queued_total",
    "delivery_drained_total",
    "delivery_attempt_total",
    "delivery_delivered_total",
    "delivery_failed_total",
    "delivery_retried_total",
    "delivery_cancelled_total",
    "delivery_timed_out_total",
    "delivery_recovered_total",
)


class DeliveryWorker:
    """Drains the delivery outbox."""

    _WORKER_TYPE = "delivery"

    def __init__(self, session_factory=async_session_factory) -> None:
        self._session_factory = session_factory

    @staticmethod
    async def _set_statement_timeout(session: AsyncSession) -> None:
        """Bound the phase's statements inside the current transaction."""
        timeout_ms = settings.DELIVERY_STATEMENT_TIMEOUT_SECONDS * 1000
        await session.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))

    # -- heartbeat -------------------------------------------------------

    async def heartbeat(
        self,
        *,
        loop_ok: bool,
        last_error: str | None,
        counters: dict | None = None,
    ) -> None:
        """Upsert this instance's heartbeat row."""
        async with self._session_factory() as session:
            svc = WorkerHealthService(session)
            await svc.heartbeat(
                worker_type=self._WORKER_TYPE,
                instance_id=INSTANCE_ID,
                loop_ok=loop_ok,
                last_error=last_error,
                counters=counters or {},
            )
            await session.commit()

    # -- event helpers ---------------------------------------------------

    @staticmethod
    def _event(
        org_id: uuid.UUID,
        delivery_id: uuid.UUID,
        event_type: DeliveryEventType,
        *,
        attempt: int,
        metadata: dict | None = None,
    ) -> DeliveryEvent:
        return DeliveryEvent(
            organization_id=org_id,
            delivery_id=delivery_id,
            event_type=event_type,
            attempt=attempt,
            metadata_=metadata or {},
        )

    # -- single-org drain ------------------------------------------------

    async def _drain_org(self, org_id: uuid.UUID, session: AsyncSession) -> int:
        """Drain due QUEUED deliveries for one organization."""
        deliveries_repo = DeliveryRepository(session)
        events_repo = DeliveryEventRepository(session)
        sent = 0

        due = await deliveries_repo.get_queued_for_org(org_id, settings.DELIVERY_BATCH_SIZE)
        if not due:
            return 0

        logger.debug("org %s: attempting %d due deliveries", org_id, len(due))

        for dlv in due:
            # Optimistic claim: QUEUED + due -> PROCESSING (one attempt).
            claimed = await deliveries_repo.claim(org_id, dlv.id)
            if not claimed:
                continue  # another worker beat us

            events_repo.add(
                self._event(
                    org_id,
                    claimed.id,
                    DeliveryEventType.CLAIMED,
                    attempt=claimed.attempts,
                )
            )

            await self._attempt(session, org_id, claimed, deliveries_repo, events_repo)
            sent += 1

            # Each delivery commits its own transaction so a crash rolls the
            # claim + provider side effect + events back together.
            await session.commit()

        return sent

    async def _attempt(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        claimed: Delivery,
        deliveries_repo: DeliveryRepository,
        events_repo: DeliveryEventRepository,
    ) -> None:
        """Dispatch one claimed delivery and land its terminal/retry state."""
        message = self._to_message(claimed)
        channel = claimed.channel.value
        attempt_started = time.perf_counter()
        try:
            provider = get_provider(claimed.channel, session)
            events_repo.add(
                self._event(
                    org_id,
                    claimed.id,
                    DeliveryEventType.PROVIDER_DISPATCHED,
                    attempt=claimed.attempts,
                )
            )
            result = await asyncio.wait_for(
                provider.deliver(message),
                timeout=settings.DELIVERY_ACTIVE_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            elapsed = time.perf_counter() - attempt_started
            self._observe_attempt(channel, "timed_out", elapsed)
            get_counter(
                "delivery_timed_out_total",
                description="Deliveries that exceeded the active provider timeout",
            ).add(1, {"channel": channel})
            await self._land(
                org_id,
                claimed,
                outcome="timed_out",
                error=f"provider exceeded {settings.DELIVERY_ACTIVE_TIMEOUT_SECONDS}s timeout",
                deliveries_repo=deliveries_repo,
                events_repo=events_repo,
            )
            logger.warning(
                "delivery %s attempt %s timed out after %ss",
                claimed.id,
                claimed.attempts,
                settings.DELIVERY_ACTIVE_TIMEOUT_SECONDS,
            )
            return
        except PermanentDeliveryError as exc:
            elapsed = time.perf_counter() - attempt_started
            self._observe_attempt(channel, "failed_permanent", elapsed)
            await self._land(
                org_id,
                claimed,
                outcome="failed",
                error=f"{exc.code}: {exc.message}",
                deliveries_repo=deliveries_repo,
                events_repo=events_repo,
            )
            logger.warning("delivery %s failed permanently (%s)", claimed.id, exc.code)
            return
        except RetryableDeliveryError as exc:
            elapsed = time.perf_counter() - attempt_started
            self._observe_attempt(channel, "failed_retryable", elapsed)
            await self._land(
                org_id,
                claimed,
                outcome="retry",
                error=f"{exc.code}: {exc.message}",
                deliveries_repo=deliveries_repo,
                events_repo=events_repo,
            )
            logger.info(
                "delivery %s retryable failure (%s), attempt %s",
                claimed.id,
                exc.code,
                claimed.attempts,
            )
            return
        except Exception as exc:
            elapsed = time.perf_counter() - attempt_started
            self._observe_attempt(channel, "failed_error", elapsed)
            logger.exception("delivery %s provider raised", claimed.id)
            await self._land(
                org_id,
                claimed,
                outcome="retry",
                error=sanitize_error(exc),
                deliveries_repo=deliveries_repo,
                events_repo=events_repo,
            )
            return

        elapsed = time.perf_counter() - attempt_started
        events_repo.add(
            self._event(
                org_id,
                claimed.id,
                DeliveryEventType.PROVIDER_RETURNED,
                attempt=claimed.attempts,
                metadata=result.provider_metadata if result else {},
            )
        )

        if result and result.ok:
            self._observe_attempt(channel, "delivered", elapsed)
            get_counter(
                "delivery_delivered_total",
                description="Deliveries marked delivered",
            ).add(1, {"channel": channel})
            await self._mark_delivered(org_id, claimed, result, deliveries_repo, events_repo)
        else:
            # Expected provider failure returned as ok=False (no raise).
            error = (result.error if result else None) or "provider returned failure"
            self._observe_attempt(channel, "failed_retryable", elapsed)
            await self._land(
                org_id,
                claimed,
                outcome="retry",
                error=error,
                deliveries_repo=deliveries_repo,
                events_repo=events_repo,
            )

    async def _mark_delivered(
        self,
        org_id: uuid.UUID,
        claimed: Delivery,
        result: DeliveryResult,
        deliveries_repo: DeliveryRepository,
        events_repo: DeliveryEventRepository,
    ) -> None:
        """PROCESSING -> DELIVERED. Delivered always wins over a cancel request."""
        delivered = await deliveries_repo.mark_delivered(
            org_id,
            claimed.id,
            provider_metadata=result.provider_metadata,
            delivered_at=datetime.now().astimezone(),
        )
        if delivered:
            events_repo.add(
                self._event(
                    org_id,
                    claimed.id,
                    DeliveryEventType.DELIVERED,
                    attempt=delivered.attempts,
                    metadata=result.provider_metadata,
                )
            )
            get_counter(
                "delivery_drained_total",
                description="Deliveries drained to a terminal state",
            ).add(1, {"channel": claimed.channel.value})

    async def _land(
        self,
        org_id: uuid.UUID,
        claimed: Delivery,
        *,
        outcome: str,
        error: str,
        deliveries_repo: DeliveryRepository,
        events_repo: DeliveryEventRepository,
    ) -> None:
        """Route a failed attempt: terminal FAILED/CANCELLED or a retry.

        ``outcome`` is ``failed`` (permanent or attempts exhausted), ``retry``
        (transient), or ``timed_out``. Cooperative cancellation is honoured for
        failures: a cancel-requested row is cancelled instead of retried.
        """
        now = datetime.now().astimezone()
        cancel_requested = claimed.cancel_requested_at is not None
        attempts_exhausted = claimed.attempts >= claimed.max_attempts
        permanent = outcome == "failed"

        if cancel_requested and not permanent:
            cancelled = await deliveries_repo.mark_cancelled_after_send(
                org_id, claimed.id, cancelled_at=now, error=error
            )
            if cancelled:
                events_repo.add(
                    self._event(
                        org_id,
                        claimed.id,
                        DeliveryEventType.CANCELLED,
                        attempt=cancelled.attempts,
                        metadata={"error": error},
                    )
                )
                get_counter(
                    "delivery_cancelled_total",
                    description="Deliveries cancelled",
                ).add(1, {"channel": claimed.channel.value})
                get_counter(
                    "delivery_drained_total",
                    description="Deliveries drained to a terminal state",
                ).add(1, {"channel": claimed.channel.value})
            return

        if permanent or attempts_exhausted:
            failed = await deliveries_repo.mark_failed(
                org_id, claimed.id, error=error, failed_at=now
            )
            if failed:
                events_repo.add(
                    self._event(
                        org_id,
                        claimed.id,
                        DeliveryEventType.FAILED,
                        attempt=failed.attempts,
                        metadata={"error": error},
                    )
                )
                get_counter(
                    "delivery_failed_total",
                    description="Deliveries marked failed",
                ).add(1, {"channel": claimed.channel.value})
                get_counter(
                    "delivery_drained_total",
                    description="Deliveries drained to a terminal state",
                ).add(1, {"channel": claimed.channel.value})
            return

        delay = self._backoff(claimed.attempts)
        next_at = now + timedelta(seconds=delay)
        retried = await deliveries_repo.schedule_retry(
            org_id,
            claimed.id,
            next_attempt_at=next_at,
            error=error,
        )
        if retried:
            events_repo.add(
                self._event(
                    org_id,
                    claimed.id,
                    DeliveryEventType.RETRYING,
                    attempt=retried.attempts,
                    metadata={"error": error, "delay_seconds": delay},
                )
            )
            get_counter(
                "delivery_retried_total",
                description="Deliveries scheduled for retry",
            ).add(1, {"channel": claimed.channel.value})

    @staticmethod
    def _to_message(delivery: Delivery) -> DeliveryMessage:
        return DeliveryMessage(
            delivery_id=delivery.id,
            idempotency_key=delivery.idempotency_key,
            organization_id=delivery.organization_id,
            recipient_user_id=delivery.recipient_user_id,
            subject=delivery.subject,
            body=delivery.body,
            action_url=delivery.action_url,
            metadata={
                **(delivery.payload or {}),
                "approval_request_id": (
                    str(delivery.approval_request_id) if delivery.approval_request_id else None
                ),
            },
        )

    @staticmethod
    def _observe_attempt(channel: str, outcome: str, elapsed: float) -> None:
        get_counter(
            "delivery_attempt_total",
            description="Delivery provider attempts",
        ).add(1, {"channel": channel, "outcome": outcome})
        get_histogram(
            "delivery_attempt_seconds",
            description="Delivery provider attempt duration",
            unit="s",
        ).observe(elapsed, {"channel": channel, "outcome": outcome})

    @staticmethod
    def _backoff(attempt: int) -> int:
        """Exponential backoff: 10s * 2^(attempt-1), capped at 1 hour.

        With ``DELIVERY_RETRY_BASE_SECONDS=10`` and max_attempts=4 the wait
        sequence is 10s, 20s, 40s (3 retries after the initial attempt).
        """
        base = settings.DELIVERY_RETRY_BASE_SECONDS
        max_delay = 3600
        delay = base * (2 ** (attempt - 1))
        return min(delay, max_delay)

    # -- recovery + retry promotion ---------------------------------------

    async def _recover_stale(self, session: AsyncSession) -> int:
        """Recover PROCESSING deliveries stuck past the recovery window.

        A live worker's provider call is bounded by ``ACTIVE_TIMEOUT``, so a
        row stuck past ``RECOVERY`` (>> ACTIVE_TIMEOUT, enforced at config
        validation) was almost certainly left by a dead instance. Stamp
        ``timed_out`` + ``recovery_guard`` events, then requeue for re-send.
        """
        deliveries_repo = DeliveryRepository(session)
        events_repo = DeliveryEventRepository(session)
        stale_threshold = datetime.now().astimezone() - timedelta(
            seconds=settings.DELIVERY_RECOVERY_SECONDS
        )
        stale = await deliveries_repo.list_stale_processing(
            stale_threshold, limit=settings.DELIVERY_BATCH_SIZE
        )
        recovered = 0
        for dlv in stale:
            events_repo.add(
                self._event(
                    dlv.organization_id,
                    dlv.id,
                    DeliveryEventType.TIMED_OUT,
                    attempt=dlv.attempts,
                    metadata={"reason": "stale_processing"},
                )
            )
            events_repo.add(
                self._event(
                    dlv.organization_id,
                    dlv.id,
                    DeliveryEventType.RECOVERY_GUARD,
                    attempt=dlv.attempts,
                    metadata={"recovery_seconds": settings.DELIVERY_RECOVERY_SECONDS},
                )
            )
            requeued = await deliveries_repo.requeue_stale(dlv.organization_id, dlv.id)
            if requeued:
                recovered += 1
        if recovered:
            logger.info("recovered %d stale deliveries", recovered)
            get_counter(
                "delivery_recovered_total",
                description="Stale deliveries recovered",
            ).add(recovered)
        return recovered

    # -- sweep loop ------------------------------------------------------

    async def sweep_once(self) -> dict[str, int]:
        """One full drain sweep across all orgs with pending work."""
        counters = {
            "delivered": 0,
            "failed": 0,
            "retried": 0,
            "cancelled": 0,
            "stale_requeued": 0,
            "retries_promoted": 0,
        }

        async with self._session_factory() as session:
            await self._set_statement_timeout(session)
            counters["stale_requeued"] = await self._recover_stale(session)
            counters["retries_promoted"] = await DeliveryRepository(session).requeue_due_retrying(
                limit=settings.DELIVERY_BATCH_SIZE
            )
            await session.commit()

        # Fair-drain across orgs
        async with self._session_factory() as session:
            await self._set_statement_timeout(session)
            deliveries_repo = DeliveryRepository(session)
            orgs = await deliveries_repo.get_queued_orgs(settings.DELIVERY_ORGS_PER_SWEEP)
            for org_id in orgs:
                try:
                    counters["delivered"] += await self._drain_org(org_id, session)
                except Exception:
                    logger.exception("drain failed for org %s", org_id)
                    await session.rollback()
            await session.commit()

        return counters

    async def run_loop(self) -> None:
        """Continuous polling loop (runs until cancelled)."""
        if not settings.DELIVERY_ENABLED:
            logger.info("DELIVERY_ENABLED=false; worker will not run")
            return

        logger.info("delivery worker starting (instance=%s)", INSTANCE_ID)
        counters: dict = {}
        while True:
            loop_start = datetime.now().astimezone()
            loop_ok = True
            last_error: str | None = None
            try:
                await self.heartbeat(loop_ok=True, last_error=None, counters={})
                with span("delivery_worker.sweep"):
                    counters = await self.sweep_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                loop_ok = False
                last_error = str(exc)
                logger.exception("delivery worker loop error")
            finally:
                await self.heartbeat(loop_ok=loop_ok, last_error=last_error, counters=counters)

            # Sleep until next poll
            elapsed = (datetime.now().astimezone() - loop_start).total_seconds()
            sleep_s = max(1, settings.DELIVERY_POLL_INTERVAL_SECONDS - elapsed)
            try:
                await asyncio.sleep(sleep_s)
            except asyncio.CancelledError:
                raise

    # Alias for CLI / single-sweep compatibility
    async def run_once(self) -> dict[str, int]:
        """Single sweep (used by tests / schedulers)."""
        return await self.sweep_once()


def _worker_entrypoint() -> None:
    """Entrypoint for ``python -m app.workers.delivery_worker``."""
    asyncio.run(DeliveryWorker().run_loop())


if __name__ == "__main__":
    _worker_entrypoint()
