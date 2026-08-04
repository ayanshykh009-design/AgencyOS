// Shared formatting helpers for the UI (dates, currency, names).
import type {
  CredentialType,
  ExecutionStatus,
  Lead,
  TaskPriority,
  TaskStatus,
  WorkflowStatus,
  WorkflowTriggerType,
} from "@/types";

/** Badge color tones supported by <Badge tone>. */
export type BadgeTone = "gray" | "green" | "red" | "amber" | "blue" | "purple";

export function formatUsd(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
}

export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
  }).format(new Date(iso));
}

export function formatRelative(iso: string): string {
  const delta = new Date(iso).getTime() - Date.now();
  const abs = Math.abs(delta);
  const units: Array<[number, Intl.RelativeTimeFormatUnit]> = [
    [365 * 24 * 60 * 60 * 1000, "year"],
    [30 * 24 * 60 * 60 * 1000, "month"],
    [7 * 24 * 60 * 60 * 1000, "week"],
    [24 * 60 * 60 * 1000, "day"],
    [60 * 60 * 1000, "hour"],
    [60 * 1000, "minute"],
  ];
  const formatter = new Intl.RelativeTimeFormat("en-US", { numeric: "auto" });
  for (const [ms, unit] of units) {
    if (abs >= ms) {
      return formatter.format(Math.round(delta / ms), unit);
    }
  }
  return formatter.format(Math.round(delta / 1000), "second");
}

/** Human-friendly display name for a lead. */
export function leadName(lead: Pick<Lead, "first_name" | "last_name" | "email">): string {
  const name = [lead.first_name, lead.last_name].filter(Boolean).join(" ").trim();
  if (name) return name;
  return lead.email ?? "Unnamed lead";
}

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  todo: "To do",
  in_progress: "In progress",
  completed: "Completed",
  cancelled: "Cancelled",
};

export const TASK_PRIORITY_LABELS: Record<TaskPriority, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  urgent: "Urgent",
};

export function taskStatusTone(status: TaskStatus): BadgeTone {
  switch (status) {
    case "completed":
      return "green";
    case "in_progress":
      return "blue";
    case "cancelled":
      return "gray";
    default:
      return "amber";
  }
}

export function taskPriorityTone(priority: TaskPriority): BadgeTone {
  switch (priority) {
    case "urgent":
      return "red";
    case "high":
      return "amber";
    case "medium":
      return "blue";
    default:
      return "gray";
  }
}

export const WORKFLOW_STATUS_LABELS: Record<WorkflowStatus, string> = {
  draft: "Draft",
  active: "Active",
  paused: "Paused",
  archived: "Archived",
};

export function workflowStatusTone(status: WorkflowStatus): BadgeTone {
  switch (status) {
    case "active":
      return "green";
    case "paused":
      return "amber";
    case "archived":
      return "gray";
    default:
      return "blue";
  }
}

export const EXECUTION_STATUS_LABELS: Record<ExecutionStatus, string> = {
  queued: "Queued",
  running: "Running",
  succeeded: "Succeeded",
  failed: "Failed",
  retrying: "Retrying",
  cancelled: "Cancelled",
  timed_out: "Timed out",
};

export function executionStatusTone(status: ExecutionStatus): BadgeTone {
  switch (status) {
    case "succeeded":
      return "green";
    case "running":
      return "blue";
    case "retrying":
      return "amber";
    case "failed":
    case "timed_out":
      return "red";
    case "cancelled":
      return "gray";
    default:
      return "purple";
  }
}

export const TRIGGER_TYPE_LABELS: Record<WorkflowTriggerType, string> = {
  manual: "Manual",
  event: "Event",
  schedule: "Schedule",
};

export const CREDENTIAL_TYPE_LABELS: Record<CredentialType, string> = {
  n8n_api_key: "n8n API key",
  api_key: "API key",
  basic_auth: "Basic auth",
};
