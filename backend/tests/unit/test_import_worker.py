"""Unit tests for the CSV import worker's pure parsing/normalization.

Only the database-free helpers are exercised here (``_parse_csv``,
``_parse_row``, ``_digits``). The full job run (savepoints, dedup, chunking)
is covered by the integration suite against a real PostgreSQL server.
"""
from __future__ import annotations

from app.workers.import_worker import _digits, _parse_csv, _parse_row


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
