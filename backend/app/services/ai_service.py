"""AI automation service: run the brain for a goal and dispatch via n8n.

The service is the thin business-logic entry point for AI automation. It:
- resolves the organization's LLM configuration (per-org override, else env),
- wires a :class:`ToolRegistry` to the request session + org,
- runs the :class:`Brain` for a goal with plan support, and
- dispatches drafts to n8n via :class:`N8nDispatchTool`.

All usage is recorded against the org via ``LLMService``.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.llm.service import LLMService
from app.repositories.lead import LeadRepository
from app.repositories.lead_research import LeadResearchRepository
from app.services.llm_settings import SUPPORTED_PROVIDERS

logger = logging.getLogger("agencyos")


class AIService:
    """Owns the AI automation workflow and its transaction boundary."""

    def __init__(
        self,
        session: AsyncSession,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._session = session
        self._http_client = http_client or httpx.AsyncClient(timeout=15.0)

    async def run(
        self,
        *,
        goal: str,
        lead_id: uuid.UUID,
        organization_id: uuid.UUID,
        channel: str | None = None,
        recent_messages: list[dict[str, Any]] | None = None,
    ) -> Any:
        """Run the brain for ``goal`` on the lead; returns a ``BrainResult``."""
        from app.ai.brain import Brain
        from app.tools.registry import ToolContext, default_registry

        lead = await LeadRepository(self._session).get_or_404(organization_id, lead_id)
        research = await LeadResearchRepository(self._session).get(organization_id, lead_id)

        llm = await self._llm_for_org(organization_id)
        ctx = ToolContext(
            session=self._session,
            organization_id=organization_id,
            llm_service=llm,
            http_client=self._http_client,
        )
        registry = default_registry(ctx)

        brain = Brain(llm, registry)
        plan_params: dict[str, Any] = {"lead_id": str(lead_id)}
        if channel:
            plan_params["channel"] = channel
        memory_context = await self._retrieve_memory_context(organization_id)
        return await brain.run_with_plan(
            goal=goal,
            lead=lead,
            research=research,
            recent_messages=recent_messages,
            memory_context=memory_context,
            **plan_params,
        )

    async def _retrieve_memory_context(self, organization_id: uuid.UUID) -> str | None:
        """Fetch ranked memory context for the AI prompt, gated + fail-open.

        Gated on ``settings.AI_MEMORY_ENABLED``; any retrieval error logs a
        warning and returns ``None`` so the AI run proceeds unchanged.
        """
        if not settings.AI_MEMORY_ENABLED:
            return None
        from app.services.memory_service import MemoryService

        try:
            return await MemoryService(self._session).retrieve_context(organization_id)
        except Exception as exc:  # pragma: no cover - defensive path
            logger.warning("memory context retrieval failed; proceeding without it: %s", exc)
            return None

    async def tools(self) -> list[dict[str, Any]]:
        """Return the static tool manifest (portable, no runtime deps)."""
        from app.tools.registry import export_manifest

        return export_manifest()

    @staticmethod
    def agent_for_goal(goal: str) -> str:
        """Map an AI-run goal to its canonical agent (M11-C routing).

        Lead/research/outreach goals route to the dedicated agents; anything
        else falls back to the general ``ai_brain`` agent which the worker
        resolves through the goal-scoped tool allow-list.
        """
        return {
            "research_lead": "research_agent",
            "search_leads": "outreach_agent",
            "draft_email": "outreach_agent",
            "draft_linkedin": "outreach_agent",
            "dispatch_outreach": "outreach_agent",
            "enrich_and_dispatch": "outreach_agent",
        }.get(goal, "ai_brain")

    async def get_ai_settings(
        self, organization_id: uuid.UUID
    ) -> tuple[str, str, bool, bool]:
        """Return (provider, model, overridden, kill_switch) for the org."""
        from app.repositories.organization import OrganizationRepository

        org = await OrganizationRepository(self._session).get(organization_id)
        ai: dict[str, Any] = {}
        if org is not None and isinstance(org.settings, dict):
            stored = org.settings.get("ai")
            if isinstance(stored, dict):
                ai = stored

        provider = ai.get("provider") or settings.LLM_PROVIDER
        model = ai.get("model") or settings.LLM_DEFAULT_MODEL
        overridden = "provider" in ai or "model" in ai
        kill_switch = bool(ai.get("kill_switch", False))
        return provider, model, overridden, kill_switch

    async def is_ai_enabled(self, organization_id: uuid.UUID) -> bool:
        """Return whether AI execution is allowed for the organization.

        Fail closed: a missing organization or malformed settings denies AI.
        The default (no ``ai.kill_switch`` key present) is enabled.
        """
        from app.repositories.organization import OrganizationRepository

        org = await OrganizationRepository(self._session).get(organization_id)
        if org is None or not isinstance(org.settings, dict):
            return False
        ai = org.settings.get("ai")
        if not isinstance(ai, dict):
            return True
        return not bool(ai.get("kill_switch", False))

    async def assert_ai_enabled(self, organization_id: uuid.UUID) -> None:
        """Raise ``AppError`` (409) when AI execution is disabled for the org."""
        if not await self.is_ai_enabled(organization_id):
            raise AppError(
                code="ai.disabled",
                message="AI execution is disabled for this organization",
                status_code=409,
            )

    async def update_ai_settings(
        self,
        organization_id: uuid.UUID,
        *,
        provider: str | None = None,
        model: str | None = None,
        kill_switch: bool | None = None,
    ) -> None:
        """Merge new AI defaults into ``organizations.settings.ai``.

        ``kill_switch`` is the per-organization AI execution kill switch (F-SEC-3):
        ``True`` disables new AI/agent execution for the org (fail closed at the
        execution boundary).
        """
        from app.core.errors import AppError
        from app.services.organization_service import OrganizationService

        if provider is not None:
            provider = provider.strip().lower()
            if provider not in SUPPORTED_PROVIDERS:
                raise AppError(
                    code="ai.invalid_provider",
                    message=f"unsupported LLM provider: {provider!r}",
                    status_code=400,
                )
        if model is not None:
            model = model.strip()

        if provider is None and model is None and kill_switch is None:
            return

        org_service = OrganizationService(self._session)
        org = await org_service.get(organization_id)
        ai = dict(org.settings.get("ai") or {})
        if provider is not None:
            ai["provider"] = provider
        if model is not None:
            ai["model"] = model
        if kill_switch is not None:
            ai["kill_switch"] = bool(kill_switch)
        await org_service.update_settings(organization_id, {"ai": ai})

    async def dispatch(self, *, workflow: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a ready-to-send draft to the n8n automation platform."""
        from app.tools.n8n_tool import N8nDispatchTool

        tool = N8nDispatchTool(client=self._http_client)
        result = await tool.run({"workflow": workflow, "payload": payload})
        if not result.ok:
            raise AppError(
                code="ai.dispatch_failed",
                message=result.error or "n8n dispatch failed",
                status_code=502,
            )
        return result.content

    async def _llm_for_org(self, organization_id: uuid.UUID) -> LLMService:
        """Build an LLMService honoring per-org AI settings (else env defaults)."""
        provider, model = await self._resolve_ai_config(organization_id)
        return LLMService.for_provider(
            provider,
            model=model,
            organization_id=organization_id,
            session=self._session,
            feature="ai.automation",
        )

    async def _resolve_ai_config(self, organization_id: uuid.UUID) -> tuple[str, str | None]:
        """Read ``organizations.settings.ai`` (provider/model), falling back to env."""
        from app.services.llm_settings import resolve_ai_config

        return await resolve_ai_config(self._session, organization_id)
