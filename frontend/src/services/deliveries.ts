// Deliveries service: outbox monitoring + manual lifecycle controls.
import { apiFetch } from "@/lib/api-client";
import type {
  Delivery,
  DeliveryChannel,
  DeliveryCreateInput,
  DeliveryEvent,
  DeliveryStatus,
  Page,
} from "@/types";

export interface DeliveryQuery {
  status?: DeliveryStatus;
  channel?: DeliveryChannel;
  recipientUserId?: string;
  limit?: number;
  offset?: number;
}

export async function listDeliveries(query: DeliveryQuery = {}): Promise<Page<Delivery>> {
  const params = new URLSearchParams();
  if (query.status) params.set("status", query.status);
  if (query.channel) params.set("channel", query.channel);
  if (query.recipientUserId) params.set("recipient_user_id", query.recipientUserId);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();
  return apiFetch<Page<Delivery>>(`/deliveries${qs ? `?${qs}` : ""}`);
}

export async function getDelivery(deliveryId: string): Promise<Delivery> {
  return apiFetch<Delivery>(`/deliveries/${deliveryId}`);
}

export async function createDelivery(input: DeliveryCreateInput): Promise<Delivery> {
  return apiFetch<Delivery>("/deliveries", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function listDeliveryEvents(
  deliveryId: string,
  query: { limit?: number; offset?: number } = {}
): Promise<Page<DeliveryEvent>> {
  const params = new URLSearchParams();
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();
  return apiFetch<Page<DeliveryEvent>>(`/deliveries/${deliveryId}/events${qs ? `?${qs}` : ""}`);
}

export async function retryDelivery(deliveryId: string): Promise<Delivery> {
  return apiFetch<Delivery>(`/deliveries/${deliveryId}/retry`, {
    method: "POST",
  });
}

export async function cancelDelivery(deliveryId: string): Promise<Delivery> {
  return apiFetch<Delivery>(`/deliveries/${deliveryId}/cancel`, {
    method: "POST",
  });
}
