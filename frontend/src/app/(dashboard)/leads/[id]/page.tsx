// Lead detail: profile, contact info, assignment, notes, tasks, and conversations.
"use client";

import { useCallback, useEffect, use, useRef, useState } from "react";

import { LeadFormModal } from "@/components/leads/lead-form-modal";
import { LeadAssignmentHistoryPanel } from "@/components/leads/lead-assignment-history-panel";
import { LeadConversationsPanel } from "@/components/leads/lead-conversations-panel";
import { LeadNotesPanel } from "@/components/leads/lead-notes-panel";
import { LeadTasksPanel } from "@/components/leads/lead-tasks-panel";
import { Badge, Button, ConfirmDialog, Field, PageHeader, Select, Spinner } from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { ROUTES } from "@/lib/constants";
import { formatDate, formatUsd, leadName } from "@/lib/format";
import { can } from "@/lib/permissions";
import { createGenerationGuard, detailIdentityKey } from "@/lib/lead-detail-identity";
import { assignLead } from "@/services/assignment";
import { deleteLead, getLead, updateLead } from "@/services/leads";
import { listUsers } from "@/services/users";
import type { Lead, LeadCreateInput, User } from "@/types";

function statusTone(status: Lead["status"]): "green" | "red" | "blue" | "amber" | "gray" {
  switch (status) {
    case "won":
      return "green";
    case "lost":
      return "red";
    case "meeting_booked":
    case "proposal_sent":
      return "blue";
    case "contacted":
      return "amber";
    default:
      return "gray";
  }
}

export default function LeadDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const session = useAuth();
  const { id: leadId } = use(params);

  // Parent-level isolation: every piece of page state (lead, users, assignee,
  // action handlers) is scoped to a composite identity. Changing the route
  // lead, the user, or the organization remounts the inner view wholesale —
  // stale data is never rendered and actions can never target a previous
  // lead/principal.
  if (!session) return null;
  return (
    <LeadDetailView
      key={detailIdentityKey(session.user, leadId) ?? "unauthenticated"}
      leadId={leadId}
    />
  );
}

