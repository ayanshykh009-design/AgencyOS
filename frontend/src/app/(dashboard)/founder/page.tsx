// Founder AI Assistant chat (M8).
// The assistant is grounded in org context and routes every action through an
// approval-gated proposal. Approve/deny happen inline on returned proposals.
"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import { founderChatDisabledReason, proposalDecisionDisabledReason } from "@/lib/ai-capabilities";
import { ApiRequestError } from "@/lib/api-client";
import { canManageFounder, canViewFounder } from "@/lib/batch5-permissions";
import { getAICapabilities } from "@/services/ai";
import {
  decideFounderProposal,
  deleteFounderConversation,
  getFounderConversation,
  listFounderConversations,
  sendFounderMessage,
} from "@/services/founder";
import type { AICapabilities, FounderConversation, FounderMessage, FounderProposal } from "@/types";

interface ChatEntry {
  message: FounderMessage;
  proposals: FounderProposal[];
  intent?: Record<string, unknown>;
  ok?: boolean;
  error?: string | null;
}

export default function FounderChatPage() {
  const session = useAuth();
  const canView = !!session && canViewFounder(session.user.role);
  const canManage = !!session && canManageFounder(session.user.role);
  const [conversations, setConversations] = useState<FounderConversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatEntry[]>([]);
  const [draft, setDraft] = useState("");
  // null means unverified: chat send and proposal decisions fail closed.
  const [capabilities, setCapabilities] = useState<AICapabilities | null>(null);
  const [busy, setBusy] = useState(false);
  const [decidingId, setDecidingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Event handlers write state after awaits: guard against stale responses when
  // the user switches conversations quickly, and against post-unmount updates.
  const mountedRef = useRef(true);
  const conversationSeqRef = useRef(0);

  const chatDisabledReason = founderChatDisabledReason(capabilities);
  const decisionDisabledReason = proposalDecisionDisabledReason(capabilities);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  async function refreshConversations() {
    const page = await listFounderConversations({ limit: 50 });
    if (mountedRef.current) setConversations(page.items);
  }

  useEffect(() => {
    if (!canView) return;
    let cancelled = false;
    listFounderConversations({ limit: 50 })
      .then((page) => {
        if (!cancelled) setConversations(page.items);
      })
      .catch(() => undefined);
    getAICapabilities()
      .then((surface) => {
        if (!cancelled) setCapabilities(surface);
      })
      .catch(() => {
        if (!cancelled) setCapabilities(null);
      });
    return () => {
      cancelled = true;
    };
  }, [canView]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  async function openConversation(id: string) {
    const seq = ++conversationSeqRef.current;
    setActiveId(id);
    setError(null);
    try {
      const { messages: loaded } = await getFounderConversation(id);
      if (!mountedRef.current || seq !== conversationSeqRef.current) return;
      setMessages(loaded.map((message) => ({ message, proposals: [] })));
    } catch (err: unknown) {
      if (!mountedRef.current || seq !== conversationSeqRef.current) return;
      setError(err instanceof ApiRequestError ? err.message : "Failed to load conversation");
    }
  }

  async function onSend() {
    const text = draft.trim();
    if (!text || busy || !canManage || chatDisabledReason) return;
    const seq = conversationSeqRef.current;
    setBusy(true);
    setError(null);
    setDraft("");
    try {
      const res = await sendFounderMessage({
        message: text,
        conversation_id: activeId,
      });
      if (!mountedRef.current || seq !== conversationSeqRef.current) return;
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
      if (!mountedRef.current || seq !== conversationSeqRef.current) return;
      setError(err instanceof ApiRequestError ? err.message : "Assistant failed to respond");
    } finally {
      if (mountedRef.current) setBusy(false);
    }
  }

  async function onDecide(proposal: FounderProposal, approve: boolean) {
    if (!canManage || decisionDisabledReason || decidingId) return;
    const seq = conversationSeqRef.current;
    setDecidingId(proposal.id);
    setError(null);
    try {
      const updated = await decideFounderProposal(proposal.id, {
        approve,
        decision_note: approve ? null : "Denied from assistant",
      });
      if (!mountedRef.current || seq !== conversationSeqRef.current) return;
      setMessages((prev) =>
        prev.map((entry) => ({
          ...entry,
          proposals: entry.proposals.map((p) => (p.id === proposal.id ? updated : p)),
        }))
      );
    } catch (err: unknown) {
      if (!mountedRef.current || seq !== conversationSeqRef.current) return;
      setError(err instanceof ApiRequestError ? err.message : "Decision failed");
    } finally {
      if (mountedRef.current) setDecidingId(null);
    }
  }

  async function onDelete(id: string) {
    if (!canManage) return;
    const seq = conversationSeqRef.current;
    try {
      await deleteFounderConversation(id);
      if (!mountedRef.current) return;
      await refreshConversations();
      // The list must refresh even if the user switched threads mid-delete; only
      // the active-thread reset is invalidated by a newer conversation request.
      if (seq !== conversationSeqRef.current) return;
      if (activeId === id) {
        setActiveId(null);
        setMessages([]);
      }
    } catch (err: unknown) {
      if (!mountedRef.current || seq !== conversationSeqRef.current) return;
      setError(err instanceof ApiRequestError ? err.message : "Delete failed");
    }
  }

  if (!session) return null;
  if (!canView) {
    return (
      <p className="text-sm text-gray-600">
        You do not have permission to view the founder assistant. Contact an administrator.
      </p>
    );
  }

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
              <ConversationListItem
                key={c.conversation_id}
                conversation={c}
                canManage={canManage}
                active={activeId === c.conversation_id}
                onOpen={() => openConversation(c.conversation_id)}
                onDelete={() => onDelete(c.conversation_id)}
              />
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
                        <ProposalCard
                          key={p.id}
                          proposal={p}
                          canManage={canManage}
                          decisionDisabledReason={decisionDisabledReason}
                          busy={decidingId !== null}
                          onDecide={onDecide}
                        />
                      ))}
                    </div>
                  ) : null}
                </div>
              ))
            )}
          </div>

          {error ? <p className="text-sm text-red-600">{error}</p> : null}

          {canManage ? (
            <FounderComposer
              busy={busy}
              disabledReason={chatDisabledReason}
              draft={draft}
              onDraftChange={setDraft}
              onSend={onSend}
            />
          ) : (
            <p className="text-sm text-gray-500">
              You can read this history, but only managers can message the assistant.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}

/** Delete affordance is manager-only; readers get an inert list item. */
export function ConversationListItem({
  conversation,
  canManage,
  active,
  onOpen,
  onDelete,
}: {
  conversation: FounderConversation;
  canManage: boolean;
  active: boolean;
  onOpen: () => void;
  onDelete: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`flex items-center justify-between rounded-md border px-3 py-2 text-left text-sm ${
        active ? "border-gray-900" : ""
      }`}
    >
      <span className="truncate">{conversation.title || "Untitled conversation"}</span>
      {canManage ? (
        <span
          role="button"
          tabIndex={0}
          aria-label="Delete conversation"
          className="ml-2 text-xs text-gray-400 hover:text-red-600"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
        >
          ✕
        </span>
      ) : null}
    </button>
  );
}

