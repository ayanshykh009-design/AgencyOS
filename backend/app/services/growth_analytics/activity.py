"""Activity engine — deterministic activity/outreach analysis (M7).

Pure function over a :class:`GrowthContext`. Summarizes outreach attempts
(by status and channel), task completion, and the activity-log event mix for
the window.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from app.services.growth_analytics.datatypes import GrowthContext

_SENT_STATUSES = ("sent", "delivered", "manually_sent")
_REPLIED_STATUSES = ("replied",)
_FAILED_STATUSES = ("failed",)


def compute_activity(context: GrowthContext) -> dict:
    """Activity snapshot for the window."""
    total_attempts = len(context.attempts)
    sent = sum(1 for attempt in context.attempts if attempt.status in _SENT_STATUSES)
    replied = sum(1 for attempt in context.attempts if attempt.status in _REPLIED_STATUSES)
    failed = sum(1 for attempt in context.attempts if attempt.status in _FAILED_STATUSES)
    reply_rate = replied / sent if sent else 0.0

    channel_sent: Counter = Counter()
    channel_replied: Counter = Counter()
    for attempt in context.attempts:
        channel = attempt.channel or "unknown"
        if attempt.status in _SENT_STATUSES:
            channel_sent[channel] += 1
        if attempt.status in _REPLIED_STATUSES:
            channel_replied[channel] += 1

    by_channel = [
        {
            "channel": channel,
            "sent": channel_sent[channel],
            "replied": channel_replied[channel],
            "reply_rate": round(channel_replied[channel] / channel_sent[channel], 4)
            if channel_sent[channel]
            else 0.0,
        }
        for channel in sorted(set(channel_sent) | set(channel_replied))
    ]

    tasks_created = len(context.tasks)
    tasks_completed = sum(1 for task in context.tasks if task.completed_at is not None)
    completion_rate = tasks_completed / tasks_created if tasks_created else 0.0

    event_counts: Counter = Counter(event.event_type for event in context.activity)
    top_events = sorted(
        [{"event_type": event_type, "count": count} for event_type, count in event_counts.items()],
        key=lambda item: item["count"],
        reverse=True,
    )[:8]

    return {
        "outreach": {
            "total_attempts": total_attempts,
            "sent": sent,
            "replied": replied,
            "failed": failed,
            "reply_rate": round(reply_rate, 4),
            "by_channel": by_channel,
        },
        "tasks": {
            "created": tasks_created,
            "completed": tasks_completed,
            "open": tasks_created - tasks_completed,
            "completion_rate": round(completion_rate, 4),
        },
        "events": {
            "total": len(context.activity),
            "top": top_events,
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
