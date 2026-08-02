// Leads service: search/filter/sort/paginate leads.
import { apiFetch } from "@/lib/api-client";
import type { Lead, LeadStatus, Page } from "@/types";

export interface LeadQuery {
  query?: string;
  status?: LeadStatus;
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
