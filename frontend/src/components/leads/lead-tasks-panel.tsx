// Task list for a single lead: create, complete, delete.
"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge, Button, EmptyState, Field, Input, Select, Spinner } from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import {
  TASK_PRIORITY_LABELS,
  TASK_STATUS_LABELS,
  formatDate,
  taskPriorityTone,
  taskStatusTone,
} from "@/lib/format";
import { can } from "@/lib/permissions";
import { completeTask, createTask, deleteTask, listTasks, updateTask } from "@/services/tasks";
import type { Page, Task, TaskPriority, TaskStatus } from "@/types";

const PRIORITIES: TaskPriority[] = ["low", "medium", "high", "urgent"];
const STATUSES: TaskStatus[] = ["todo", "in_progress", "completed", "cancelled"];

export function LeadTasksPanel({ leadId }: { leadId: string }) {
  const session = useAuth();
  const [data, setData] = useState<Page<Task>>({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState<TaskPriority>("medium");
  const [dueDate, setDueDate] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    listTasks({ leadId, sort: "due_at", order: "asc", limit: 50 })
      .then((page) => setData(page))
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Failed to load tasks");
      })
      .finally(() => setLoading(false));
  }, [leadId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!session) return null;
  const canWrite = can(session.user.role, "task_write");

  async function handleCreate() {
    if (title.trim() === "") return;
    setSaving(true);
    setError(null);
    try {
      await createTask({
        title: title.trim(),
        lead_id: leadId,
        priority,
        due_at: dueDate ? new Date(dueDate).toISOString() : undefined,
      });
      setTitle("");
      setPriority("medium");
      setDueDate("");
      load();
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to create task");
    } finally {
      setSaving(false);
    }
  }

  async function handleComplete(task: Task) {
    try {
      await completeTask(task.id);
      load();
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to complete task");
    }
  }

  async function handleStatus(task: Task, status: TaskStatus) {
    try {
      await updateTask(task.id, { status });
      load();
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to update task");
    }
  }

  async function handleDelete(task: Task) {
    try {
      await deleteTask(task.id);
      load();
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to delete task");
    }
  }

  return (
    <section className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold">Tasks</h3>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {loading ? (
        <Spinner label="Loading tasks…" />
      ) : data.items.length === 0 ? (
        <EmptyState
          title="No tasks"
          description="Create a task to track follow-up work for this lead."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {data.items.map((task) => (
            <li
              key={task.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-white p-3 text-sm"
            >
              <div className="flex flex-col gap-1">
                <span className={task.status === "completed" ? "text-gray-400 line-through" : ""}>
                  {task.title}
                </span>
                <span className="flex flex-wrap items-center gap-2 text-xs text-gray-500">
                  <Badge tone={taskPriorityTone(task.priority)}>
                    {TASK_PRIORITY_LABELS[task.priority]}
                  </Badge>
                  <Badge tone={taskStatusTone(task.status)}>
                    {TASK_STATUS_LABELS[task.status]}
                  </Badge>
                  {task.due_at ? <time>{formatDate(task.due_at)}</time> : null}
                </span>
              </div>
              {canWrite ? (
                <span className="flex gap-2">
                  <Select
                    value={task.status}
                    onChange={(e) => handleStatus(task, e.target.value as TaskStatus)}
                    className="w-32"
                  >
                    {STATUSES.map((status) => (
                      <option key={status} value={status}>
                        {TASK_STATUS_LABELS[status]}
                      </option>
                    ))}
                  </Select>
                  {task.status !== "completed" ? (
                    <Button variant="outline" onClick={() => handleComplete(task)}>
                      Complete
                    </Button>
                  ) : null}
                  <Button variant="ghost" onClick={() => handleDelete(task)}>
                    Delete
                  </Button>
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {canWrite ? (
        <div className="flex flex-col gap-2 rounded-lg border bg-white p-3">
          <Input
            placeholder="New task title…"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Priority" className="w-32">
              <Select
                value={priority}
                onChange={(e) => setPriority(e.target.value as TaskPriority)}
              >
                {PRIORITIES.map((value) => (
                  <option key={value} value={value}>
                    {TASK_PRIORITY_LABELS[value]}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Due date" className="w-40">
              <Input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
            </Field>
            <Button onClick={handleCreate} disabled={saving || title.trim() === ""}>
              {saving ? "Adding…" : "Add task"}
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
