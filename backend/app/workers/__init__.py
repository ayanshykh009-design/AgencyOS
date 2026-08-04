"""Workers package: background / async task processing.

- ``import_worker``: CSV import processing (validates rows, inserts leads,
  records per-row errors). Runs in the request's background task today; the
  worker is written to move to a real queue (Celery/ARQ/RQ) without changes.
- ``research_worker``: AI lead research (web search + signal extraction).
  Runs via FastAPI ``BackgroundTasks`` today; queue-ready like ImportWorker.
- ``execution_worker``: drains the workflow execution queue (queued ->
  running -> succeeded/failed), re-queues due retries, and times out stuck
  executions. Runs as a standalone loop or one-off sweep.

Keep workers dependency-injected (import repositories, never endpoints).
"""
from app.workers.execution_worker import ExecutionWorker
from app.workers.import_worker import ImportWorker
from app.workers.research_worker import ResearchWorker

__all__ = ["ExecutionWorker", "ImportWorker", "ResearchWorker"]
