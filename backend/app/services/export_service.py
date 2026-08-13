"""Export service: serializes org-scoped lead data to CSV or JSON."""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.repositories.lead import LeadRepository

_MAX_EXPORT_ROWS = 5000

CSV_COLUMNS = [
    "id",
    "status",
    "score",
    "first_name",
    "last_name",
    "company",
    "position",
    "location",
    "linkedin_url",
    "email",
    "phone",
    "whatsapp",
    "website",
    "notes",
    "deal_value",
    "stage_id",
    "close_reason_id",
    "won_at",
    "lost_at",
    "lead_source_id",
    "owner_user_id",
    "created_at",
    "updated_at",
]


def _scalar(value: Any) -> Any:
    """Normalize ORM attribute values for plain serialization."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _to_row(lead: Lead) -> dict[str, Any]:
    return {column: _scalar(getattr(lead, column)) for column in CSV_COLUMNS}


def _to_csv(rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


class ExportService:
    """Read-only lead export for a single organization."""

    def __init__(self, session: AsyncSession) -> None:
        self._leads = LeadRepository(session)

    async def export_leads(
        self,
        organization_id: uuid.UUID,
        *,
        fmt: str,
        query: str | None = None,
        status: Any = None,
        source_id: uuid.UUID | None = None,
        owner_user_id: uuid.UUID | None = None,
        min_score: int | None = None,
        max_score: int | None = None,
    ) -> str:
        """Return the matching leads serialized as ``fmt`` (csv or json)."""
        leads = await self._leads.search(
            organization_id,
            query=query,
            status=status,
            source_id=source_id,
            owner_user_id=owner_user_id,
            min_score=min_score,
            max_score=max_score,
            sort="created_at",
            order="desc",
            limit=_MAX_EXPORT_ROWS,
            offset=0,
        )
        rows = [_to_row(lead) for lead in leads]
        if fmt == "json":
            payload = {"count": len(rows), "leads": rows}
            return json.dumps(payload, ensure_ascii=False)
        return _to_csv(rows)