function LeadDetailView({ leadId }: { leadId: string }) {
  const session = useAuth();
  const [lead, setLead] = useState<Lead | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [assignee, setAssignee] = useState("");

  // Generation guard: a slow response for a superseded request must not
  // overwrite this view (the keyed remount also discards it).
  const guardRef = useRef(createGenerationGuard());

  const load = useCallback(() => {
    const generation = guardRef.current.capture();
    Promise.all([getLead(leadId), listUsers(100)])
      .then(([data, page]) => {
        if (!guardRef.current.isCurrent(generation)) return;
        setLead(data);
        setUsers(page.items);
        setAssignee(data.owner_user_id ?? "");
      })
      .catch((err: unknown) => {
        if (!guardRef.current.isCurrent(generation)) return;
        setError(err instanceof ApiRequestError ? err.message : "Failed to load lead");
      })
      .finally(() => {
        if (guardRef.current.isCurrent(generation)) setLoading(false);
      });
  }, [leadId]);

  useEffect(() => {
    const guard = guardRef.current;
    load();
    return () => {
      guard.invalidate();
    };
  }, [load]);

  if (!session) return null;
  const canWrite = can(session.user.role, "lead_write");
  const canDelete = can(session.user.role, "lead_delete");
  const canAssign = can(session.user.role, "lead_assign");

  if (loading) {
    return <Spinner label="Loading lead…" />;
  }
  if (error) {
    return <p className="text-red-600">{error}</p>;
  }
  if (!lead) {
    return null;
  }

  const currentLead = lead;

  const handleUpdate = async (input: LeadCreateInput) => {
    setBusy(true);
    setError(null);
    try {
      await updateLead(currentLead.id, input);
      setEditOpen(false);
      load();
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to update lead");
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    setBusy(true);
    try {
      await deleteLead(currentLead.id);
      window.location.href = ROUTES.leads;
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to delete lead");
      setBusy(false);
    }
  };

  const handleAssign = async () => {
    setBusy(true);
    setError(null);
    try {
      const updated = await assignLead(currentLead.id, {
        user_id: assignee || undefined,
      });
      setLead(updated);
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to assign lead");
    } finally {
      setBusy(false);
    }
  };

  const contactRows: Array<[string, string | null | undefined]> = [
    ["Email", lead.email],
    ["Phone", lead.phone],
    ["WhatsApp", lead.whatsapp],
    ["Website", lead.website],
    ["LinkedIn", lead.linkedin_url],
    ["Location", lead.location],
  ];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={leadName(lead)}
        description={`Created ${formatDate(lead.created_at)}`}
        actions={
          <>
            {canAssign ? (
              <>
                <Select
                  value={assignee}
                  onChange={(e) => setAssignee(e.target.value)}
                  className="w-52"
                >
                  <option value="">Unassigned</option>
                  {users.map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.full_name || user.email}
                    </option>
                  ))}
                </Select>
                <Button
                  variant="outline"
                  onClick={handleAssign}
                  disabled={busy || assignee === (lead.owner_user_id ?? "")}
                >
                  Assign
                </Button>
              </>
            ) : null}
            {canWrite ? (
              <Button variant="outline" onClick={() => setEditOpen(true)}>
                Edit
              </Button>
            ) : null}
            {canDelete ? (
              <Button variant="danger" onClick={() => setDeleteOpen(true)}>
                Delete
              </Button>
            ) : null}
          </>
        }
      />

      <div className="flex flex-wrap gap-2">
        <Badge tone={statusTone(lead.status)}>{lead.status.replace(/_/g, " ")}</Badge>
        <Badge tone={lead.score >= 70 ? "green" : lead.score >= 40 ? "amber" : "gray"}>
          Score {lead.score}
        </Badge>
        {lead.deal_value != null ? (
          <Badge tone="blue">Deal {formatUsd(lead.deal_value)}</Badge>
        ) : null}
        {lead.won_at ? <Badge tone="green">Won {formatDate(lead.won_at)}</Badge> : null}
        {lead.lost_at ? <Badge tone="red">Lost {formatDate(lead.lost_at)}</Badge> : null}
      </div>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <section className="flex flex-col gap-3 lg:col-span-1">
          <h3 className="text-sm font-semibold">Profile</h3>
          <div className="rounded-lg border bg-white p-4 text-sm">
            <dl className="flex flex-col gap-2">
              {[["Company", lead.company], ["Position", lead.position], ...contactRows].map(
                ([label, value]) => (
                  <div key={label} className="flex justify-between gap-4">
                    <dt className="text-gray-500">{label}</dt>
                    <dd className="max-w-[60%] truncate text-right text-gray-800">
                      {value || "—"}
                    </dd>
                  </div>
                )
              )}
            </dl>
          </div>
        </section>

        <div className="flex flex-col gap-8 lg:col-span-2">
          <LeadNotesPanel
            key={`notes:${session.user.id}:${session.user.organization_id}:${lead.id}`}
            leadId={lead.id}
          />
          <LeadTasksPanel
            key={`tasks:${session.user.id}:${session.user.organization_id}:${lead.id}`}
            leadId={lead.id}
          />
          <LeadConversationsPanel
            key={`conversations:${session.user.id}:${session.user.organization_id}:${lead.id}`}
            leadId={lead.id}
          />
          <LeadAssignmentHistoryPanel
            key={`assignment:${session.user.id}:${session.user.organization_id}:${lead.id}`}
            leadId={lead.id}
            users={users}
          />
        </div>
      </div>

      <LeadFormModal
        open={editOpen}
        title="Edit lead"
        lead={lead}
        busy={busy}
        error={error}
        onClose={() => setEditOpen(false)}
        onSubmit={handleUpdate}
      />

      <ConfirmDialog
        open={deleteOpen}
        title="Delete lead"
        message="This permanently deletes the lead. This action cannot be undone."
        confirmLabel="Delete lead"
        busy={busy}
        onClose={() => setDeleteOpen(false)}
        onConfirm={handleDelete}
      />
    </div>
  );
}
