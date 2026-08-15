// Founder action proposals (M8) — the approval queue for assistant actions.
"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { can } from "@/lib/permissions";
import { decideFounderProposal, listFounderProposals } from "@/services/founder";
import type { FounderProposal, FounderProposalStatus } from "@/types";

const STATUSES: Array<FounderProposalStatus | "all"> = [
  "all",
  "proposed",
  "approved",
  "denied",
  "expired",
  "succeeded",
  "failed",
];

export default function FounderProposalsPage() {
  const session = useAuth();
  const [proposals, setProposals] = useState<FounderProposal[]>([]);
  const [status, setStatus] = useState<FounderProposalStatus | "all">("all");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canManage = !!session && can(session.user.role, "founder_manage");

  async function refresh() {
    const page = await listFounderProposals({
      status: status === "all" ? undefined : status,
      limit: 100,
    });
    setProposals(page.items);
  }

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    listFounderProposals({
      status: status === "all" ? undefined : status,
      limit: 100,
    })
      .then((page) => {
        if (!cancelled) setProposals(page.items);
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(err instanceof ApiRequestError ? err.message : "Failed to load proposals");
      });
    return () => {
      cancelled = true;
    };
  }, [session, status]);

  async function onDecide(proposal: FounderProposal, approve: boolean) {
    setBusyId(proposal.id);
    setError(null);
    try {
      const updated = await decideFounderProposal(proposal.id, {
        approve,
        decision_note: approve ? null : "Denied from queue",
      });
      setProposals((prev) => prev.map((p) => (p.id === proposal.id ? updated : p)));
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Decision failed");
    } finally {
      setBusyId(null);
    }
  }

  if (!session) return null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Founder actions</h1>
        <div className="flex items-center gap-2 text-sm">
          {STATUSES.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setStatus(s)}
              className={s === status ? "font-medium text-gray-900" : "text-gray-500"}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {proposals.length === 0 ? (
        <p className="text-sm text-gray-500">No proposals match this filter.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {proposals.map((p) => {
            const terminal = p.status !== "proposed";
            return (
              <li key={p.id} className="rounded-lg border bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">{p.title}</p>
                    <p className="text-xs text-gray-500">
                      {p.action_type} · {p.created_at ?? "—"}
                    </p>
                  </div>
                  <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                    {p.status}
                  </span>
                </div>
                {p.justification ? (
                  <p className="mt-2 text-sm text-gray-600">{p.justification}</p>
                ) : null}
                {!terminal && canManage ? (
                  <div className="mt-3 flex items-center gap-2">
                    <Button
                      variant="ghost"
                      onClick={() => onDecide(p, true)}
                      disabled={busyId === p.id}
                      className="text-green-700"
                    >
                      Approve
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => onDecide(p, false)}
                      disabled={busyId === p.id}
                      className="text-red-700"
                    >
                      Deny
                    </Button>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
