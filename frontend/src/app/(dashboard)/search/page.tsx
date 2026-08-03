// Search: unified results across leads, tasks, and notes.
"use client";

import { useState } from "react";

import { Badge, Button, EmptyState, Input, Spinner } from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { ROUTES } from "@/lib/constants";
import { formatDateTime, leadName, taskPriorityTone, taskStatusTone } from "@/lib/format";
import { TASK_PRIORITY_LABELS, TASK_STATUS_LABELS } from "@/lib/format";
import { globalSearch } from "@/services/search";
import type { SearchResponse } from "@/types";

export default function SearchPage() {
  const session = useAuth();
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!session) return null;

  async function runSearch() {
    const q = query.trim();
    if (q === "") {
      setResult(null);
      setSubmitted("");
      return;
    }
    setLoading(true);
    setError(null);
    setSubmitted(q);
    try {
      const data = await globalSearch(q);
      setResult(data);
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Search failed");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-lg font-semibold">Search</h2>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          runSearch();
        }}
      >
        <Input
          placeholder="Search leads, tasks, and notes…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="max-w-xl"
        />
        <Button type="submit" disabled={loading || query.trim() === ""}>
          {loading ? "Searching…" : "Search"}
        </Button>
      </form>

      {error ? <p className="text-red-600">{error}</p> : null}

      {loading ? (
        <Spinner label="Searching…" />
      ) : result ? (
        <div className="flex flex-col gap-8">
          <div className="flex flex-wrap gap-2 text-sm text-gray-500">
            <span>
              {result.counts.leads} lead{result.counts.leads === 1 ? "" : "s"}
            </span>
            <span>
              {result.counts.tasks} task{result.counts.tasks === 1 ? "" : "s"}
            </span>
            <span>
              {result.counts.notes} note{result.counts.notes === 1 ? "" : "s"}
            </span>
            <span>for “{submitted}”</span>
          </div>

          <SearchSection title="Leads" count={result.leads.length} empty="No matching leads.">
            <ul className="flex flex-col gap-2">
              {result.leads.map((lead) => (
                <li key={lead.id} className="rounded-lg border bg-white p-3 text-sm">
                  <a
                    href={ROUTES.leadDetail(lead.id)}
                    className="font-medium text-gray-900 hover:underline"
                  >
                    {leadName(lead)}
                  </a>
                  <div className="text-xs text-gray-500">
                    {lead.company ?? "—"} · {lead.email ?? "no email"}
                  </div>
                </li>
              ))}
            </ul>
          </SearchSection>

          <SearchSection title="Tasks" count={result.tasks.length} empty="No matching tasks.">
            <ul className="flex flex-col gap-2">
              {result.tasks.map((task) => (
                <li
                  key={task.id}
                  className="flex flex-col gap-1 rounded-lg border bg-white p-3 text-sm"
                >
                  <span className="font-medium">{task.title}</span>
                  <span className="flex gap-2">
                    <Badge tone={taskStatusTone(task.status)}>
                      {TASK_STATUS_LABELS[task.status]}
                    </Badge>
                    <Badge tone={taskPriorityTone(task.priority)}>
                      {TASK_PRIORITY_LABELS[task.priority]}
                    </Badge>
                    {task.due_at ? (
                      <span className="text-xs text-gray-400">{formatDateTime(task.due_at)}</span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          </SearchSection>

          <SearchSection title="Notes" count={result.notes.length} empty="No matching notes.">
            <ul className="flex flex-col gap-2">
              {result.notes.map((note) => (
                <li key={note.id} className="rounded-lg border bg-white p-3 text-sm">
                  <p className="whitespace-pre-wrap text-gray-700">{note.body}</p>
                  <span className="text-xs text-gray-400">
                    On{" "}
                    <a href={ROUTES.leadDetail(note.lead_id)} className="text-gray-600 underline">
                      lead
                    </a>{" "}
                    · {formatDateTime(note.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          </SearchSection>
        </div>
      ) : submitted === "" && !error ? (
        <EmptyState
          title="Search the workspace"
          description="Find leads, tasks, and notes by typing keywords above."
        />
      ) : null}
    </div>
  );
}

function SearchSection({
  title,
  count,
  empty,
  children,
}: {
  title: string;
  count: number;
  empty: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold">
        {title} <span className="font-normal text-gray-400">({count})</span>
      </h3>
      {count === 0 ? <p className="text-sm text-gray-500">{empty}</p> : children}
    </section>
  );
}
