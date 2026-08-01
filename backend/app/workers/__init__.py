"""Workers package: background / async task processing.

Intended for long-running jobs: email sends, enrichment, campaign execution.
Plan to plug a task queue here (Celery + Redis, RQ, or ARQ) once needed.

Keep workers dependency-injected (import services, never endpoints).
"""
