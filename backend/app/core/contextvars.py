"""Request-scoped context variables (contextvars).

Values set here are isolated per async task and automatically propagated
through awaits — safe for concurrent request handling.
"""

from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
