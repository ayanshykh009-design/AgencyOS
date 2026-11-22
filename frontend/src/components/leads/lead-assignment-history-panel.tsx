// Assignment history panel for a single lead: read-only ownership trail.
// Data comes from GET /assignment/leads/{id}/history; ordering (newest first)
// and pagination are the backend's. User names are resolved from the org
// users already loaded by the Lead Detail page (no extra request per panel).
//
// A failed request is never rendered as an empty success: loading, failure
// (with retry), genuinely empty history, and history are distinct states, and
// the last successfully loaded page is preserved when a refresh fails.
//
// Pagination contract: 50 records per request (the backend's `limit`), offset
// pages continue until a short page arrives. The backend `Page.total` is the
// length of the page — NOT a global match count — so it is never used to
// cap history. A full page simply means more may exist; a short page ends it.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Badge, Button, EmptyState, Spinner } from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { formatDateTime } from "@/lib/format";
import { listAssignmentHistory } from "@/services/assignment";
import type { AssignmentLogEntry, AssignmentMethod, User } from "@/types";

const METHOD_LABELS: Record<AssignmentMethod, string> = {
  manual: "Manual",
  round_robin: "Round robin",
  rules: "Rules",
  bulk: "Bulk",
  unassigned: "Unassigned",
};

const PAGE_SIZE = 50; // backend default page; "load more" pages offset by PAGE_SIZE

type LoadState = "loading" | "error" | "ready";

function methodTone(method: AssignmentMethod): "green" | "blue" | "amber" | "gray" {
  switch (method) {
    case "manual":
      return "blue";
    case "round_robin":
    case "rules":
      return "green";
    case "unassigned":
      return "gray";
    default:
      return "amber";
  }
}

export function LeadAssignmentHistoryPanel({ leadId, users }: { leadId: string; users: User[] }) {
  const session = useAuth();
  const [entries, setEntries] = useState<AssignmentLogEntry[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  // Generation guard against stale/out-of-order responses from a previous
  // lead or a superseded request.
  const generationRef = useRef(0);
  // Atomic in-flight guard for load-more (prevents duplicate concurrent appends).
  const busyRef = useRef(false);

  const fetchPage = useCallback(
    (offset: number, append: boolean) => {
      const generation = ++generationRef.current;
      // NOTE: state is only ever set inside promise callbacks below, never
      // synchronously — the mount path runs inside an effect.
      return listAssignmentHistory(leadId, { limit: PAGE_SIZE, offset })
        .then((page) => {
          if (generation !== generationRef.current) return;
          setEntries((prev) => (append ? [...prev, ...page.items] : page.items));
          // A full page means more may exist; a short page terminates.
          // `Page.total` is deliberately ignored (page length, not a global count).
          setHasMore(page.items.length === PAGE_SIZE);
          setState("ready");
          setError(null);
        })
        .catch((err: unknown) => {
          if (generation !== generationRef.current) return;
          // Keep whatever history is already loaded (do NOT blank it).
          setState("error");
          setError(
            err instanceof ApiRequestError ? err.message : "Failed to load assignment history"
          );
        })
        .finally(() => {
          if (generation === generationRef.current) {
            setLoadingMore(false);
            busyRef.current = false;
          }
        });
    },
    [leadId]
  );

  const load = useCallback(() => fetchPage(0, false), [fetchPage]);
  const loadMore = useCallback(() => {
    // Event-handler path: synchronous setState is allowed here.
    if (busyRef.current) return null;
    busyRef.current = true;
    setLoadingMore(true);
    return fetchPage(entries.length, true);
  }, [entries.length, fetchPage]);

  // Retry the FAILED page when at least one page succeeded (offset = items
  // loaded); otherwise retry the initial page. Never discards loaded pages.
  const retry = useCallback(() => {
    if (entries.length > 0) {
      return loadMore();
    }
    return load();
  }, [entries.length, load, loadMore]);

  // Reset per-lead state during render when the lead changes (React-endorsed
  // alternative to syncing state in an effect). The parent also remounts this
  // panel via a key on lead/principal change.
  const [activeLeadId, setActiveLeadId] = useState(leadId);
  if (activeLeadId !== leadId) {
    setActiveLeadId(leadId);
    setEntries([]);
    setHasMore(false);
    setError(null);
    setState("loading");
    setLoadingMore(false);
  }

  useEffect(() => {
    load();
    return () => {
      generationRef.current += 1;
      busyRef.current = false;
    };
  }, [load]);

  if (!session) return null;

  const userName = (userId: string | null): string => {
    if (!userId) return "—";
    const user = users.find((candidate) => candidate.id === userId);
    return user ? user.full_name || user.email : "—";
  };

  const refreshFailure = state === "error" && entries.length > 0;

  if (state === "loading" && entries.length === 0) {
    return (
      <section aria-label="Assignment history" className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold">Assignment history</h3>
        <Spinner label="Loading assignment history…" />
      </section>
    );
  }

  return (
    <section aria-label="Assignment history" className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Assignment history</h3>
        {state === "error" ? (
          <Button variant="outline" onClick={retry}>
            Retry
          </Button>
        ) : null}
      </div>

      {refreshFailure ? (
        <p role="alert" className="text-sm text-red-600">
          {error}{" "}
          <button type="button" className="underline" onClick={retry}>
            Retry
          </button>
        </p>
      ) : null}

      {state === "error" && entries.length === 0 ? (
        <div className="flex flex-col items-start gap-2">
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
          <Button variant="outline" onClick={retry}>
            Retry
          </Button>
        </div>
      ) : entries.length === 0 ? (
        <EmptyState
          title="No assignment changes"
          description="Ownership changes for this lead will appear here."
        />
      ) : (
        <>
          <ul className="flex flex-col gap-2">
            {entries.map((entry) => (
              <li key={entry.id} className="rounded-lg border bg-white p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="flex items-center gap-2">
                    <Badge tone={methodTone(entry.method)}>{METHOD_LABELS[entry.method]}</Badge>
                    <span className="text-gray-700">
                      {userName(entry.from_user_id)} → {userName(entry.to_user_id)}
                    </span>
                  </span>
                  <time className="text-xs text-gray-400" dateTime={entry.created_at}>
                    {formatDateTime(entry.created_at)}
                  </time>
                </div>
                {entry.reason ? <p className="mt-1 text-gray-500">Reason: {entry.reason}</p> : null}
              </li>
            ))}
          </ul>
          {hasMore ? (
            <p className="text-xs text-gray-500">
              Showing the {entries.length} most recent ownership changes. Older records may exist.
            </p>
          ) : null}
          {hasMore ? (
            <div className="flex justify-center">
              <Button variant="outline" onClick={loadMore} disabled={loadingMore}>
                {loadingMore ? "Loading…" : "Load more history"}
              </Button>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
