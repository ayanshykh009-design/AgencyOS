"""Repositories package: data-access layer.

The ONLY place that talks to the persistence layer (SQLAlchemy / Supabase).
Routers and services never touch SQL or ORM sessions directly.

Naming convention: <domain>_repository.py (e.g. prospect_repository.py).
"""
