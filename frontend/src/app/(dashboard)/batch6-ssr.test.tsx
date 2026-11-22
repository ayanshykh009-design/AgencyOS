// Static-markup coverage for all six canonical Batch 6 Automation routes.
// Patterned after `ai/batch5-ssr.test.tsx`: renders the real client page
// components to HTML with mocked auth/services. Verifies fail-closed
// permission state, truthful loading/error states, permission-hidden actions,
// state-dependent disabled actions, and metadata redaction. It does NOT verify
// hydration, event handlers or browser interactivity.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import type { Session } from "@/lib/session";
import type { User, UserRole } from "@/types";

const state = vi.hoisted(() => ({
  session: null as Session | null,
}));

vi.mock("@/hooks/use-auth", () => ({ useAuth: () => state.session }));

vi.mock("@/services/workflows", () => ({
  listWorkflows: vi.fn(async () => ({ items: [], total: 0 })),
  getWorkflow: vi.fn(async () => null),
  createWorkflow: vi.fn(),
  updateWorkflow: vi.fn(),
  activateWorkflow: vi.fn(),
  pauseWorkflow: vi.fn(),
  archiveWorkflow: vi.fn(),
  deleteWorkflow: vi.fn(),
}));

vi.mock("@/services/workflow-triggers", () => ({
  listWorkflowTriggers: vi.fn(async () => ({ items: [], total: 0 })),
  createWorkflowTrigger: vi.fn(),
  updateWorkflowTrigger: vi.fn(),
  enableWorkflowTrigger: vi.fn(),
  disableWorkflowTrigger: vi.fn(),
}));

vi.mock("@/services/workflow-executions", () => ({
  listWorkflowExecutions: vi.fn(async () => ({ items: [], total: 0 })),
  getWorkflowExecution: vi.fn(async () => null),
  listExecutionEvents: vi.fn(async () => ({ items: [], total: 0 })),
  queueWorkflowExecution: vi.fn(),
  startWorkflowExecution: vi.fn(),
  retryWorkflowExecution: vi.fn(),
  cancelWorkflowExecution: vi.fn(),
}));

vi.mock("@/services/credentials", () => ({
  listCredentials: vi.fn(async () => ({ items: [], total: 0 })),
  rotateCredential: vi.fn(),
  deleteCredential: vi.fn(),
}));

vi.mock("@/services/deliveries", () => ({
  listDeliveries: vi.fn(async () => ({ items: [], total: 0 })),
  getDelivery: vi.fn(async () => null),
  listDeliveryEvents: vi.fn(async () => ({ items: [], total: 0 })),
  retryDelivery: vi.fn(),
  cancelDelivery: vi.fn(),
}));

import WorkflowsPage, { WorkflowRowActions } from "@/app/(dashboard)/workflows/page";
import WorkflowDetailPage, { WorkflowDetailActions } from "@/app/(dashboard)/workflows/[id]/page";
import TriggersPage, { TriggerRowActions } from "@/app/(dashboard)/triggers/page";
import ExecutionsPage, {
  ExecutionRowActions,
  formatExecutionDuration,
} from "@/app/(dashboard)/executions/page";
import CredentialsPage, {
  CREDENTIAL_WRITE_UNAVAILABLE,
  CredentialActions,
} from "@/app/(dashboard)/credentials/page";
import DeliveriesPage, {
  DeliveryRowActions,
  MANUAL_DISPATCH_UNAVAILABLE,
} from "@/app/(dashboard)/deliveries/page";
import { RedactedMetadata, REDACTED } from "@/components/automation/automation-states";

