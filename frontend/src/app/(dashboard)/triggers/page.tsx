// Triggers: org-wide view of all workflow triggers with enable/disable.
"use client";

import { useCallback, useEffect, useState } from "react";

import {
  Badge,
  Button,
  EmptyState,
  PageHeader,
  Select,
  Spinner,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TRow,
} from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { ROUTES } from "@/lib/constants";
import { TRIGGER_TYPE_LABELS, formatDateTime } from "@/lib/format";
import { can } from "@/lib/permissions";
import {
  disableWorkflowTrigger,
  enableWorkflowTrigger,
  listWorkflowTriggers,
} from "@/services/workflow-triggers";
import type { WorkflowTrigger } from "@/types";

export default function TriggersPage() {
  const session = useAuth();
  const [triggers, setTriggers] = useState<WorkflowTrigger[]>([]);
  const [typeFilter, setTypeFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(() => {
    listWorkflowTriggers({ limit: 200 })
      .then((page) => {
        setTriggers(page.items);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Failed to load triggers");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!session) return null;
  const canWrite = can(session.user.role, "automation_write");

  const toggle = (trigger: WorkflowTrigger) => {
    setBusyId(trigger.id);
    (trigger.enabled ? disableWorkflowTrigger(trigger.id) : enableWorkflowTrigger(trigger.id))
      .then(load)
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Toggle failed");
      })
      .finally(() => setBusyId(null));
  };

  const visible = typeFilter ? triggers.filter((t) => t.trigger_type === typeFilter) : triggers;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Triggers"
        description="Everything that can kick off an automation across all workflows."
        actions={
          <Select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="w-48"
          >
            <option value="">All types</option>
            <option value="event">Event</option>
            <option value="schedule">Schedule</option>
            <option value="manual">Manual</option>
          </Select>
        }
      />

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {loading ? (
        <Spinner label="Loading triggers…" />
      ) : visible.length === 0 ? (
        <EmptyState title="No triggers" description="Add triggers from a workflow's detail page." />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Name</TH>
              <TH>Workflow</TH>
              <TH>Type</TH>
              <TH>Condition</TH>
              <TH>Status</TH>
              <TH>Updated</TH>
              <TH />
            </tr>
          </THead>
          <TBody>
            {visible.map((trigger) => (
              <TRow key={trigger.id}>
                <TD className="font-medium text-gray-900">{trigger.name}</TD>
                <TD>
                  <a
                    href={ROUTES.workflowDetail(trigger.workflow_id)}
                    className="text-gray-600 hover:underline"
                  >
                    {trigger.workflow_id.slice(0, 8)}
                  </a>
                </TD>
                <TD className="text-gray-600">{TRIGGER_TYPE_LABELS[trigger.trigger_type]}</TD>
                <TD className="text-gray-600">
                  {trigger.trigger_type === "event"
                    ? (trigger.event_type ?? "—")
                    : trigger.trigger_type === "schedule"
                      ? (trigger.schedule_cron ?? "—")
                      : "—"}
                </TD>
                <TD>
                  <Badge tone={trigger.enabled ? "green" : "gray"}>
                    {trigger.enabled ? "Enabled" : "Disabled"}
                  </Badge>
                </TD>
                <TD className="text-xs text-gray-400">{formatDateTime(trigger.updated_at)}</TD>
                <TD className="text-right">
                  {canWrite ? (
                    <Button
                      variant="outline"
                      disabled={busyId === trigger.id}
                      onClick={() => toggle(trigger)}
                    >
                      {trigger.enabled ? "Disable" : "Enable"}
                    </Button>
                  ) : null}
                </TD>
              </TRow>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}
