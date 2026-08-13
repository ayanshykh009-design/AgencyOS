import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, setSession } from "@/lib/session";
import {
  createScenario,
  deleteScenario,
  getAnalysis,
  getHealthWeights,
  getScenario,
  listAnalyses,
  listRecommendations,
  listScenarios,
  recommendationCounts,
  runAllAnalyses,
  runAnalysis,
  runForecast,
  updateRecommendation,
  upsertHealthWeights,
} from "@/services/growth";
import type { GrowthAnalysis, GrowthRecommendation, GrowthScenario, User } from "@/types";

const USER: User = {
  id: "11111111-1111-1111-1111-111111111111",
  organization_id: "22222222-2222-2222-2222-222222222222",
  email: "owner@example.com",
  full_name: "Owner",
  role: "owner",
  is_active: true,
  last_login_at: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

const ANALYSIS: GrowthAnalysis = {
  id: "33333333-3333-3333-3333-333333333333",
  organization_id: USER.organization_id,
  analysis_type: "kpis",
  period_start: "2026-07-01T00:00:00Z",
  period_end: "2026-07-31T00:00:00Z",
  health_score: 71.5,
  summary: "KPIs are healthy.",
  details: {},
  evidence: [],
  weights: {},
  metrics_used: [],
  status: "completed",
  error: null,
  generated_by: "user",
  generated_at: "2026-08-01T00:00:00Z",
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

const RECOMMENDATION: GrowthRecommendation = {
  id: "44444444-4444-4444-4444-444444444444",
  organization_id: USER.organization_id,
  recommendation_type: "bottleneck",
  priority: "high",
  confidence: "medium",
  status: "active",
  title: "Follow up faster",
  summary: "Slower follow-ups correlate with lower conversion.",
  rationale: null,
  action_type: null,
  action_payload: {},
  source_analysis_id: null,
  evidence: [],
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

const SCENARIO: GrowthScenario = {
  id: "55555555-5555-5555-5555-555555555555",
  organization_id: USER.organization_id,
  forecast_id: null,
  name: "Double leads",
  description: null,
  assumption_deltas: { new_leads_delta: 2.0 },
  result: { projected_revenue: 280000 },
  created_by_user_id: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function noContentResponse(): Response {
  return new Response(null, { status: 204 });
}

describe("growth service", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    clearSession();
    setSession({ accessToken: "access-123", refreshToken: "r", expiresIn: 3600, user: USER });
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    clearSession();
  });

  it("listAnalyses encodes filters and query params", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [ANALYSIS], total: 1 }));

    const page = await listAnalyses({ analysisType: "kpis", status: "completed", limit: 10 });

    expect(page.total).toBe(1);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/growth/analyses");
    expect(url).toContain("analysis_type=kpis");
    expect(url).toContain("status=completed");
    expect(url).toContain("limit=10");
  });

  it("getAnalysis fetches one analysis", async () => {
    fetchMock.mockResolvedValue(jsonResponse(ANALYSIS));

    const analysis = await getAnalysis(ANALYSIS.id);

    expect(analysis.analysis_type).toBe("kpis");
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/growth/analyses/${ANALYSIS.id}`);
  });

  it("runAnalysis POSTs the requested engine and window", async () => {
    fetchMock.mockResolvedValue(jsonResponse(ANALYSIS));

    const result = await runAnalysis({
      analysis_type: "kpis",
      period_start: ANALYSIS.period_start,
      period_end: ANALYSIS.period_end,
    });

    expect(result.id).toBe(ANALYSIS.id);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/growth/analyses/run");
    expect(init.method).toBe("POST");
    expect(init.body).toContain('"analysis_type":"kpis"');
    expect(init.body).toContain('"period_end":"2026-07-31T00:00:00Z"');
  });

  it("runAllAnalyses POSTs the full run", async () => {
    fetchMock.mockResolvedValue(jsonResponse([ANALYSIS]));

    const results = await runAllAnalyses({
      period_start: ANALYSIS.period_start,
      period_end: ANALYSIS.period_end,
    });

    expect(results).toHaveLength(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/growth/analyses/run-all");
    expect(init.method).toBe("POST");
  });

  it("listRecommendations encodes filters", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [RECOMMENDATION], total: 1 }));

    const page = await listRecommendations({ status: "active", priority: "high" });

    expect(page.items[0].title).toBe("Follow up faster");
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/growth/recommendations");
    expect(url).toContain("status=active");
    expect(url).toContain("priority=high");
  });

  it("recommendationCounts fetches per-status counts", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ active: 3, acknowledged: 1, applied: 0, dismissed: 2 })
    );

    const counts = await recommendationCounts();

    expect(counts.active).toBe(3);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/growth/recommendations/counts");
  });

  it("updateRecommendation PATCHes status and priority", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...RECOMMENDATION, status: "applied" }));

    const result = await updateRecommendation(RECOMMENDATION.id, {
      status: "applied",
      priority: "medium",
    });

    expect(result.status).toBe("applied");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/growth/recommendations/${RECOMMENDATION.id}`);
    expect(init.method).toBe("PATCH");
    expect(init.body).toContain('"status":"applied"');
    expect(init.body).toContain('"priority":"medium"');
  });

  it("listScenarios and getScenario fetch saved scenarios", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ items: [SCENARIO], total: 1 }))
      .mockResolvedValueOnce(jsonResponse(SCENARIO));

    const page = await listScenarios({ limit: 25 });
    expect(page.items[0].name).toBe("Double leads");
    const [listUrl] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(listUrl).toContain("/growth/scenarios");
    expect(listUrl).toContain("limit=25");

    const scenario = await getScenario(SCENARIO.id);
    expect(scenario.name).toBe("Double leads");
    const [detailUrl] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(detailUrl).toContain(`/growth/scenarios/${SCENARIO.id}`);
  });

  it("createScenario POSTs deltas and window", async () => {
    fetchMock.mockResolvedValue(jsonResponse(SCENARIO));

    const result = await createScenario({
      name: "Double leads",
      assumption_deltas: { new_leads_delta: 2.0 },
      period_start: "2026-07-01T00:00:00Z",
      period_end: "2026-07-31T00:00:00Z",
    });

    expect(result.id).toBe(SCENARIO.id);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/growth/scenarios");
    expect(init.method).toBe("POST");
    expect(init.body).toContain('"name":"Double leads"');
    expect(init.body).toContain('"new_leads_delta":2');
  });

  it("deleteScenario DELETEs and tolerates a 204", async () => {
    fetchMock.mockResolvedValue(noContentResponse());

    await expect(deleteScenario(SCENARIO.id)).resolves.toBeUndefined();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/growth/scenarios/${SCENARIO.id}`);
    expect(init.method).toBe("DELETE");
  });

  it("health-weights GET returns the active weight set", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ version: 2, weights: { pipeline_health: 0.3 }, is_default: false })
    );

    const weights = await getHealthWeights();

    expect(weights.version).toBe(2);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/growth/health-weights");
  });

  it("upsertHealthWeights POSTs the new weight set", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        id: "77777777-7777-7777-7777-777777777777",
        organization_id: USER.organization_id,
        version: 3,
        weights: { activity_level: 0.2 },
        is_active: true,
        created_at: "2026-08-01T00:00:00Z",
        updated_at: "2026-08-01T00:00:00Z",
      })
    );

    const weights = await upsertHealthWeights({ weights: { activity_level: 0.2 } });

    expect(weights.version).toBe(3);
    expect(weights.is_active).toBe(true);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/growth/health-weights");
    expect(init.method).toBe("POST");
    expect(init.body).toContain('"activity_level":0.2');
  });

  it("runForecast POSTs method and window", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        id: "66666666-6666-6666-6666-666666666666",
        organization_id: USER.organization_id,
        forecast_type: "revenue",
        horizon_start: "2026-08-01T00:00:00Z",
        horizon_end: "2026-08-31T00:00:00Z",
        total_value: 280000,
        confidence_low: null,
        confidence_high: null,
        method: "linear_trend",
        base_period_start: null,
        base_period_end: null,
        point_estimate: 280000,
        lower_bound: null,
        upper_bound: null,
        series: [],
        errors: {},
        generated_at: "2026-08-01T00:00:00Z",
        created_at: "2026-08-01T00:00:00Z",
        updated_at: "2026-08-01T00:00:00Z",
      })
    );

    const forecast = await runForecast({
      method: "linear_trend",
      period_start: ANALYSIS.period_start,
      period_end: ANALYSIS.period_end,
      horizon_start: "2026-08-01T00:00:00Z",
      horizon_end: "2026-08-31T00:00:00Z",
    });

    expect(forecast.method).toBe("linear_trend");
    expect(forecast.point_estimate).toBe(280000);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/growth/forecasts/run");
    expect(init.method).toBe("POST");
    expect(init.body).toContain('"method":"linear_trend"');
  });
});
