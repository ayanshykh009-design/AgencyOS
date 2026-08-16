"""Test-only PostgreSQL connection helpers.

Kept out of application code on purpose. These helpers let integration/e2e
fixtures open a per-test database while PRESERVING the original credentials.

NOTE: ``psycopg2.connection.get_dsn_parameters()`` intentionally strips the
password from the returned dict. Cloning an admin connection through it and
passing the result to ``psycopg2.connect(**params)`` therefore opens the
per-test database WITHOUT a password (``fe_sendauth: no password supplied``).
Always swap only the database name on the original authenticated DSN instead.
"""
from urllib.parse import urlparse, urlunparse


def dsn_for_database(url: str, dbname: str) -> str:
    """Return ``url`` with only the database (path) component replaced.

    The scheme, credentials, host, and port are preserved verbatim, so the
    resulting connection still authenticates with the password carried by
    ``url``. This is the safe alternative to ``get_dsn_parameters()`` for
    cloning a connection to a different database on the same server.
    """
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path=f"/{dbname}"))
