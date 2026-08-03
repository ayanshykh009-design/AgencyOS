"""Service-layer unit tests: lead CSV/JSON export serialization."""
from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.models.enums import LeadStatus
from app.models.lead import Lead
from app.services.export_service import ExportService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.committed = False

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        pass


def _service() -> ExportService:
    """Build an export service whose lead repo is stubbed out."""
    service = ExportService(FakeSession())
    service._leads = MagicMock()
    return service


def _lead(**overrides: object) -> Lead:
    lead = Lead(
        organization_id=ORG_ID,
        email="Prospect@Example.com",
        first_name="Ada",
        last_name="Lovelace",
        status=LeadStatus.NEW,
        score=42,
        deal_value=Decimal("1250.50"),
    )
    lead.id = uuid.uuid4()
    lead.created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    lead.updated_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    for key, value in overrides.items():
        setattr(lead, key, value)
    return lead


def _wire_leads(service: ExportService, leads: list[Lead]) -> None:
    service._leads.search = AsyncMock(return_value=leads)


async def test_export_json_serializes_rows_and_count() -> None:
    service = _service()
    lead = _lead()
    _wire_leads(service, [lead])

    payload = await service.export_leads(ORG_ID, fmt="json")

    data = json.loads(payload)
    assert data["count"] == 1
    row = data["leads"][0]
    assert row["email"] == "Prospect@Example.com"
    assert row["status"] == "new"
    assert row["score"] == 42
    assert row["deal_value"] == 1250.5
    assert row["id"] == str(lead.id)
    assert row["created_at"] == "2026-01-02T03:04:05+00:00"


async def test_export_csv_has_header_and_rows() -> None:
    service = _service()
    _wire_leads(service, [_lead(), _lead(first_name="Grace", last_name="Hopper")])

    payload = await service.export_leads(ORG_ID, fmt="csv")

    rows = list(csv.DictReader(io.StringIO(payload)))
    assert len(rows) == 2
    assert set(rows[0].keys()) >= {
        "id", "first_name", "email", "status", "score", "deal_value",
    }
    assert rows[0]["first_name"] == "Ada"
    assert rows[0]["status"] == "new"
    assert rows[1]["first_name"] == "Grace"


async def test_export_passes_filters_to_repository() -> None:
    service = _service()
    _wire_leads(service, [])
    status = LeadStatus.WON

    await service.export_leads(
        ORG_ID,
        fmt="csv",
        query="acme",
        status=status,
        source_id=uuid.UUID("00000000-0000-0000-0000-000000000099"),
        owner_user_id=uuid.UUID("00000000-0000-0000-0000-000000000098"),
        min_score=10,
        max_score=90,
    )

    service._leads.search.assert_awaited_once_with(
        ORG_ID,
        query="acme",
        status=status,
        source_id=uuid.UUID("00000000-0000-0000-0000-000000000099"),
        owner_user_id=uuid.UUID("00000000-0000-0000-0000-000000000098"),
        min_score=10,
        max_score=90,
        sort="created_at",
        order="desc",
        limit=5000,
        offset=0,
    )


async def test_export_empty_result() -> None:
    service = _service()
    _wire_leads(service, [])

    csv_payload = await service.export_leads(ORG_ID, fmt="csv")
    json_payload = await service.export_leads(ORG_ID, fmt="json")

    assert csv_payload.startswith("id,")
    assert json.loads(json_payload) == {"count": 0, "leads": []}
