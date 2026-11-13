"""Unit tests for the application-relative action_url validator.

The grammar is allow-list only: a single leading ``/``, RFC 3986
path/query/fragment characters, no backslashes (browser URL parsers treat
``\\`` as ``/`` so ``/\\evil.com`` becomes ``//evil.com``), no percent
encoding (blocks ``%2F%2F`` variants), no control characters, no scheme.
"""

import pytest

from app.core.url_validation import is_safe_app_relative_url


@pytest.mark.parametrize(
    "value",
    [
        "/",
        "/inbox",
        "/approvals/1",
        "/leads/00000000-0000-0000-0000-000000000001",
        "/inbox?tab=unread",
        "/inbox?tab=unread#anchor",
        "/a/b-c_d~e",
        "/a+b=c&d=e$f,g:h;i@j?k#l",
    ],
)
def test_accepts_application_relative_paths(value: str) -> None:
    assert is_safe_app_relative_url(value) is True


@pytest.mark.parametrize(
    "value",
    [
        # External absolute URLs / unexpected schemes.
        "https://attacker.example/phish",
        "http://attacker.example",
        "javascript:alert(1)",
        "data:text/html,hello",
        "mailto:attacker@example.com",
        # Protocol-relative and backslash confusion.
        "//attacker.example/phish",
        "/\\attacker.example",
        "\\attacker.example",
        "/a\\b",
        # Percent-encoded external variants.
        "/%2F%2Fattacker.example",
        "%2F%2Fattacker.example",
        "/inbox%00",
        # Control characters / whitespace / malformed.
        "/inbox\n",
        "/inbox\r",
        "/inbox\t",
        "/inbox\x00",
        "/inbox zero",
        "",
        "inbox",
        " /inbox",
        # Non-string values are unsafe by default.
        None,
        b"/inbox",
        123,
        ["inbox"],
    ],
)
def test_rejects_everything_outside_the_app(value: object) -> None:
    assert is_safe_app_relative_url(value) is False
