"""Unit tests: automation kill switch gates and pause/resume audit trail."""
from __future__ import annotations

import uuid

import pytest

from app.core.errors import AppError
from app.core.metrics import read_counter, reset
from app.models.activity_log import ActivityLog
from app.models.enums import ActivityEventType
from app.models.system_setting import SystemSetting
from app.services.automation_control_service import (
    KEY_ENABLED,
    KEY_PAUSED_AT,
    KEY_PAUSED_BY,
    KEY_PAUSED_REASON,
    AutomationControlService,
)

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000201")


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    reset()


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1


class FakeSettingsRepo:
    def __init__(self) -> None:
        self._settings: dict[str, SystemSetting] = {}

    async def get(self, key: str) -> SystemSetting | None:
        return self._settings.get(key)

    async def set_value(
        self,
        key: str,
        value: dict,
        *,
        updated_by_user_id: uuid.UUID | None = None,
    ) -> SystemSetting:
        setting = self._settings.get(key)
        if setting is None:
            setting = SystemSetting(key=key, value=value)
            self._settings[key] = setting
        else:
            setting.value = value
        return setting

    async def delete(self, key: str) -> bool:
        return self._settings.pop(key, None) is not None


def _service(paused: bool = False, reason: str | None = None) -> AutomationControlService:
    session = FakeSession()
    service = AutomationControlService(session)  # type: ignore[arg-type]
    repo = FakeSettingsRepo()
    if paused:
        repo._settings[KEY_ENABLED] = SystemSetting(key=KEY_ENABLED, value={"enabled": False})
        if reason:
            repo._settings[KEY_PAUSED_REASON] = SystemSetting(
                key=KEY_PAUSED_REASON, value={"reason": reason}
            )
    service._repo = repo  # type: ignore[assignment]
    service._session = session  # type: ignore[assignment]
    return service


async def test_is_enabled_defaults_to_true_when_setting_missing() -> None:
    service = _service()

    assert await service.is_enabled() is True


async def test_is_enabled_false_when_paused() -> None:
    service = _service(paused=True)

    assert await service.is_enabled() is False


async def test_gates_return_when_enabled() -> None:
    service = _service()
    await service.block_execution_if_paused()
    await service.block_queue_if_paused()
    await service.block_schedule_if_paused()
    await service.gate_execution_phases()


@pytest.mark.parametrize(
    ("gate", "expected_code"),
    [
        ("block_execution_if_paused", "automation.paused"),
        ("block_queue_if_paused", "automation.paused.queue_blocked"),
        ("block_schedule_if_paused", "automation.paused.schedule_blocked"),
        ("gate_execution_phases", "automation.paused.global"),
    ],
)
async def test_gates_raise_409_when_paused(gate: str, expected_code: str) -> None:
    service = _service(paused=True)

    with pytest.raises(AppError) as exc_info:
        await getattr(service, gate)()

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == expected_code


async def test_gate_message_includes_pause_reason() -> None:
    service = _service(paused=True, reason="Maintenance window")

    with pytest.raises(AppError) as exc_info:
        await service.block_queue_if_paused()

    assert "Maintenance window" in exc_info.value.message


async def test_gate_message_without_reason() -> None:
    service = _service(paused=True)

    with pytest.raises(AppError) as exc_info:
        await service.block_queue_if_paused()

    assert "Reason:" not in exc_info.value.message


async def test_pause_disables_automation_and_audits() -> None:
    service = _service()
    await service.pause(USER_ID, "Deploy freeze", organization_id=ORG_ID)

    repo = service._repo
    assert repo._settings[KEY_ENABLED].value["enabled"] is False
    assert repo._settings[KEY_PAUSED_BY].value["user_id"] == str(USER_ID)
    assert repo._settings[KEY_PAUSED_AT].value["timestamp"] is not None
    assert repo._settings[KEY_PAUSED_REASON].value["reason"] == "Deploy freeze"

    logs = service._session.added
    assert len(logs) == 1
    entry = logs[0]
    assert isinstance(entry, ActivityLog)
    assert entry.event_type == ActivityEventType.AUTOMATION_PAUSED
    assert entry.organization_id == ORG_ID
    assert entry.user_id == USER_ID
    assert entry.metadata_ == {"before": True, "after": False, "reason": "Deploy freeze"}
    assert read_counter("automation_paused_total") == 1
    assert service._session.commits == 2


async def test_pause_when_already_paused_raises_409() -> None:
    service = _service(paused=True)

    with pytest.raises(AppError) as exc_info:
        await service.pause(USER_ID, "again", organization_id=ORG_ID)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "automation.already_paused"


async def test_resume_re_enables_automation_and_audits() -> None:
    service = _service(paused=True, reason="Maintenance")
    await service.resume(USER_ID, organization_id=ORG_ID)

    repo = service._repo
    assert repo._settings[KEY_ENABLED].value["enabled"] is True
    assert KEY_PAUSED_BY not in repo._settings
    assert KEY_PAUSED_AT not in repo._settings
    assert KEY_PAUSED_REASON not in repo._settings

    logs = service._session.added
    assert len(logs) == 1
    entry = logs[0]
    assert entry.event_type == ActivityEventType.AUTOMATION_RESUMED
    assert entry.metadata_ == {"before": False, "after": True}
    assert read_counter("automation_resumed_total") == 1
    assert service._session.commits == 2


async def test_resume_when_already_resumed_raises_409() -> None:
    service = _service()
    service._repo._settings[KEY_ENABLED] = SystemSetting(
        key=KEY_ENABLED, value={"enabled": True}
    )

    with pytest.raises(AppError) as exc_info:
        await service.resume(USER_ID, organization_id=ORG_ID)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "automation.already_resumed"


async def test_get_status_reports_pause_metadata() -> None:
    from datetime import UTC, datetime

    service = _service(paused=True, reason="Maintenance window")
    service._repo._settings[KEY_PAUSED_BY] = SystemSetting(
        key=KEY_PAUSED_BY, value={"user_id": str(USER_ID)}
    )
    service._repo._settings[KEY_PAUSED_AT] = SystemSetting(
        key=KEY_PAUSED_AT, value={"timestamp": "2026-08-05T00:00:00+00:00"}
    )

    status = await service.get_status()

    assert status.enabled is False
    assert status.paused_by == str(USER_ID)
    assert status.paused_reason == "Maintenance window"
    assert status.paused_at == datetime(2026, 8, 5, tzinfo=UTC)
    assert read_counter("automation_status_reads") == 1
