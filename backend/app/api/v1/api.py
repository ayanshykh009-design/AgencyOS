"""v1 router aggregation.

Every feature router is included here exactly once, then mounted in
app/main.py under the API_V1_PREFIX.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    activity,
    ai,
    auth,
    conversations,
    dashboard,
    health,
    imports,
    lead_sources,
    leads,
    outreach,
    provider_usage,
    research,
    users,
    webhooks,
)

api_router = APIRouter()

# Operational endpoints.
api_router.include_router(health.router, prefix="/health", tags=["health"])

# Authentication.
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

# Core CRM.
api_router.include_router(leads.router, prefix="/leads", tags=["leads"])
api_router.include_router(lead_sources.router, prefix="/lead-sources", tags=["lead-sources"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(outreach.router, prefix="/outreach", tags=["outreach"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])

# Automation & analytics.
api_router.include_router(imports.router, prefix="/imports", tags=["imports"])
api_router.include_router(provider_usage.router, prefix="/usage", tags=["usage"])
api_router.include_router(activity.router, prefix="/activity", tags=["activity"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(research.router, prefix="/research", tags=["research"])

# AI automation & per-org AI settings.
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])

# External system ingestion (n8n / contact forms) — no user session.
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
