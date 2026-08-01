"""Workers package: background / async task processing.

- ``import_worker``: CSV import processing (validates rows, inserts leads,
  records per-row errors). Runs in the request's background task today; the
  worker is written to move to a real queue (Celery/ARQ/RQ) without changes.

Keep workers dependency-injected (import repositories, never endpoints).
"""
from app.workers.import_worker import ImportWorker

__all__ = ["ImportWorker"]
