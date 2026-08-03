// Exports service: download org-scoped lead data as CSV or JSON attachments.
import { env } from "@/lib/env";
import { getAccessToken } from "@/lib/session";
import type { LeadStatus } from "@/types";

export interface ExportQuery {
  query?: string;
  status?: LeadStatus;
  sourceId?: string;
  ownerUserId?: string;
  minScore?: number;
  maxScore?: number;
}

export type ExportFormat = "csv" | "json";

/** Build the export URL with the given filters and format. */
export function buildExportUrl(fmt: ExportFormat, query: ExportQuery = {}): string {
  const params = new URLSearchParams();
  params.set("fmt", fmt);
  if (query.query) params.set("query", query.query);
  if (query.status) params.set("status", query.status);
  if (query.sourceId) params.set("source_id", query.sourceId);
  if (query.ownerUserId) params.set("owner_user_id", query.ownerUserId);
  if (query.minScore !== undefined) params.set("min_score", String(query.minScore));
  if (query.maxScore !== undefined) params.set("max_score", String(query.maxScore));
  return `${env.NEXT_PUBLIC_API_URL}/exports/leads?${params.toString()}`;
}

/** Trigger a download of the export in the browser using the stored token. */
export async function downloadExport(fmt: ExportFormat, query: ExportQuery = {}): Promise<void> {
  const token = getAccessToken();
  const res = await fetch(buildExportUrl(fmt, query), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    throw new Error(`Export failed with status ${res.status}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `leads.${fmt}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
