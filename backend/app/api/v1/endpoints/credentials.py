"""Credential endpoints: CRUD (masked values only in responses)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.models.enums import CredentialType
from app.schemas.credential import (
    CredentialCreate,
    CredentialListResponse,
    CredentialRead,
    CredentialUpdate,
)
from app.services.credential_service import CredentialService

if TYPE_CHECKING:
    pass

router = APIRouter()

_read = Depends(require_permission(Permission.CREDENTIAL_MANAGE))
_write = Depends(require_permission(Permission.CREDENTIAL_MANAGE))


@router.get(
    "",
    response_model=CredentialListResponse,
    summary="List credentials (masked values only)",
    dependencies=[_read],
)
async def list_credentials(
    db: DbSession,
    current_user: CurrentUser,
    credential_type: CredentialType | None = None,
    sort: str = Query(default="created_at", pattern="^(created_at|name|credential_type)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> CredentialListResponse:
    service = CredentialService(db)
    credentials = await service.list_credentials(
        current_user.organization_id,
        credential_type=credential_type,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    total = await service.count_credentials(
        current_user.organization_id,
        credential_type=credential_type,
    )
    return CredentialListResponse(
        items=[CredentialRead.model_validate(c) for c in credentials],
        total=total,
    )


@router.post(
    "",
    response_model=CredentialRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a credential (encrypted value + masked preview)",
    dependencies=[_write],
)
async def create_credential(
    body: CredentialCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> CredentialRead:
    service = CredentialService(db)
    credential = await service.create(
        body.model_copy(update={"organization_id": current_user.organization_id}),
        created_by_user_id=current_user.id,
    )
    return CredentialRead.model_validate(credential)


@router.get(
    "/{credential_id}",
    response_model=CredentialRead,
    summary="Get a credential (masked value only)",
    dependencies=[_read],
)
async def get_credential(
    credential_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> CredentialRead:
    service = CredentialService(db)
    credential = await service.get_or_404(current_user.organization_id, credential_id)
    return CredentialRead.model_validate(credential)


@router.patch(
    "/{credential_id}",
    response_model=CredentialRead,
    summary="Update credential metadata (secret is never replaced)",
    dependencies=[_write],
)
async def update_credential(
    credential_id: uuid.UUID,
    body: CredentialUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> CredentialRead:
    service = CredentialService(db)
    credential = await service.update(
        current_user.organization_id,
        credential_id,
        body,
    )
    return CredentialRead.model_validate(credential)


@router.delete(
    "/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a credential",
    dependencies=[_write],
)
async def delete_credential(
    credential_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
):
    service = CredentialService(db)
    await service.delete(current_user.organization_id, credential_id)


@router.post(
    "/{credential_id}/rotate",
    response_model=CredentialRead,
    summary="Rotate a credential (re-encrypt with the current key version)",
    dependencies=[_write],
)
async def rotate_credential(
    credential_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> CredentialRead:
    service = CredentialService(db)
    credential = await service.rotate(current_user.organization_id, credential_id)
    return CredentialRead.model_validate(credential)