/** Read-only for non-managers; disabled with a truthful notice when blocked. */
export function ProposalCard({
  proposal,
  canManage,
  decisionDisabledReason,
  busy = false,
  onDecide,
}: {
  proposal: FounderProposal;
  canManage: boolean;
  decisionDisabledReason: string | null;
  busy?: boolean;
  onDecide: (p: FounderProposal, approve: boolean) => void;
}) {
  const terminal = proposal.status !== "proposed";
  const showDecisionNotice = !terminal && canManage && !!decisionDisabledReason;
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
      {!terminal && canManage && !decisionDisabledReason ? (
        <div className="mt-2 flex items-center gap-2">
          <Button
            variant="ghost"
            onClick={() => onDecide(proposal, true)}
            disabled={busy}
            className="text-green-700"
          >
            Approve
          </Button>
          <Button
            variant="ghost"
            onClick={() => onDecide(proposal, false)}
            disabled={busy}
            className="text-red-700"
          >
            Deny
          </Button>
        </div>
      ) : null}
      {showDecisionNotice ? (
        <p className="mt-2 text-xs text-amber-700">{decisionDisabledReason}</p>
      ) : null}
    </div>
  );
}

/** Send control is only rendered for managers and fails closed when unavailable. */
export function FounderComposer({
  busy,
  disabledReason,
  draft,
  onDraftChange,
  onSend,
}: {
  busy: boolean;
  disabledReason: string | null;
  draft: string;
  onDraftChange: (value: string) => void;
  onSend: () => void;
}) {
  const disabled = busy || !!disabledReason || !draft.trim();
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-end gap-2">
        <textarea
          className="min-h-[44px] flex-1 rounded-md border px-3 py-2 text-sm"
          placeholder="Message the founder assistant…"
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (!disabled) onSend();
            }
          }}
        />
        <Button onClick={onSend} disabled={disabled}>
          {busy ? "Thinking…" : "Send"}
        </Button>
      </div>
      {disabledReason ? <p className="text-sm text-amber-700">{disabledReason}</p> : null}
    </div>
  );
}
