// Audit service: admin-only, enriched activity-trail reads.
import { apiFetch } from "@/lib/api-client";
import type { AuditLogEntry } from "@/types";

export interface AuditQuery {
  entityType?: string;
  entityId?: string;
  leadId?: string;
  userId?: string;
  eventType?: string;
  occurredAfter?: string;
  occurredBefore?: string;
  limit?: number;
  offset?: number;
}

export async function listAuditLogs(query: AuditQuery = {}): Promise<AuditLogEntry[]> {
  const params = new URLSearchParams();
  if (query.entityType) params.set("entity_type", query.entityType);
  if (query.entityId) params.set("entity_id", query.entityId);
  if (query.leadId) params.set("lead_id", query.leadId);
  if (query.userId) params.set("user_id", query.userId);
  if (query.eventType) params.set("event_type", query.eventType);
  if (query.occurredAfter) params.set("occurred_after", query.occurredAfter);
  if (query.occurredBefore) params.set("occurred_before", query.occurredBefore);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));

  const qs = params.toString();
  return apiFetch<AuditLogEntry[]>(`/audit${qs ? `?${qs}` : ""}`);
}

export async function getEntityAudit(
  entityType: string,
  entityId: string,
  eventType?: string,
  limit = 50,
  offset = 0
): Promise<AuditLogEntry[]> {
  const params = new URLSearchParams();
  if (eventType) params.set("event_type", eventType);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return apiFetch<AuditLogEntry[]>(
    `/audit/entity/${encodeURIComponent(entityType)}/${entityId}?${params.toString()}`
  );
}
