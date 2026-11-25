// Founder action proposals (M8) — the approval queue for assistant actions.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ErrorState } from "@/components/automation/automation-states";
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
  "cancelled",
  "executing",
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
  const [loading, setLoading] = useState(true);
  const listSeqRef = useRef(0);

  const decisionDisabledReason = proposalDecisionDisabledReason(capabilities);

  const loadProposals = useCallback(async () => {
    const seq = ++listSeqRef.current;
    try {
      const page = await listFounderProposals({
        status: status === "all" ? undefined : status,
        limit: 100,
      });
      if (seq !== listSeqRef.current) return;
      setProposals(page.items);
    } catch (err: unknown) {
      if (seq !== listSeqRef.current) return;
      setError(err instanceof ApiRequestError ? err.message : "Failed to load proposals");
    } finally {
      if (seq === listSeqRef.current) setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    if (!canView) return;
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (!cancelled) void loadProposals();
    });
    return () => {
      cancelled = true;
      listSeqRef.current += 1;
    };
  }, [canView, loadProposals]);

  useEffect(() => {
    if (!canView) return;
    let cancelled = false;
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
  }, [canView]);

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
              onClick={() => {
                setStatus(s);
                setLoading(true);
                setError(null);
              }}
              className={s === status ? "font-medium text-gray-900" : "text-gray-500"}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {canManage && decisionDisabledReason ? (
        <p className="text-sm text-amber-700">
          Proposal decisions are currently disabled: {decisionDisabledReason}
        </p>
      ) : null}

      {loading ? (
        <p className="text-sm text-gray-500">Loading proposals…</p>
      ) : error ? (
        <ErrorState
          message={error}
          onRetry={() => {
            setLoading(true);
            setError(null);
            void loadProposals();
          }}
        />
      ) : proposals.length === 0 ? (
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
