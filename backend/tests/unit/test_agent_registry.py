"""Unit tests for the canonical M5 agent registry.

The registry is a closed set: exactly 7 executable agents, one registered-only
agent (``growth_agent`` — execution lands in M7), and 4 future-only agent
names. The runtime refuses anything outside the executable set, and the
registry validates its own integrity (no duplicate names, well-formed
metadata, and supported goals that the deterministic planner actually knows).
"""
from __future__ import annotations

import pytest

from app.agents.registry import (
    AGENTS_BY_NAME,
    CANONICAL_AGENTS,
    AgentCategory,
    get_agent,
    is_executable,
    is_known,
    list_executable,
    require_executable,
)
from app.ai.planner import all_known_goals
from app.core.errors import AppError

EXECUTABLE_AGENTS = {
    "ai_brain",
    "founder_assistant",
    "research_agent",
    "crm_agent",
    "outreach_agent",
    "workflow_agent",
    "notification_agent",
}

REGISTERED_ONLY_AGENTS = {"growth_agent"}

FUTURE_AGENTS = {"finance", "hr", "calendar", "voice"}


def test_canonical_agent_inventory_is_closed() -> None:
    names = {agent.name for agent in CANONICAL_AGENTS}
    assert names == EXECUTABLE_AGENTS | REGISTERED_ONLY_AGENTS | FUTURE_AGENTS
    assert len(names) == 12


def test_executable_agents_exact_set() -> None:
    assert set(list_executable()) == EXECUTABLE_AGENTS


def test_registered_only_agent_is_growth() -> None:
    growth = get_agent("growth_agent")
    assert growth is not None
    assert growth.category is AgentCategory.REGISTERED


def test_future_agents_are_future_category() -> None:
    for name in FUTURE_AGENTS:
        agent = get_agent(name)
        assert agent is not None
        assert agent.category is AgentCategory.FUTURE


def test_growth_agent_not_executable() -> None:
    assert not is_executable("growth_agent")


def test_future_agents_not_executable() -> None:
    for name in FUTURE_AGENTS:
        assert not is_executable(name)
        assert is_known(name)


def test_unknown_agent_not_known() -> None:
    assert not is_known("does_not_exist")
    assert get_agent("does_not_exist") is None
    assert not is_executable("does_not_exist")


def test_no_duplicate_names() -> None:
    names = [agent.name for agent in CANONICAL_AGENTS]
    assert len(names) == len(set(names))
    assert set(AGENTS_BY_NAME) == set(names)


def test_registry_lookup_matches_canonical_list() -> None:
    for agent in CANONICAL_AGENTS:
        assert AGENTS_BY_NAME[agent.name] is agent
        assert get_agent(agent.name) is agent


def test_definitions_are_well_formed() -> None:
    for agent in CANONICAL_AGENTS:
        assert agent.name
        assert agent.display_name.strip()
        assert agent.description.strip()


def test_executable_supported_goals_are_known_to_planner() -> None:
    known = set(all_known_goals())
    for agent in CANONICAL_AGENTS:
        if agent.category is not AgentCategory.EXECUTABLE:
            continue
        for goal in agent.supported_goals:
            assert goal in known, (
                f"{agent.name} declares unsupported goal {goal!r}"
            )


def test_require_executable_returns_definition() -> None:
    definition = require_executable("research_agent")
    assert definition.name == "research_agent"


def test_require_executable_unknown_raises_404() -> None:
    with pytest.raises(AppError) as exc:
        require_executable("does_not_exist")
    assert exc.value.status_code == 404
    assert exc.value.code == "agent.unknown"


def test_require_executable_registered_raises_409() -> None:
    with pytest.raises(AppError) as exc:
        require_executable("growth_agent")
    assert exc.value.status_code == 409
    assert exc.value.code == "agent.not_executable"


def test_require_executable_future_raises_409() -> None:
    for name in FUTURE_AGENTS:
        with pytest.raises(AppError) as exc:
            require_executable(name)
        assert exc.value.status_code == 409
