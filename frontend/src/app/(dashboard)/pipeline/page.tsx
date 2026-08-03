// Pipeline: Kanban board with drag-and-drop stage moves.
"use client";

import { useCallback, useEffect, useState } from "react";

import {
  Badge,
  Button,
  EmptyState,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  Spinner,
} from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { ROUTES } from "@/lib/constants";
import { formatUsd, leadName } from "@/lib/format";
import { can } from "@/lib/permissions";
import {
  createCloseReason,
  createStage,
  deleteCloseReason,
  deleteStage,
  getBoard,
  listCloseReasons,
  listStages,
  moveLead,
} from "@/services/pipeline";
import type {
  CloseReason,
  Lead,
  PipelineBoardColumn,
  PipelineStage,
  StageLifecycle,
} from "@/types";

const LIFECYCLE_LABELS: Record<StageLifecycle, string> = {
  open: "Open",
  won: "Won",
  lost: "Lost",
};

function lifecycleTone(lifecycle: StageLifecycle): "gray" | "green" | "red" {
  switch (lifecycle) {
    case "won":
      return "green";
    case "lost":
      return "red";
    default:
      return "gray";
  }
}

export default function PipelinePage() {
  const session = useAuth();
  const [columns, setColumns] = useState<PipelineBoardColumn[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [manageOpen, setManageOpen] = useState(false);
  const [closeOpen, setCloseOpen] = useState(false);
  const [dragLead, setDragLead] = useState<Lead | null>(null);
  const [pendingStage, setPendingStage] = useState<PipelineStage | null>(null);
  const [closeReasonId, setCloseReasonId] = useState("");

  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [closeReasons, setCloseReasons] = useState<CloseReason[]>([]);
  const [newStageName, setNewStageName] = useState("");
  const [newStageLifecycle, setNewStageLifecycle] = useState<StageLifecycle>("open");
  const [newReasonName, setNewReasonName] = useState("");
  const [newReasonLifecycle, setNewReasonLifecycle] = useState<StageLifecycle>("won");

  const load = useCallback(() => {
    getBoard()
      .then((board) => setColumns(board))
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Failed to load pipeline");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!session) return null;
  const canManage = can(session.user.role, "pipeline_manage");

  async function openManage() {
    setManageOpen(true);
    setError(null);
    const [stageList, reasonList] = await Promise.all([listStages(), listCloseReasons()]);
    setStages(stageList);
    setCloseReasons(reasonList);
  }

  async function handleDrop(target: PipelineStage, lead: Lead) {
    if (target.lifecycle === "open") {
      await performMove(lead, target.id);
      return;
    }
    setPendingStage(target);
    setDragLead(lead);
    setCloseReasonId("");
    setCloseOpen(true);
  }

  async function performMove(lead: Lead, stageId: string, reasonId?: string) {
    setBusy(true);
    setError(null);
    try {
      await moveLead(lead.id, { stage_id: stageId, close_reason_id: reasonId });
      load();
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to move lead");
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirmCloseMove() {
    if (!dragLead || !pendingStage) return;
    const reason = closeReasons.find((item) => item.id === closeReasonId);
    setCloseOpen(false);
    await performMove(dragLead, pendingStage.id, reason?.id);
  }

  async function handleAddStage() {
    if (newStageName.trim() === "") return;
    setBusy(true);
    setError(null);
    try {
      await createStage({ name: newStageName.trim(), lifecycle: newStageLifecycle });
      setNewStageName("");
      const stageList = await listStages();
      setStages(stageList);
      load();
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to create stage");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteStage(stage: PipelineStage) {
    setBusy(true);
    setError(null);
    try {
      await deleteStage(stage.id);
      setStages((prev) => prev.filter((item) => item.id !== stage.id));
      load();
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to delete stage");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddReason() {
    if (newReasonName.trim() === "") return;
    setBusy(true);
    setError(null);
    try {
      await createCloseReason({ name: newReasonName.trim(), lifecycle: newReasonLifecycle });
      setNewReasonName("");
      setCloseReasons(await listCloseReasons());
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to create close reason");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteReason(reason: CloseReason) {
    setBusy(true);
    setError(null);
    try {
      await deleteCloseReason(reason.id);
      setCloseReasons((prev) => prev.filter((item) => item.id !== reason.id));
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to delete close reason");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <Spinner label="Loading pipeline…" />;
  }
  if (error && columns.length === 0) {
    return <p className="text-red-600">{error}</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Pipeline"
        description="Drag leads between stages. Won/lost moves record a close reason."
        actions={
          canManage ? (
            <>
              <Button variant="outline" onClick={openManage}>
                Manage stages
              </Button>
              <Button onClick={openManage}>Add stage</Button>
            </>
          ) : undefined
        }
      />

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {columns.length === 0 ? (
        <EmptyState
          title="No pipeline stages"
          description="Create a stage to start organizing leads."
          action={canManage ? <Button onClick={openManage}>Add stage</Button> : undefined}
        />
      ) : (
        <div className="flex gap-4 overflow-x-auto pb-4">
          {columns.map((column) => (
            <div
              key={column.stage.id}
              className="flex w-72 shrink-0 flex-col rounded-lg border bg-gray-50"
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => {
                if (dragLead) handleDrop(column.stage, dragLead);
              }}
            >
              <div className="flex items-center justify-between px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold">{column.stage.name}</span>
                  <Badge tone={lifecycleTone(column.stage.lifecycle)}>
                    {LIFECYCLE_LABELS[column.stage.lifecycle]}
                  </Badge>
                </div>
                <span className="text-xs text-gray-400">{column.leads.length}</span>
              </div>
              <div className="flex min-h-24 flex-col gap-2 px-3 pb-3">
                {column.leads.length === 0 ? (
                  <p className="rounded border border-dashed p-3 text-center text-xs text-gray-400">
                    Drop leads here
                  </p>
                ) : (
                  column.leads.map((lead) => (
                    <a
                      key={lead.id}
                      href={ROUTES.leadDetail(lead.id)}
                      draggable
                      onDragStart={(e) => {
                        setDragLead(lead);
                        e.dataTransfer.effectAllowed = "move";
                      }}
                      onDragEnd={() => setDragLead(null)}
                      className="rounded-md border bg-white p-3 text-sm shadow-sm hover:shadow"
                    >
                      <p className="font-medium text-gray-900">{leadName(lead)}</p>
                      {lead.company ? (
                        <p className="text-xs text-gray-500">{lead.company}</p>
                      ) : null}
                      <div className="mt-2 flex items-center justify-between">
                        <Badge tone="gray">Score {lead.score}</Badge>
                        {lead.deal_value != null ? (
                          <span className="text-xs font-medium">{formatUsd(lead.deal_value)}</span>
                        ) : null}
                      </div>
                    </a>
                  ))
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal
        open={manageOpen}
        title="Manage pipeline"
        width="lg"
        onClose={() => setManageOpen(false)}
      >
        <div className="flex flex-col gap-6">
          <section className="flex flex-col gap-2">
            <h4 className="text-sm font-semibold">Stages</h4>
            <ul className="flex flex-col gap-1">
              {stages.map((stage) => (
                <li
                  key={stage.id}
                  className="flex items-center justify-between rounded border px-3 py-2 text-sm"
                >
                  <span className="flex items-center gap-2">
                    {stage.name}
                    <Badge tone={lifecycleTone(stage.lifecycle)}>
                      {LIFECYCLE_LABELS[stage.lifecycle]}
                    </Badge>
                    {stage.is_default ? <Badge tone="blue">Default</Badge> : null}
                  </span>
                  <Button
                    variant="ghost"
                    disabled={busy || stage.is_default}
                    onClick={() => handleDeleteStage(stage)}
                  >
                    Delete
                  </Button>
                </li>
              ))}
            </ul>
            <div className="mt-2 flex flex-wrap items-end gap-2">
              <Field label="New stage name" className="w-48">
                <Input value={newStageName} onChange={(e) => setNewStageName(e.target.value)} />
              </Field>
              <Field label="Lifecycle" className="w-36">
                <Select
                  value={newStageLifecycle}
                  onChange={(e) => setNewStageLifecycle(e.target.value as StageLifecycle)}
                >
                  {(Object.keys(LIFECYCLE_LABELS) as StageLifecycle[]).map((value) => (
                    <option key={value} value={value}>
                      {LIFECYCLE_LABELS[value]}
                    </option>
                  ))}
                </Select>
              </Field>
              <Button onClick={handleAddStage} disabled={busy || newStageName.trim() === ""}>
                Add
              </Button>
            </div>
          </section>

          <section className="flex flex-col gap-2">
            <h4 className="text-sm font-semibold">Close reasons</h4>
            <ul className="flex flex-col gap-1">
              {closeReasons.map((reason) => (
                <li
                  key={reason.id}
                  className="flex items-center justify-between rounded border px-3 py-2 text-sm"
                >
                  <span className="flex items-center gap-2">
                    {reason.name}
                    <Badge tone={lifecycleTone(reason.lifecycle)}>
                      {LIFECYCLE_LABELS[reason.lifecycle]}
                    </Badge>
                    {reason.is_default ? <Badge tone="blue">Default</Badge> : null}
                  </span>
                  <Button
                    variant="ghost"
                    disabled={busy || reason.is_default}
                    onClick={() => handleDeleteReason(reason)}
                  >
                    Delete
                  </Button>
                </li>
              ))}
            </ul>
            <div className="mt-2 flex flex-wrap items-end gap-2">
              <Field label="New close reason" className="w-48">
                <Input value={newReasonName} onChange={(e) => setNewReasonName(e.target.value)} />
              </Field>
              <Field label="Lifecycle" className="w-36">
                <Select
                  value={newReasonLifecycle}
                  onChange={(e) => setNewReasonLifecycle(e.target.value as StageLifecycle)}
                >
                  <option value="won">Won</option>
                  <option value="lost">Lost</option>
                </Select>
              </Field>
              <Button onClick={handleAddReason} disabled={busy || newReasonName.trim() === ""}>
                Add
              </Button>
            </div>
          </section>
        </div>
      </Modal>

      <Modal
        open={closeOpen}
        title={pendingStage ? `Close as ${pendingStage.name.toLowerCase()}` : "Close lead"}
        width="sm"
        onClose={() => setCloseOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setCloseOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={handleConfirmCloseMove} disabled={busy}>
              {busy ? "Moving…" : "Move lead"}
            </Button>
          </>
        }
      >
        <Field label="Close reason" hint="Selecting a close reason records the win/loss detail.">
          <Select value={closeReasonId} onChange={(e) => setCloseReasonId(e.target.value)}>
            <option value="">No close reason</option>
            {closeReasons
              .filter((reason) => reason.lifecycle === pendingStage?.lifecycle)
              .map((reason) => (
                <option key={reason.id} value={reason.id}>
                  {reason.name}
                </option>
              ))}
          </Select>
        </Field>
      </Modal>
    </div>
  );
}
