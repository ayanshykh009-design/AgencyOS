// AI assistant: queue an AI run for a goal on a lead, poll to completion,
// review the draft, and optionally dispatch via n8n. (M11-C async contract.)
"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import {
  cancelAgentRun,
  dispatchDraft,
  getAISettings,
  getAgentRun,
  listAITools,
  runBrain,
} from "@/services/ai";
import { listLeads } from "@/services/leads";
import type {
  AgentRunRead,
  AgentRunStatus,
  Lead,
  OrganizationAISettings,
  OutreachChannel,
  ToolManifestEntry,
} from "@/types";

const GOALS: Array<{ value: string; label: string }> = [
  { value: "research_lead", label: "Research lead" },
  { value: "draft_email", label: "Draft cold email" },
  { value: "draft_linkedin", label: "Draft LinkedIn message" },
  { value: "dispatch_outreach", label: "Draft + dispatch via n8n" },
];

const CHANNELS: Array<{ value: OutreachChannel; label: string }> = [
  { value: "email", label: "Email" },
  { value: "linkedin", label: "LinkedIn" },
];

const TERMINAL: ReadonlySet<AgentRunStatus> = new Set(["succeeded", "failed", "cancelled"]);

const POLL_MS = 1500;

function responseFromRun(run: AgentRunRead | null): string | null {
  const out = run?.output;
  if (out && typeof out === "object" && typeof out.response === "string") {
    return out.response;
  }
  return null;
}

