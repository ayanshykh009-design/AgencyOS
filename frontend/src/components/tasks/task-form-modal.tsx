// Task create/edit form.
"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { TASK_PRIORITY_LABELS } from "@/lib/format";
import type { RecurrenceFrequency, Task, TaskCreateInput, TaskPriority, User } from "@/types";

const PRIORITIES: TaskPriority[] = ["low", "medium", "high", "urgent"];
const RECURRENCE: Array<{ value: RecurrenceFrequency; label: string }> = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
];

interface TaskFormModalProps {
  open: boolean;
  title: string;
  task?: Task | null;
  users: User[];
  busy?: boolean;
  error?: string | null;
  onClose: () => void;
  onSubmit: (input: TaskCreateInput) => void;
}

function toLocalDate(iso?: string | null): string {
  if (!iso) return "";
  return new Date(iso).toISOString().slice(0, 16);
}

export function TaskFormModal({
  open,
  title,
  task,
  users,
  busy = false,
  error = null,
  onClose,
  onSubmit,
}: TaskFormModalProps) {
  const [form, setForm] = useState({
    title: task?.title ?? "",
    description: task?.description ?? "",
    assignee_user_id: task?.assignee_user_id ?? "",
    due_at: toLocalDate(task?.due_at),
    reminder_at: toLocalDate(task?.reminder_at),
    priority: (task?.priority ?? "medium") as TaskPriority,
    recurrence_frequency: (task?.recurrence_frequency ?? "") as RecurrenceFrequency | "",
    recurrence_interval: task?.recurrence_interval != null ? String(task.recurrence_interval) : "1",
  });

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit() {
    if (form.title.trim() === "") return;
    onSubmit({
      title: form.title.trim(),
      description: form.description.trim() || undefined,
      assignee_user_id: form.assignee_user_id || undefined,
      due_at: form.due_at ? new Date(form.due_at).toISOString() : undefined,
      reminder_at: form.reminder_at ? new Date(form.reminder_at).toISOString() : undefined,
      priority: form.priority,
      recurrence_frequency: form.recurrence_frequency || undefined,
      recurrence_interval:
        form.recurrence_frequency && Number.parseInt(form.recurrence_interval, 10) > 0
          ? Number.parseInt(form.recurrence_interval, 10)
          : undefined,
    });
  }

  return (
    <Modal
      open={open}
      title={title}
      width="md"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={busy || form.title.trim() === ""}>
            {busy ? "Saving…" : "Save task"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field label="Title" required>
          <Input value={form.title} onChange={(e) => set("title", e.target.value)} />
        </Field>
        <Field label="Description">
          <Textarea
            rows={3}
            value={form.description}
            onChange={(e) => set("description", e.target.value)}
          />
        </Field>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Assignee">
            <Select
              value={form.assignee_user_id}
              onChange={(e) => set("assignee_user_id", e.target.value)}
            >
              <option value="">Unassigned</option>
              {users.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.full_name || user.email}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Priority">
            <Select value={form.priority} onChange={(e) => set("priority", e.target.value)}>
              {PRIORITIES.map((value) => (
                <option key={value} value={value}>
                  {TASK_PRIORITY_LABELS[value]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Due at">
            <Input
              type="datetime-local"
              value={form.due_at}
              onChange={(e) => set("due_at", e.target.value)}
            />
          </Field>
          <Field label="Reminder at">
            <Input
              type="datetime-local"
              value={form.reminder_at}
              onChange={(e) => set("reminder_at", e.target.value)}
            />
          </Field>
          <Field label="Recurrence" hint="Optional; repeats the task after completion.">
            <Select
              value={form.recurrence_frequency}
              onChange={(e) => set("recurrence_frequency", e.target.value)}
            >
              <option value="">None</option>
              {RECURRENCE.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Repeat every">
            <Input
              type="number"
              min={1}
              value={form.recurrence_interval}
              disabled={!form.recurrence_frequency}
              onChange={(e) => set("recurrence_interval", e.target.value)}
            />
          </Field>
        </div>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
      </div>
    </Modal>
  );
}
