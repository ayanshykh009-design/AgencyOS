// Pipeline service: stages, close reasons, Kanban board, stage moves.
import { apiFetch } from "@/lib/api-client";
import type {
  CloseReason,
  CloseReasonCreateInput,
  Lead,
  LeadStageMoveInput,
  PipelineBoardColumn,
  PipelineStage,
  PipelineStageCreateInput,
  PipelineStageUpdateInput,
  StageLifecycle,
} from "@/types";

export async function listStages(): Promise<PipelineStage[]> {
  return apiFetch<PipelineStage[]>("/pipeline/stages");
}

export async function createStage(input: PipelineStageCreateInput): Promise<PipelineStage> {
  return apiFetch<PipelineStage>("/pipeline/stages", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateStage(
  stageId: string,
  patch: PipelineStageUpdateInput
): Promise<PipelineStage> {
  return apiFetch<PipelineStage>(`/pipeline/stages/${stageId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function deleteStage(stageId: string): Promise<void> {
  await apiFetch<void>(`/pipeline/stages/${stageId}`, { method: "DELETE" });
}

export async function reorderStages(stageIds: string[]): Promise<PipelineStage[]> {
  return apiFetch<PipelineStage[]>("/pipeline/stages/reorder", {
    method: "POST",
    body: JSON.stringify({ stage_ids: stageIds }),
  });
}

export async function listCloseReasons(lifecycle?: StageLifecycle): Promise<CloseReason[]> {
  const qs = lifecycle ? `?lifecycle=${lifecycle}` : "";
  return apiFetch<CloseReason[]>(`/pipeline/close-reasons${qs}`);
}

export async function createCloseReason(input: CloseReasonCreateInput): Promise<CloseReason> {
  return apiFetch<CloseReason>("/pipeline/close-reasons", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function deleteCloseReason(closeReasonId: string): Promise<void> {
  await apiFetch<void>(`/pipeline/close-reasons/${closeReasonId}`, {
    method: "DELETE",
  });
}

export async function getBoard(limitPerStage = 50): Promise<PipelineBoardColumn[]> {
  return apiFetch<PipelineBoardColumn[]>(`/pipeline/board?limit_per_stage=${limitPerStage}`);
}

export async function moveLead(leadId: string, input: LeadStageMoveInput): Promise<Lead> {
  return apiFetch<Lead>(`/pipeline/leads/${leadId}/stage`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}
