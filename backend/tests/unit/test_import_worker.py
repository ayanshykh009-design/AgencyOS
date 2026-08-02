"""Unit tests for the CSV import worker's pure parsing/normalization.

Only the database-free helpers are exercised here (``_parse_csv``,
``_parse_row``, ``_digits``). The full job run (savepoints, dedup, chunking)
is covered by the integration suite against a real PostgreSQL server.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.models.enums import ImportStatus
from app.workers.import_worker import (
    ImportWorker,
    _digits,
    _parse_csv,
    _parse_row,
)


def test_parse_csv_normalizes_headers() -> None:
    content = (
        b"First Name,Last Name,Email,Company,Title,LinkedIn\n"
        b"Ada,Lovelace,ada@example.com,Analytical Engine,Engineer,https://li.in/x\n"
    )
    rows = _parse_csv(content)
    assert rows == [
        {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "company": "Analytical Engine",
            "position": "Engineer",
            "linkedin_url": "https://li.in/x",
        }
    ]


def test_parse_csv_handles_utf8_bom_and_blank_cells() -> None:
    content = b"\xef\xbb\xbfemail,first_name\nADA@example.com,\n"
    rows = _parse_csv(content)
    assert rows[0] == {"email": "ADA@example.com", "first_name": ""}


def test_parse_row_normalizes_email_and_phone() -> None:
    parsed, error = _parse_row(
        {"email": " Ada@Example.com ", "phone": "+1 (212) 555-0142", "first_name": "Ada"}
    )
    assert error is None
    assert parsed["email"] == "ada@example.com"
    assert parsed["phone"] == "12125550142"


def test_parse_row_requires_contact_field() -> None:
    parsed, error = _parse_row({"first_name": "Ada", "last_name": "Lovelace"})
    assert parsed == {}
    assert error == "at least one of email/phone/whatsapp/website is required"


def test_parse_row_rejects_invalid_email() -> None:
    parsed, error = _parse_row({"email": "not-an-email"})
    assert error == "email must be valid"


def test_parse_row_accepts_website_only() -> None:
    parsed, error = _parse_row({"website": "https://example.com"})
    assert error is None
    assert parsed["website"] == "https://example.com"


def test_parse_row_rejects_garbage_phone() -> None:
    parsed, error = _parse_row({"phone": "n/a"})
    assert parsed == {}
    assert error == "at least one of email/phone/whatsapp/website is required"


def test_digits_returns_none_for_empty() -> None:
    assert _digits(None) is None
    assert _digits("") is None
    assert _digits("abc") is None


def test_digits_keeps_only_ascii_digits() -> None:
    assert _digits("+44 (20) 1234-5678 ext. 9") == "4420123456789"


class _FakeAwait:
    def __init__(self, value: Any) -> None:
        self._value = value

    def __await__(self) -> Any:
        yield
        return self._value


class _FakeSession:
    """Minimal stand-in for an AsyncSession used by ``ImportWorker._run``."""

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.committed = False
        self.flushed = False

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushed = True

    async def commit(self) -> None:
        self.committed = True


class _FakeSessionCM:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeSession:
        return self._session

    async def __aexit__(self, *exc_info: Any) -> bool:
        return False


def _run_import_job(claimed: bool, monkeypatch: pytest.MonkeyPatch) -> _FakeSession:
    session = _FakeSession()
    job = SimpleNamespace(
        id="job-1",
        created_by_user_id="user-1",
        file_name="leads.csv",
        status=ImportStatus.PENDING,
    )
    inserts: list[dict[str, Any]] = []

    async def _fake_insert(session_: Any, model: Any, *args: Any, **kwargs: Any) -> bool:
        inserts.append(kwargs)
        return True

    def _fake_factory() -> _FakeSessionCM:
        return _FakeSessionCM(session)

    def _fake_upload_path(job_id: Any) -> Any:
        return SimpleNamespace(read_bytes=lambda: b"email\nx@example.com")

    def _claim(self, org_id: Any, job_id: Any) -> _FakeAwait:
        return _FakeAwait(job if claimed else None)

    monkeypatch.setattr("app.workers.import_worker.async_session_factory", _fake_factory)
    monkeypatch.setattr(
        "app.workers.import_worker.ImportService",
        type("S", (), {"upload_path": staticmethod(_fake_upload_path)}),
    )
    monkeypatch.setattr(
        "app.workers.import_worker._parse_csv",
        lambda content: [{"email": "x@example.com"}],
    )
    monkeypatch.setattr(
        "app.workers.import_worker.ImportJobRepository",
        type(
            "R",
            (),
            {
                "__init__": lambda self, s: None,
                "claim": _claim,
            },
        ),
    )
    monkeypatch.setattr(
        "app.workers.import_worker.LeadRepository",
        type(
            "L",
            (),
            {
                "__init__": lambda self, s: None,
                "find_duplicates": lambda self, o, **kwargs: _FakeAwait([]),
            },
        ),
    )
    monkeypatch.setattr("app.workers.import_worker._insert_with_savepoint", _fake_insert)
    monkeypatch.setattr("app.workers.import_worker.utcnow", lambda: None)

    import asyncio

    asyncio.run(ImportWorker.process_job("job-1", "org-1"))
    return session


def test_run_returns_early_when_claim_loses_race(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _run_import_job(claimed=False, monkeypatch=monkeypatch)

    assert session.committed is False
    assert session.flushed is False
    assert session.added == []


def test_run_claims_inserts_and_logs_activity(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _run_import_job(claimed=True, monkeypatch=monkeypatch)

    assert session.committed is True
    log = next(obj for obj in session.added if type(obj).__name__ == "ActivityLog")
    assert log.metadata_ == {"processed": 1, "failed": 0}
    assert log.description.startswith("Imported 1 lead(s)")
