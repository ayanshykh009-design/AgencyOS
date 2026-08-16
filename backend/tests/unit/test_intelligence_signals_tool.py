"""M11-D: read-only intelligence_signals tool (authorization, bounds, shape)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.permissions import Permission
from app.models.enums import (
    IntelligenceConfidence,
    IntelligenceSignalSeverity,
    IntelligenceSignalStatus,
    SignalCategory,
    SignalSourceType,
)
from app.tools.base import ToolResult
from app.tools.intelligence_signals_tool import IntelligenceSignalsTool
from app.tools.registry import ToolAuthorizationError, assert_can_invoke_tool


def _fake_signal() -> Any:
    class _S:
        pass

    s = _S()
    s.id = uuid.uuid4()
    s.signal_category = SignalCategory.GROWTH_RECOMMENDATION
    s.source_type = SignalSourceType.GROWTH_RECOMMENDATION
    s.source_row_id = uuid.uuid4()
    s.title = "Pipeline risk"
    s.summary = "Churn increasing"
    s.severity = IntelligenceSignalSeverity.HIGH
    s.business_impact = {"amount": 5000}
    s.priority_score = Decimal("0.82")
    s.priority_components = {"a": 1}
    s.evidence = ["e1"]
    s.recommended_next_step = "Review"
    s.confidence = IntelligenceConfidence.HIGH
    s.status = IntelligenceSignalStatus.ACTIVE
    s.content_hash = "abc"
    s.first_seen_at = datetime.now(UTC)
    s.last_triaged_at = None
    s.created_at = datetime.now(UTC)
    s.updated_at = datetime.now(UTC)
    return s


def _tool() -> tuple[IntelligenceSignalsTool, MagicMock]:
    session = MagicMock()
    org_id = uuid.uuid4()
    tool = IntelligenceSignalsTool(session, org_id)
    return tool, session


async def test_tool_is_read_only_and_serializes() -> None:
    tool, _ = _tool()
    fake = _fake_signal()
    with patch(
        "app.tools.intelligence_signals_tool.FounderIntelligenceService"
    ) as svc_cls:
        svc_cls.return_value.list_signals = AsyncMock(return_value=[fake])
        result = await tool.run({})
    assert isinstance(result, ToolResult)
    assert result.ok is True
    assert isinstance(result.content, list) and len(result.content) == 1
    row = result.content[0]
    assert row["id"] == str(fake.id)
    assert row["title"] == "Pipeline risk"
    assert row["severity"] == "high"
    assert row["priority_score"] == 0.82
    assert row["status"] == "active"
    assert "evidence" in row and "business_impact" in row


async def test_tool_validates_status_filter() -> None:
    tool, _ = _tool()
    result = await tool.run({"status": "not_a_real_status"})
    assert result.ok is False
    assert "invalid status" in (result.error or "")


async def test_tool_clamps_limit() -> None:
    tool, _ = _tool()
    with patch(
        "app.tools.intelligence_signals_tool.FounderIntelligenceService"
    ) as svc_cls:
        svc_cls.return_value.list_signals = AsyncMock(return_value=[])
        await tool.run({"limit": 9999})
        _, kwargs = svc_cls.return_value.list_signals.call_args
    assert kwargs["limit"] == 100


async def test_tool_permission_required() -> None:
    # Authorized (INTELLIGENCE_READ) -> allowed.
    perms = frozenset({Permission.INTELLIGENCE_READ})
    assert assert_can_invoke_tool(perms, "intelligence_signals") is None
    # Without it -> denied (fail closed).
    with pytest.raises(ToolAuthorizationError):
        assert_can_invoke_tool(frozenset({Permission.LEAD_READ}), "intelligence_signals")


async def test_tool_never_mutates() -> None:
    tool, _ = _tool()
    with patch(
        "app.tools.intelligence_signals_tool.FounderIntelligenceService"
    ) as svc_cls:
        svc_cls.return_value.list_signals = AsyncMock(return_value=[])
        await tool.run({})
    # Only read calls are made; no acknowledge/dismiss/write methods invoked.
    called = {c[0] for c in svc_cls.return_value.method_calls}
    assert called == {"list_signals"}
