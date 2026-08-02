// Dashboard overview: aggregate metrics + recent activity.
"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { getDashboardSummary } from "@/services/dashboard";
import type { ActivityLogEntry, DashboardSummary } from "@/types";

function formatUsd(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatTime(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
}

export default function DashboardPage() {
  const session = useAuth();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    getDashboardSummary()
      .then((data) => {
        if (cancelled) return;
        setSummary(data);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiRequestError ? err.message : "Failed to load dashboard");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session]);

  if (loading) {
    return <p className="text-gray-500">Loading dashboard…</p>;
  }

  if (error) {
    return <p className="text-red-600">{error}</p>;
  }

  if (!summary) {
    return null;
  }

  const statuses: Array<{ key: keyof DashboardSummary["leads"]; label: string }> = [
    { key: "new", label: "New" },
    { key: "researching", label: "Researching" },
    { key: "contacted", label: "Contacted" },
    { key: "meeting_booked", label: "Meetings booked" },
    { key: "proposal_sent", label: "Proposals sent" },
    { key: "won", label: "Won" },
    { key: "lost", label: "Lost" },
  ];

  return (
    <div className="flex flex-col gap-8">
      <section>
        <h2 className="text-lg font-semibold">Pipeline</h2>
        <div className="mt-3 grid grid-cols-2 gap-4 md:grid-cols-4">
          <MetricCard label="Total leads" value={summary.leads.total.toString()} />
          <MetricCard label="Open conversations" value={summary.conversations.open.toString()} />
          <MetricCard
            label="Outstanding outreach"
            value={summary.outreach.outstanding.toString()}
          />
          <MetricCard
            label="30-day spend"
            value={formatUsd(summary.usage.spend_last_30_days_usd)}
          />
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
          {statuses.map(({ key, label }) => (
            <MetricCard key={key} label={label} value={summary.leads[key].toString()} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold">Recent activity</h2>
        {summary.activity.recent.length === 0 ? (
          <p className="mt-3 text-gray-500">No activity yet.</p>
        ) : (
          <ul className="mt-3 flex flex-col gap-2">
            {summary.activity.recent.map((entry) => (
              <ActivityRow key={entry.id} entry={entry} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <p className="text-sm text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  );
}

function ActivityRow({ entry }: { entry: ActivityLogEntry }) {
  return (
    <li className="flex items-center justify-between rounded-md border bg-white px-4 py-2 text-sm">
      <div>
        <span className="font-medium capitalize">{entry.event_type.replace(/_/g, " ")}</span>
        {entry.description ? <span className="ml-2 text-gray-600">{entry.description}</span> : null}
      </div>
      <time className="text-xs text-gray-400">{formatTime(entry.occurred_at)}</time>
    </li>
  );
}
