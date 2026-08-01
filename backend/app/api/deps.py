"""Shared FastAPI dependencies.

Dependencies are reusable injectables for route handlers, e.g.:
- `get_db` (async SQLAlchemy session),
- `get_current_user` (JWT auth guard),
- `get_supabase` (Supabase admin client).

Only dependency plumbing belongs here — never business rules.
"""
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

# Re-export for convenient `Annotated` typing in routers.
DbSession = Annotated[AsyncSession, Depends(get_db)]

# Placeholder guards — implement once auth flows are designed:
# CurrentUser = Annotated[User, Depends(get_current_user)]
# SupabaseClient = Annotated[Client, Depends(get_supabase)]