const USER: User = {
  id: "11111111-1111-1111-1111-111111111111",
  organization_id: "22222222-2222-2222-2222-222222222222",
  email: "owner@example.com",
  full_name: "Test User",
  role: "owner",
  is_active: true,
  last_login_at: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

function setRole(role: UserRole): void {
  state.session = { accessToken: "token", expiresIn: 3600, user: { ...USER, role } };
}

/**
 * The shared matrix grants workflow/execution/delivery reads to every known
 * role, so a genuinely read-denied principal is an unmapped role. This still
 * exercises the real fail-closed helper rather than mocking it.
 */
function setDeniedRole(): void {
  setRole("__unmapped_role__" as UserRole);
}

/** A thenable React `use()` can consume synchronously during static markup. */
function resolvedParams<T>(value: T): Promise<T> {
  const thenable = {
    status: "fulfilled",
    value,
    then() {
      return undefined;
    },
  };
  return thenable as unknown as Promise<T>;
}

function escapeHtml(value: string): string {
  return value.replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buttonTag(html: string, label: string): string | null {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return html.match(new RegExp(`<button[^>]*>[^<]*${escaped}[^<]*</button>`))?.[0] ?? null;
}

function isDisabled(tag: string | null): boolean {
  return !!tag && /\sdisabled(?:="")?(?:\s|>)/.test(tag);
}

function noop(): void {
  return undefined;
}

describe("/workflows static markup", () => {
  it("denies unmapped roles with no create or lifecycle buttons and uses alert + honest loading", () => {
    setDeniedRole();
    const denied = renderToStaticMarkup(<WorkflowsPage />);
    expect(denied).toContain("You do not have permission to view workflows.");
    expect(denied).toContain('data-state="denied"');
    expect(denied).toContain('role="alert"');
    expect(denied).not.toContain(">New workflow</button>");
    expect(denied).not.toContain(">Activate</button>");

    setRole("owner");
    const loading = renderToStaticMarkup(<WorkflowsPage />);
    expect(loading).toContain("Loading workflows…");
    expect(loading).toContain('role="status"');
  });

  it("hides lifecycle actions from members but keeps Edit; manager sees state-aware transitions", () => {
    const member = renderToStaticMarkup(
      <WorkflowRowActions
        role="member"
        status="active"
        busy={false}
        onEdit={noop}
        onActivate={noop}
        onPause={noop}
        onArchive={noop}
        onDelete={noop}
      />
    );
    expect(buttonTag(member, "Edit")).not.toBeNull();
    expect(member).not.toContain(">Activate</button>");
    expect(member).not.toContain(">Delete</button>");

    const viewer = renderToStaticMarkup(
      <WorkflowRowActions
        role="viewer"
        status="draft"
        busy={false}
        onEdit={noop}
        onActivate={noop}
        onPause={noop}
        onArchive={noop}
        onDelete={noop}
      />
    );
    expect(viewer).toBe("");

    const active = renderToStaticMarkup(
      <WorkflowRowActions
        role="manager"
        status="active"
        busy={false}
        onEdit={noop}
        onActivate={noop}
        onPause={noop}
        onArchive={noop}
        onDelete={noop}
      />
    );
    expect(isDisabled(buttonTag(active, "Activate"))).toBe(true);
    expect(isDisabled(buttonTag(active, "Pause"))).toBe(false);
    expect(isDisabled(buttonTag(active, "Delete"))).toBe(true);

    const draft = renderToStaticMarkup(
      <WorkflowRowActions
        role="manager"
        status="draft"
        busy={false}
        onEdit={noop}
        onActivate={noop}
        onPause={noop}
        onArchive={noop}
        onDelete={noop}
      />
    );
    expect(isDisabled(buttonTag(draft, "Activate"))).toBe(false);
    expect(isDisabled(buttonTag(draft, "Pause"))).toBe(true);
    expect(draft).toContain("Only active workflows can be paused.");
  });
});

describe("/workflows/[id] static markup", () => {
  it("denies unmapped roles and shows no Run now or lifecycle actions", () => {
    setDeniedRole();
    const denied = renderToStaticMarkup(
      <WorkflowDetailPage params={resolvedParams({ id: "workflow-1" })} />
    );
    expect(denied).toContain("You do not have permission to view workflow definitions.");
    expect(denied).not.toContain(">Run now</button>");
    expect(denied).not.toContain(">Delete</button>");
  });

  it("gates Run now to active workflows and lifecycle to managers", () => {
    const member = renderToStaticMarkup(
      <WorkflowDetailActions
        role="member"
        status="active"
        busy={false}
        onEdit={noop}
        onActivate={noop}
        onPause={noop}
        onArchive={noop}
        onDelete={noop}
        onRunNow={noop}
      />
    );
    expect(buttonTag(member, "Run now")).not.toBeNull();
    expect(buttonTag(member, "Edit")).not.toBeNull();
    expect(member).not.toContain(">Activate</button>");

    const draft = renderToStaticMarkup(
      <WorkflowDetailActions
        role="manager"
        status="draft"
        busy={false}
        onEdit={noop}
        onActivate={noop}
        onPause={noop}
        onArchive={noop}
        onDelete={noop}
        onRunNow={noop}
      />
    );
    expect(isDisabled(buttonTag(draft, "Run now"))).toBe(true);
    expect(draft).toContain("Run now is available only for active workflows.");
    expect(isDisabled(buttonTag(draft, "Activate"))).toBe(false);

    const viewer = renderToStaticMarkup(
      <WorkflowDetailActions
        role="viewer"
        status="active"
        busy={false}
        onEdit={noop}
        onActivate={noop}
        onPause={noop}
        onArchive={noop}
        onDelete={noop}
        onRunNow={noop}
      />
    );
    expect(viewer).toBe("");
  });
});

describe("/triggers static markup", () => {
  it("denies unmapped roles and hides trigger mutation buttons", () => {
    setDeniedRole();
    const denied = renderToStaticMarkup(<TriggersPage />);
    expect(denied).toContain("You do not have permission to view workflow triggers.");
    expect(denied).not.toContain(">New trigger</button>");

    const actions = renderToStaticMarkup(
      <TriggerRowActions role="viewer" enabled busy={false} onEdit={noop} onToggle={noop} />
    );
    expect(actions).toBe("");
  });

  it("shows Edit/Disable to writers and no local-time scheduling claim", () => {
    setRole("member");
    const html = renderToStaticMarkup(<TriggersPage />);
    expect(html).toContain("Times are shown in UTC.");
    const actions = renderToStaticMarkup(
      <TriggerRowActions role="member" enabled busy={false} onEdit={noop} onToggle={noop} />
    );
    expect(buttonTag(actions, "Edit")).not.toBeNull();
    expect(buttonTag(actions, "Disable")).not.toBeNull();
    expect(buttonTag(actions, "Enable")).toBeNull();
  });
});

describe("/executions static markup", () => {
  it("denies unmapped roles and hides all write actions", () => {
    setDeniedRole();
    const denied = renderToStaticMarkup(<ExecutionsPage />);
    expect(denied).toContain("You do not have permission to view workflow executions.");
    expect(denied).not.toContain(">Start</button>");
    expect(denied).not.toContain(">Retry</button>");
    expect(denied).not.toContain(">Cancel</button>");

    const actions = renderToStaticMarkup(
      <ExecutionRowActions
        role="viewer"
        status="queued"
        busy={false}
        onStart={noop}
        onRetry={noop}
        onCancel={noop}
        onDetails={noop}
      />
    );
    expect(actions).toContain(">Details</button>");
    expect(actions).not.toContain(">Start</button>");
  });

  it("disables writes by execution state for members (workflow_write)", () => {
    const queued = renderToStaticMarkup(
      <ExecutionRowActions
        role="member"
        status="queued"
        busy={false}
        onStart={noop}
        onRetry={noop}
        onCancel={noop}
        onDetails={noop}
      />
    );
    expect(isDisabled(buttonTag(queued, "Start"))).toBe(false);
    expect(isDisabled(buttonTag(queued, "Retry"))).toBe(true);
    expect(isDisabled(buttonTag(queued, "Cancel"))).toBe(false);

    const succeeded = renderToStaticMarkup(
      <ExecutionRowActions
        role="sales_agent"
        status="succeeded"
        busy={false}
        onStart={noop}
        onRetry={noop}
        onCancel={noop}
        onDetails={noop}
      />
    );
    expect(isDisabled(buttonTag(succeeded, "Start"))).toBe(true);
    expect(isDisabled(buttonTag(succeeded, "Retry"))).toBe(true);
    expect(isDisabled(buttonTag(succeeded, "Cancel"))).toBe(true);
  });

  it("derives UTC-safe execution durations and stays honest when unfinished", () => {
    expect(formatExecutionDuration("2026-08-01T00:00:00Z", "2026-08-01T00:01:05Z")).toBe("1m 5s");
    expect(formatExecutionDuration("2026-08-01T00:00:00Z", null)).toBe("—");
    expect(formatExecutionDuration("invalid", "2026-08-01T00:00:00Z")).toBe("—");
  });
});

describe("/credentials static markup", () => {
  it("denies non-managers and hides every credential action", () => {
    setRole("member");
    const denied = renderToStaticMarkup(<CredentialsPage />);
    expect(denied).toContain("You do not have permission to view credentials.");
    expect(denied).not.toContain(">New credential</button>");
    expect(denied).not.toContain(">Rotate</button>");

    const actions = renderToStaticMarkup(
      <CredentialActions role="member" busy={false} onRotate={noop} onDelete={noop} />
    );
    expect(actions).toBe("");
  });

  it("shows admin actions but keeps plaintext-style entry disabled with a truthful notice", () => {
    setRole("admin");
    const html = renderToStaticMarkup(<CredentialsPage />);
    expect(html).toContain(CREDENTIAL_WRITE_UNAVAILABLE);
    expect(html).not.toContain("Encrypted value");
    expect(isDisabled(buttonTag(html, "New credential"))).toBe(true);

    const actions = renderToStaticMarkup(
      <CredentialActions role="admin" busy={false} onRotate={noop} onDelete={noop} />
    );
    expect(isDisabled(buttonTag(actions, "Replace value"))).toBe(true);
    expect(buttonTag(actions, "Rotate")).not.toBeNull();
    expect(buttonTag(actions, "Delete")).not.toBeNull();
  });
});

describe("/deliveries static markup", () => {
  it("denies unmapped roles and hides retry/cancel/dispatch buttons", () => {
    setDeniedRole();
    const denied = renderToStaticMarkup(<DeliveriesPage />);
    expect(denied).toContain("You do not have permission to view deliveries.");
    expect(denied).not.toContain(">Retry</button>");
    expect(denied).not.toContain(">Cancel</button>");
    expect(denied).not.toContain(">Send manually</button>");
    expect(denied).not.toContain("Destination");

    const actions = renderToStaticMarkup(
      <DeliveryRowActions
        role="viewer"
        status="failed"
        busy={false}
        onRetry={noop}
        onCancel={noop}
        onDetails={noop}
      />
    );
    expect(actions).toContain(">Details</button>");
    expect(actions).not.toContain(">Retry</button>");
  });

  it("gates retry/cancel to delivery_manage and state, keeps dispatch unavailable", () => {
    const failed = renderToStaticMarkup(
      <DeliveryRowActions
        role="admin"
        status="failed"
        busy={false}
        onRetry={noop}
        onCancel={noop}
        onDetails={noop}
      />
    );
    expect(isDisabled(buttonTag(failed, "Retry"))).toBe(false);
    expect(isDisabled(buttonTag(failed, "Cancel"))).toBe(true);
    expect(isDisabled(buttonTag(failed, "Send manually"))).toBe(true);
    expect(failed).toContain(MANUAL_DISPATCH_UNAVAILABLE);

    const member = renderToStaticMarkup(
      <DeliveryRowActions
        role="member"
        status="queued"
        busy={false}
        onRetry={noop}
        onCancel={noop}
        onDetails={noop}
      />
    );
    expect(member).not.toContain(">Retry</button>");
    expect(member).not.toContain(">Cancel</button>");
    expect(member).not.toContain(">Send manually</button>");
  });

  it("redacts sensitive metadata fields and keeps only allowlisted values", () => {
    const html = renderToStaticMarkup(
      <RedactedMetadata
        metadata={{
          status: "ok",
          code: 200,
          token: "sk-super-secret",
          host: "internal.example.com",
          authorization: "Bearer secret",
          provider_response: { nested: "secret" },
        }}
      />
    );
    expect(html).toContain("status:");
    expect(html).toContain("ok");
    expect(html).toContain("code:");
    expect(html).toContain("200");
    expect(html).toContain(escapeHtml(REDACTED));
    expect(html).not.toContain("sk-super-secret");
    expect(html).not.toContain("internal.example.com");
    expect(html).not.toContain("Bearer secret");
    expect(html).not.toContain("nested");
  });
});
