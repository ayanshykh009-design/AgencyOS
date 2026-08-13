"""Common list pagination schema used by every list endpoint."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Paginated result envelope: items + total match count."""

    items: list[T]
    total: int
