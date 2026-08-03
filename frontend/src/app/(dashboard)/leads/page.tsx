// Leads list: filter, search, export, create, and open a lead.
"use client";

import { useCallback, useEffect, useState } from "react";

import { LeadFormModal } from "@/components/leads/lead-form-modal";
import { Badge, Button, EmptyState, Input, PageHeader, Spinner, Select } from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { ROUTES } from "@/lib/constants";
import { formatUsd, leadName } from "@/lib/format";
import { can } from "@/lib/permissions";
import { createLead, listLeads, type LeadQuery } from "@/services/leads";
import { downloadExport, type ExportFormat } from "@/services/exports";
import type { Lead, LeadCreateInput, LeadStatus, Page } from "@/types";
import type { BadgeTone } from "@/lib/format";

const STATUSES: Array<{ value: LeadStatus; label: string }> = [
  { value: "new", label: "New" },
  { value: "researching", label: "Researching" },
  { value: "contacted", label: "Contacted" },
  { value: "meeting_booked", label: "Meeting booked" },
  { value: "proposal_sent", label: "Proposal sent" },
  { value: "won", label: "Won" },
  { value: "lost", label: "Lost" },
];

const PAGE_SIZE = 20;

function statusTone(status: LeadStatus): BadgeTone {
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

export default function LeadsPage() {
  const session = useAuth();
  const [data, setData] = useState<Page<Lead>>({ items: [], total: 0 });
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const load = useCallback(
    (search: string, filter: string, pageOffset: number) => {
      if (!session) return;
      const q: LeadQuery = {
        query: search.trim() || undefined,
        status: (filter || undefined) as LeadStatus | undefined,
        sort: "created_at",
        order: "desc",
        limit: PAGE_SIZE,
        offset: pageOffset,
      };
      listLeads(q)
        .then((page) => {
          setData(page);
          setError(null);
        })
        .catch((err: unknown) => {
          setError(err instanceof ApiRequestError ? err.message : "Failed to load leads");
        })
        .finally(() => setLoading(false));
    },
    [session]
  );

  useEffect(() => {
    load(query, status, offset);
  }, [load, query, status, offset]);

  async function handleCreate(input: LeadCreateInput) {
    if (!session) return;
    setSaving(true);
    setSaveError(null);
    try {
      await createLead(input);
      setCreateOpen(false);
      load(query, status, 0);
    } catch (err: unknown) {
      setSaveError(err instanceof ApiRequestError ? err.message : "Failed to create lead");
    } finally {
      setSaving(false);
    }
  }

  async function handleExport(fmt: ExportFormat) {
    if (!session) return;
    try {
      await downloadExport(fmt, {
        query: query.trim() || undefined,
        status: (status || undefined) as LeadStatus | undefined,
      });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Export failed");
    }
  }

  if (!session) return null;
  const canWrite = can(session.user.role, "lead_write");
  const canExport = can(session.user.role, "export");
  const totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Leads"
        description={`${data.total} total`}
        actions={
          <>
            {canExport ? (
              <>
                <Button variant="outline" onClick={() => handleExport("csv")}>
                  Export CSV
                </Button>
                <Button variant="outline" onClick={() => handleExport("json")}>
                  Export JSON
                </Button>
              </>
            ) : null}
            {canWrite ? <Button onClick={() => setCreateOpen(true)}>New lead</Button> : null}
          </>
        }
      />

      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          placeholder="Search name, company, email…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOffset(0);
          }}
          className="sm:max-w-xs"
        />
        <Select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setOffset(0);
          }}
          className="sm:w-48"
        >
          <option value="">All statuses</option>
          {STATUSES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
      </div>

      {loading ? (
        <Spinner label="Loading leads…" />
      ) : error ? (
        <p className="text-red-600">{error}</p>
      ) : data.items.length === 0 ? (
        <EmptyState
          title="No leads found"
          description="Try adjusting your filters, or create a new lead to get started."
          action={
            canWrite ? <Button onClick={() => setCreateOpen(true)}>New lead</Button> : undefined
          }
        />
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead className="border-b bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
                <tr>
                  <th className="px-4 py-2 font-medium">Name</th>
                  <th className="px-4 py-2 font-medium">Company</th>
                  <th className="px-4 py-2 font-medium">Email</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Score</th>
                  <th className="px-4 py-2 font-medium">Deal value</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.items.map((lead) => (
                  <tr key={lead.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 align-middle">
                      <a
                        href={ROUTES.leadDetail(lead.id)}
                        className="font-medium text-gray-900 hover:underline"
                      >
                        {leadName(lead)}
                      </a>
                    </td>
                    <td className="px-4 py-3 align-middle text-gray-600">{lead.company ?? "—"}</td>
                    <td className="px-4 py-3 align-middle text-gray-600">{lead.email ?? "—"}</td>
                    <td className="px-4 py-3 align-middle">
                      <Badge tone={statusTone(lead.status)}>{lead.status.replace(/_/g, " ")}</Badge>
                    </td>
                    <td className="px-4 py-3 align-middle">{lead.score}</td>
                    <td className="px-4 py-3 align-middle">
                      {lead.deal_value != null ? formatUsd(lead.deal_value) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between text-sm">
            <p className="text-gray-500">
              Page {currentPage} of {totalPages}
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                disabled={offset === 0}
                onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                disabled={offset + PAGE_SIZE >= data.total}
                onClick={() => setOffset((value) => value + PAGE_SIZE)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}

      <LeadFormModal
        open={createOpen}
        title="New lead"
        busy={saving}
        error={saveError}
        onClose={() => setCreateOpen(false)}
        onSubmit={handleCreate}
      />
    </div>
  );
}
