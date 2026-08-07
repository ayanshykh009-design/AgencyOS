"""Permission-matrix unit tests.

Verifies the RBAC grants in ``app/core/permissions.py`` so the backend
source of truth stays consistent with the frontend mirror
(``frontend/src/lib/permissions.ts``).
"""
from __future__ import annotations

from app.core.permissions import (
    PERMISSION_MATRIX,
    Permission,
    has_permission,
    role_can_manage,
)
from app.models.enums import UserRole

ALL_ROLES = list(UserRole)
MANAGE_ROLES = [UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER]


def test_ai_manage_is_manager_level() -> None:
    for role in MANAGE_ROLES:
        assert has_permission(role, Permission.AI_MANAGE)
    for role in [UserRole.MEMBER, UserRole.SALES_AGENT, UserRole.VIEWER]:
        assert not has_permission(role, Permission.AI_MANAGE)


def test_pipeline_manage_is_admin_only() -> None:
    for role in [UserRole.OWNER, UserRole.ADMIN]:
        assert has_permission(role, Permission.PIPELINE_MANAGE)
    for role in [UserRole.MANAGER, UserRole.MEMBER, UserRole.SALES_AGENT, UserRole.VIEWER]:
        assert not has_permission(role, Permission.PIPELINE_MANAGE)


def test_every_permission_grants_at_least_owner() -> None:
    for permission in Permission:
        assert has_permission(UserRole.OWNER, permission)


def test_lead_read_grants_every_role() -> None:
    for role in ALL_ROLES:
        assert has_permission(role, Permission.LEAD_READ)


def test_owner_can_manage_any_target() -> None:
    for target in ALL_ROLES:
        assert role_can_manage(UserRole.OWNER, target)


def test_manager_cannot_manage_admin_or_owner() -> None:
    assert not role_can_manage(UserRole.MANAGER, UserRole.ADMIN)
    assert not role_can_manage(UserRole.MANAGER, UserRole.OWNER)
    assert not role_can_manage(UserRole.MANAGER, UserRole.MANAGER)


def test_matrix_covers_every_permission() -> None:
    for permission in Permission:
        assert permission in PERMISSION_MATRIX
        assert PERMISSION_MATRIX[permission]


def test_automation_read_grants_every_role() -> None:
    for role in ALL_ROLES:
        assert has_permission(role, Permission.AUTOMATION_READ)


def test_automation_write_excludes_viewers() -> None:
    for role in [
        UserRole.OWNER,
        UserRole.ADMIN,
        UserRole.MANAGER,
        UserRole.MEMBER,
        UserRole.SALES_AGENT,
    ]:
        assert has_permission(role, Permission.AUTOMATION_WRITE)
    assert not has_permission(UserRole.VIEWER, Permission.AUTOMATION_WRITE)


def test_automation_manage_is_admin_only() -> None:
    for role in [UserRole.OWNER, UserRole.ADMIN]:
        assert has_permission(role, Permission.AUTOMATION_MANAGE)
    for role in [UserRole.MANAGER, UserRole.MEMBER, UserRole.SALES_AGENT, UserRole.VIEWER]:
        assert not has_permission(role, Permission.AUTOMATION_MANAGE)


def test_credential_read_grants_every_role() -> None:
    for role in ALL_ROLES:
        assert has_permission(role, Permission.CREDENTIAL_READ)


def test_credential_delete_is_admin_only() -> None:
    for role in [UserRole.OWNER, UserRole.ADMIN]:
        assert has_permission(role, Permission.CREDENTIAL_DELETE)
    for role in [UserRole.MANAGER, UserRole.MEMBER, UserRole.SALES_AGENT, UserRole.VIEWER]:
        assert not has_permission(role, Permission.CREDENTIAL_DELETE)


def test_phase5d_read_permissions_grant_every_role() -> None:
    for permission in [
        Permission.MEMORY_READ,
        Permission.APPROVAL_READ,
        Permission.NOTIFICATION_READ,
        Permission.AGENT_READ,
    ]:
        for role in ALL_ROLES:
            assert has_permission(role, permission)


def test_phase5d_notification_write_excludes_viewers() -> None:
    for role in [
        UserRole.OWNER,
        UserRole.ADMIN,
        UserRole.MANAGER,
        UserRole.MEMBER,
        UserRole.SALES_AGENT,
    ]:
        assert has_permission(role, Permission.NOTIFICATION_WRITE)
    assert not has_permission(UserRole.VIEWER, Permission.NOTIFICATION_WRITE)


def test_phase5d_manage_permissions_require_manager() -> None:
    for permission in [
        Permission.MEMORY_WRITE,
        Permission.APPROVAL_MANAGE,
        Permission.GROWTH_READ,
    ]:
        for role in MANAGE_ROLES:
            assert has_permission(role, permission)
        for role in [UserRole.MEMBER, UserRole.SALES_AGENT, UserRole.VIEWER]:
            assert not has_permission(role, permission)


def test_phase5d_manage_permissions_are_admin_only() -> None:
    for permission in [Permission.GROWTH_MANAGE, Permission.AGENT_MANAGE]:
        for role in [UserRole.OWNER, UserRole.ADMIN]:
            assert has_permission(role, permission)
        for role in [UserRole.MANAGER, UserRole.MEMBER, UserRole.SALES_AGENT, UserRole.VIEWER]:
            assert not has_permission(role, permission)
