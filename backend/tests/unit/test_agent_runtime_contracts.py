"""Unit tests for the M5 agent runtime contracts.

Covers the strict run state machine, the executor base contract, and the
registry metadata types — all pure logic with no database. The state machine
rules here back every guarded transition in the agent run repository, so a
change to the enum requires a change to the transition table (enforced by a
completeness test).
"""
from __future__ import annotations

import uuid

import pytest

from app.agents.executors.base import AgentExecutor, ExecutorContext, ExecutorResult
from app.agents.registry import AgentCategory, AgentDefinition
from app.agents.state_machine import (
    _ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    assert_transition,
    can_transition,
    is_cancellable,
    is_terminal,
)
from app.core.errors import AppError
from app.models.enums import AgentRunStatus

# -- State machine ----------------------------------------------------


def test_terminal_statuses_match_the_approved_set() -> None:
    assert TERMINAL_STATUSES == {
        AgentRunStatus.SUCCEEDED,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
    }


@pytest.mark.parametrize("status", list(AgentRunStatus))
def test_is_terminal_only_for_terminal_statuses(status: AgentRunStatus) -> None:
    assert is_terminal(status) is (status in TERMINAL_STATUSES)


def test_queued_may_start_fail_or_cancel() -> None:
    assert can_transition(AgentRunStatus.QUEUED, AgentRunStatus.RUNNING)
    assert can_transition(AgentRunStatus.QUEUED, AgentRunStatus.FAILED)
    assert can_transition(AgentRunStatus.QUEUED, AgentRunStatus.CANCELLED)


def test_queued_cannot_skip_running() -> None:
    assert not can_transition(AgentRunStatus.QUEUED, AgentRunStatus.SUCCEEDED)


def test_running_may_succeed_fail_or_cancel() -> None:
    assert can_transition(AgentRunStatus.RUNNING, AgentRunStatus.SUCCEEDED)
    assert can_transition(AgentRunStatus.RUNNING, AgentRunStatus.FAILED)
    assert can_transition(AgentRunStatus.RUNNING, AgentRunStatus.CANCELLED)


def test_running_cannot_revert_to_queued() -> None:
    assert not can_transition(AgentRunStatus.RUNNING, AgentRunStatus.QUEUED)


def test_terminal_statuses_never_transition() -> None:
    for terminal in TERMINAL_STATUSES:
        for target in AgentRunStatus:
            assert not can_transition(terminal, target), (
                f"terminal state {terminal.value} must not transition to {target.value}"
            )


def test_assert_transition_raises_conflict_on_illegal() -> None:
    with pytest.raises(AppError) as exc:
        assert_transition(AgentRunStatus.QUEUED, AgentRunStatus.SUCCEEDED)
    assert exc.value.status_code == 409
    assert exc.value.code == "agent_run.illegal_transition"


def test_assert_transition_accepts_legal() -> None:
    assert_transition(AgentRunStatus.RUNNING, AgentRunStatus.SUCCEEDED)


def test_transition_table_covers_every_status() -> None:
    for status in AgentRunStatus:
        assert status in _ALLOWED_TRANSITIONS, (
            f"state machine missing transition row for {status.value}"
        )


def test_unknown_enum_member_rejected_by_lookup() -> None:
    with pytest.raises(KeyError):
        _ALLOWED_TRANSITIONS["does_not_exist"]  # type: ignore[index]


def test_is_cancellable_only_while_non_terminal() -> None:
    assert is_cancellable(AgentRunStatus.QUEUED)
    assert is_cancellable(AgentRunStatus.RUNNING)
    assert not is_cancellable(AgentRunStatus.SUCCEEDED)
    assert not is_cancellable(AgentRunStatus.FAILED)
    assert not is_cancellable(AgentRunStatus.CANCELLED)


# -- Executor contract ------------------------------------------------


def test_executor_result_defaults() -> None:
    result = ExecutorResult(success=True)
    assert result.output == {}
    assert result.error is None
    assert result.steps == 0
    assert result.duration_ms == 0


def test_executor_result_success_shape() -> None:
    result = ExecutorResult(
        success=True,
        output={"draft": "hello"},
        steps=3,
        duration_ms=250,
    )
    assert result.output == {"draft": "hello"}
    assert result.steps == 3
    assert result.duration_ms == 250


def test_executor_context_carries_run_identity() -> None:
    run_id = uuid.uuid4()
    org_id = uuid.uuid4()
    ctx = ExecutorContext(
        session=object(),
        organization_id=org_id,
        run_id=run_id,
        goal="research_lead",
        input={"lead_id": "abc"},
    )
    assert ctx.organization_id == org_id
    assert ctx.run_id == run_id
    assert ctx.goal == "research_lead"
    assert ctx.input == {"lead_id": "abc"}


def test_agent_executor_protocol_is_runtime_checkable() -> None:
    class _FakeExecutor:
        name = "fake"
        description = "fake executor"

        async def execute(self, ctx: ExecutorContext) -> ExecutorResult:
            return ExecutorResult(success=True)

    assert isinstance(_FakeExecutor(), AgentExecutor)


def test_agent_executor_rejects_missing_execute() -> None:
    class _NotAnExecutor:
        name = "fake"

    assert not isinstance(_NotAnExecutor(), AgentExecutor)


# -- Registry types ---------------------------------------------------


def test_agent_category_values() -> None:
    assert set(AgentCategory) == {"executable", "registered", "future"}


def test_agent_definition_construction() -> None:
    definition = AgentDefinition(
        name="research_agent",
        display_name="Research Agent",
        description="Researches leads",
        category=AgentCategory.EXECUTABLE,
        supported_goals=("research_lead",),
    )
    assert definition.name == "research_agent"
    assert definition.category is AgentCategory.EXECUTABLE
    assert definition.supported_goals == ("research_lead",)


def test_agent_definition_supported_goals_default_empty() -> None:
    definition = AgentDefinition(
        name="growth_agent",
        display_name="Growth Agent",
        description="Test definition for supported_goals default",
        category=AgentCategory.REGISTERED,
    )
    assert definition.supported_goals == ()
