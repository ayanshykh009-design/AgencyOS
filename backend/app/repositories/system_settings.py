"""SystemSetting repository (operator key/value settings)."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_setting import SystemSetting

if TYPE_CHECKING:
    pass


class SystemSettingRepository:
    """Data access for operator settings (instance-global)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str) -> SystemSetting | None:
        stmt = select(SystemSetting).where(SystemSetting.key == key)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_404(self, key: str) -> SystemSetting:
        from app.core.errors import AppError

        setting = await self.get(key)
        if setting is None:
            raise AppError(
                code="system_setting.not_found",
                message="System setting not found",
                status_code=404,
            )
        return setting

    def add(self, setting: SystemSetting) -> None:
        self._session.add(setting)

    async def delete(self, key: str) -> bool:
        setting = await self.get(key)
        if setting is None:
            return False
        await self._session.delete(setting)
        return True

    async def set_value(
        self,
        key: str,
        value: dict,
        *,
        updated_by_user_id: uuid.UUID | None,
    ) -> SystemSetting:
        """Upsert a setting by key; returns the (persisted-on-commit) instance."""
        setting = await self.get(key)
        if setting is None:
            setting = SystemSetting(
                key=key,
                value=value,
                updated_by_user_id=updated_by_user_id,
            )
            self._session.add(setting)
        else:
            setting.value = value
            setting.updated_by_user_id = updated_by_user_id
        return setting
