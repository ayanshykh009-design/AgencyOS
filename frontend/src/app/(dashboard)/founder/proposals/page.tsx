// Founder action proposals (M8) — the approval queue for assistant actions.
"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import { proposalDecisionDisabledReason } from "@/lib/ai-capabilities";
import { ApiRequestError } from "@/lib/api-client";
import { canManageFounder, canViewFounder } from "@/lib/batch5-permissions";
import { getAICapabilities } from "@/services/ai";
import { decideFounderProposal, listFounderProposals } from "@/services/founder";
import type { AICapabilities, FounderProposal, FounderProposalStatus } from "@/types";

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
  const canView = !!session && canViewFounder(session.user.role);
  const canManage = !!session && canManageFounder(session.user.role);
  const [proposals, setProposals] = useState<FounderProposal[]>([]);
  const [status, setStatus] = useState<FounderProposalStatus | "all">("all");
  // null means unverified: proposal decisions fail closed.
  const [capabilities, setCapabilities] = useState<AICapabilities | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const decisionDisabledReason = proposalDecisionDisabledReason(capabilities);

  useEffect(() => {
    if (!canView) return;
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
    getAICapabilities()
      .then((surface) => {
        if (!cancelled) setCapabilities(surface);
      })
      .catch(() => {
        if (!cancelled) setCapabilities(null);
      });
    return () => {
      cancelled = true;
    };
  }, [canView, status]);

  async function onDecide(proposal: FounderProposal, approve: boolean) {
    if (!canManage || decisionDisabledReason) return;
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
  if (!canView) {
    return (
      <p className="text-sm text-gray-600">
        You do not have permission to view founder proposals. Contact an administrator.
      </p>
    );
  }

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

      {canManage && decisionDisabledReason ? (
        <p className="text-sm text-amber-700">
          Proposal decisions are currently disabled: {decisionDisabledReason}
        </p>
      ) : null}

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
                {!terminal ? (
                  <ProposalDecisionControls
                    canManage={canManage}
                    disabledReason={decisionDisabledReason}
                    busy={busyId === p.id}
                    onDecide={(approve) => onDecide(p, approve)}
                  />
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/** Decisions require founder_manage and an enabled org AI execution path. */
export function ProposalDecisionControls({
  canManage,
  disabledReason,
  busy,
  onDecide,
}: {
  canManage: boolean;
  disabledReason: string | null;
  busy: boolean;
  onDecide: (approve: boolean) => void;
}) {
  if (!canManage || disabledReason) return null;
  return (
    <div className="mt-3 flex items-center gap-2">
      <Button
        variant="ghost"
        onClick={() => onDecide(true)}
        disabled={busy}
        className="text-green-700"
      >
        Approve
      </Button>
      <Button
        variant="ghost"
        onClick={() => onDecide(false)}
        disabled={busy}
        className="text-red-700"
      >
        Deny
      </Button>
    </div>
  );
}
