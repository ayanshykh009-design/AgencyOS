// Founder Intelligence feed (M9).
// Surfaces the triaged, prioritized signal feed — never conversational. Founder
// can acknowledge/dismiss signals and trigger a manual sweep (manage only).
"use client";

import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { can } from "@/lib/permissions";
import { ROUTES } from "@/lib/constants";
import {
  useAcknowledgeSignal,
  useRunTriage,
  useSignalSummary,
  useSignals,
} from "@/services/intelligence";
import type { IntelligenceSignal, IntelligenceSignalStatus } from "@/types/intelligence";

const SEVERITY_STYLES: Record<string, string> = {
  critical: "bg-red-100 text-red-700",
  high: "bg-red-50 text-red-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-gray-100 text-gray-600",
  info: "bg-gray-50 text-gray-500",
};

const STATUS_FILTERS: Array<{ label: string; value: IntelligenceSignalStatus | "all" }> = [
  { label: "All", value: "all" },
  { label: "Active", value: "active" },
  { label: "Acknowledged", value: "acknowledged" },
  { label: "Dismissed", value: "dismissed" },
];

export default function FounderIntelligencePage() {
  const session = useAuth();
  const canManage = !!session && can(session.user.role, "founder_manage");
  const [statusFilter, setStatusFilter] = useState<IntelligenceSignalStatus | "all">("all");
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(
    () => ({ status: statusFilter === "all" ? undefined : statusFilter, limit: 100, offset: 0 }),
    [statusFilter]
  );

  const { data, isLoading } = useSignals(query);
  const { data: summary } = useSignalSummary();
  const ack = useAcknowledgeSignal();
  const run = useRunTriage();

  async function onTransition(signal: IntelligenceSignal, next: IntelligenceSignalStatus) {
    setError(null);
    try {
      await ack.mutateAsync({ id: signal.id, status: next });
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Update failed");
    }
  }

  async function onRunTriage() {
    setError(null);
    try {
      await run.mutateAsync();
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Triage run failed");
    }
  }

  if (!session) return null;

  const signals = data?.items ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Intelligence signals</h1>
          <p className="text-xs text-gray-500">
            Prioritized, deduplicated triage of growth &amp; pipeline signals
          </p>
        </div>
        {canManage ? (
          <Button onClick={onRunTriage} disabled={run.isPending}>
            {run.isPending ? "Triaging…" : "Run triage now"}
          </Button>
        ) : null}
      </div>

      {summary ? (
        <div className="flex flex-wrap gap-3 text-sm">
          <SummaryChip label="Active" value={summary.active} />
          <SummaryChip label="High priority" value={summary.high_priority} tone="red" />
          <SummaryChip label="Acknowledged" value={summary.acknowledged} />
          <SummaryChip label="Dismissed" value={summary.dismissed} />
          <SummaryChip
            label="Top score"
            value={summary.highest_priority_score?.toFixed(2) ?? "—"}
          />
        </div>
      ) : null}

      <div className="flex gap-2">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            onClick={() => setStatusFilter(f.value)}
            className={`rounded-md border px-3 py-1 text-sm ${
              statusFilter === f.value ? "border-gray-900 bg-gray-50" : ""
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {run.data?.narrative ? (
        <p className="rounded-md border bg-gray-50 p-3 text-sm text-gray-700">
          {run.data.narrative}
        </p>
      ) : null}

      {isLoading ? (
        <p className="text-sm text-gray-500">Loading signals…</p>
      ) : signals.length === 0 ? (
        <p className="text-sm text-gray-500">No signals in this view.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {signals.map((signal) => (
            <SignalCard
              key={signal.id}
              signal={signal}
              canManage={canManage}
              onTransition={onTransition}
              busy={ack.isPending}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function SummaryChip({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | string;
  tone?: "red";
}) {
  return (
    <div className="rounded-md border px-3 py-1.5">
      <span className="text-gray-500">{label}: </span>
      <span className={tone === "red" ? "font-semibold text-red-700" : "font-semibold"}>
        {value}
      </span>
    </div>
  );
}

function SignalCard({
  signal,
  canManage,
  onTransition,
  busy,
}: {
  signal: IntelligenceSignal;
  canManage: boolean;
  onTransition: (s: IntelligenceSignal, next: IntelligenceSignalStatus) => void;
  busy: boolean;
}) {
  const impact = signal.business_impact as { amount?: number; dimension?: string } | null;
  const amount = impact?.amount;
  const terminal = signal.status === "acknowledged" || signal.status === "dismissed";

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span
              className={`rounded px-2 py-0.5 text-xs font-medium ${
                SEVERITY_STYLES[signal.severity] ?? "bg-gray-100 text-gray-600"
              }`}
            >
              {signal.severity}
            </span>
            <span className="text-xs uppercase tracking-wide text-gray-400">
              {signal.signal_category}
            </span>
            {amount !== undefined ? (
              <span className="rounded bg-green-50 px-2 py-0.5 text-xs text-green-700">
                ${Number(amount).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                {impact?.dimension ? ` ${impact.dimension}` : ""}
              </span>
            ) : null}
          </div>
          <h2 className="mt-1 font-medium">{signal.title}</h2>
          <p className="mt-0.5 text-sm text-gray-600">{signal.summary}</p>
        </div>
        <div className="text-right">
          <div className="text-xs text-gray-400">priority</div>
          <div className="text-lg font-semibold">{signal.priority_score.toFixed(3)}</div>
        </div>
      </div>

      {signal.evidence && signal.evidence.length > 0 ? (
        <details className="mt-2 text-xs text-gray-500">
          <summary className="cursor-pointer">Evidence ({signal.evidence.length})</summary>
          <ul className="mt-1 list-disc pl-4">
            {signal.evidence.slice(0, 5).map((item, i) => (
              <li key={i}>{JSON.stringify(item)}</li>
            ))}
          </ul>
        </details>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
          {signal.status}
        </span>
        {signal.recommended_next_step ? (
          <span className="text-xs text-gray-500">Next: {signal.recommended_next_step}</span>
        ) : null}
        {canManage && !terminal && signal.status === "active" ? (
          <div className="ml-auto flex gap-2">
            <Button
              variant="ghost"
              className="text-green-700"
              disabled={busy}
              onClick={() => onTransition(signal, "acknowledged")}
            >
              Acknowledge
            </Button>
            <Button
              variant="ghost"
              className="text-gray-600"
              disabled={busy}
              onClick={() => onTransition(signal, "dismissed")}
            >
              Dismiss
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
