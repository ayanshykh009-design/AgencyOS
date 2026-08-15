// Founder Intelligence & Growth Triage (M9) types — mirror backend
// app/schemas/intelligence_signal.py. Keep in sync with the API.

/** What kind of business signal (backend SignalCategory). */
export type SignalCategory =
  | "growth_recommendation"
  | "business_insight"
  | "pipeline_risk"
  | "pipeline_opportunity"
  | "growth_anomaly"
  | "founder_briefing";

/** Which source produced the signal (backend SignalSourceType). */
export type SignalSourceType =
  "growth_recommendation" | "business_insight" | "growth_analysis" | "pipeline_fact" | "briefing";

/** Triage lifecycle of a signal (backend IntelligenceSignalStatus). */
export type IntelligenceSignalStatus = "active" | "acknowledged" | "dismissed" | "superseded";

/** Urgency of the underlying finding (backend IntelligenceSignalSeverity). */
export type IntelligenceSignalSeverity = "info" | "low" | "medium" | "high" | "critical";

/** Qualitative confidence in the signal itself (backend IntelligenceConfidence). */
export type IntelligenceConfidence = "low" | "medium" | "high";

/** A single triaged signal (backend IntelligenceSignalRead). */
export interface IntelligenceSignal {
  id: string;
  organization_id: string;
  signal_category: SignalCategory;
  source_type: SignalSourceType;
  source_row_id: string | null;
  title: string;
  summary: string;
  severity: IntelligenceSignalSeverity;
  business_impact: Record<string, unknown>;
  priority_score: number;
  priority_components: Record<string, unknown>;
  evidence: Array<Record<string, unknown>>;
  recommended_next_step: string | null;
  confidence: IntelligenceConfidence;
  status: IntelligenceSignalStatus;
  first_seen_at: string;
  last_triaged_at: string | null;
  acknowledged_by_user_id: string | null;
  acknowledged_at: string | null;
  last_notified_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Paginated signal list (backend IntelligenceSignalListResponse). */
export interface IntelligenceSignalListResponse {
  items: IntelligenceSignal[];
  total: number;
}

/** Roll-up counts (backend IntelligenceSignalSummary). */
export interface IntelligenceSignalSummary {
  active: number;
  acknowledged: number;
  dismissed: number;
  superseded: number;
  high_priority: number;
  medium_priority: number;
  low_priority: number;
  highest_priority_score: number | null;
}

/** Manual triage trigger result (backend POST /intelligence/triage/run). */
export interface IntelligenceTriageRunResult {
  candidates: number;
  created: number;
  updated: number;
  superseded: number;
  high_priority: number;
  narrative: string;
}

/** Ack/dismiss payload (backend IntelligenceSignalUpdate). */
export interface IntelligenceSignalUpdate {
  status: IntelligenceSignalStatus;
}
