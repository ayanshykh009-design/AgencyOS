"""v1 router aggregation.

Every feature router is included here exactly once, then mounted in
app/main.py under the API_V1_PREFIX.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    activity,
    agents,
    ai,
    approvals,
    assignment,
    audit,
    auth,
    automation_control,
    communications,
    conversations,
    credentials,
    dashboard,
    deliveries,
    exports,
    founder,
    founder_chat,
    growth,
    health,
    imports,
    intelligence,
    lead_sources,
    leads,
    memory,
    monitoring,
    notes,
    notifications,
    outreach,
    pipeline,
    provider_usage,
    research,
    search,
    tasks,
    teams,
    users,
    webhooks,
    workflow_events,
    workflow_executions,
    workflow_triggers,
    workflows,
)

api_router = APIRouter()

# Operational endpoints.
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(monitoring.router, prefix="/monitoring", tags=["monitoring"])

# Authentication.
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

# Core CRM.
api_router.include_router(leads.router, prefix="/leads", tags=["leads"])
api_router.include_router(lead_sources.router, prefix="/lead-sources", tags=["lead-sources"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(teams.router, prefix="/teams", tags=["teams"])
api_router.include_router(assignment.router, prefix="/assignment", tags=["assignment"])
api_router.include_router(pipeline.router, prefix="/pipeline", tags=["pipeline"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(notes.router, prefix="/notes", tags=["notes"])
api_router.include_router(outreach.router, prefix="/outreach", tags=["outreach"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])

# Automation: workflows, triggers, executions, events, credentials, control.
api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
api_router.include_router(
    workflow_triggers.router, prefix="/workflow-triggers", tags=["workflow-triggers"]
)
api_router.include_router(
    workflow_executions.router, prefix="/workflow-executions", tags=["workflow-executions"]
)
api_router.include_router(
    workflow_events.router, prefix="/workflow-events", tags=["workflow-events"]
)
api_router.include_router(credentials.router, prefix="/credentials", tags=["credentials"])
api_router.include_router(automation_control.router, prefix="/automation", tags=["automation"])

# Analytics & reporting.
api_router.include_router(imports.router, prefix="/imports", tags=["imports"])
api_router.include_router(provider_usage.router, prefix="/usage", tags=["usage"])
api_router.include_router(activity.router, prefix="/activity", tags=["activity"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(exports.router, prefix="/exports", tags=["exports"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(research.router, prefix="/research", tags=["research"])

# AI automation & per-org AI settings.
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])

# Phase 5D AI Intelligence Layer.
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(memory.router, prefix="/memory", tags=["memory"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(approvals.router, prefix="/approvals", tags=["approvals"])
api_router.include_router(deliveries.router, prefix="/deliveries", tags=["deliveries"])
api_router.include_router(founder.router, prefix="/founder", tags=["founder"])
api_router.include_router(founder_chat.router, prefix="/founder", tags=["founder-assistant"])
api_router.include_router(growth.router, prefix="/growth", tags=["growth"])
api_router.include_router(intelligence.router, prefix="/intelligence", tags=["intelligence"])
api_router.include_router(communications.router, prefix="/communications", tags=["communications"])

# External system ingestion (n8n / contact forms) — no user session.
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
