// Tasks service: filters, CRUD, completion, and the due-reminder sweep.
import { apiFetch } from "@/lib/api-client";
import type {
  Page,
  Task,
  TaskCompleteResponse,
  TaskCreateInput,
  TaskPriority,
  TaskStatus,
  TaskUpdateInput,
} from "@/types";

export interface TaskQuery {
  leadId?: string;
  assigneeUserId?: string;
  status?: TaskStatus;
  priority?: TaskPriority;
  dueBefore?: string;
  dueAfter?: string;
  sort?: string;
  order?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export async function listTasks(query: TaskQuery = {}): Promise<Page<Task>> {
  const params = new URLSearchParams();
  if (query.leadId) params.set("lead_id", query.leadId);
  if (query.assigneeUserId) params.set("assignee_user_id", query.assigneeUserId);
  if (query.status) params.set("status", query.status);
  if (query.priority) params.set("priority", query.priority);
  if (query.dueBefore) params.set("due_before", query.dueBefore);
  if (query.dueAfter) params.set("due_after", query.dueAfter);
  if (query.sort) params.set("sort", query.sort);
  if (query.order) params.set("order", query.order);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));

  const qs = params.toString();
  return apiFetch<Page<Task>>(`/tasks${qs ? `?${qs}` : ""}`);
}

export async function listTasksDueForReminder(): Promise<Task[]> {
  return apiFetch<Task[]>("/tasks/reminders/due");
}

export async function getTask(taskId: string): Promise<Task> {
  return apiFetch<Task>(`/tasks/${taskId}`);
}

export async function createTask(input: TaskCreateInput): Promise<Task> {
  return apiFetch<Task>("/tasks", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateTask(taskId: string, patch: TaskUpdateInput): Promise<Task> {
  return apiFetch<Task>(`/tasks/${taskId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function completeTask(taskId: string): Promise<TaskCompleteResponse> {
  return apiFetch<TaskCompleteResponse>(`/tasks/${taskId}/complete`, {
    method: "POST",
  });
}

export async function deleteTask(taskId: string): Promise<void> {
  await apiFetch<void>(`/tasks/${taskId}`, { method: "DELETE" });
}
