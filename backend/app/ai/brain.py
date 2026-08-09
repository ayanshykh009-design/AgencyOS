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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.llm.models import LLMMessage, MessageRole, ToolCall, ToolDefinition
from app.llm.service import LLMService
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry

if TYPE_CHECKING:
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
        lead: Lead,
        research: LeadResearch | None,
        conversation: Conversation | None = None,
        recent_messages: list[dict[str, Any]] | None = None,
        plan_override: list[dict[str, Any]] | None = None,
        memory_context: str | None = None,
    ) -> BrainResult:
        """Execute the brain loop for a single goal."""
        from app.ai.context_builder import build_message_history, build_system_prompt

        system_prompt = build_system_prompt(
            lead=lead,
            research=research,
            recent_messages=recent_messages,
            memory_context=memory_context,
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
                    steps_taken=steps,
                )

            # If no tool calls, we're done — return the text response.
            if not result.tool_calls:
                return BrainResult(
                    success=True,
                    response=result.text,
                    tool_calls=[],
                    tool_results=tool_results,
                    steps_taken=steps,
                )

            # Execute tool calls
            for tc in result.tool_calls:
                tool = self._registry.get(tc.name)
                if tool is None:
                    tool_results.append(ToolResult(ok=False, error=f"unknown tool: {tc.name}"))
                    continue

                try:
                    arguments = self._parse_arguments(tc.arguments)
                    tool_result = await tool.run(arguments)
                    tool_results.append(tool_result)

                    # Append tool result as a "tool" role message
                    messages.append(
                        LLMMessage(
                            role=MessageRole.TOOL,
                            content=tool_result.text,
                            tool_call_id=tc.id,
                        )
                    )
                except Exception as exc:
                    tool_results.append(ToolResult(ok=False, error=str(exc)))

            # If all tool calls failed, we may still want to let the LLM decide next.
            # Continue loop.

        # Max steps reached
        return BrainResult(
            success=False,
            error=f"max steps ({self._config.max_steps}) reached",
            tool_results=tool_results,
            steps_taken=steps,
        )

    async def run_with_plan(
        self,
        *,
        goal: str,
        lead: Lead,
        research: LeadResearch | None,
        conversation: Conversation | None = None,
        recent_messages: list[dict[str, Any]] | None = None,
        memory_context: str | None = None,
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
            )

        return await self.run(
            goal=goal,
            lead=lead,
            research=research,
            conversation=conversation,
            recent_messages=recent_messages,
            plan_override=[{"tool": s.tool, "input": s.input} for s in plan.steps],
            memory_context=memory_context,
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
