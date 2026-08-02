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
        return await brain.run_with_plan(
            goal=goal,
            lead=lead,
            research=research,
            recent_messages=recent_messages,
            **plan_params,
        )

    async def tools(self) -> list[dict[str, Any]]:
        """Return the static tool manifest (portable, no runtime deps)."""
        from app.tools.registry import export_manifest

        return export_manifest()

    async def get_ai_settings(self, organization_id: uuid.UUID) -> tuple[str, str, bool]:
        """Return (provider, model, overridden) for the org's effective AI config."""
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
        return provider, model, overridden

    async def update_ai_settings(
        self,
        organization_id: uuid.UUID,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        """Merge new AI defaults into ``organizations.settings.ai``."""
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

        if provider is None and model is None:
            return

        org_service = OrganizationService(self._session)
        org = await org_service.get(organization_id)
        ai = dict(org.settings.get("ai") or {})
        if provider is not None:
            ai["provider"] = provider
        if model is not None:
            ai["model"] = model
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
