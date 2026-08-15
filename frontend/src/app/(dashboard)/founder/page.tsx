// Founder AI Assistant chat (M8).
// The assistant is grounded in org context and routes every action through an
// approval-gated proposal. Approve/deny happen inline on returned proposals.
"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { can } from "@/lib/permissions";
import {
  decideFounderProposal,
  deleteFounderConversation,
  getFounderConversation,
  listFounderConversations,
  listFounderProposals,
  sendFounderMessage,
} from "@/services/founder";
import type { FounderConversation, FounderMessage, FounderProposal } from "@/types";

interface ChatEntry {
  message: FounderMessage;
  proposals: FounderProposal[];
  intent?: Record<string, unknown>;
  ok?: boolean;
  error?: string | null;
}

export default function FounderChatPage() {
  const session = useAuth();
  const [conversations, setConversations] = useState<FounderConversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatEntry[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const canManage = !!session && can(session.user.role, "founder_manage");

  async function refreshConversations() {
    const page = await listFounderConversations({ limit: 50 });
    setConversations(page.items);
  }

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    listFounderConversations({ limit: 50 })
      .then((page) => {
        if (!cancelled) setConversations(page.items);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [session]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  async function openConversation(id: string) {
    setActiveId(id);
    setError(null);
    try {
      const { messages: loaded } = await getFounderConversation(id);
      setMessages(loaded.map((message) => ({ message, proposals: [] })));
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to load conversation");
    }
  }

  async function onSend() {
    const text = draft.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    setDraft("");
    try {
      const res = await sendFounderMessage({
        message: text,
        conversation_id: activeId,
      });
      setActiveId(res.conversation_id);
      setMessages((prev) => [
        ...prev,
        {
          message: { id: "u", sender: "user", body: text, metadata: {} },
          proposals: [],
        },
        {
          message: res.message,
          proposals: res.proposals,
          intent: res.intent,
          ok: res.ok,
          error: res.error,
        },
      ]);
      await refreshConversations();
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Assistant failed to respond");
    } finally {
      setBusy(false);
    }
  }

  async function onDecide(proposal: FounderProposal, approve: boolean) {
    try {
      const updated = await decideFounderProposal(proposal.id, {
        approve,
        decision_note: approve ? null : "Denied from assistant",
      });
      setMessages((prev) =>
        prev.map((entry) => ({
          ...entry,
          proposals: entry.proposals.map((p) => (p.id === proposal.id ? updated : p)),
        }))
      );
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Decision failed");
    }
  }

  async function onDelete(id: string) {
    try {
      await deleteFounderConversation(id);
      if (activeId === id) {
        setActiveId(null);
        setMessages([]);
      }
      await refreshConversations();
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Delete failed");
    }
  }

  if (!session) return null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Founder assistant</h1>
        <span className="text-xs text-gray-500">Grounded in your org · actions need approval</span>
      </div>

      <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
        <aside className="flex flex-col gap-2">
          <p className="text-xs uppercase tracking-wide text-gray-400">Conversations</p>
          {conversations.length === 0 ? (
            <p className="text-sm text-gray-500">No conversations yet.</p>
          ) : (
            conversations.map((c) => (
              <button
                key={c.conversation_id}
                type="button"
                onClick={() => openConversation(c.conversation_id)}
                className={`flex items-center justify-between rounded-md border px-3 py-2 text-left text-sm ${
                  activeId === c.conversation_id ? "border-gray-900" : ""
                }`}
              >
                <span className="truncate">{c.title || "Untitled conversation"}</span>
                {canManage ? (
                  <span
                    role="button"
                    tabIndex={0}
                    aria-label="Delete conversation"
                    className="ml-2 text-xs text-gray-400 hover:text-red-600"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(c.conversation_id);
                    }}
                  >
                    ✕
                  </span>
                ) : null}
              </button>
            ))
          )}
        </aside>

        <section className="flex flex-col gap-4">
          <div ref={scrollRef} className="flex max-h-[60vh] flex-col gap-3 overflow-y-auto">
            {messages.length === 0 ? (
              <p className="text-sm text-gray-500">
                Ask about pipeline health, propose a task, or request an export — every action is
                gated by approval.
              </p>
            ) : (
              messages.map((entry, i) => (
                <div key={i} className="flex flex-col gap-2">
                  <div
                    className={`rounded-lg border p-3 text-sm ${
                      entry.message.sender === "user" ? "self-end bg-gray-50" : "bg-white"
                    }`}
                  >
                    {entry.message.body}
                  </div>
                  {entry.proposals.length > 0 ? (
                    <div className="flex flex-col gap-2">
                      {entry.proposals.map((p) => (
                        <ProposalCard key={p.id} proposal={p} onDecide={onDecide} />
                      ))}
                    </div>
                  ) : null}
                </div>
              ))
            )}
          </div>

          {error ? <p className="text-sm text-red-600">{error}</p> : null}

          <div className="flex items-end gap-2">
            <textarea
              className="min-h-[44px] flex-1 rounded-md border px-3 py-2 text-sm"
              placeholder="Message the founder assistant…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  onSend();
                }
              }}
            />
            <Button onClick={onSend} disabled={busy || !draft.trim()}>
              {busy ? "Thinking…" : "Send"}
            </Button>
          </div>
        </section>
      </div>
    </div>
  );
}

function ProposalCard({
  proposal,
  onDecide,
}: {
  proposal: FounderProposal;
  onDecide: (p: FounderProposal, approve: boolean) => void;
}) {
  const terminal = proposal.status !== "proposed";
  return (
    <div className="rounded-lg border bg-white p-3 text-sm shadow-sm">
      <div className="flex items-center justify-between">
        <span className="font-medium">{proposal.title}</span>
        <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
          {proposal.status}
        </span>
      </div>
      {proposal.justification ? (
        <p className="mt-1 text-xs text-gray-500">{proposal.justification}</p>
      ) : null}
      {!terminal ? (
        <div className="mt-2 flex items-center gap-2">
          <Button
            variant="ghost"
            onClick={() => onDecide(proposal, true)}
            className="text-green-700"
          >
            Approve
          </Button>
          <Button
            variant="ghost"
            onClick={() => onDecide(proposal, false)}
            className="text-red-700"
          >
            Deny
          </Button>
        </div>
      ) : null}
    </div>
  );
}
