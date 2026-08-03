import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, setSession } from "@/lib/session";
import {
  completeTask,
  createTask,
  deleteTask,
  listTasks,
  listTasksDueForReminder,
  updateTask,
} from "@/services/tasks";
import type { Task, User } from "@/types";

const USER: User = {
  id: "11111111-1111-1111-1111-111111111111",
  organization_id: "22222222-2222-2222-2222-222222222222",
  email: "owner@example.com",
  full_name: "Owner",
  role: "owner",
  is_active: true,
  last_login_at: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

const TASK: Task = {
  id: "44444444-4444-4444-4444-444444444444",
  organization_id: USER.organization_id,
  lead_id: null,
  assignee_user_id: USER.id,
  created_by_user_id: USER.id,
  title: "Follow up",
  description: null,
  status: "todo",
  priority: "medium",
  due_at: "2026-08-05T00:00:00Z",
  reminder_at: null,
  completed_at: null,
  recurrence_frequency: null,
  recurrence_interval: null,
  created_at: "2026-08-02T00:00:00Z",
  updated_at: "2026-08-02T00:00:00Z",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("tasks service", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    clearSession();
    setSession({ accessToken: "access-123", refreshToken: "r", expiresIn: 3600, user: USER });
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    clearSession();
  });

  it("listTasks encodes filters", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [TASK], total: 1 }));

    const page = await listTasks({
      status: "in_progress",
      priority: "high",
      dueBefore: "2026-08-06",
    });

    expect(page.total).toBe(1);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("status=in_progress");
    expect(url).toContain("priority=high");
    expect(url).toContain("due_before=2026-08-06");
  });

  it("listTasksDueForReminder hits the reminders sweep", async () => {
    fetchMock.mockResolvedValue(jsonResponse([TASK]));

    const tasks = await listTasksDueForReminder();

    expect(tasks).toHaveLength(1);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/tasks/reminders/due");
  });

  it("createTask POSTs the payload including recurrence", async () => {
    fetchMock.mockResolvedValue(jsonResponse(TASK));

    await createTask({ title: "Follow up", priority: "high", recurrence_frequency: "weekly" });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    const body = (init.body as string) ?? "";
    expect(body).toContain('"title":"Follow up"');
    expect(body).toContain('"recurrence_frequency":"weekly"');
  });

  it("updateTask PATCHes status", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...TASK, status: "in_progress" }));

    await updateTask(TASK.id, { status: "in_progress" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/tasks/${TASK.id}`);
    expect(init.method).toBe("PATCH");
    expect((init.body as string) ?? "").toContain('"status":"in_progress"');
  });

  it("completeTask POSTs the completion endpoint", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...TASK, status: "completed" }));

    const result = await completeTask(TASK.id);

    expect(result.status).toBe("completed");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/tasks/${TASK.id}/complete`);
    expect(init.method).toBe("POST");
  });

  it("deleteTask issues a DELETE", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await deleteTask(TASK.id);

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("DELETE");
  });
});
