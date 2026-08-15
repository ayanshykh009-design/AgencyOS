"""Workers package: background / async task processing.

- ``import_worker``: CSV import processing (validates rows, inserts leads,
  records per-row errors). Runs in the request's background task today; the
  worker is written to move to a real queue (Celery/ARQ/RQ) without changes.
- ``research_worker``: AI lead research (web search + signal extraction).
  Runs via FastAPI ``BackgroundTasks`` today; queue-ready like ImportWorker.
- ``execution_worker``: drains the workflow execution queue (queued ->
  running -> succeeded/failed), re-queues due retries, and times out stuck
  executions. Runs as a standalone loop or one-off sweep.
- ``approval_gate_worker``: applies terminal approval decisions to gated
  workflow executions. Runs as a standalone loop.
- ``delivery_worker``: drains the delivery outbox (queued ->
  processing -> delivered/failed), re-queues due retries, and recovers stuck
  deliveries. Runs as a standalone loop or one-off sweep.
- ``agent_worker``: drains the agent run queue through the runtime (queued ->
  running -> succeeded/failed/cancelled), applies in-flight cancellations, and
  re-converges stuck runs. No-op while ``AGENT_RUNTIME_ENABLED`` is false.
- ``retention_worker``: chunked pruning of expired execution telemetry
  (execution_events + dead worker heartbeats). Runs as a standalone loop.
- ``intelligence_triage_worker``: materializes the M9 founder intelligence
  signal feed (deterministic per-org sweeps over M7/M8 output). Runs as a
  standalone loop. Gated on ``INTELLIGENCE_TRIAGE_ENABLED``.

Keep workers dependency-injected (import repositories, never endpoints).
"""

from app.workers.agent_worker import AgentWorker
from app.workers.approval_gate_worker import ApprovalGateWorker
from app.workers.delivery_worker import DeliveryWorker
from app.workers.execution_worker import ExecutionWorker
from app.workers.import_worker import ImportWorker
from app.workers.intelligence_triage_worker import IntelligenceTriageWorker
from app.workers.research_worker import ResearchWorker
from app.workers.retention_worker import RetentionWorker

__all__ = [
    "AgentWorker",
    "ApprovalGateWorker",
    "DeliveryWorker",
    "ExecutionWorker",
    "ImportWorker",
    "IntelligenceTriageWorker",
    "ResearchWorker",
    "RetentionWorker",
]
