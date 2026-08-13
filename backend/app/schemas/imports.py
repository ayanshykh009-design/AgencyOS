"""Import API schemas: import jobs and per-row errors."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ImportStatus


class ImportJobBase(BaseModel):
    """Fields a client can set on an import job."""

    model_config = ConfigDict(populate_by_name=True)

    file_name: str = Field(min_length=1, max_length=1024)
    file_size_bytes: int = Field(default=0, ge=0)
    total_rows: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(
        default_factory=dict, alias="metadata_", serialization_alias="metadata"
    )


class ImportJobCreate(ImportJobBase):
    """Payload to create an import job."""

    organization_id: UUID
    created_by_user_id: UUID
    lead_source_id: UUID | None = None


class ImportJobUpdate(BaseModel):
    """Partial update of an import job (all fields optional)."""

    model_config = ConfigDict(populate_by_name=True)

    status: ImportStatus | None = None
    processed_rows: int | None = Field(default=None, ge=0)
    failed_rows: int | None = Field(default=None, ge=0)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metadata: dict[str, Any] | None = Field(
        default=None, alias="metadata_", serialization_alias="metadata"
    )


class ImportJobRead(ImportJobBase):
    """Full import job returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    created_by_user_id: UUID
    lead_source_id: UUID | None = None
    status: ImportStatus
    processed_rows: int
    failed_rows: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ImportRowErrorCreate(BaseModel):
    """Payload to record a rejected row."""

    import_job_id: UUID
    organization_id: UUID
    row_number: int = Field(ge=1)
    error_code: str = Field(min_length=1)
    error_message: str = Field(min_length=1)
    raw_row: dict[str, Any] = Field(default_factory=dict)


class ImportRowErrorRead(BaseModel):
    """Full import row error returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    import_job_id: UUID
    organization_id: UUID
    row_number: int
    error_code: str
    error_message: str
    raw_row: dict[str, Any]
    created_at: datetime
