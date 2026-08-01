"""Models package: ORM definitions.

Each model here mirrors a table defined in database/ (the source of truth for
the schema). Add domain models (e.g. User, Campaign, Prospect, OutreachSequence)
as features are designed.

Rule: models stay dumb (fields + relationships only); behavior lives in services.
"""
from app.models.base import Base

__all__ = ["Base"]
