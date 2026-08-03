// Leads service: search/filter/sort/paginate, create, update, soft-delete.
import { apiFetch } from "@/lib/api-client";
import type { Lead, LeadCreateInput, LeadStatus, LeadUpdateInput, Page } from "@/types";

export interface LeadQuery {
  query?: string;
  status?: LeadStatus;
  sourceId?: string;
  ownerUserId?: string;
  minScore?: number;
  maxScore?: number;
  sort?: string;
  order?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export async function listLeads(query: LeadQuery = {}): Promise<Page<Lead>> {
  const params = new URLSearchParams();
  if (query.query) params.set("query", query.query);
  if (query.status) params.set("status", query.status);
  if (query.sourceId) params.set("source_id", query.sourceId);
  if (query.ownerUserId) params.set("owner_user_id", query.ownerUserId);
  if (query.minScore !== undefined) params.set("min_score", String(query.minScore));
  if (query.maxScore !== undefined) params.set("max_score", String(query.maxScore));
  if (query.sort) params.set("sort", query.sort);
  if (query.order) params.set("order", query.order);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));

  const qs = params.toString();
  return apiFetch<Page<Lead>>(`/leads${qs ? `?${qs}` : ""}`);
}

export async function getLead(leadId: string): Promise<Lead> {
  return apiFetch<Lead>(`/leads/${leadId}`);
}

export async function createLead(input: LeadCreateInput): Promise<Lead> {
  return apiFetch<Lead>("/leads", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateLead(leadId: string, patch: LeadUpdateInput): Promise<Lead> {
  return apiFetch<Lead>(`/leads/${leadId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function deleteLead(leadId: string): Promise<void> {
  await apiFetch<void>(`/leads/${leadId}`, { method: "DELETE" });
}

export interface DuplicateQuery {
  email?: string;
  phone?: string;
  website?: string;
}

export async function checkDuplicates(query: DuplicateQuery = {}): Promise<Lead[]> {
  const params = new URLSearchParams();
  if (query.email) params.set("email", query.email);
  if (query.phone) params.set("phone", query.phone);
  if (query.website) params.set("website", query.website);
  const qs = params.toString();
  return apiFetch<Lead[]>(`/leads/duplicates${qs ? `?${qs}` : ""}`);
}
