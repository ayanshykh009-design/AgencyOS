"""Application-relative URL validation for client-supplied deep links.

Notifications and deliveries carry an optional ``action_url`` that the
dashboard renders as a clickable link. A client-supplied value must never
navigate the user outside the application, so the accepted grammar is
deliberately narrow:

* exactly one leading ``/`` (no scheme, no protocol-relative ``//host``);
* RFC 3986 unreserved + path/query/fragment characters only;
* no backslash anywhere — browser URL parsers treat ``\\`` as ``/``, so
  ``/\\evil.com`` normalizes to ``//evil.com`` (an external origin);
* no ``%`` — percent-encoded variants such as ``%2F%2Fevil.com`` are
  rejected instead of being decoded and re-checked;
* no control characters, whitespace, or Unicode — the frontend route table
  is ASCII, so anything outside the grammar is malformed for this use.

The validator is intentionally allow-list based: anything it does not
explicitly accept is unsafe by default.
"""

from __future__ import annotations

import re

# RFC 3986 pchar + "/" + "?" + "#": enough for app-relative paths with query
# strings and fragments. Excludes "\", "%", whitespace, and control chars.
_APP_RELATIVE_URL_RE = re.compile(r"^/[A-Za-z0-9\-._~!$&'()*+,;=:@/?#]*$")


def is_safe_app_relative_url(value: object) -> bool:
    """Return True only for a safe application-relative destination."""
    if not isinstance(value, str):
        return False
    if not value.startswith("/") or value.startswith("//"):
        return False
    # fullmatch (not $-terminated match): Python's ``$`` also matches just
    # before a trailing newline, which would let "/inbox\n" slip through.
    return _APP_RELATIVE_URL_RE.fullmatch(value) is not None
