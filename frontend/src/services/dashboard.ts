// Dashboard service: aggregate metrics for the overview page.
import { apiFetch } from "@/lib/api-client";
import type { DashboardSummary } from "@/types";

export async function getDashboardSummary(): Promise<DashboardSummary> {
  return apiFetch<DashboardSummary>("/dashboard/summary");
}
