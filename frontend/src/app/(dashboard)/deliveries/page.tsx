// Deliveries: outbox monitoring and manual lifecycle control.
"use client";

import { useCallback, useEffect, useState } from "react";

import {
  Badge,
  Button,
  ConfirmDialog,
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
import {
  DELIVERY_CHANNEL_LABELS,
  DELIVERY_STATUS_LABELS,
  deliveryStatusTone,
  formatDateTime,
} from "@/lib/format";
import { can } from "@/lib/permissions";
import {
  cancelDelivery,
  listDeliveries,
  listDeliveryEvents,
  retryDelivery,
} from "@/services/deliveries";
import type { Delivery, DeliveryChannel, DeliveryEvent, DeliveryStatus } from "@/types";

const STATUS_OPTIONS: Array<{ value: DeliveryStatus; label: string }> = Object.entries(
  DELIVERY_STATUS_LABELS
).map(([value, label]) => ({ value: value as DeliveryStatus, label }));

const CHANNEL_OPTIONS: Array<{ value: DeliveryChannel; label: string }> = Object.entries(
  DELIVERY_CHANNEL_LABELS
).map(([value, label]) => ({ value: value as DeliveryChannel, label }));

const EVENT_TYPE_LABELS: Record<DeliveryEvent["event_type"], string> = {
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

export function deliveryErrorMessage(err: unknown): string {
  return err instanceof ApiRequestError ? err.message : "Failed to load deliveries";
}

export default function DeliveriesPage() {
  const session = useAuth();
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [channelFilter, setChannelFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [cancelTarget, setCancelTarget] = useState<Delivery | null>(null);
  const [timeline, setTimeline] = useState<{
    delivery: Delivery;
    events: DeliveryEvent[];
    loading: boolean;
  } | null>(null);

  const load = useCallback((status: string, channel: string) => {
    listDeliveries({
      status: (status || undefined) as DeliveryStatus | undefined,
      channel: (channel || undefined) as DeliveryChannel | undefined,
      limit: 200,
    })
      .then((page) => {
        setDeliveries(page.items);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(deliveryErrorMessage(err));
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load(statusFilter, channelFilter);
  }, [load, statusFilter, channelFilter]);

  if (!session) return null;
  const canManage = can(session.user.role, "delivery_manage");

  const runAction = (id: string, fn: (id: string) => Promise<Delivery>) => {
    setBusyId(id);
    fn(id)
      .then(() => load(statusFilter, channelFilter))
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Action failed");
      })
      .finally(() => setBusyId(null));
  };

  const openTimeline = (delivery: Delivery) => {
    setTimeline({ delivery, events: [], loading: true });
    listDeliveryEvents(delivery.id, { limit: 100 })
      .then((page) => {
        setTimeline((current) =>
          current ? { ...current, events: page.items, loading: false } : current
        );
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Failed to load timeline");
        setTimeline(null);
      });
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Deliveries"
        description="Outbox of every message sent to users, with an append-only timeline."
        actions={
          <div className="flex gap-2">
            <Select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-40"
            >
              <option value="">All statuses</option>
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
            <Select
              value={channelFilter}
              onChange={(e) => setChannelFilter(e.target.value)}
              className="w-40"
            >
              <option value="">All channels</option>
              {CHANNEL_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </div>
        }
      />

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {loading ? (
        <Spinner label="Loading deliveries…" />
      ) : deliveries.length === 0 ? (
        <EmptyState
          title="No deliveries"
          description="Messages queued by workflows will appear here as an outbox."
        />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Status</TH>
              <TH>Channel</TH>
              <TH>Subject</TH>
              <TH>Attempts</TH>
              <TH>Created</TH>
              <TH />
            </tr>
          </THead>
          <TBody>
            {deliveries.map((delivery) => (
              <TRow key={delivery.id}>
                <TD>
                  <Badge tone={deliveryStatusTone(delivery.status)}>
                    {DELIVERY_STATUS_LABELS[delivery.status]}
                  </Badge>
                </TD>
                <TD className="text-gray-600">{DELIVERY_CHANNEL_LABELS[delivery.channel]}</TD>
                <TD className="max-w-xs truncate font-medium">
                  {delivery.subject}
                  {delivery.last_error ? (
                    <span className="block truncate text-xs font-normal text-red-600">
                      {delivery.last_error}
                    </span>
                  ) : null}
                </TD>
                <TD className="text-gray-600">
                  {delivery.attempts}/{delivery.max_attempts}
                </TD>
                <TD className="text-xs text-gray-400">{formatDateTime(delivery.created_at)}</TD>
                <TD className="text-right">
                  <div className="flex items-center justify-end gap-2">
                    <Button variant="ghost" onClick={() => openTimeline(delivery)}>
                      Timeline
                    </Button>
                    {canManage ? (
                      <>
                        {(delivery.status === "failed" || delivery.status === "cancelled") && (
                          <Button
                            variant="outline"
                            disabled={busyId === delivery.id}
                            onClick={() => runAction(delivery.id, retryDelivery)}
                          >
                            Retry
                          </Button>
                        )}
                        {(delivery.status === "queued" ||
                          delivery.status === "processing" ||
                          delivery.status === "retrying") && (
                          <Button
                            variant="ghost"
                            disabled={busyId === delivery.id}
                            onClick={() => setCancelTarget(delivery)}
                          >
                            Cancel
                          </Button>
                        )}
                      </>
                    ) : null}
                  </div>
                </TD>
              </TRow>
            ))}
          </TBody>
        </Table>
      )}

      <Modal
        open={timeline !== null}
        title={timeline ? timeline.delivery.subject : undefined}
        onClose={() => setTimeline(null)}
        width="lg"
      >
        {timeline?.loading ? (
          <Spinner label="Loading timeline…" />
        ) : timeline?.events.length === 0 ? (
          <EmptyState title="No events" description="No timeline events recorded yet." />
        ) : (
          <ol className="flex flex-col gap-3">
            {timeline?.events.map((event) => (
              <li key={event.id} className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-medium">
                    {EVENT_TYPE_LABELS[event.event_type] ?? event.event_type}
                  </p>
                  <p className="text-xs text-gray-400">
                    Attempt {event.attempt} · {formatDateTime(event.occurred_at)}
                  </p>
                </div>
                {event.metadata && Object.keys(event.metadata).length > 0 ? (
                  <code className="max-w-[40%] truncate text-xs text-gray-500">
                    {JSON.stringify(event.metadata)}
                  </code>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </Modal>

      <ConfirmDialog
        open={cancelTarget !== null}
        title="Cancel delivery"
        message={`Cancel "${cancelTarget?.subject}"? This stops the delivery from being sent.`}
        confirmLabel="Cancel delivery"
        busy={busyId === cancelTarget?.id}
        onConfirm={() => {
          if (cancelTarget) {
            runAction(cancelTarget.id, cancelDelivery);
            setCancelTarget(null);
          }
        }}
        onClose={() => setCancelTarget(null)}
      />
    </div>
  );
}
