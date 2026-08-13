"""Automation control: global pause/resume kill switch.

Single source of truth: ``system_settings`` table stores ``automation.enabled`` and
pause metadata (``paused_by``, ``paused_at``, ``paused_reason``). Checked once per
loop iteration so a crash or rollout can only freeze for up to
``EXECUTION_POLL_INTERVAL_SECONDS`` (default 60s).

Implements the Operator Controls layer defined in ``docs/phase5c-plan.md``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.metrics import get_counter
from app.models.activity_log import ActivityLog
from app.models.enums import ActivityEventType
from app.repositories.activity_log import ActivityLogRepository
from app.repositories.system_settings import SystemSettingRepository
from app.schemas.system_settings import SystemSettingStatusResponse
from app.services.base import commit_with_retry

# Metrics for automation control
for _name, _desc, _unit in [
    ("automation_paused_total", "Automation pause requests", "1"),
    ("automation_resumed_total", "Automation resume requests", "1"),
    ("automation_status_reads", "Automation status queries", "1"),
]:
    get_counter(_name, _desc, _unit)

KEY_ENABLED = "automation.enabled"
KEY_PAUSED_BY = "paused_by"
KEY_PAUSED_AT = "paused_at"
KEY_PAUSED_REASON = "paused_reason"


def _now_utc() -> datetime:
    return datetime.now(UTC)


class AutomationControlService:
    """Manage the global automation kill switch and audit state changes."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = SystemSettingRepository(session)
        self._logs = ActivityLogRepository(session)

    async def get_status(self) -> SystemSettingStatusResponse:
        """Return current automation enabled status and pause metadata."""
        get_counter("automation_status_reads").add()

        enabled_setting = await self._repo.get(KEY_ENABLED) or await self._repo.set_value(
            KEY_ENABLED, {"enabled": True}, updated_by_user_id=None
        )
        enabled = bool(enabled_setting.value.get("enabled", True))

        paused_by = None
        paused_at = None
        paused_reason = None

        paused_by_setting = await self._repo.get(KEY_PAUSED_BY)
        if paused_by_setting:
            paused_by = paused_by_setting.value.get("user_id")

        paused_at_setting = await self._repo.get(KEY_PAUSED_AT)
        if paused_at_setting:
            paused_at = paused_at_setting.value.get("timestamp")

        paused_reason_setting = await self._repo.get(KEY_PAUSED_REASON)
        if paused_reason_setting:
            paused_reason = paused_reason_setting.value.get("reason")

        return SystemSettingStatusResponse(
            enabled=enabled,
            paused_by=paused_by,
            paused_at=paused_at,
            paused_reason=paused_reason,
        )

    async def pause(
        self,
        user_id: uuid.UUID,
        reason: str,
        *,
        organization_id: uuid.UUID,
    ) -> SystemSettingStatusResponse:
        """Pause automation and record an audit log entry."""
        get_counter("automation_paused_total").add()

        enabled_setting = await self._repo.get(KEY_ENABLED) or await self._repo.set_value(
            KEY_ENABLED, {"enabled": True}, updated_by_user_id=user_id
        )
        if not enabled_setting.value.get("enabled", True):
            raise AppError(
                code="automation.already_paused",
                message="Automation is already paused",
                status_code=409,
            )

        await self._repo.set_value(KEY_ENABLED, {"enabled": False}, updated_by_user_id=user_id)
        await self._repo.set_value(
            KEY_PAUSED_BY,
            {"user_id": str(user_id)},
            updated_by_user_id=user_id,
        )
        await self._repo.set_value(
            KEY_PAUSED_AT,
            {"timestamp": _now_utc().isoformat()},
            updated_by_user_id=user_id,
        )
        await self._repo.set_value(
            KEY_PAUSED_REASON,
            {"reason": reason},
            updated_by_user_id=user_id,
        )

        await commit_with_retry(self._session)

        self._logs.add(
            ActivityLog(
                organization_id=organization_id,
                user_id=user_id,
                event_type=ActivityEventType.AUTOMATION_PAUSED,
                entity_type="system_settings",
                entity_id=None,
                description=reason or "Automation paused by operator",
                metadata_={
                    "before": True,
                    "after": False,
                    "reason": reason,
                },
            )
        )
        await commit_with_retry(self._session)

        return await self.get_status()

    async def resume(
        self,
        user_id: uuid.UUID,
        *,
        organization_id: uuid.UUID,
    ) -> SystemSettingStatusResponse:
        """Resume automation and record an audit log entry."""
        get_counter("automation_resumed_total").add()

        enabled_setting = await self._repo.get(KEY_ENABLED) or await self._repo.set_value(
            KEY_ENABLED, {"enabled": False}, updated_by_user_id=user_id
        )
        if enabled_setting.value.get("enabled", False):
            raise AppError(
                code="automation.already_resumed",
                message="Automation is already resumed",
                status_code=409,
            )

        await self._repo.set_value(KEY_ENABLED, {"enabled": True}, updated_by_user_id=user_id)
        await self._repo.delete(KEY_PAUSED_BY)
        await self._repo.delete(KEY_PAUSED_AT)
        await self._repo.delete(KEY_PAUSED_REASON)

        await commit_with_retry(self._session)

        self._logs.add(
            ActivityLog(
                organization_id=organization_id,
                user_id=user_id,
                event_type=ActivityEventType.AUTOMATION_RESUMED,
                entity_type="system_settings",
                entity_id=None,
                description="Automation resumed by operator",
                metadata_={
                    "before": False,
                    "after": True,
                },
            )
        )
        await commit_with_retry(self._session)

        return await self.get_status()

    async def is_enabled(self) -> bool:
        """Return whether automation is currently enabled."""
        setting = await self._repo.get(KEY_ENABLED)
        if setting is None:
            return True
        return bool(setting.value.get("enabled", True))

    async def _paused_reason(self) -> str | None:
        """Return the stored pause reason, if any."""
        setting = await self._repo.get(KEY_PAUSED_REASON)
        if setting is None:
            return None
        reason = setting.value.get("reason")
        return str(reason) if reason else None

    @staticmethod
    def _with_reason(message: str, reason: str | None) -> str:
        return f"{message} Reason: {reason}" if reason else message

    async def block_execution_if_paused(self) -> None:
        """Check if automation is paused and block if necessary."""
        if await self.is_enabled():
            return
        raise AppError(
            code="automation.paused",
            message=self._with_reason(
                "Automation is currently paused. Operations are blocked until resumed.",
                await self._paused_reason(),
            ),
            status_code=409,
        )

    async def block_queue_if_paused(self) -> None:
        """Check if automation is paused and block queue operations if necessary."""
        if await self.is_enabled():
            return
        raise AppError(
            code="automation.paused.queue_blocked",
            message=self._with_reason(
                "Automation is currently paused. New executions cannot be queued.",
                await self._paused_reason(),
            ),
            status_code=409,
        )

    async def block_schedule_if_paused(self) -> None:
        """Check if automation is paused and block schedule dispatch if necessary."""
        if await self.is_enabled():
            return
        raise AppError(
            code="automation.paused.schedule_blocked",
            message=self._with_reason(
                "Automation is currently paused. Schedule dispatch is disabled.",
                await self._paused_reason(),
            ),
            status_code=409,
        )

    async def gate_execution_phases(self) -> None:
        """Gate all automation phases if paused."""
        if await self.is_enabled():
            return
        raise AppError(
            code="automation.paused.global",
            message=self._with_reason(
                "Automation is currently paused globally. All execution phases are blocked.",
                await self._paused_reason(),
            ),
            status_code=409,
        )
