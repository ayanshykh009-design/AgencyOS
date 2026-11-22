// Shared, typed UX states for the six canonical Automation routes.
//
// These are presentational only: they never fetch, never invent data, and
// never imply that a blocked action succeeded. `ErrorState` uses role="alert"
// plus an explicit Retry affordance; permission denials explain the gate
// instead of silently returning null.

import { Button, EmptyState, Spinner } from "@/components/ui";

/** Permission-denied panel. Rendered instead of the page data and all actions. */
export function PermissionDeniedState({
  message = "You do not have permission to view this automation data.",
}: {
  message?: string;
}) {
  return (
    <div
      role="alert"
      data-state="denied"
      className="flex flex-col gap-1 rounded-lg border border-amber-200 bg-amber-50 px-5 py-6"
    >
      <p className="text-sm font-medium text-amber-900">Access restricted</p>
      <p className="text-sm text-amber-800">{message}</p>
    </div>
  );
}

/** Loading panel used while a real service call is in flight. */
export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div data-state="loading" className="px-1 py-4">
      <Spinner label={label} />
    </div>
  );
}

/** Empty panel used only when a successful call returned zero items. */
export function EmptyAutomationState({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return <EmptyState title={title} description={description} />;
}

/** Error panel with a real retry callback. Never shows fake success. */
export function ErrorState({
  message,
  onRetry,
  retryLabel = "Retry",
}: {
  message: string;
  onRetry: () => void;
  retryLabel?: string;
}) {
  return (
    <div
      role="alert"
      data-state="error"
      className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-5 py-4"
    >
      <p className="text-sm text-red-800">{message}</p>
      <Button variant="outline" onClick={onRetry}>
        {retryLabel}
      </Button>
    </div>
  );
}

/**
 * Composes the four read states in a fixed priority order so every route
 * renders them consistently. Returns null when data should be displayed.
 */
export function AutomationListState({
  denied,
  deniedMessage,
  loading,
  loadingLabel,
  error,
  onRetry,
  empty,
  emptyTitle,
  emptyDescription,
}: {
  denied: boolean;
  deniedMessage: string;
  loading: boolean;
  loadingLabel: string;
  error: string | null;
  onRetry: () => void;
  empty: boolean;
  emptyTitle: string;
  emptyDescription?: string;
}) {
  if (denied) return <PermissionDeniedState message={deniedMessage} />;
  if (loading) return <LoadingState label={loadingLabel} />;
  if (error) return <ErrorState message={error} onRetry={onRetry} />;
  if (empty) {
    return <EmptyAutomationState title={emptyTitle} description={emptyDescription} />;
  }
  return null;
}

/**
 * Return the reason an action must stay disabled, or null when it may run.
 * Used to keep disabled buttons explainable instead of silently inert.
 */
export function actionDisabledReason(
  allowed: boolean,
  reason: string | null | undefined
): string | null {
  if (!allowed) return reason ?? "You do not have permission to perform this action.";
  return null;
}

/** Small text explaining why a visible action is disabled. */
export function DisabledActionReason({ reason }: { reason: string | null | undefined }) {
  if (!reason) return null;
  return <p className="text-xs text-gray-500">{reason}</p>;
}

/** Format a stored UTC timestamp with an explicit UTC label (D-04: UTC only). */
export function formatUtcTimestamp(iso: string): string {
  return `${new Date(iso).toISOString()} (UTC)`;
}

/** Null-safe variant for "never fired" style fields. */
export function formatUtcOrNever(iso: string | null | undefined): string {
  return iso ? formatUtcTimestamp(iso) : "Never";
}

// Only non-sensitive, enum-like fields are ever rendered. Every other key is
// shown as <redacted> so payloads, tokens, hosts and provider data cannot leak
// through the UI even when the backend returns a broad metadata object.
const METADATA_ALLOWLIST = new Set([
  "code",
  "type",
  "step",
  "status",
  "attempt",
  "event_type",
  "reason",
]);
export const REDACTED = "<redacted>";

export function redactMetadata(
  input: Record<string, unknown> | null | undefined
): Record<string, string> {
  if (!input) return {};
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(input)) {
    const safe =
      METADATA_ALLOWLIST.has(key) &&
      value !== null &&
      value !== undefined &&
      typeof value !== "object";
    out[key] = safe ? String(value) : REDACTED;
  }
  return out;
}

/** Render allowlisted metadata pairs. Never calls JSON.stringify on raw data. */
export function RedactedMetadata({
  metadata,
}: {
  metadata: Record<string, unknown> | null | undefined;
}) {
  const rows = Object.entries(redactMetadata(metadata));
  if (rows.length === 0) return null;
  return (
    <dl className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-gray-500">
      {rows.map(([key, value]) => (
        <div key={key} className="flex gap-1">
          <dt className="text-gray-600">{key}:</dt>
          <dd className="font-mono">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
