"""AI Brain — orchestrates the LLM + tool loop for autonomous outreach tasks.

The brain is the central reasoning engine. Given a goal and context (lead +
research + conversation), it runs a bounded loop:

1. Build system prompt + message history (via context_builder).
2. If a plan exists for the goal, pre-pend the plan's tool calls as a hint.
3. Call LLMService.chat with tools enabled.
4. If the model emits tool calls, execute them via the ToolRegistry.
5. Append tool results to the message history and repeat (up to max_steps).
6. Return the final assistant message or the last tool result.

The brain is stateless per invocation; all state lives in the message history
and the ToolRegistry's execution context.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.core.metrics import get_counter
from app.core.permissions import Permission
from app.llm.models import LLMMessage, MessageRole, ToolCall, ToolDefinition
from app.llm.service import LLMService
from app.tools.base import ToolResult
from app.tools.registry import ToolAuthorizationError, ToolRegistry, assert_can_invoke_tool

if TYPE_CHECKING:
    from uuid import UUID

    from app.models.conversation import Conversation
    from app.models.lead import Lead
    from app.models.lead_research import LeadResearch


@dataclass
class BrainConfig:
    """Configuration knobs for the brain loop."""

    max_steps: int = 8
    temperature: float | None = 0.2
    max_tokens: int | None = 2048


@dataclass
class BrainResult:
    """Outcome of a brain run."""

    success: bool
    response: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_results: list[ToolResult] | None = None
    error: str | None = None
    steps_taken: int = 0
    # M11-A/M11-C: per-tool audit trail. Each entry records the tool name, goal,
    # authorization + allow-list outcome, success/failure, a sanitized error,
    # and timing context. Empty when no tools were attempted.
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    organization_id: UUID | None = None
    trace_id: UUID | None = None
    run_id: UUID | None = None


class Brain:
    """Main brain orchestrator."""

    def __init__(
        self,
        llm_service: LLMService,
        tool_registry: ToolRegistry,
        config: BrainConfig | None = None,
    ) -> None:
        self._llm = llm_service
        self._registry = tool_registry
        self._config = config or BrainConfig()

    async def run(
        self,
        *,
        goal: str,
        lead: Lead | None,
        research: LeadResearch | None,
        conversation: Conversation | None = None,
        recent_messages: list[dict[str, Any]] | None = None,
        plan_override: list[dict[str, Any]] | None = None,
        memory_context: str | None = None,
        persona: str | None = None,
        caller_permissions: frozenset[Permission] | None = None,
        allowed_tools: set[str] | None = None,
        organization_id: UUID | None = None,
        trace_id: UUID | None = None,
        run_id: UUID | None = None,
    ) -> BrainResult:
        """Execute the brain loop for a single goal.

        M11 enforcement: when ``allowed_tools`` is provided, a tool call whose
        name is not in that set is rejected (goal-scoped allow-list, fail
        closed). When ``caller_permissions`` is provided, every tool call is
        checked against its declared :data:`~app.tools.registry.TOOL_MANIFEST`
        permission (per-tool authorization, fail closed). Both must be supplied
        by the AI run path; legacy/trusted callers may pass ``None`` to skip
        enforcement (backward compatible).

        Every tool attempt is recorded in ``tool_trace`` for audit, carrying the
        run/goal/authorization context and a sanitized outcome.
        """
        from app.ai.context_builder import build_message_history, build_system_prompt

        system_prompt = build_system_prompt(
            lead=lead,
            research=research,
            recent_messages=recent_messages,
            memory_context=memory_context,
            persona=persona,
        )
        messages = build_message_history(
            recent_messages=recent_messages, system_prompt=system_prompt
        )

        # If a plan is available, inject it as a synthetic "assistant" message
        # with a tool_calls block so the model knows the expected sequence.
        if plan_override:
            messages.append(
                LLMMessage(
                    role=MessageRole.ASSISTANT,
                    content="",
                    tool_calls=[
                        ToolCall(
                            id=f"plan_{i}",
                            name=s["tool"],
                            arguments=json.dumps(s["input"]),
                        )
                        for i, s in enumerate(plan_override)
                    ],
                )
            )

        tool_results: list[ToolResult] = []
        tool_trace: list[dict[str, Any]] = []
        steps = 0

        while steps < self._config.max_steps:
            steps += 1
            # Call the LLM with all available tool definitions
            tool_defs = [
                ToolDefinition(
                    name=t.name,
                    description=t.description,
                    parameters=t.parameters,
                )
                for t in self._registry.iter()
            ]

            try:
                result = await self._llm.chat(
                    messages,
                    tools=tool_defs,
                    temperature=self._config.temperature,
                    max_tokens=self._config.max_tokens,
                )
            except Exception as exc:
                return BrainResult(
                    success=False,
                    error=f"LLM call failed: {exc}",
                    tool_results=tool_results,
                    tool_trace=tool_trace,
                    steps_taken=steps,
                    organization_id=organization_id,
                    trace_id=trace_id,
                    run_id=run_id,
                )

            # If no tool calls, we're done — return the text response.
            if not result.tool_calls:
                return BrainResult(
                    success=True,
                    response=result.text,
                    tool_calls=[],
                    tool_results=tool_results,
                    tool_trace=tool_trace,
                    steps_taken=steps,
                    organization_id=organization_id,
                    trace_id=trace_id,
                    run_id=run_id,
                )

            # Execute tool calls (with M11 authorization + allow-list + audit).
            for tc in result.tool_calls:
                entry: dict[str, Any] = {
                    "tool": tc.name,
                    "goal": goal,
                    "organization_id": str(organization_id) if organization_id else None,
                    "trace_id": str(trace_id) if trace_id else None,
                    "run_id": str(run_id) if run_id else None,
                }

                # 1) Goal-scoped allow-list (fail closed). When unrestricted,
                #    ``allowed_tools`` is None and the check is skipped — but the
                #    AI run path always supplies a bounded set.
                if allowed_tools is not None and tc.name not in allowed_tools:
                    denial = f"tool {tc.name!r} is not permitted for goal {goal!r}"
                    tool_results.append(ToolResult(ok=False, error=denial))
                    entry.update(
                        allowed=False,
                        authorized=False,
                        ok=False,
                        error=denial,
                        duration_ms=0,
                        char_len=0,
                    )
                    tool_trace.append(entry)
                    get_counter(
                        "tool_authorization_denied",
                        description="Tool calls rejected by goal allow-list or permission",
                    ).add()
                    continue

                # 2) Existence (fail closed).
                tool = self._registry.get(tc.name)
                if tool is None:
                    denial = f"unknown tool: {tc.name}"
                    tool_results.append(ToolResult(ok=False, error=denial))
                    entry.update(
                        allowed=True,
                        authorized=False,
                        ok=False,
                        error=denial,
                        duration_ms=0,
                        char_len=0,
                    )
                    tool_trace.append(entry)
                    get_counter(
                        "tool_authorization_denied",
                        description="Tool calls rejected by goal allow-list or permission",
                    ).add()
                    continue

                # 3) Per-tool permission (fail closed).
                if caller_permissions is not None:
                    try:
                        assert_can_invoke_tool(caller_permissions, tc.name)
                    except ToolAuthorizationError as exc:
                        tool_results.append(ToolResult(ok=False, error=str(exc)))
                        entry.update(
                            allowed=True,
                            authorized=False,
                            ok=False,
                            error=str(exc),
                            duration_ms=0,
                            char_len=0,
                        )
                        tool_trace.append(entry)
                        get_counter(
                            "tool_authorization_denied",
                            description="Tool calls rejected by goal allow-list or permission",
                        ).add()
                        continue

                # 4) Execute the authorized tool.
                get_counter(
                    "tool_calls_total",
                    description="Authorized tool calls dispatched by the brain",
                ).add()
                start = time.perf_counter()
                try:
                    arguments = self._parse_arguments(tc.arguments)
                    tool_result = await tool.run(arguments)
                    duration_ms = round((time.perf_counter() - start) * 1000, 2)
                    tool_results.append(tool_result)
                    # Append the tool result so the model can reason about it.
                    messages.append(
                        LLMMessage(
                            role=MessageRole.TOOL,
                            content=tool_result.text,
                            tool_call_id=tc.id,
                        )
                    )
                    entry.update(
                        allowed=True,
                        authorized=True,
                        ok=tool_result.ok,
                        error=tool_result.error,
                        duration_ms=duration_ms,
                        char_len=len(tool_result.text),
                    )
                    tool_trace.append(entry)
                except Exception as exc:
                    duration_ms = round((time.perf_counter() - start) * 1000, 2)
                    tool_results.append(ToolResult(ok=False, error=str(exc)))
                    entry.update(
                        allowed=True,
                        authorized=True,
                        ok=False,
                        error=str(exc),
                        duration_ms=duration_ms,
                        char_len=0,
                    )
                    tool_trace.append(entry)

            # If all tool calls failed, we may still want to let the LLM decide
            # next. Continue loop.

        # Max steps reached
        return BrainResult(
            success=False,
            error=f"max steps ({self._config.max_steps}) reached",
            tool_results=tool_results,
            tool_trace=tool_trace,
            steps_taken=steps,
            organization_id=organization_id,
            trace_id=trace_id,
            run_id=run_id,
        )

    async def run_with_plan(
        self,
        *,
        goal: str,
        lead: Lead | None,
        research: LeadResearch | None,
        conversation: Conversation | None = None,
        recent_messages: list[dict[str, Any]] | None = None,
        memory_context: str | None = None,
        persona: str | None = None,
        caller_permissions: frozenset[Permission] | None = None,
        allowed_tools: set[str] | None = None,
        organization_id: UUID | None = None,
        trace_id: UUID | None = None,
        run_id: UUID | None = None,
        **plan_params: Any,
    ) -> BrainResult:
        """Run the brain using the planner's pre-defined plan for the goal."""
        from app.ai.planner import plan_for_goal

        plan = plan_for_goal(goal, **plan_params)
        if plan is None:
            # No pre-defined plan — run free-form.
            return await self.run(
                goal=goal,
                lead=lead,
                research=research,
                conversation=conversation,
                recent_messages=recent_messages,
                memory_context=memory_context,
                persona=persona,
                caller_permissions=caller_permissions,
                allowed_tools=allowed_tools,
                organization_id=organization_id,
                trace_id=trace_id,
                run_id=run_id,
            )

        return await self.run(
            goal=goal,
            lead=lead,
            research=research,
            conversation=conversation,
            recent_messages=recent_messages,
            plan_override=[{"tool": s.tool, "input": s.input} for s in plan.steps],
            memory_context=memory_context,
            persona=persona,
            caller_permissions=caller_permissions,
            allowed_tools=allowed_tools,
            organization_id=organization_id,
            trace_id=trace_id,
            run_id=run_id,
        )

    @staticmethod
    def _parse_arguments(raw: str) -> dict[str, Any]:
        """Best-effort parse of an LLM tool-call arguments JSON string."""
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
