// Growth Intelligence: deterministic analyses, recommendations, scenarios,
// health weights, and forecast generation.
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  ConfirmDialog,
  EmptyState,
  Input,
  PageHeader,
  Select,
  Spinner,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TRow,
} from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import {
  GROWTH_ANALYSIS_STATUS_LABELS,
  GROWTH_ANALYSIS_TYPE_LABELS,
  RECOMMENDATION_PRIORITY_LABELS,
  RECOMMENDATION_STATUS_LABELS,
  formatDateTime,
  formatUsd,
  growthAnalysisStatusTone,
  recommendationPriorityTone,
  recommendationStatusTone,
} from "@/lib/format";
import { can } from "@/lib/permissions";
import {
  createScenario,
  deleteScenario,
  getHealthWeights,
  listAnalyses,
  listRecommendations,
  listScenarios,
  runAllAnalyses,
  runAnalysis,
  runForecast,
  updateRecommendation,
} from "@/services/growth";
import type {
  GrowthAnalysisType,
  GrowthForecast,
  GrowthForecastMethod,
  GrowthScenario,
  RecommendationStatus,
} from "@/types";

const ANALYSIS_TYPE_OPTIONS = Object.entries(GROWTH_ANALYSIS_TYPE_LABELS) as Array<
  [GrowthAnalysisType, string]
>;

const FORECAST_METHOD_OPTIONS: Array<{ value: GrowthForecastMethod; label: string }> = [
  { value: "linear_trend", label: "Linear trend" },
  { value: "moving_average", label: "Moving average" },
  { value: "pipeline_weighted", label: "Pipeline-weighted" },
  { value: "seasonal_naive", label: "Seasonal naive" },
];

const TRIAGE_OPTIONS = Object.entries(RECOMMENDATION_STATUS_LABELS) as Array<
  [RecommendationStatus, string]
>;

function windowStart(iso: string): string {
  return formatDateTime(iso);
}

export function growthErrorMessage(err: unknown): string {
  return err instanceof ApiRequestError ? err.message : "Failed to load growth data";
}

