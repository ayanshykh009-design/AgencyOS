// Founder Intelligence & Growth Triage (M9) API client.
//
// Provides TypeScript wrappers around the intelligence endpoints:
//   GET  /intelligence/signals
//   GET  /intelligence/signals/{id}
//   PATCH /intelligence/signals/{id}
//   GET  /intelligence/summary
//   POST /intelligence/triage/run
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api-client";
import type {
  IntelligenceSignal,
  IntelligenceSignalListResponse,
  IntelligenceSignalStatus,
  IntelligenceSignalSummary,
  IntelligenceSignalUpdate,
  IntelligenceTriageRunResult,
} from "@/types/intelligence";

const API_BASE = "/intelligence";

export interface IntelligenceSignalQuery {
  status?: IntelligenceSignalStatus;
  category?: string;
  sourceType?: string;
  limit?: number;
  offset?: number;
}

export async function listSignals(
  query: IntelligenceSignalQuery = {}
): Promise<IntelligenceSignalListResponse> {
  const params = new URLSearchParams();
  if (query.status) params.set("status", query.status);
  if (query.category) params.set("category", query.category);
  if (query.sourceType) params.set("sourceType", query.sourceType);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();
  return apiFetch<IntelligenceSignalListResponse>(`${API_BASE}/signals${qs ? `?${qs}` : ""}`);
}

export async function getSignal(signalId: string): Promise<IntelligenceSignal> {
  return apiFetch<IntelligenceSignal>(`${API_BASE}/signals/${signalId}`);
}

export async function updateSignal(
  signalId: string,
  body: IntelligenceSignalUpdate
): Promise<IntelligenceSignal> {
  return apiFetch<IntelligenceSignal>(`${API_BASE}/signals/${signalId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function getSummary(): Promise<IntelligenceSignalSummary> {
  return apiFetch<IntelligenceSignalSummary>(`${API_BASE}/summary`);
}

export async function runTriage(): Promise<IntelligenceTriageRunResult> {
  return apiFetch<IntelligenceTriageRunResult>(`${API_BASE}/triage/run`, {
    method: "POST",
  });
}

export const intelligenceKeys = {
  all: ["intelligence"] as const,
  signals: (query?: IntelligenceSignalQuery) =>
    [...intelligenceKeys.all, "signals", query] as const,
  summary: () => [...intelligenceKeys.all, "summary"] as const,
};

export function useSignals(query: IntelligenceSignalQuery = {}) {
  return useQuery({
    queryKey: intelligenceKeys.signals(query),
    queryFn: () => listSignals(query),
    refetchInterval: 60000,
    staleTime: 30000,
  });
}

export function useSignalSummary() {
  return useQuery({
    queryKey: intelligenceKeys.summary(),
    queryFn: getSummary,
    refetchInterval: 60000,
    staleTime: 30000,
  });
}

export function useAcknowledgeSignal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: IntelligenceSignalStatus }) =>
      updateSignal(id, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: intelligenceKeys.all });
    },
  });
}

export function useRunTriage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: runTriage,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: intelligenceKeys.all });
    },
  });
}
