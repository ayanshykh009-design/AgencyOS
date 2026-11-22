// Triggers: org-wide read-only table plus real create/edit/enable/disable
// flows. Scheduling is UTC-only; no local-time picker is offered.
"use client";

import { useCallback, useEffect, useState } from "react";

import { AutomationListState, formatUtcOrNever } from "@/components/automation/automation-states";
import {
  Badge,
  Button,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
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
import { TRIGGER_TYPE_LABELS } from "@/lib/format";
import { canReadTriggers, canWriteTriggers } from "@/lib/batch6-permissions";
import {
  disableWorkflowTrigger,
  enableWorkflowTrigger,
  listWorkflowTriggers,
  updateWorkflowTrigger,
  createWorkflowTrigger,
} from "@/services/workflow-triggers";
import { listWorkflows } from "@/services/workflows";
import type { UserRole, Workflow, WorkflowTrigger, WorkflowTriggerType } from "@/types";

/** Exported for static-markup tests: denied roles see no mutation buttons. */
export function TriggerRowActions({
  role,
  enabled,
  busy,
  onEdit,
  onToggle,
}: {
  role: UserRole;
  enabled: boolean;
  busy: boolean;
  onEdit: () => void;
  onToggle: () => void;
}) {
  if (!canWriteTriggers(role)) return null;
  return (
    <div className="flex items-center justify-end gap-2">
      <Button variant="ghost" disabled={busy} onClick={onEdit}>
        Edit
      </Button>
      <Button variant="outline" disabled={busy} onClick={onToggle}>
        {enabled ? "Disable" : "Enable"}
      </Button>
    </div>
  );
}

export default function TriggersPage() {
  const session = useAuth();
  const [triggers, setTriggers] = useState<WorkflowTrigger[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [typeFilter, setTypeFilter] = useState<"" | WorkflowTriggerType>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [formTarget, setFormTarget] = useState<WorkflowTrigger | "new" | null>(null);
  const [formName, setFormName] = useState("");
  const [formWorkflowId, setFormWorkflowId] = useState("");
  const [formType, setFormType] = useState<WorkflowTriggerType>("event");
  const [formEventType, setFormEventType] = useState("");
  const [formCron, setFormCron] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const role = session?.user.role;
  const canRead = role ? canReadTriggers(role) : false;
  const canWrite = role ? canWriteTriggers(role) : false;

  const fetchTriggers = useCallback(() => {
    return listWorkflowTriggers({
      limit: 200,
      triggerType: typeFilter || undefined,
    })
      .then((page) => {
        setTriggers(page.items);
        setError(null);
      })
      .catch((err: unknown) => {
        setTriggers([]);
        setError(err instanceof ApiRequestError ? err.message : "Failed to load triggers");
      })
      .finally(() => setLoading(false));
  }, [typeFilter]);

  const reload = useCallback(() => {
    setLoading(true);
    return fetchTriggers();
  }, [fetchTriggers]);

  useEffect(() => {
    if (canRead) void fetchTriggers();
  }, [canRead, fetchTriggers]);

  useEffect(() => {
    if (!canWrite) return;
    listWorkflows({ limit: 200 })
      .then((page) => setWorkflows(page.items))
      .catch(() => setWorkflows([]));
  }, [canWrite]);

  if (!session) return null;

  const openForm = (target: WorkflowTrigger | "new") => {
    setFormTarget(target);
    setFormError(null);
    if (target === "new") {
      setFormName("");
      setFormWorkflowId(workflows[0]?.id ?? "");
      setFormType("event");
      setFormEventType("");
      setFormCron("");
    } else {
      setFormName(target.name);
      setFormWorkflowId(target.workflow_id);
      setFormType(target.trigger_type);
      setFormEventType(target.event_type ?? "");
      setFormCron(target.schedule_cron ?? "");
    }
  };

  const saveForm = () => {
    if (!formName.trim() || !formWorkflowId) {
      setFormError("Name and workflow are required");
      return;
    }
    if (formType === "event" && !formEventType.trim()) {
      setFormError("Event type is required for event triggers");
      return;
    }
    const target = formTarget;
    if (!target) return;
    setBusyId(target === "new" ? "new" : target.id);
    setFormError(null);
    const payload = {
      name: formName.trim(),
      trigger_type: formType,
      event_type: formType === "event" ? formEventType.trim() : undefined,
      schedule_cron: formType === "schedule" ? formCron.trim() : undefined,
    };
    const request =
      target === "new"
        ? createWorkflowTrigger({ ...payload, workflow_id: formWorkflowId })
        : updateWorkflowTrigger(target.id, payload);
    request
      .then(() => {
        setFormTarget(null);
        return reload();
      })
      .catch((err: unknown) => {
        setFormError(err instanceof ApiRequestError ? err.message : "Failed to save trigger");
      })
      .finally(() => setBusyId(null));
  };

  const toggle = (trigger: WorkflowTrigger) => {
    setBusyId(trigger.id);
    (trigger.enabled ? disableWorkflowTrigger(trigger.id) : enableWorkflowTrigger(trigger.id))
      .then(() => {
        setError(null);
        return reload();
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Toggle failed");
      })
      .finally(() => setBusyId(null));
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Triggers"
        description="Everything that can start an automation across all workflows. Times are shown in UTC."
        actions={
          canRead && canWrite ? (
            <div className="flex items-center gap-2">
              <Select
                value={typeFilter}
                onChange={(e) => {
                  setLoading(true);
                  setTypeFilter(e.target.value as "" | WorkflowTriggerType);
                }}
                className="w-40"
                aria-label="Filter by trigger type"
              >
                <option value="">All types</option>
                <option value="event">Event</option>
                <option value="schedule">Schedule</option>
                <option value="manual">Manual</option>
              </Select>
              <Button onClick={() => openForm("new")}>New trigger</Button>
            </div>
          ) : undefined
        }
      />

      <AutomationListState
        denied={!canRead}
        deniedMessage="You do not have permission to view workflow triggers."
        loading={loading}
        loadingLabel="Loading triggers…"
        error={error}
        onRetry={() => void reload()}
        empty={triggers.length === 0}
        emptyTitle="No triggers"
        emptyDescription="Add triggers from a workflow's detail page or with New trigger."
      />

      {canRead && !loading && !error && triggers.length > 0 ? (
        <Table>
          <THead>
            <tr>
              <TH>Name</TH>
              <TH>Workflow</TH>
              <TH>Type</TH>
              <TH>Condition</TH>
              <TH>Last fired (UTC)</TH>
              <TH>Status</TH>
              <TH>Actions</TH>
            </tr>
          </THead>
          <TBody>
            {triggers.map((trigger) => (
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
                <TD className="text-xs text-gray-600">{formatUtcOrNever(trigger.last_fired_at)}</TD>
                <TD>
                  <Badge tone={trigger.enabled ? "green" : "gray"}>
                    {trigger.enabled ? "Enabled" : "Disabled"}
                  </Badge>
                </TD>
                <TD>
                  <TriggerRowActions
                    role={session.user.role}
                    enabled={trigger.enabled}
                    busy={busyId === trigger.id}
                    onEdit={() => openForm(trigger)}
                    onToggle={() => toggle(trigger)}
                  />
                </TD>
              </TRow>
            ))}
          </TBody>
        </Table>
      ) : null}

      <Modal
        open={formTarget !== null}
        title={formTarget === "new" ? "New trigger" : "Edit trigger"}
        onClose={() => setFormTarget(null)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setFormTarget(null)} disabled={busyId !== null}>
              Cancel
            </Button>
            <Button onClick={saveForm} disabled={busyId !== null}>
              {busyId !== null ? "Saving…" : "Save"}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label="Name" htmlFor="trg-name" required>
            <Input id="trg-name" value={formName} onChange={(e) => setFormName(e.target.value)} />
          </Field>
          <Field
            label="Workflow"
            htmlFor="trg-workflow"
            required
            hint={formTarget === "new" ? undefined : "Workflow cannot be changed here."}
          >
            <Select
              id="trg-workflow"
              value={formWorkflowId}
              disabled={formTarget !== "new"}
              onChange={(e) => setFormWorkflowId(e.target.value)}
            >
              <option value="">Select a workflow</option>
              {workflows.map((workflow) => (
                <option key={workflow.id} value={workflow.id}>
                  {workflow.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Trigger type" htmlFor="trg-type">
            <Select
              id="trg-type"
              value={formType}
              onChange={(e) => setFormType(e.target.value as WorkflowTriggerType)}
            >
              <option value="event">Event</option>
              <option value="schedule">Schedule</option>
              <option value="manual">Manual</option>
            </Select>
          </Field>
          {formType === "event" ? (
            <Field label="Event type" htmlFor="trg-event" required>
              <Input
                id="trg-event"
                value={formEventType}
                onChange={(e) => setFormEventType(e.target.value)}
                placeholder="e.g. lead_created"
              />
            </Field>
          ) : null}
          {formType === "schedule" ? (
            <Field
              label="Cron expression"
              htmlFor="trg-cron"
              hint="UTC only; local-time scheduling is not available."
            >
              <Input
                id="trg-cron"
                value={formCron}
                onChange={(e) => setFormCron(e.target.value)}
                placeholder="e.g. 0 9 * * 1"
              />
            </Field>
          ) : null}
          {formError ? (
            <p role="alert" className="text-sm text-red-600">
              {formError}
            </p>
          ) : null}
        </div>
      </Modal>
    </div>
  );
}
