// Growth intelligence service: deterministic analyses, recommendations,
// scenarios, health weights, and forecast generation.
import { apiFetch } from "@/lib/api-client";
import type {
  GrowthAnalysis,
  GrowthAnalysisRunAllInput,
  GrowthAnalysisRunInput,
  GrowthAnalysisType,
  GrowthForecast,
  GrowthForecastRunInput,
  GrowthHealthWeight,
  GrowthHealthWeightCreateInput,
  GrowthHealthWeights,
  GrowthRecommendation,
  GrowthRecommendationUpdateInput,
  GrowthScenario,
  GrowthScenarioCreateInput,
  Page,
  RecommendationCounts,
  RecommendationPriority,
  RecommendationStatus,
} from "@/types";

export interface GrowthAnalysisQuery {
  analysisType?: GrowthAnalysisType;
  status?: "completed" | "failed";
  start?: string;
  end?: string;
  limit?: number;
  offset?: number;
}

export interface GrowthRecommendationQuery {
  status?: RecommendationStatus;
  priority?: RecommendationPriority;
  limit?: number;
  offset?: number;
}

export interface GrowthScenarioQuery {
  forecastId?: string;
  limit?: number;
  offset?: number;
}

export async function listAnalyses(query: GrowthAnalysisQuery = {}): Promise<Page<GrowthAnalysis>> {
  const params = new URLSearchParams();
  if (query.analysisType) params.set("analysis_type", query.analysisType);
  if (query.status) params.set("status", query.status);
  if (query.start) params.set("start", query.start);
  if (query.end) params.set("end", query.end);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();
  return apiFetch<Page<GrowthAnalysis>>(`/growth/analyses${qs ? `?${qs}` : ""}`);
}

export async function getAnalysis(analysisId: string): Promise<GrowthAnalysis> {
  return apiFetch<GrowthAnalysis>(`/growth/analyses/${analysisId}`);
}

export async function runAnalysis(input: GrowthAnalysisRunInput): Promise<GrowthAnalysis> {
  return apiFetch<GrowthAnalysis>("/growth/analyses/run", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function runAllAnalyses(input: GrowthAnalysisRunAllInput): Promise<GrowthAnalysis[]> {
  return apiFetch<GrowthAnalysis[]>("/growth/analyses/run-all", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function listRecommendations(
  query: GrowthRecommendationQuery = {}
): Promise<Page<GrowthRecommendation>> {
  const params = new URLSearchParams();
  if (query.status) params.set("status", query.status);
  if (query.priority) params.set("priority", query.priority);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();
  return apiFetch<Page<GrowthRecommendation>>(`/growth/recommendations${qs ? `?${qs}` : ""}`);
}

export async function recommendationCounts(): Promise<RecommendationCounts> {
  return apiFetch<RecommendationCounts>("/growth/recommendations/counts");
}

export async function updateRecommendation(
  recommendationId: string,
  input: GrowthRecommendationUpdateInput
): Promise<GrowthRecommendation> {
  return apiFetch<GrowthRecommendation>(`/growth/recommendations/${recommendationId}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export async function listScenarios(
  query: GrowthScenarioQuery = {}
): Promise<Page<GrowthScenario>> {
  const params = new URLSearchParams();
  if (query.forecastId) params.set("forecast_id", query.forecastId);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();
  return apiFetch<Page<GrowthScenario>>(`/growth/scenarios${qs ? `?${qs}` : ""}`);
}

export async function getScenario(scenarioId: string): Promise<GrowthScenario> {
  return apiFetch<GrowthScenario>(`/growth/scenarios/${scenarioId}`);
}

export async function createScenario(input: GrowthScenarioCreateInput): Promise<GrowthScenario> {
  return apiFetch<GrowthScenario>("/growth/scenarios", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function deleteScenario(scenarioId: string): Promise<void> {
  await apiFetch<void>(`/growth/scenarios/${scenarioId}`, { method: "DELETE" });
}

export async function getHealthWeights(): Promise<GrowthHealthWeights> {
  return apiFetch<GrowthHealthWeights>("/growth/health-weights");
}

export async function upsertHealthWeights(
  input: GrowthHealthWeightCreateInput
): Promise<GrowthHealthWeight> {
  return apiFetch<GrowthHealthWeight>("/growth/health-weights", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function runForecast(input: GrowthForecastRunInput): Promise<GrowthForecast> {
  return apiFetch<GrowthForecast>("/growth/forecasts/run", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
