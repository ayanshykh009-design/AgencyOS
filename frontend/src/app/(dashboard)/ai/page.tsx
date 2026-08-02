// AI assistant: run the brain for a goal on a lead, review the draft, dispatch via n8n.
"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { dispatchDraft, getAISettings, listAITools, runBrain } from "@/services/ai";
import { listLeads } from "@/services/leads";
import type {
  BrainRunResponse,
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

  const [result, setResult] = useState<BrainRunResponse | null>(null);
  const [dispatchMsg, setDispatchMsg] = useState<string | null>(null);

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

  const usesChannel = goal === "draft_email" || goal === "draft_linkedin";

  async function onRun() {
    if (!leadId) {
      setError("Select a lead first");
      return;
    }
    setBusy(true);
    setResult(null);
    setDispatchMsg(null);
    setError(null);
    try {
      const outcome = await runBrain({
        goal,
        leadId,
        ...(usesChannel ? { channel } : {}),
      });
      setResult(outcome);
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to run AI");
    } finally {
      setBusy(false);
    }
  }

  async function onDispatch() {
    if (!result?.response) return;
    setBusy(true);
    setDispatchMsg(null);
    try {
      await dispatchDraft("outreach-dispatch", {
        lead_id: leadId,
        channel: usesChannel ? channel : "email",
        body: result.response,
      });
      setDispatchMsg("Dispatched to n8n for sending.");
    } catch (err: unknown) {
      setDispatchMsg(err instanceof ApiRequestError ? err.message : "Dispatch failed");
    } finally {
      setBusy(false);
    }
  }

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
            <Button onClick={onRun} disabled={busy}>
              {busy ? "Running…" : "Run AI"}
            </Button>
          </div>
        </div>
      </section>

      {error ? <p className="text-red-600">{error}</p> : null}

      {result ? (
        <section>
          <h2 className="text-lg font-semibold">Result</h2>
          <div className="mt-3 flex flex-col gap-4">
            <div className="rounded-lg border bg-white p-4 shadow-sm">
              <p className="text-xs text-gray-400">
                {result.success ? "Succeeded" : "Failed"} · {result.steps_taken} steps
              </p>
              {result.error ? <p className="mt-2 text-red-600">{result.error}</p> : null}
              {result.response ? (
                <pre className="mt-3 whitespace-pre-wrap text-sm">{result.response}</pre>
              ) : null}
            </div>

            {result.tool_calls.length > 0 ? (
              <div className="rounded-lg border bg-white p-4 shadow-sm">
                <p className="text-sm font-medium">Tool calls</p>
                <ul className="mt-2 flex flex-col gap-1 text-xs text-gray-600">
                  {result.tool_calls.map((call, i) => (
                    <li key={i}>
                      {call.name} {JSON.stringify(call.arguments)}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {result.response && goal !== "research_lead" ? (
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
