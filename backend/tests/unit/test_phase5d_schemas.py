"""Schema contract tests for the Phase 5D request payloads.

Locks the alias/dump contract that tripped up the M3 endpoints: a field
declared with ``alias="metadata_"`` and python name ``metadata`` dumps under
the key ``metadata`` (never ``metadata_``), while ``GrowthForecastCreate``'s
``model_config_`` field dumps under ``model_config_``. If this regresses, the
router-to-service keyword wiring breaks at runtime.
"""
from __future__ import annotations

from app.schemas.ai_memory import AiMemoryCreate, AiMemoryUpdate
from app.schemas.approval import ApprovalRequestCreate
from app.schemas.briefing import BriefingCreate
from app.schemas.business_insight import BusinessInsightUpdate
from app.schemas.growth import GrowthForecastCreate, GrowthMetricCreate
from app.schemas.knowledge_item import KnowledgeItemUpdate
from app.schemas.notification import NotificationCreate

ORG = "00000000-0000-0000-0000-000000000001"


def test_metadata_field_dumps_under_wire_name_not_alias() -> None:
    body = AiMemoryCreate(
        organization_id=ORG,
        memory_type="working",
        scope="conversation",
        content="remember this",
        metadata_={"source": "api"},
    )
    dumped = body.model_dump()
    assert "metadata" in dumped
    assert "metadata_" not in dumped
    assert dumped["metadata"] == {"source": "api"}


def test_metadata_update_field_dumps_under_wire_name() -> None:
    body = AiMemoryUpdate(metadata_={"a": 1})
    dumped = body.model_dump()
    assert "metadata" in dumped
    assert "metadata_" not in dumped


def test_forecast_model_config_dumps_under_field_name() -> None:
    body = GrowthForecastCreate(
        forecast_type="revenue",
        horizon_start="2026-01-01T00:00:00Z",
        horizon_end="2026-02-01T00:00:00Z",
        total_value="1000",
        model_config={"engine": "linear"},
    )
    dumped = body.model_dump()
    assert "model_config_" in dumped
    assert "model_config" not in dumped
    assert dumped["model_config_"] == {"engine": "linear"}


def test_notification_create_dumps_metadata_wire_name() -> None:
    body = NotificationCreate(
        organization_id=ORG,
        type="system",
        title="Hi",
        body="hello",
        metadata_={"k": 1},
    )
    dumped = body.model_dump(exclude={"organization_id"})
    assert "metadata" in dumped
    assert "metadata_" not in dumped


def test_knowledge_update_optional_metadata_can_be_none() -> None:
    body = KnowledgeItemUpdate()
    dumped = body.model_dump(exclude_unset=True)
    assert dumped == {}


def test_business_insight_update_empty_dump() -> None:
    body = BusinessInsightUpdate()
    assert body.model_dump(exclude_unset=True) == {}


def test_approval_request_create_has_no_metadata_field() -> None:
    body = ApprovalRequestCreate(organization_id=ORG, title="Ship")
    assert "metadata" not in body.model_dump()


def test_briefing_and_metric_create_dump_contract() -> None:
    briefing = BriefingCreate(
        organization_id=ORG,
        briefing_type="daily",
        title="Daily",
        summary="summary text",
        metadata_={"a": 1},
    )
    bdumped = briefing.model_dump(exclude={"organization_id"})
    assert bdumped["metadata"] == {"a": 1}

    metric = GrowthMetricCreate(
        organization_id=ORG,
        metric_type="revenue",
        period_start="2026-01-01T00:00:00Z",
        period_end="2026-02-01T00:00:00Z",
        value="10",
        metadata_={"b": 2},
    )
    mdumped = metric.model_dump(exclude={"organization_id"})
    assert mdumped["metadata"] == {"b": 2}
