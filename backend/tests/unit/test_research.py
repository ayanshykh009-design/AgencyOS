"""Unit tests for the ResearchService pipeline (web search + LLM extraction).

Repositories are stubbed and the web-search tool uses an ``httpx`` mock
transport, so no network or database is touched.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.llm.models import ChatResult, LLMUsage
from app.llm.service import LLMService
from app.services.research_service import ResearchService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
LEAD_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _lead() -> SimpleNamespace:
    return SimpleNamespace(
        id=LEAD_ID,
        first_name="Ada",
        last_name="Lovelace",
        company="Analytical",
        position="Engineer",
    )


def _signals_json() -> str:
    return json.dumps(
        {
            "company_overview": "Analytical builds engines.",
            "pain_points": ["scaling", "recruiting"],
            "tech_stack": ["Python", "Postgres"],
            "recent_news": ["Raised series B"],
            "linkedin_summary": "Ada is an engineer.",
            "icp_match_score": 85,
        }
    )


class _DummyLlm(LLMService):
    """LLMService whose chat returns a fixed JSON payload."""

    def __init__(self, payload: str, *, fail: bool = False) -> None:
        super().__init__(client=None)
        self.payload = payload
        self.fail = fail

    async def chat(self, messages, *, tools=None, temperature=None, max_tokens=None):
        if self.fail:
            raise RuntimeError("llm unavailable")
        return ChatResult(
            self.payload,
            LLMUsage("openai", "gpt-4o-mini", 100, 50, 0.01),
            "gpt-4o-mini",
            "stop",
        )

    def render_prompt(self, name: str, version: str, variables: dict[str, Any]) -> str:
        return f"rendered {name} {version}"


class _FakeLeadRepo:
    """Stub for LeadRepository.get_or_404 used by ResearchService."""

    def __init__(self, session: Any) -> None:
        self.session = session

    async def get_or_404(self, organization_id: uuid.UUID, lead_id: uuid.UUID):
        return _lead()


class _FakeResearchRepo:
    def __init__(self, session: Any) -> None:
        self.session = session
        self.rows: dict[uuid.UUID, SimpleNamespace] = {}

    async def get(self, organization_id: uuid.UUID, lead_id: uuid.UUID):
        return self.rows.get(lead_id)

    async def upsert(
        self,
        organization_id: uuid.UUID,
        lead_id: uuid.UUID,
        *,
        status: str = "in_progress",
        **fields: Any,
    ):
        row = self.rows.get(lead_id)
        if row is None:
            row = SimpleNamespace(
                lead_id=lead_id,
                organization_id=organization_id,
                status=status,
                **fields,
            )
            self.rows[lead_id] = row
        else:
            row.status = status
            for key, value in fields.items():
                setattr(row, key, value)
        return row


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.committed = 0

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed += 1


def _web_search_client() -> httpx.AsyncClient:
    html = (
        '<div class="result"><a class="result__url" href="https://e.com/a">Analytical</a>'
        '<a class="result__snippet">Funding news</a></div>'
    )
    return httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=html))
    )


def _service(
    session: _FakeSession,
    research_repo: _FakeResearchRepo,
    *,
    payload: str = _signals_json(),
    http_client: httpx.AsyncClient | None = None,
) -> ResearchService:
    service = ResearchService(session, llm_service=_DummyLlm(payload), http_client=http_client)
    service._leads = _FakeLeadRepo(session)
    service._research_repo = research_repo
    return service


@pytest.mark.asyncio
async def test_run_completes_research_and_logs_activity() -> None:
    session = _FakeSession()
    repo = _FakeResearchRepo(session)
    service = _service(session, repo, http_client=_web_search_client())

    result = await service.run(lead_id=LEAD_ID, organization_id=ORG_ID)

    assert result.status == "completed"
    assert result.company_overview == "Analytical builds engines."
    assert result.pain_points == ["scaling", "recruiting"]
    assert result.tech_stack == ["Python", "Postgres"]
    assert result.icp_match_score == 85
    assert result.research_source == "ai_enrichment"
    assert session.committed == 1
    # Activity log recorded under the ORM's mapped column name (metadata_).
    log = session.added[0]
    assert getattr(log, "metadata_", None) == {"lead_id": str(LEAD_ID)}


@pytest.mark.asyncio
async def test_run_returns_existing_completed_research_when_not_forced() -> None:
    session = _FakeSession()
    repo = _FakeResearchRepo(session)
    repo.rows[LEAD_ID] = SimpleNamespace(
        lead_id=LEAD_ID,
        organization_id=ORG_ID,
        status="completed",
        company_overview="Existing",
    )
    service = _service(session, repo, http_client=_web_search_client())

    result = await service.run(lead_id=LEAD_ID, organization_id=ORG_ID)

    assert result.company_overview == "Existing"
    assert session.committed == 0


@pytest.mark.asyncio
async def test_run_marks_failed_on_error_and_reraises() -> None:
    session = _FakeSession()
    repo = _FakeResearchRepo(session)
    service = _service(
        session,
        repo,
        payload="",
        http_client=_web_search_client(),
    )
    service._llm = _DummyLlm(_signals_json(), fail=True)

    with pytest.raises(RuntimeError):
        await service.run(lead_id=LEAD_ID, organization_id=ORG_ID)

    assert repo.rows[LEAD_ID].status == "failed"


def test_parse_signals_json_handles_markdown_fences() -> None:
    service = _service(_FakeSession(), _FakeResearchRepo(_FakeSession()))
    parsed = service._parse_signals_json(f"```json\n{_signals_json()}\n```")
    assert parsed["company_overview"] == "Analytical builds engines."
    assert parsed["pain_points"] == ["scaling", "recruiting"]


def test_parse_signals_json_falls_back_to_empty() -> None:
    service = _service(_FakeSession(), _FakeResearchRepo(_FakeSession()))
    parsed = service._parse_signals_json("no json here")
    assert parsed["company_overview"] == "Could not parse structured output"
    assert parsed["pain_points"] == []


def test_snippets_to_text_formats_and_caps() -> None:
    service = _service(_FakeSession(), _FakeResearchRepo(_FakeSession()))
    text = service._snippets_to_text([{"title": "T", "url": "https://x", "snippet": "s" * 500}])
    assert "T (https://x)" in text
    assert len(text.split(": ")[-1]) <= 300
