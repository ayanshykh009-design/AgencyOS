// Deliveries: outbox monitoring with summary, attempt/last-attempt fields,
// redacted metadata timeline and state-dependent, authorized actions.
//
// No destination/provider column is rendered: no channel provider is
// registered in Batch 6, so manual dispatch stays explicitly unavailable.
// Raw payload/provider metadata is never rendered; only an allowlist is shown.
"use client";

import { useCallback, useEffect, useState } from "react";

import {
  AutomationListState,
  DisabledActionReason,
  RedactedMetadata,
  actionDisabledReason,
  formatUtcOrNever,
} from "@/components/automation/automation-states";
import {
  Badge,
  Button,
  Card,
  CardBody,
  EmptyState,
  Modal,
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
import { DELIVERY_CHANNEL_LABELS, DELIVERY_STATUS_LABELS, deliveryStatusTone } from "@/lib/format";
import {
  canCancelDelivery,
  canDispatchDelivery,
  canReadDeliveries,
  canRetryDelivery,
} from "@/lib/batch6-permissions";
import {
  cancelDelivery,
  getDelivery,
  listDeliveryEvents,
  listDeliveries,
  retryDelivery,
} from "@/services/deliveries";
import type { Delivery, DeliveryChannel, DeliveryEvent, DeliveryStatus, UserRole } from "@/types";

const DELIVERY_EVENT_LABELS: Record<DeliveryEvent["event_type"], string> = {
  queued: "Queued",
  claimed: "Claimed",
  provider_dispatched: "Provider dispatched",
  provider_returned: "Provider returned",
  delivered: "Delivered",
  retrying: "Retrying",
  failed: "Failed",
  cancelled: "Cancelled",
  timed_out: "Timed out",
  recovery_guard: "Recovery guard",
  superseded: "Superseded",
};

export const MANUAL_DISPATCH_UNAVAILABLE =
  "Manual dispatch is unavailable: no email, WhatsApp or push provider is registered. Retry uses the existing outbox worker instead.";

/** Normalize API/network failures into a user-facing error message. */
export function deliveryErrorMessage(err: unknown): string {
  return err instanceof ApiRequestError ? err.message : "Failed to load deliveries";
}

/** Exported for static-markup tests: denied roles see no action buttons. */
export function DeliveryRowActions({
  role,
  status,
  busy,
  onRetry,
  onCancel,
  onDetails,
}: {
  role: UserRole;
  status: DeliveryStatus;
  busy: boolean;
  onRetry: () => void;
  onCancel: () => void;
  onDetails: () => void;
}) {
  const mayRetry = canRetryDelivery(role);
  const mayCancel = canCancelDelivery(role);
  const mayDispatch = canDispatchDelivery(role);

  const retryReason = actionDisabledReason(
    status === "failed" || status === "cancelled",
    "Retry is available only for failed or cancelled deliveries."
  );
  const cancelReason = actionDisabledReason(
    status === "queued" || status === "processing",
    "Cancel is available only for queued or processing deliveries."
  );

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <Button variant="ghost" onClick={onDetails}>
        Details
      </Button>
      {mayRetry ? (
        <Button
          variant="outline"
          disabled={busy || retryReason !== null}
          title={retryReason ?? undefined}
          onClick={onRetry}
        >
          Retry
        </Button>
      ) : null}
      {mayCancel ? (
        <Button
          variant="ghost"
          disabled={busy || cancelReason !== null}
          title={cancelReason ?? undefined}
          onClick={onCancel}
        >
          Cancel
        </Button>
      ) : null}
      {mayDispatch ? (
        <Button variant="outline" disabled title={MANUAL_DISPATCH_UNAVAILABLE}>
          Send manually
        </Button>
      ) : null}
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: number }) {
  return (
    <Card className="min-w-[8rem] flex-1">
      <CardBody>
        <p className="text-xs uppercase tracking-wide text-gray-500">{label}</p>
        <p className="mt-1 text-xl font-semibold text-gray-900">{value}</p>
      </CardBody>
    </Card>
  );
}

