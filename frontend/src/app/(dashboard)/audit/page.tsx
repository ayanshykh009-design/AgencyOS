// Audit log: admin-only read of the organization activity trail.
"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge, EmptyState, PageHeader, Select, Spinner } from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { formatDateTime } from "@/lib/format";
import { can } from "@/lib/permissions";
import { listAuditLogs } from "@/services/audit";
import type { AuditLogEntry } from "@/types";

const EVENT_TYPES: string[] = [
  "lead_created",
  "lead_updated",
  "lead_deleted",
  "lead_assigned",
  "lead_stage_moved",
  "note_created",
  "task_created",
  "task_completed",
  "task_updated",
  "task_deleted",
  "user_login",
  "user_invited",
  "invite_accepted",
  "invite_revoked",
];

export default function AuditPage() {
  const session = useAuth();
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [eventType, setEventType] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((filter: string) => {
    listAuditLogs({
      eventType: filter || undefined,
      limit: 200,
    })
      .then((entries) => {
        setEntries(entries);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Failed to load audit log");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load(eventType);
  }, [load, eventType]);

  if (!session) return null;
  if (!can(session.user.role, "audit_read")) {
    return (
      <p className="text-red-600">
        You do not have permission to view the audit log. Contact an administrator.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Audit log"
        description="A read-only trail of activity across the organization."
        actions={
          <Select value={eventType} onChange={(e) => setEventType(e.target.value)} className="w-52">
            <option value="">All events</option>
            {EVENT_TYPES.map((value) => (
              <option key={value} value={value}>
                {value.replace(/_/g, " ")}
              </option>
            ))}
          </Select>
        }
      />

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {loading ? (
        <Spinner label="Loading audit log…" />
      ) : entries.length === 0 ? (
        <EmptyState
          title="No audit entries"
          description="Activity will appear here as events occur."
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="border-b bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-2 font-medium">Actor</th>
                <th className="px-4 py-2 font-medium">Event</th>
                <th className="px-4 py-2 font-medium">Entity</th>
                <th className="px-4 py-2 font-medium">Description</th>
                <th className="px-4 py-2 font-medium">Occurred</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {entries.map((entry) => (
                <tr key={entry.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 align-middle text-gray-700">
                    {entry.actor_name ?? "System"}
                  </td>
                  <td className="px-4 py-3 align-middle">
                    <Badge tone="gray">{entry.event_type.replace(/_/g, " ")}</Badge>
                  </td>
                  <td className="px-4 py-3 align-middle text-gray-600">
                    {entry.entity_type
                      ? `${entry.entity_type}:${entry.entity_id?.slice(0, 8)}`
                      : "—"}
                  </td>
                  <td className="px-4 py-3 align-middle text-gray-600">
                    {entry.description ?? "—"}
                  </td>
                  <td className="px-4 py-3 align-middle text-xs text-gray-400">
                    {formatDateTime(entry.occurred_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
