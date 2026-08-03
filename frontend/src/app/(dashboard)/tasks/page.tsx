// Tasks: filterable list with create, complete, and delete.
"use client";

import { useCallback, useEffect, useState } from "react";

import { TaskFormModal } from "@/components/tasks/task-form-modal";
import {
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  PageHeader,
  Select,
  Spinner,
} from "@/components/ui";
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
import { listUsers } from "@/services/users";
import type { Page, Task, TaskCreateInput, TaskPriority, TaskStatus, User } from "@/types";

const PRIORITIES: TaskPriority[] = ["low", "medium", "high", "urgent"];
const STATUSES: TaskStatus[] = ["todo", "in_progress", "completed", "cancelled"];
const PAGE_SIZE = 25;

export default function TasksPage() {
  const session = useAuth();
  const [data, setData] = useState<Page<Task>>({ items: [], total: 0 });
  const [users, setUsers] = useState<User[]>([]);
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [assignee, setAssignee] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Task | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    (filterStatus: string, filterPriority: string, filterAssignee: string, pageOffset: number) => {
      listTasks({
        status: (filterStatus || undefined) as TaskStatus | undefined,
        priority: (filterPriority || undefined) as TaskPriority | undefined,
        assigneeUserId: filterAssignee || undefined,
        sort: "due_at",
        order: "asc",
        limit: PAGE_SIZE,
        offset: pageOffset,
      })
        .then((page) => {
          setData(page);
          setError(null);
        })
        .catch((err: unknown) => {
          setError(err instanceof ApiRequestError ? err.message : "Failed to load tasks");
        })
        .finally(() => setLoading(false));
    },
    []
  );

  useEffect(() => {
    load(status, priority, assignee, offset);
  }, [load, status, priority, assignee, offset]);

  useEffect(() => {
    listUsers(100)
      .then((page) => setUsers(page.items))
      .catch(() => undefined);
  }, []);

  if (!session) return null;
  const canWrite = can(session.user.role, "task_write");

  async function handleCreate(input: TaskCreateInput) {
    setBusy(true);
    setError(null);
    try {
      await createTask(input);
      setCreateOpen(false);
      load(status, priority, assignee, offset);
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to create task");
    } finally {
      setBusy(false);
    }
  }

  async function handleStatus(task: Task, next: TaskStatus) {
    try {
      await updateTask(task.id, { status: next });
      load(status, priority, assignee, offset);
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to update task");
    }
  }

  async function handleComplete(task: Task) {
    try {
      await completeTask(task.id);
      load(status, priority, assignee, offset);
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to complete task");
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setBusy(true);
    setError(null);
    try {
      await deleteTask(deleteTarget.id);
      setDeleteTarget(null);
      load(status, priority, assignee, offset);
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to delete task");
    } finally {
      setBusy(false);
    }
  }

  const userById = new Map(users.map((user) => [user.id, user]));
  const totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Tasks"
        description={`${data.total} total`}
        actions={
          canWrite ? <Button onClick={() => setCreateOpen(true)}>New task</Button> : undefined
        }
      />

      <div className="flex flex-col gap-2 sm:flex-row">
        <Select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setOffset(0);
          }}
          className="sm:w-40"
        >
          <option value="">All statuses</option>
          {STATUSES.map((value) => (
            <option key={value} value={value}>
              {TASK_STATUS_LABELS[value]}
            </option>
          ))}
        </Select>
        <Select
          value={priority}
          onChange={(e) => {
            setPriority(e.target.value);
            setOffset(0);
          }}
          className="sm:w-40"
        >
          <option value="">All priorities</option>
          {PRIORITIES.map((value) => (
            <option key={value} value={value}>
              {TASK_PRIORITY_LABELS[value]}
            </option>
          ))}
        </Select>
        <Select
          value={assignee}
          onChange={(e) => {
            setAssignee(e.target.value);
            setOffset(0);
          }}
          className="sm:w-48"
        >
          <option value="">All assignees</option>
          {users.map((user) => (
            <option key={user.id} value={user.id}>
              {user.full_name || user.email}
            </option>
          ))}
        </Select>
      </div>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {loading ? (
        <Spinner label="Loading tasks…" />
      ) : data.items.length === 0 ? (
        <EmptyState
          title="No tasks found"
          description="Adjust the filters, or create a task to get started."
          action={
            canWrite ? <Button onClick={() => setCreateOpen(true)}>New task</Button> : undefined
          }
        />
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead className="border-b bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
                <tr>
                  <th className="px-4 py-2 font-medium">Title</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Priority</th>
                  <th className="px-4 py-2 font-medium">Assignee</th>
                  <th className="px-4 py-2 font-medium">Due</th>
                  <th className="px-4 py-2 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.items.map((task) => {
                  const assigneeUser = task.assignee_user_id
                    ? userById.get(task.assignee_user_id)
                    : undefined;
                  return (
                    <tr key={task.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 align-middle">
                        <div className="flex flex-col">
                          <span
                            className={
                              task.status === "completed"
                                ? "text-gray-400 line-through"
                                : "font-medium"
                            }
                          >
                            {task.title}
                          </span>
                          {task.recurrence_frequency ? (
                            <span className="text-xs text-gray-400">
                              Repeats {task.recurrence_frequency}
                              {task.recurrence_interval ? ` ×${task.recurrence_interval}` : ""}
                            </span>
                          ) : null}
                        </div>
                      </td>
                      <td className="px-4 py-3 align-middle">
                        <Select
                          value={task.status}
                          onChange={(e) => handleStatus(task, e.target.value as TaskStatus)}
                          className="w-36"
                        >
                          {STATUSES.map((value) => (
                            <option key={value} value={value}>
                              {TASK_STATUS_LABELS[value]}
                            </option>
                          ))}
                        </Select>
                      </td>
                      <td className="px-4 py-3 align-middle">
                        <Badge tone={taskPriorityTone(task.priority)}>
                          {TASK_PRIORITY_LABELS[task.priority]}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 align-middle text-gray-600">
                        {assigneeUser?.full_name || assigneeUser?.email || "—"}
                      </td>
                      <td className="px-4 py-3 align-middle text-gray-600">
                        {task.due_at ? formatDate(task.due_at) : "—"}
                      </td>
                      <td className="px-4 py-3 align-middle">
                        <span className="flex gap-2">
                          <Badge tone={taskStatusTone(task.status)}>
                            {TASK_STATUS_LABELS[task.status]}
                          </Badge>
                          {task.status !== "completed" ? (
                            <Button variant="outline" onClick={() => handleComplete(task)}>
                              Complete
                            </Button>
                          ) : null}
                          {canWrite ? (
                            <Button variant="ghost" onClick={() => setDeleteTarget(task)}>
                              Delete
                            </Button>
                          ) : null}
                        </span>
                      </td>
                    </tr>
                  );
                })}
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

      <TaskFormModal
        open={createOpen}
        title="New task"
        users={users}
        busy={busy}
        error={error}
        onClose={() => setCreateOpen(false)}
        onSubmit={handleCreate}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete task"
        message={`Delete "${deleteTarget?.title ?? ""}"? This action cannot be undone.`}
        confirmLabel="Delete task"
        busy={busy}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
      />
    </div>
  );
}