export default function GrowthPage() {
  const session = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [health, setHealth] = useState<{
    version: number;
    weights: Record<string, number>;
    isDefault: boolean;
  } | null>(null);
  const [analyses, setAnalyses] = useState<
    Array<{
      id: string;
      analysis_type: GrowthAnalysisType;
      status: "completed" | "failed";
      period_start: string;
      period_end: string;
      summary: string;
      health_score: number | null;
    }>
  >([]);
  const [recommendations, setRecommendations] = useState<
    Array<{
      id: string;
      recommendation_type: string;
      priority: "high" | "medium" | "low";
      status: RecommendationStatus;
      title: string;
      summary: string;
      created_at: string;
    }>
  >([]);
  const [scenarios, setScenarios] = useState<GrowthScenario[]>([]);
  const [forecast, setForecast] = useState<GrowthForecast | null>(null);

  const [selectedType, setSelectedType] = useState<GrowthAnalysisType>("kpis");
  const [forecastMethod, setForecastMethod] = useState<GrowthForecastMethod>("linear_trend");
  const [scenarioName, setScenarioName] = useState("");
  const [scenarioDeltas, setScenarioDeltas] = useState('{\n  "new_leads_delta": 2.0\n}');
  const [deleteTarget, setDeleteTarget] = useState<GrowthScenario | null>(null);

  const reload = useCallback(() => {
    getHealthWeights()
      .then((weights) => {
        setHealth({
          version: weights.version,
          weights: weights.weights,
          isDefault: weights.is_default,
        });
      })
      .catch(() => {
        setHealth(null);
      });
    listAnalyses({ limit: 20 })
      .then((page) => setAnalyses(page.items))
      .catch(() => setAnalyses([]));
    listRecommendations({ limit: 50 })
      .then((page) => setRecommendations(page.items))
      .catch(() => setRecommendations([]));
    listScenarios({ limit: 50 })
      .then((page) => setScenarios(page.items))
      .catch(() => setScenarios([]));
  }, []);

  useEffect(() => {
    Promise.all([
      getHealthWeights(),
      listAnalyses({ limit: 20 }),
      listRecommendations({ limit: 50 }),
      listScenarios({ limit: 50 }),
    ])
      .then(([weights, analysisPage, recPage, scenarioPage]) => {
        setHealth({
          version: weights.version,
          weights: weights.weights,
          isDefault: weights.is_default,
        });
        setAnalyses(analysisPage.items);
        setRecommendations(recPage.items);
        setScenarios(scenarioPage.items);
      })
      .catch((err: unknown) => setError(growthErrorMessage(err)))
      .finally(() => setLoading(false));
  }, []);

  const window = useMemo(() => {
    const end = new Date();
    const start = new Date(end.getTime() - 30 * 24 * 60 * 60 * 1000);
    return { start: start.toISOString(), end: end.toISOString() };
  }, []);

  const runAction = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      reload();
    } catch (err) {
      setError(growthErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const runForecastAction = () => {
    setBusy(true);
    setError(null);
    runForecast({
      method: forecastMethod,
      period_start: window.start,
      period_end: window.end,
      horizon_start: window.end,
      horizon_end: new Date(
        new Date(window.end).getTime() + 30 * 24 * 60 * 60 * 1000
      ).toISOString(),
    })
      .then((result) => {
        setForecast(result);
        reload();
      })
      .catch((err: unknown) => setError(growthErrorMessage(err)))
      .finally(() => setBusy(false));
  };

  const triage = (id: string, status: RecommendationStatus) => {
    updateRecommendation(id, { status })
      .then(() => reload())
      .catch((err: unknown) => setError(growthErrorMessage(err)));
  };

  const create = () => {
    if (!scenarioName.trim()) {
      setError("Scenario name is required");
      return;
    }
    let deltas: Record<string, unknown>;
    try {
      deltas = scenarioDeltas.trim() ? (JSON.parse(scenarioDeltas) as Record<string, unknown>) : {};
    } catch {
      setError("Assumption deltas must be valid JSON");
      return;
    }
    runAction(() =>
      createScenario({
        name: scenarioName.trim(),
        description: "Created from the Growth Intelligence page",
        assumption_deltas: deltas,
        period_start: window.start,
        period_end: window.end,
      })
    ).then(() => setScenarioName(""));
  };

  if (!session) return null;
  const canManage = can(session.user.role, "growth_manage");
  const healthScore = analyses.find((a) => a.analysis_type === "health")?.health_score;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Growth Intelligence"
        description="Deterministic analyses of your agency's growth levers, with evidence-backed recommendations and what-if scenarios."
      />

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {loading ? (
        <Spinner label="Loading growth intelligence…" />
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-3">
            <Card>
              <CardHeader title="Health score" description="Latest health analysis" />
              <CardBody>
                <p className="text-3xl font-semibold">
                  {healthScore !== null && healthScore !== undefined
                    ? `${healthScore.toFixed(1)}`
                    : "—"}
                </p>
                <p className="mt-1 text-xs text-gray-500">Weighted 0–100 composite</p>
              </CardBody>
            </Card>

            <Card className="lg:col-span-2">
              <CardHeader
                title="Health weights"
                description={
                  health?.isDefault
                    ? "Using default weights (v0)"
                    : `Weight set v${health?.version}`
                }
              />
              <CardBody>
                {health ? (
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(health.weights).map(([key, value]) => (
                      <Badge key={key} tone="blue">
                        {key}: {value}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500">No weight set configured.</p>
                )}
              </CardBody>
            </Card>
          </div>

          {canManage ? (
            <Card>
              <CardHeader
                title="Run analysis"
                description="Generate a snapshot over the last 30 days with the deterministic engines."
              />
              <CardBody className="flex flex-col gap-3">
                <div className="flex flex-wrap items-end gap-3">
                  <label className="flex flex-col gap-1 text-xs text-gray-500">
                    Analysis type
                    <Select
                      className="w-48"
                      value={selectedType}
                      onChange={(e) => setSelectedType(e.target.value as GrowthAnalysisType)}
                    >
                      {ANALYSIS_TYPE_OPTIONS.map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </Select>
                  </label>
                  <Button
                    disabled={busy}
                    onClick={() =>
                      runAction(() =>
                        runAnalysis({
                          analysis_type: selectedType,
                          period_start: window.start,
                          period_end: window.end,
                        })
                      )
                    }
                  >
                    Run {GROWTH_ANALYSIS_TYPE_LABELS[selectedType]}
                  </Button>
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() =>
                      runAction(() =>
                        runAllAnalyses({ period_start: window.start, period_end: window.end })
                      )
                    }
                  >
                    Run full analysis
                  </Button>
                </div>

                <div className="flex flex-wrap items-end gap-3 border-t pt-3">
                  <label className="flex flex-col gap-1 text-xs text-gray-500">
                    Forecast method
                    <Select
                      className="w-48"
                      value={forecastMethod}
                      onChange={(e) => setForecastMethod(e.target.value as GrowthForecastMethod)}
                    >
                      {FORECAST_METHOD_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </Select>
                  </label>
                  <Button variant="outline" disabled={busy} onClick={runForecastAction}>
                    Run forecast
                  </Button>
                  {forecast ? (
                    <span className="text-xs text-gray-500">
                      Latest: {forecast.forecast_type} {forecast.method} —{" "}
                      {formatUsd(Number(forecast.point_estimate ?? 0))}
                    </span>
                  ) : null}
                </div>
              </CardBody>
            </Card>
          ) : null}

          <Card>
            <CardHeader title="Recent analyses" description="Latest deterministic snapshots" />
            <CardBody>
              {analyses.length === 0 ? (
                <EmptyState
                  title="No analyses"
                  description="Run an analysis to see snapshots here."
                />
              ) : (
                <Table>
                  <THead>
                    <tr>
                      <TH>Type</TH>
                      <TH>Status</TH>
                      <TH>Window</TH>
                      <TH>Summary</TH>
                    </tr>
                  </THead>
                  <TBody>
                    {analyses.map((analysis) => (
                      <TRow key={analysis.id}>
                        <TD className="font-medium">
                          {GROWTH_ANALYSIS_TYPE_LABELS[analysis.analysis_type]}
                        </TD>
                        <TD>
                          <Badge tone={growthAnalysisStatusTone(analysis.status)}>
                            {GROWTH_ANALYSIS_STATUS_LABELS[analysis.status]}
                          </Badge>
                        </TD>
                        <TD className="text-xs text-gray-500">
                          {windowStart(analysis.period_start)} – {windowStart(analysis.period_end)}
                        </TD>
                        <TD className="max-w-md truncate text-gray-600">{analysis.summary}</TD>
                      </TRow>
                    ))}
                  </TBody>
                </Table>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Recommendations"
              description="Evidence-backed actions to grow revenue"
            />
            <CardBody>
              {recommendations.length === 0 ? (
                <EmptyState
                  title="No recommendations"
                  description="Run the full analysis to generate recommendations."
                />
              ) : (
                <Table>
                  <THead>
                    <tr>
                      <TH>Priority</TH>
                      <TH>Status</TH>
                      <TH>Title</TH>
                      <TH>Created</TH>
                      {canManage ? <TH /> : null}
                    </tr>
                  </THead>
                  <TBody>
                    {recommendations.map((recommendation) => (
                      <TRow key={recommendation.id}>
                        <TD>
                          <Badge tone={recommendationPriorityTone(recommendation.priority)}>
                            {RECOMMENDATION_PRIORITY_LABELS[recommendation.priority]}
                          </Badge>
                        </TD>
                        <TD>
                          <Badge tone={recommendationStatusTone(recommendation.status)}>
                            {RECOMMENDATION_STATUS_LABELS[recommendation.status]}
                          </Badge>
                        </TD>
                        <TD className="max-w-md">
                          <p className="font-medium">{recommendation.title}</p>
                          <p className="truncate text-xs text-gray-500">{recommendation.summary}</p>
                        </TD>
                        <TD className="text-xs text-gray-400">
                          {formatDateTime(recommendation.created_at)}
                        </TD>
                        {canManage ? (
                          <TD className="text-right">
                            <Select
                              className="w-40"
                              value={recommendation.status}
                              onChange={(e) =>
                                triage(recommendation.id, e.target.value as RecommendationStatus)
                              }
                            >
                              {TRIAGE_OPTIONS.map(([value, label]) => (
                                <option key={value} value={value}>
                                  {label}
                                </option>
                              ))}
                            </Select>
                          </TD>
                        ) : null}
                      </TRow>
                    ))}
                  </TBody>
                </Table>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Scenarios" description="Saved what-if projections" />
            <CardBody className="flex flex-col gap-4">
              {scenarios.length === 0 ? (
                <EmptyState
                  title="No scenarios"
                  description="Create a what-if scenario to project growth."
                />
              ) : (
                <Table>
                  <THead>
                    <tr>
                      <TH>Name</TH>
                      <TH>Deltas</TH>
                      <TH>Created</TH>
                      {canManage ? <TH /> : null}
                    </tr>
                  </THead>
                  <TBody>
                    {scenarios.map((scenario) => (
                      <TRow key={scenario.id}>
                        <TD className="font-medium">{scenario.name}</TD>
                        <TD className="max-w-xs truncate text-xs text-gray-500">
                          {JSON.stringify(scenario.assumption_deltas)}
                        </TD>
                        <TD className="text-xs text-gray-400">
                          {formatDateTime(scenario.created_at)}
                        </TD>
                        {canManage ? (
                          <TD className="text-right">
                            <Button variant="ghost" onClick={() => setDeleteTarget(scenario)}>
                              Delete
                            </Button>
                          </TD>
                        ) : null}
                      </TRow>
                    ))}
                  </TBody>
                </Table>
              )}

              {canManage ? (
                <div className="flex flex-wrap items-end gap-3 border-t pt-3">
                  <label className="flex min-w-40 flex-1 flex-col gap-1 text-xs text-gray-500">
                    Scenario name
                    <Input
                      value={scenarioName}
                      onChange={(e) => setScenarioName(e.target.value)}
                      placeholder="Double leads"
                    />
                  </label>
                  <label className="flex min-w-64 flex-1 flex-col gap-1 text-xs text-gray-500">
                    Assumption deltas (JSON)
                    <textarea
                      className="rounded-md border border-gray-300 px-3 py-2 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-gray-900"
                      rows={3}
                      value={scenarioDeltas}
                      onChange={(e) => setScenarioDeltas(e.target.value)}
                    />
                  </label>
                  <Button variant="outline" disabled={busy} onClick={create}>
                    Save scenario
                  </Button>
                </div>
              ) : null}
            </CardBody>
          </Card>
        </>
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete scenario"
        message={`Delete "${deleteTarget?.name}"? This cannot be undone.`}
        confirmLabel="Delete"
        busy={busy}
        onConfirm={() => {
          if (deleteTarget) {
            runAction(() => deleteScenario(deleteTarget.id));
            setDeleteTarget(null);
          }
        }}
        onClose={() => setDeleteTarget(null)}
      />
    </div>
  );
}
