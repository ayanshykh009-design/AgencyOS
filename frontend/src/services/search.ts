// Search service: unified text search across leads, tasks, and notes.
import { apiFetch } from "@/lib/api-client";
import type { SearchResponse } from "@/types";

export async function globalSearch(query: string, limit = 10): Promise<SearchResponse> {
  const params = new URLSearchParams();
  params.set("q", query);
  if (limit > 0) params.set("limit", String(limit));
  return apiFetch<SearchResponse>(`/search?${params.toString()}`);
}
