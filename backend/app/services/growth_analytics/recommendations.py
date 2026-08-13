"""Recommendations engine — deterministic recommendation generation (M7).

Pure function over engine results (pipeline/conversion/funnel/bottleneck/
opportunity/activity/trend/revenue/health). Emits actionable recommendations
with deterministic priority/status and an associated target metric, keyed to
the analysis results so they persist alongside a growth analysis.
"""

from __future__ import annotations

from datetime import datetime


def generate_recommendations(results: dict) -> list[dict]:
    """Generate deterministic recommendations from a full analysis result set."""
    recommendations: list[dict] = []

    _recommend_bottlenecks(results, recommendations)
    _recommend_conversion(results, recommendations)
    _recommend_activity(results, recommendations)
    _recommend_trends(results, recommendations)
    _recommend_pipeline(results, recommendations)
    _recommend_health(results, recommendations)

    if not recommendations:
        recommendations.append(
            {
                "type": "maintain",
                "priority": "low",
                "status": "active",
                "summary": "No urgent growth blockers detected.",
                "description": (
                    "Current funnel, conversion, and activity metrics are within healthy bounds."
                ),
                "action": "Continue current cadence and re-run the growth analysis next period.",
                "metric_target": "growth_score",
            }
        )

    for recommendation in recommendations:
        recommendation["generated_at"] = datetime.utcnow().isoformat() + "Z"

    return recommendations


def _recommend_bottlenecks(results: dict, out: list[dict]) -> None:
    for item in results.get("bottlenecks", {}).get("bottlenecks", [])[:2]:
        if item.get("severity") in ("high", "medium"):
            out.append(
                {
                    "type": "bottleneck",
                    "priority": "high" if item["severity"] == "high" else "medium",
                    "status": "active",
                    "summary": f"Leads stall at '{item['stage']}'.",
                    "description": (
                        f"{item['dropoff']} of {item['entered']} leads dropped before "
                        f"{item['stage']} (dropoff ratio {round(item['dropoff_ratio'] * 100, 1)}%)."
                    ),
                    "action": (
                        f"Review the {item['stage']} workflow and follow-up cadence; "
                        "re-run the growth analysis after changes."
                    ),
                    "metric_target": f"stage:{item['stage_id']}",
                }
            )


def _recommend_conversion(results: dict, out: list[dict]) -> None:
    conversion = results.get("conversion", {})
    win_rate = conversion.get("win_rate", 0.0)
    if win_rate and win_rate < 0.2:
        out.append(
            {
                "type": "conversion",
                "priority": "high",
                "status": "active",
                "summary": "Win rate is below 20%.",
                "description": (
                    f"Historical win rate is {round(win_rate * 100, 1)}%; review deal "
                    "qualification and proposal quality."
                ),
                "action": "Audit lost deals and tighten qualification criteria.",
                "metric_target": "win_rate",
            }
        )
    reply_rate = conversion.get("reply_rate")
    if reply_rate is None:
        reply_rate = results.get("activity", {}).get("outreach", {}).get("reply_rate")
    if reply_rate is not None and reply_rate < 0.05:
        out.append(
            {
                "type": "conversion",
                "priority": "medium",
                "status": "active",
                "summary": "Outreach reply rate is very low.",
                "description": (
                    f"Reply rate is {round(reply_rate * 100, 1)}%; messaging may need "
                    "a sequence refresh."
                ),
                "action": "Refresh outreach templates and test new angles.",
                "metric_target": "reply_rate",
            }
        )


def _recommend_activity(results: dict, out: list[dict]) -> None:
    activity = results.get("activity", {}).get("outreach", {})
    sent = activity.get("sent", 0)
    if sent == 0:
        out.append(
            {
                "type": "activity",
                "priority": "high",
                "status": "active",
                "summary": "No outreach was sent this period.",
                "description": "The pipeline depends on fresh outreach to stay full.",
                "action": "Launch a new outreach campaign immediately.",
                "metric_target": "outreach_sent",
            }
        )


def _recommend_trends(results: dict, out: list[dict]) -> None:
    trend = results.get("trends", {})
    revenue = trend.get("revenue", {})
    if revenue.get("trend") == "down":
        out.append(
            {
                "type": "trend",
                "priority": "high",
                "status": "active",
                "summary": "Revenue is trending downward.",
                "description": (
                    f"Revenue slope is {revenue.get('slope', 0.0)} over "
                    f"{revenue.get('count', 0)} periods."
                ),
                "action": "Investigate root cause and prioritize recovery initiatives.",
                "metric_target": "revenue",
            }
        )
    leads = trend.get("leads", {})
    if leads.get("trend") == "down":
        out.append(
            {
                "type": "trend",
                "priority": "medium",
                "status": "active",
                "summary": "Inbound lead volume is declining.",
                "description": f"Lead slope is {leads.get('slope', 0.0)}; acquisition is slowing.",
                "action": "Boost lead generation and refresh acquisition channels.",
                "metric_target": "new_leads",
            }
        )


def _recommend_health(results: dict, out: list[dict]) -> None:
    health = results.get("health", {})
    score = health.get("score")
    if score is not None and score < 40:
        out.append(
            {
                "type": "health",
                "priority": "high",
                "status": "active",
                "summary": "Growth health score is critically low.",
                "description": (
                    f"Composite growth health is {score} out of 100; "
                    "address the weakest dimension first."
                ),
                "action": "Run a full growth analysis and act on its recommendations.",
                "metric_target": "growth_score",
            }
        )


def _recommend_pipeline(results: dict, out: list[dict]) -> None:
    revenue = results.get("revenue", {})
    coverage = revenue.get("pipeline_coverage")
    if coverage is not None and coverage < 3.0:
        out.append(
            {
                "type": "pipeline",
                "priority": "medium",
                "status": "active",
                "summary": "Pipeline coverage is below 3x.",
                "description": (
                    f"Weighted pipeline is {round(coverage, 2)}x current revenue; "
                    "deal flow may not sustain targets."
                ),
                "action": "Increase outreach volume and stage advancement.",
                "metric_target": "pipeline_coverage",
            }
        )