export default function DeliveriesPage() {
  const session = useAuth();
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [channelFilter, setChannelFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [detail, setDetail] = useState<{
    delivery: Delivery | null;
    events: DeliveryEvent[];
    loading: boolean;
    error: string | null;
  } | null>(null);

  const fetchDeliveries = useCallback((status: string, channel: string) => {
    return listDeliveries({
      status: (status || undefined) as DeliveryStatus | undefined,
      channel: (channel || undefined) as DeliveryChannel | undefined,
      limit: 200,
    })
      .then((page) => {
        setDeliveries(page.items);
        setError(null);
      })
      .catch((err: unknown) => {
        setDeliveries([]);
        setError(deliveryErrorMessage(err));
      })
      .finally(() => setLoading(false));
  }, []);

  const reload = useCallback(
    (status: string, channel: string) => {
      setLoading(true);
      return fetchDeliveries(status, channel);
    },
    [fetchDeliveries]
  );

  useEffect(() => {
    if (session) void fetchDeliveries(statusFilter, channelFilter);
  }, [channelFilter, fetchDeliveries, session, statusFilter]);

  if (!session) return null;
  const role = session.user.role;
  const canRead = canReadDeliveries(role);

  const counts = {
    total: deliveries.length,
    queued: deliveries.filter((d) => d.status === "queued").length,
    processing: deliveries.filter((d) => d.status === "processing").length,
    delivered: deliveries.filter((d) => d.status === "delivered").length,
    failed: deliveries.filter((d) => d.status === "failed").length,
  };

  const runAction = (id: string, fn: (id: string) => Promise<Delivery>) => {
    setBusyId(id);
    fn(id)
      .then(() => {
        setError(null);
        return reload(statusFilter, channelFilter);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Action failed");
      })
      .finally(() => setBusyId(null));
  };

  const openDetail = (id: string) => {
    setDetailId(id);
    setDetail({ delivery: null, events: [], loading: true, error: null });
    Promise.all([getDelivery(id), listDeliveryEvents(id, { limit: 100 })])
      .then(([delivery, page]) => {
        setDetail({ delivery, events: page.items, loading: false, error: null });
      })
      .catch((err: unknown) => {
        setDetail({
          delivery: null,
          events: [],
          loading: false,
          error: err instanceof ApiRequestError ? err.message : "Failed to load delivery detail",
        });
      });
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Deliveries"
        description="Outbox delivery status for the organization. Metadata is redacted; no provider destination is shown."
        actions={
          canRead ? (
            <div className="flex items-center gap-2">
              <Select
                value={channelFilter}
                onChange={(e) => setChannelFilter(e.target.value)}
                className="w-36"
                aria-label="Filter by channel"
              >
                <option value="">All channels</option>
                {Object.entries(DELIVERY_CHANNEL_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
              <Select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="w-40"
                aria-label="Filter by status"
              >
                <option value="">All statuses</option>
                {Object.entries(DELIVERY_STATUS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </div>
          ) : undefined
        }
      />

      <AutomationListState
        denied={!canRead}
        deniedMessage="You do not have permission to view deliveries."
        loading={loading}
        loadingLabel="Loading deliveries…"
        error={error}
        onRetry={() => void reload(statusFilter, channelFilter)}
        empty={deliveries.length === 0}
        emptyTitle="No deliveries"
        emptyDescription="Outbox deliveries will appear here as notifications and workflows dispatch them."
      />

      {canRead && !loading && !error && deliveries.length > 0 ? (
        <>
          <div>
            <p className="mb-2 text-xs text-gray-500">Counts across the loaded deliveries</p>
            <div className="flex flex-wrap gap-3">
              <SummaryCard label="Loaded" value={counts.total} />
              <SummaryCard label="Queued" value={counts.queued} />
              <SummaryCard label="Processing" value={counts.processing} />
              <SummaryCard label="Delivered" value={counts.delivered} />
              <SummaryCard label="Failed" value={counts.failed} />
            </div>
          </div>

          <Table>
            <THead>
              <tr>
                <TH>Delivery ID</TH>
                <TH>Channel</TH>
                <TH>Status</TH>
                <TH>Attempts</TH>
                <TH>Last attempt (UTC)</TH>
                <TH>Next attempt (UTC)</TH>
                <TH>Actions</TH>
              </tr>
            </THead>
            <TBody>
              {deliveries.map((delivery) => (
                <TRow key={delivery.id}>
                  <TD className="font-mono text-xs text-gray-600">{delivery.id.slice(0, 8)}</TD>
                  <TD className="text-gray-600">{DELIVERY_CHANNEL_LABELS[delivery.channel]}</TD>
                  <TD>
                    <Badge tone={deliveryStatusTone(delivery.status)}>
                      {DELIVERY_STATUS_LABELS[delivery.status]}
                    </Badge>
                  </TD>
                  <TD className="text-gray-600">
                    {delivery.attempts}/{delivery.max_attempts}
                  </TD>
                  <TD className="text-xs text-gray-600">
                    {formatUtcOrNever(delivery.attempt_started_at)}
                  </TD>
                  <TD className="text-xs text-gray-600">
                    {formatUtcOrNever(delivery.next_attempt_at)}
                  </TD>
                  <TD>
                    <DeliveryRowActions
                      role={role}
                      status={delivery.status}
                      busy={busyId === delivery.id}
                      onRetry={() => runAction(delivery.id, retryDelivery)}
                      onCancel={() => runAction(delivery.id, cancelDelivery)}
                      onDetails={() => openDetail(delivery.id)}
                    />
                  </TD>
                </TRow>
              ))}
            </TBody>
          </Table>
        </>
      ) : null}

      <Modal
        open={detailId !== null}
        title="Delivery detail"
        onClose={() => {
          setDetailId(null);
          setDetail(null);
        }}
        width="lg"
      >
        {detail?.loading ? (
          <Spinner label="Loading delivery detail…" />
        ) : detail?.error ? (
          <div role="alert" className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-red-700">{detail.error}</p>
            <Button variant="outline" onClick={() => detailId && openDetail(detailId)}>
              Retry
            </Button>
          </div>
        ) : detail?.delivery ? (
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-2 text-sm text-gray-600">
              <Badge tone={deliveryStatusTone(detail.delivery.status)}>
                {DELIVERY_STATUS_LABELS[detail.delivery.status]}
              </Badge>
              <span className="font-mono text-xs">{detail.delivery.id}</span>
              <span>{DELIVERY_CHANNEL_LABELS[detail.delivery.channel]}</span>
              <span>
                Attempts: {detail.delivery.attempts}/{detail.delivery.max_attempts}
              </span>
            </div>

            <div className="grid gap-2 text-sm text-gray-600">
              <p>
                <span className="text-gray-600">Scheduled (UTC): </span>
                {formatUtcOrNever(detail.delivery.scheduled_for)}
              </p>
              <p>
                <span className="text-gray-600">Delivered (UTC): </span>
                {formatUtcOrNever(detail.delivery.delivered_at)}
              </p>
              <p>
                <span className="text-gray-600">Last attempt (UTC): </span>
                {formatUtcOrNever(detail.delivery.attempt_started_at)}
              </p>
            </div>

            {detail.delivery.last_error ? (
              <div
                data-testid="delivery-error-summary"
                className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800"
              >
                {detail.delivery.last_error}
              </div>
            ) : null}

            <div>
              <h4 className="text-sm font-semibold">Provider metadata (redacted)</h4>
              <RedactedMetadata metadata={detail.delivery.provider_metadata} />
            </div>
            <div>
              <h4 className="text-sm font-semibold">Payload (redacted)</h4>
              <RedactedMetadata metadata={detail.delivery.payload} />
              <DisabledActionReason reason="Only allowlisted fields are displayed; all other values are redacted." />
            </div>

            <div>
              <h4 className="text-sm font-semibold">Attempt history</h4>
              {detail.events.length === 0 ? (
                <EmptyState title="No events" description="No timeline events recorded yet." />
              ) : (
                <ol className="mt-2 flex flex-col gap-3">
                  {detail.events.map((event) => (
                    <li key={event.id} className="rounded-md border px-3 py-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-sm font-medium">
                          {DELIVERY_EVENT_LABELS[event.event_type] ?? event.event_type}
                        </p>
                        <p className="text-xs text-gray-600">
                          Attempt {event.attempt} · {formatUtcOrNever(event.occurred_at)}
                        </p>
                      </div>
                      <RedactedMetadata metadata={event.metadata} />
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        ) : (
          <EmptyState title="Delivery unavailable" description="No detail was returned." />
        )}
      </Modal>
    </div>
  );
}