export default function AIPage() {
  const session = useAuth();
  const [leads, setLeads] = useState<Lead[]>([]);
  const [tools, setTools] = useState<ToolManifestEntry[]>([]);
  const [settings, setSettings] = useState<OrganizationAISettings | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [leadId, setLeadId] = useState("");
  const [goal, setGoal] = useState("research_lead");
  const [channel, setChannel] = useState<OutreachChannel>("email");
  const [busy, setBusy] = useState(false);

  const [run, setRun] = useState<AgentRunRead | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [cancelMsg, setCancelMsg] = useState<string | null>(null);
  const [dispatchMsg, setDispatchMsg] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    Promise.all([listLeads({ limit: 50 }), listAITools(), getAISettings()])
      .then(([leadPage, toolList, aiSettings]) => {
        if (cancelled) return;
        setLeads(leadPage.items);
        setTools(toolList);
        setSettings(aiSettings);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiRequestError ? err.message : "Failed to load AI workspace");
      });
    return () => {
      cancelled = true;
    };
  }, [session]);

  // Poll the run to completion once a run id exists.
  useEffect(() => {
    if (!runId) return;
    const id = runId;
    let active = true;

    async function tick() {
      try {
        const current = await getAgentRun(id);
        if (!active) return;
        setRun(current);
        if (TERMINAL.has(current.status)) {
          stopPolling();
        }
      } catch (err: unknown) {
        if (!active) return;
        setError(err instanceof ApiRequestError ? err.message : "Failed to fetch run status");
        stopPolling();
      }
    }

    tick();
    pollRef.current = setInterval(tick, POLL_MS);
    return () => {
      active = false;
      stopPolling();
    };

    function stopPolling() {
      if (pollRef.current !== null) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }
  }, [runId]);

  const usesChannel = goal === "draft_email" || goal === "draft_linkedin";

  async function onRun() {
    if (!leadId) {
      setError("Select a lead first");
      return;
    }
    setBusy(true);
    setRun(null);
    setRunId(null);
    setCancelMsg(null);
    setDispatchMsg(null);
    setError(null);
    try {
      const created = await runBrain({
        goal,
        leadId,
        ...(usesChannel ? { channel } : {}),
      });
      setRun(created);
      setRunId(created.id);
    } catch (err: unknown) {
      const msg = err instanceof ApiRequestError ? err.message : "Failed to run AI";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function onCancel() {
    if (!runId) return;
    setBusy(true);
    try {
      const updated = await cancelAgentRun(runId);
      setRun(updated);
      setCancelMsg("Run cancelled.");
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to cancel run");
    } finally {
      setBusy(false);
    }
  }

  async function onDispatch() {
    const response = responseFromRun(run);
    if (!response) return;
    setBusy(true);
    setDispatchMsg(null);
    try {
      await dispatchDraft("outreach-dispatch", {
        lead_id: leadId,
        channel: usesChannel ? channel : "email",
        body: response,
      });
      setDispatchMsg("Dispatched to n8n for sending.");
    } catch (err: unknown) {
      setDispatchMsg(err instanceof ApiRequestError ? err.message : "Dispatch failed");
    } finally {
      setBusy(false);
    }
  }

  const response = responseFromRun(run);
  const status = run?.status;

  return (
    <div className="flex flex-col gap-8">
      <section>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">AI assistant</h2>
          {settings ? (
            <span className="text-xs text-gray-500">
              {settings.provider} · {settings.model}
              {settings.overridden ? " (org override)" : " (default)"}
            </span>
          ) : null}
        </div>

        <div className="mt-4 flex flex-col gap-4">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-gray-600">Lead</span>
            <select
              className="rounded-md border px-3 py-2"
              value={leadId}
              onChange={(e) => setLeadId(e.target.value)}
            >
              <option value="">Select a lead…</option>
              {leads.map((lead) => (
                <option key={lead.id} value={lead.id}>
                  {[lead.first_name, lead.last_name].filter(Boolean).join(" ") ||
                    lead.email ||
                    lead.id}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-sm">
            <span className="text-gray-600">Goal</span>
            <select
              className="rounded-md border px-3 py-2"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
            >
              {GOALS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          {usesChannel ? (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-gray-600">Channel</span>
              {CHANNELS.map((option) => (
                <label key={option.value} className="flex items-center gap-1">
                  <input
                    type="radio"
                    name="channel"
                    value={option.value}
                    checked={channel === option.value}
                    onChange={() => setChannel(option.value)}
                  />
                  {option.label}
                </label>
              ))}
            </div>
          ) : null}

          <div className="flex items-center gap-3">
            <Button onClick={onRun} disabled={busy || (status != null && !TERMINAL.has(status))}>
              {busy ? "Running…" : runId ? "Re-run AI" : "Run AI"}
            </Button>
            {runId && status != null && !TERMINAL.has(status) ? (
              <Button onClick={onCancel} disabled={busy} variant="ghost">
                Cancel
              </Button>
            ) : null}
          </div>
        </div>
      </section>

      {error ? <p className="text-red-600">{error}</p> : null}
      {cancelMsg ? <p className="text-sm text-gray-600">{cancelMsg}</p> : null}

      {run ? (
        <section>
          <h2 className="text-lg font-semibold">Run status</h2>
          <div className="mt-3 flex flex-col gap-4">
            <div className="rounded-lg border bg-white p-4 shadow-sm">
              <p className="text-xs text-gray-400">
                {run.status}
                {run.trace_id ? ` · trace ${run.trace_id}` : ""}
              </p>
              {run.error ? <p className="mt-2 text-red-600">{run.error}</p> : null}
              {response ? <pre className="mt-3 whitespace-pre-wrap text-sm">{response}</pre> : null}
            </div>

            {run.output && Array.isArray((run.output as { tool_trace?: unknown }).tool_trace) ? (
              <div className="rounded-lg border bg-white p-4 shadow-sm">
                <p className="text-sm font-medium">Tool audit</p>
                <ul className="mt-2 flex flex-col gap-1 text-xs text-gray-600">
                  {(
                    (run.output as { tool_trace?: Array<Record<string, unknown>> }).tool_trace ?? []
                  ).map((entry, i) => (
                    <li key={i}>
                      {String(entry.tool)} — {entry.authorized ? "authorized" : "denied"} ·{" "}
                      {entry.ok ? "ok" : "failed"}
                      {entry.error ? ` (${String(entry.error)})` : ""}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {response && goal !== "research_lead" ? (
              <div className="flex items-center gap-3">
                <Button onClick={onDispatch} disabled={busy} variant="ghost">
                  Dispatch to n8n
                </Button>
                {dispatchMsg ? <span className="text-sm text-gray-600">{dispatchMsg}</span> : null}
              </div>
            ) : null}
          </div>
        </section>
      ) : null}

      {tools.length > 0 ? (
        <section>
          <h2 className="text-lg font-semibold">Available tools</h2>
          <ul className="mt-3 flex flex-col gap-2">
            {tools.map((tool) => (
              <li key={tool.name} className="rounded-md border bg-white px-4 py-2 text-sm">
                <span className="font-medium">{tool.name}</span>
                <span className="ml-2 text-gray-600">{tool.description}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
