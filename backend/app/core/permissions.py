"""Role hierarchy and permission matrix for RBAC.

``UserRole`` defines the role set; this module owns the *meaning* of each
role: a total ordering (for role-change sanity checks) and a closed set of
named permissions. Every new endpoint that needs authorization picks one of
the permission names here via :func:`require_permission` — never hand-rolled
role checks inside route handlers.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from enum import StrEnum
from typing import Any

from fastapi import HTTPException

from app.api.deps import CurrentUser
from app.models.enums import UserRole

# Total order: lower numbers are strictly more privileged. Keeps "can a
# manager act on an admin?" style checks as a simple integer comparison.
ROLE_LEVELS: dict[UserRole, int] = {
    UserRole.VIEWER: 0,
    UserRole.MEMBER: 1,
    UserRole.SALES_AGENT: 1,
    UserRole.MANAGER: 2,
    UserRole.ADMIN: 3,
    UserRole.OWNER: 4,
}

# All users can read leads; a small subset may mutate them.
_READ = {
    UserRole.OWNER,
    UserRole.ADMIN,
    UserRole.MANAGER,
    UserRole.MEMBER,
    UserRole.SALES_AGENT,
    UserRole.VIEWER,
}
_WRITE = {
    UserRole.OWNER,
    UserRole.ADMIN,
    UserRole.MANAGER,
    UserRole.MEMBER,
    UserRole.SALES_AGENT,
}
_MANAGE = {UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER}
_ADMIN_ONLY = {UserRole.OWNER, UserRole.ADMIN}


class Permission(StrEnum):
    """Named capabilities a role may hold (see ``PERMISSION_MATRIX``)."""

    LEAD_READ = "lead_read"
    LEAD_WRITE = "lead_write"
    LEAD_DELETE = "lead_delete"
    LEAD_ASSIGN = "lead_assign"
    PIPELINE_MANAGE = "pipeline_manage"
    AI_MANAGE = "ai_manage"
    TASK_READ = "task_read"
    TASK_WRITE = "task_write"
    TASK_MANAGE = "task_manage"
    NOTE_READ = "note_read"
    NOTE_WRITE = "note_write"
    SEARCH = "search"
    EXPORT = "export"
    ANALYTICS_READ = "analytics_read"
    TEAM_MANAGE = "team_manage"
    INVITE_MANAGE = "invite_manage"
    AUDIT_READ = "audit_read"
    WORKFLOW_READ = "workflow_read"
    WORKFLOW_WRITE = "workflow_write"
    WORKFLOW_MANAGE = "workflow_manage"
    EXECUTION_READ = "execution_read"
    EXECUTION_WRITE = "execution_write"
    EXECUTION_MANAGE = "execution_manage"
    AUTOMATION_READ = "automation_read"
    AUTOMATION_WRITE = "automation_write"
    AUTOMATION_MANAGE = "automation_manage"
    AUTOMATION_CONTROL = "automation_control"
    CREDENTIAL_MANAGE = "credential_manage"
    CREDENTIAL_READ = "credential_read"
    CREDENTIAL_WRITE = "credential_write"
    CREDENTIAL_DELETE = "credential_delete"
    # Phase 5D AI Intelligence Layer
    MEMORY_READ = "memory_read"
    MEMORY_WRITE = "memory_write"
    APPROVAL_READ = "approval_read"
    APPROVAL_MANAGE = "approval_manage"
    NOTIFICATION_READ = "notification_read"
    NOTIFICATION_WRITE = "notification_write"
    GROWTH_READ = "growth_read"
    GROWTH_MANAGE = "growth_manage"
    AGENT_READ = "agent_read"
    AGENT_MANAGE = "agent_manage"
    # M6 Founder Communication & Delivery Layer
    DELIVERY_READ = "delivery_read"
    DELIVERY_WRITE = "delivery_write"
    DELIVERY_MANAGE = "delivery_manage"


PERMISSION_MATRIX: dict[Permission, set[UserRole]] = {
    Permission.LEAD_READ: _READ,
    Permission.LEAD_WRITE: _WRITE,
    Permission.LEAD_DELETE: _MANAGE,
    Permission.LEAD_ASSIGN: _MANAGE,
    Permission.PIPELINE_MANAGE: _ADMIN_ONLY,
    Permission.AI_MANAGE: _MANAGE,
    Permission.TASK_READ: _READ,
    Permission.TASK_WRITE: _WRITE,
    Permission.TASK_MANAGE: _MANAGE,
    Permission.NOTE_READ: _READ,
    Permission.NOTE_WRITE: _WRITE,
    Permission.SEARCH: _READ,
    Permission.EXPORT: _MANAGE,
    Permission.ANALYTICS_READ: _MANAGE,
    Permission.TEAM_MANAGE: _ADMIN_ONLY,
    Permission.INVITE_MANAGE: _ADMIN_ONLY,
    Permission.AUDIT_READ: _ADMIN_ONLY,
    Permission.WORKFLOW_READ: _READ,
    Permission.WORKFLOW_WRITE: _WRITE,
    Permission.WORKFLOW_MANAGE: _MANAGE,
    Permission.EXECUTION_READ: _READ,
    Permission.EXECUTION_WRITE: _WRITE,
    Permission.EXECUTION_MANAGE: _ADMIN_ONLY,
    Permission.AUTOMATION_READ: _READ,
    Permission.AUTOMATION_WRITE: _WRITE,
    Permission.AUTOMATION_MANAGE: _ADMIN_ONLY,
    Permission.AUTOMATION_CONTROL: _ADMIN_ONLY,
    Permission.CREDENTIAL_MANAGE: _ADMIN_ONLY,
    Permission.CREDENTIAL_READ: _READ,
    Permission.CREDENTIAL_WRITE: _WRITE,
    Permission.CREDENTIAL_DELETE: _ADMIN_ONLY,
    # Phase 5D AI Intelligence Layer
    Permission.MEMORY_READ: _READ,
    Permission.MEMORY_WRITE: _MANAGE,
    Permission.APPROVAL_READ: _READ,
    Permission.APPROVAL_MANAGE: _MANAGE,
    Permission.NOTIFICATION_READ: _READ,
    Permission.NOTIFICATION_WRITE: _WRITE,
    Permission.GROWTH_READ: _MANAGE,
    Permission.GROWTH_MANAGE: _ADMIN_ONLY,
    Permission.AGENT_READ: _READ,
    Permission.AGENT_MANAGE: _ADMIN_ONLY,
    # M6 Founder Communication & Delivery Layer
    Permission.DELIVERY_READ: _READ,
    Permission.DELIVERY_WRITE: _WRITE,
    Permission.DELIVERY_MANAGE: _ADMIN_ONLY,
}


def has_permission(role: UserRole, permission: Permission) -> bool:
    """Return whether ``role`` is granted ``permission``."""
    return role in PERMISSION_MATRIX[permission]


def role_can_manage(actor: UserRole, target: UserRole) -> bool:
    """Return whether ``actor`` may change the role/status of ``target``.

    An OWNER may manage anyone (including another owner, gated separately by
    the last-owner safety check). Any other role may only manage strictly
    less-privileged peers; equal-or-higher targets are off-limits.
    """
    if actor is UserRole.OWNER:
        return True
    return ROLE_LEVELS[actor] > ROLE_LEVELS[target]


def role_can_invite(actor: UserRole, role: UserRole) -> bool:
    """Return whether ``actor`` may invite a new member with ``role``.

    Invites never create owners (ownership cannot be transferred through an
    unverified link), and the invited role must be manageable by ``actor``.
    """
    return role is not UserRole.OWNER and role_can_manage(actor, role)


def require_permission(
    *permissions: Permission,
) -> Callable[[CurrentUser], Coroutine[Any, Any, CurrentUser]]:
    """Return a dependency that requires at least one of ``permissions``."""

    async def _require(current_user: CurrentUser) -> CurrentUser:
        if not any(has_permission(current_user.role, p) for p in permissions):
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions for this operation",
            )
        return current_user

    return _require
