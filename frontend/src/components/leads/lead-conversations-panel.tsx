// Conversations panel for a single lead: thread list, thread view, replies.
// Conversations live ONLY inside Lead Detail (V1 boundary) — there is no
// separate inbox/messaging surface.
//
// TRUTHFUL DELIVERY: the backend `add_message` endpoint records an AGENT
// message in AgencyOS. It does NOT dispatch email, WhatsApp, or any other
// external provider message. Nothing in this panel sends anything externally;
// the copy below says so wherever a user might misunderstand.
//
// The backend is authoritative for sender attribution: replies are always
// AGENT messages created by the authenticated user (sender identity and
// timestamps are stamped server-side). The frontend keeps sending the legacy
// required contract fields (organization_id, conversation_id, sender_type),
// which the backend overwrites/validates; the client never chooses a tenant
// or a sender identity.
//
// NAVIGATION GUARD: one synchronous generation (lib/navigation-guard.ts)
// identifies the view every explicit navigation action lands in (thread list
// or a specific thread). Every asynchronous mutation captures the context at
// start and applies its UI effects only while that context is still current —
// so no completed mutation (record reply, create thread, close/reopen) can
// steal the user's selection or stamp the wrong thread's error.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Badge, Button, EmptyState, Input, Select, Spinner, Textarea } from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { formatDateTime, formatRelative } from "@/lib/format";
import {
  applyPage,
  applyPageError,
  beginPage,
  initialPagedList,
  nextOffset,
  type PagedListState,
} from "@/lib/paged-list";
import { createNavigationGuard, type NavigationToken } from "@/lib/navigation-guard";
import { createOwnershipLock } from "@/lib/ownership-lock";
import { shouldClearComposerAfter } from "@/lib/reply-draft";
import { can } from "@/lib/permissions";
import {
  addConversationMessage,
  createConversation,
  listConversationMessages,
  listConversationsForLead,
  updateConversation,
} from "@/services/conversations";
import type { Conversation, ConversationMessage, OutreachChannel } from "@/types";

const CHANNEL_LABELS: Record<OutreachChannel, string> = {
  email: "Email",
  whatsapp: "WhatsApp",
  contact_form: "Contact form",
  linkedin: "LinkedIn",
  instagram: "Instagram",
  facebook: "Facebook",
};

const MESSAGE_SENDER_LABELS: Record<ConversationMessage["sender_type"], string> = {
  agent: "Agent",
  lead: "Lead",
  system: "System",
};

/** Backend maximum page size for messages (limit ≤ 1000). Pages are offset by raw records consumed. */
const MESSAGE_PAGE_SIZE = 1000;

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiRequestError ? err.message : fallback;
}

type LoadState = "loading" | "error" | "ready";

export function LeadConversationsPanel({ leadId }: { leadId: string }) {
  const session = useAuth();

  // Thread list state. The last successfully loaded list is preserved when a
  // refresh fails; `state` tells loading/error/ready apart explicitly so a
  // failed request never renders as an empty-success result.
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [listState, setListState] = useState<LoadState>("loading");
  const [listError, setListError] = useState<string | null>(null);

  const [selected, setSelected] = useState<Conversation | null>(null);

  // Message history state — machine-driven: unique items, RAW-consumed cursor,
  // loading flag, last error, and pagination bookkeeping.
  const [msgList, setMsgList] = useState<PagedListState<ConversationMessage>>(() =>
    initialPagedList<ConversationMessage>()
  );
  const [msgKind, setMsgKind] = useState<"initial" | "more">("initial");

  // New-thread form state.
  const [channel, setChannel] = useState<OutreachChannel>("email");
  const [subject, setSubject] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<{
    token: NavigationToken;
    message: string;
  } | null>(null);

  // Record-reply composer — records only, never dispatches. Errors are tagged
  // with their thread so they can never surface in another thread's composer.
  const [reply, setReply] = useState("");
  const [sending, setSending] = useState(false);
  const [replyError, setReplyError] = useState<{
    token: NavigationToken;
    threadId: string;
    message: string;
  } | null>(null);
  const [statusError, setStatusError] = useState<{
    token: NavigationToken;
    threadId: string;
    message: string;
  } | null>(null);
  const [statusBusy, setStatusBusy] = useState(false);

  // Single source of truth for "where is the user".
  const navGuardRef = useRef(createNavigationGuard());
  // Thread list keeps a simple numeric generation for its fetch staleness.
  const listGen = useRef(0);
  // Ownership-aware lock for the load-more pagination request.
  const msgLockRef = useRef(createOwnershipLock());
  // Mirror of the draft for event handlers (updated in an effect).
  const replyRef = useRef("");
  // Synchronous mirror of the subject draft — updated directly in the input's
  // onChange so late mutations (create success/failure) can detect whether the
  // composer value is still the one they captured.
  const subjectRef = useRef("");

  useEffect(() => {
    replyRef.current = reply;
  }, [reply]);

  const loadThreads = useCallback(() => {
    const generation = ++listGen.current;
    return listConversationsForLead(leadId)
      .then((data) => {
        if (generation !== listGen.current) return;
        setConversations(data);
        setListState("ready");
        setListError(null);
      })
      .catch((err: unknown) => {
        if (generation !== listGen.current) return;
        // Keep whatever list is already loaded (do NOT blank it on failure).
        setListState("error");
        setListError(errorMessage(err, "Failed to load conversations"));
      });
  }, [leadId]);

  // Reset per-lead state during render when the lead changes (React-endorsed
  // alternative to syncing state in an effect). The parent also remounts this
  // panel via a key on lead/principal change.
  const [activeLeadId, setActiveLeadId] = useState(leadId);
  if (activeLeadId !== leadId) {
    setActiveLeadId(leadId);
    setSelected(null);
    setMsgList(initialPagedList());
    setMsgKind("initial");
    setReply("");
    setReplyError(null);
    setStatusError(null);
    setCreateError(null);
    setListState("loading");
    setListError(null);
  }

  useEffect(() => {
    const nav = navGuardRef.current;
    const lock = msgLockRef.current;
    loadThreads();
    return () => {
      nav.invalidate();
      lock.invalidate();
    };
  }, [loadThreads]);

  const openThread = useCallback((conversation: Conversation) => {
    // Read the CURRENT view BEFORE navigating, to decide same-thread refresh.
    const sameThread = navGuardRef.current.view() === conversation.id;
    const token = navGuardRef.current.navigateThread(conversation.id);
    // A stale load-more in flight may not hold the lock for this thread.
    msgLockRef.current.invalidate();
    setSelected(conversation);
    if (!sameThread) setReply(""); // switching threads discards the previous thread's draft
    setReplyError(null);
    setStatusError(null);
    setCreateError(null);
    setMsgKind("initial");
    if (!sameThread) setMsgList(initialPagedList());
    setMsgList((s) => beginPage(s));
    listConversationMessages(conversation.id, { limit: MESSAGE_PAGE_SIZE, offset: 0 })
      .then((page) => {
        if (!navGuardRef.current.isCurrent(token)) return;
        setMsgList((s) => applyPage(s, page, MESSAGE_PAGE_SIZE, false));
      })
      .catch((err: unknown) => {
        if (!navGuardRef.current.isCurrent(token)) return;
        setMsgList((s) => applyPageError(s, errorMessage(err, "Failed to load messages")));
      });
  }, []);

  const retryMessages = useCallback(() => {
    if (selected) openThread(selected);
  }, [selected, openThread]);

  const loadMoreMessages = useCallback(() => {
    const target = selected;
    if (!target) return;
    if (!msgList.hasMore || msgList.loading) return;
    const token = navGuardRef.current.capture();
    if (!msgLockRef.current.tryAcquire(token.generation)) return; // duplicate rejected
    const offset = nextOffset(msgList);
    setMsgKind("more");
    setMsgList((s) => beginPage(s));
    listConversationMessages(target.id, { limit: MESSAGE_PAGE_SIZE, offset })
      .then((page) => {
        if (!navGuardRef.current.isCurrent(token)) return;
        setMsgList((s) => applyPage(s, page, MESSAGE_PAGE_SIZE, true));
      })
      .catch((err: unknown) => {
        if (!navGuardRef.current.isCurrent(token)) return;
        setMsgList((s) => applyPageError(s, errorMessage(err, "Couldn't load more messages")));
      })
      .finally(() => {
        // Only the owning request may release the lock; never a stale one.
        msgLockRef.current.release(token.generation);
      });
  }, [selected, msgList]);

  if (!session) return null;
  const canWrite = can(session.user.role, "lead_write");
  const orgId = session.user.organization_id;
  // Backend constraint (uq_conversations_open_per_channel): only one OPEN
  // thread per (lead, channel). Block a duplicate create up front instead of
  // surfacing a database error.
  const openChannels = new Set(
    conversations.filter((conversation) => conversation.is_open).map((c) => c.channel)
  );
  const channelTaken = openChannels.has(channel);

  async function handleCreateThread() {
    const token = navGuardRef.current.capture();
    const submittedSubject = subject;
    setCreating(true);
    setCreateError(null);
    try {
      const created = await createConversation({
        lead_id: leadId,
        channel,
        subject: submittedSubject.trim() === "" ? null : submittedSubject.trim(),
        organization_id: orgId,
      });
      // Clear the subject ONLY when still in the list context AND the composer
      // still holds exactly the draft captured at submit time.
      if (
        shouldClearComposerAfter(
          navGuardRef.current.isList(token),
          subjectRef.current,
          submittedSubject
        )
      ) {
        setSubject("");
        subjectRef.current = "";
      }
      await loadThreads();
      // Open the new thread ONLY if the user is still on the list context the
      // mutation started in; the database record exists regardless.
      if (navGuardRef.current.isList(token)) {
        openThread(created);
      }
    } catch (err: unknown) {
      // The failure is scoped to the list context it started in.
      if (navGuardRef.current.isList(token)) {
        setCreateError({
          token,
          message: errorMessage(err, "Failed to create the thread record"),
        });
      }
    } finally {
      setCreating(false);
    }
  }

  async function handleRecordReply() {
    if (!selected || reply.trim() === "") return;
    const target = selected;
    const token = navGuardRef.current.capture();
    const submittedDraft = reply;
    setSending(true);
    setReplyError(null);
    try {
      await addConversationMessage(target.id, {
        conversation_id: target.id,
        sender_type: "agent",
        body: submittedDraft.trim(),
        organization_id: orgId,
      });
      // The DB mutation succeeded regardless of where the user navigated.
      await loadThreads();
      const stillSameThread = navGuardRef.current.isThread(token, target.id);
      if (stillSameThread) {
        // Still on the same thread: refresh the view; clear the draft only if
        // it is exactly what we submitted.
        const refreshToken = navGuardRef.current.capture();
        listConversationMessages(target.id, { limit: MESSAGE_PAGE_SIZE, offset: 0 })
          .then((page) => {
            if (!navGuardRef.current.isCurrent(refreshToken)) return;
            setMsgKind("initial");
            setMsgList((s) => applyPage(s, page, MESSAGE_PAGE_SIZE, false));
          })
          .catch((err: unknown) => {
            if (!navGuardRef.current.isCurrent(refreshToken)) return;
            setReplyError({
              token: refreshToken,
              threadId: target.id,
              message: errorMessage(
                err,
                "Message recorded, but the thread view could not be refreshed."
              ),
            });
          });
        if (shouldClearComposerAfter(stillSameThread, replyRef.current, submittedDraft)) {
          setReply("");
        }
      }
      // Else: user navigated away — leave the composer/view untouched.
    } catch (err: unknown) {
      if (navGuardRef.current.isThread(token, target.id)) {
        setReplyError({
          token,
          threadId: target.id,
          message: errorMessage(err, "Failed to record the message"),
        });
      }
    } finally {
      setSending(false);
    }
  }

  async function handleToggleOpen() {
    if (!selected) return;
    const target = selected;
    const token = navGuardRef.current.capture();
    setStatusBusy(true);
    setStatusError(null);
    try {
      const updated = await updateConversation(target.id, { is_open: !target.is_open });
      await loadThreads();
      // Update the detail view ONLY if the user is still on this same thread.
      if (navGuardRef.current.isThread(token, target.id)) {
        setSelected(updated);
      }
    } catch (err: unknown) {
      // Thread-scoped error: visible only when still on the same thread at the
      // same navigation generation.
      if (navGuardRef.current.isThread(token, target.id)) {
        setStatusError({
          token,
          threadId: target.id,
          message: errorMessage(err, "Failed to update conversation"),
        });
      }
    } finally {
      setStatusBusy(false);
    }
  }

  function backToThreads() {
    navGuardRef.current.navigateList();
    msgLockRef.current.invalidate();
    setSelected(null);
    setMsgList(initialPagedList());
    setMsgKind("initial");
    setReply("");
    setReplyError(null);
    setStatusError(null);
    setCreateError(null);
  }

  const listRefreshFailure = listState === "error" && conversations.length > 0;
  // Errors are written only while their context is still current (gated at
  // write time) and are cleared synchronously on every navigation — a stale
  // error therefore cannot render.
  const visibleReplyError =
    replyError && selected && replyError.threadId === selected.id ? replyError.message : null;
  const visibleStatusError =
    statusError && selected && statusError.threadId === selected.id ? statusError.message : null;
  const visibleCreateError = createError ? createError.message : null;
  const initialError = msgList.error !== null && msgList.items.length === 0;
  const moreError = msgList.error !== null && msgList.items.length > 0;

  return (
    <section aria-label="Conversations" className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Conversations</h3>
        {listState === "error" ? (
          <Button variant="outline" onClick={() => loadThreads()}>
            Retry
          </Button>
        ) : null}
      </div>
      <p className="text-xs text-gray-500">
        Messages are recorded in AgencyOS only. Nothing here is sent to the lead through email,
        WhatsApp, or any external channel.
      </p>

      {listRefreshFailure ? (
        <p role="alert" className="text-sm text-red-600">
          {listError}{" "}
          <button type="button" className="underline" onClick={() => loadThreads()}>
            Retry
          </button>
        </p>
      ) : null}

      {selected ? (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Button variant="outline" onClick={backToThreads} aria-label="Back to thread list">
              ← Back to conversations
            </Button>
            <span className="flex items-center gap-2">
              <Badge tone="blue">{CHANNEL_LABELS[selected.channel]}</Badge>
              <Badge tone={selected.is_open ? "green" : "gray"}>
                {selected.is_open ? "Open" : "Closed"}
              </Badge>
              {canWrite ? (
                <Button variant="outline" onClick={handleToggleOpen} disabled={statusBusy}>
                  {selected.is_open ? "Close thread" : "Reopen thread"}
                </Button>
              ) : null}
            </span>
          </div>

          {visibleStatusError ? (
            <p role="alert" className="text-sm text-red-600">
              {visibleStatusError}
            </p>
          ) : null}
          <h4 className="text-sm text-gray-700">
            {selected.subject ?? CHANNEL_LABELS[selected.channel]}
          </h4>

          {msgList.loading && msgList.items.length === 0 && msgKind === "initial" ? (
            <Spinner label="Loading messages…" />
          ) : initialError ? (
            <div className="flex flex-col items-start gap-2">
              <p role="alert" className="text-sm text-red-600">
                {msgList.error}
              </p>
              <Button variant="outline" onClick={retryMessages}>
                Retry
              </Button>
            </div>
          ) : msgList.items.length === 0 ? (
            <EmptyState
              title="No messages recorded yet"
              description={
                canWrite
                  ? "Record the first message — it is saved in AgencyOS and is not sent anywhere externally."
                  : "No messages have been recorded in this thread."
              }
            />
          ) : (
            <>
              {moreError ? (
                <p role="alert" className="text-sm text-red-600">
                  {msgList.error}{" "}
                  <button type="button" className="underline" onClick={loadMoreMessages}>
                    Retry
                  </button>
                </p>
              ) : null}
              <ul className="flex flex-col gap-2" aria-label="Messages">
                {msgList.items.map((message) => (
                  <li key={message.id} className="rounded-lg border bg-white p-3 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium text-gray-700">
                        {MESSAGE_SENDER_LABELS[message.sender_type]}
                      </span>
                      <time
                        className="text-xs text-gray-400"
                        dateTime={message.sent_at ?? message.created_at}
                      >
                        {formatDateTime(message.sent_at ?? message.created_at)}
                      </time>
                    </div>
                    <p className="mt-1 whitespace-pre-wrap text-gray-700">{message.body}</p>
                  </li>
                ))}
              </ul>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs text-gray-500">
                  Showing {msgList.items.length.toLocaleString()} recorded message
                  {msgList.items.length === 1 ? "" : "s"}
                  {msgList.hasMore
                    ? " (backend pages of up to 1,000)."
                    : ". All recorded messages are shown."}
                </span>
                {msgList.hasMore ? (
                  <Button variant="outline" onClick={loadMoreMessages} disabled={msgList.loading}>
                    {msgList.loading && msgKind === "more" ? "Loading…" : "Load more messages"}
                  </Button>
                ) : null}
              </div>
            </>
          )}

          {canWrite ? (
            <div className="flex flex-col gap-2">
              <p className="text-xs text-gray-500">
                Recording a reply saves it to this thread in AgencyOS. It is not sent to the lead
                through any external channel.
              </p>
              <Textarea
                rows={3}
                aria-label="Record a message"
                placeholder="Record a message…"
                value={reply}
                onChange={(e) => setReply(e.target.value)}
              />
              {visibleReplyError ? (
                <p role="alert" className="text-sm text-red-600">
                  {visibleReplyError}
                </p>
              ) : null}
              <div className="flex justify-end">
                <Button onClick={handleRecordReply} disabled={sending || reply.trim() === ""}>
                  {sending ? "Recording…" : "Record reply"}
                </Button>
              </div>
            </div>
          ) : (
            <p className="text-xs text-gray-500">
              You do not have permission to record messages in conversations.
            </p>
          )}
        </div>
      ) : listState === "loading" && conversations.length === 0 ? (
        <Spinner label="Loading conversations…" />
      ) : listState === "error" && conversations.length === 0 ? (
        <div className="flex flex-col items-start gap-2">
          <p role="alert" className="text-sm text-red-600">
            {listError}
          </p>
          <Button variant="outline" onClick={() => loadThreads()}>
            Retry
          </Button>
        </div>
      ) : conversations.length === 0 ? (
        <EmptyState
          title="No conversations yet"
          description="Create a thread to record messages with this lead. Threads and messages are stored in AgencyOS only and are never sent externally."
        />
      ) : (
        <ul className="flex flex-col gap-2" aria-label="Conversations">
          {conversations.map((conversation) => (
            <li key={conversation.id}>
              <button
                type="button"
                onClick={() => openThread(conversation)}
                className="flex w-full flex-wrap items-center justify-between gap-2 rounded-lg border bg-white p-3 text-left text-sm hover:border-gray-400"
              >
                <span className="flex min-w-0 flex-col">
                  <span className="truncate font-medium text-gray-800">
                    {conversation.subject ?? CHANNEL_LABELS[conversation.channel]}
                  </span>
                  <span className="text-xs text-gray-400">
                    {CHANNEL_LABELS[conversation.channel]}
                    {conversation.last_message_at
                      ? ` · Last message ${formatRelative(conversation.last_message_at)}`
                      : " · No messages recorded"}
                  </span>
                </span>
                <Badge tone={conversation.is_open ? "green" : "gray"}>
                  {conversation.is_open ? "Open" : "Closed"}
                </Badge>
              </button>
            </li>
          ))}
        </ul>
      )}

      {canWrite && !selected ? (
        <form
          className="flex flex-col gap-2 rounded-lg border bg-white p-3"
          onSubmit={(e) => {
            e.preventDefault();
            handleCreateThread();
          }}
        >
          <h4 className="text-sm font-medium text-gray-700">Start a conversation</h4>
          <p className="text-xs text-gray-500">
            This records a new thread in AgencyOS for this lead. It does not create a conversation
            with any external provider, and no message is sent anywhere.
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Select
              aria-label="Conversation channel"
              value={channel}
              onChange={(e) => setChannel(e.target.value as OutreachChannel)}
              className="sm:w-44"
            >
              {(Object.keys(CHANNEL_LABELS) as OutreachChannel[]).map((value) => (
                <option key={value} value={value}>
                  {CHANNEL_LABELS[value]}
                </option>
              ))}
            </Select>
            <Input
              aria-label="Conversation subject"
              placeholder="Subject (optional)"
              value={subject}
              onChange={(e) => {
                subjectRef.current = e.target.value;
                setSubject(e.target.value);
              }}
              maxLength={255}
            />
          </div>
          {visibleCreateError ? (
            <p role="alert" className="text-sm text-red-600">
              {visibleCreateError}
            </p>
          ) : null}
          <div className="flex justify-end">
            <Button type="submit" disabled={creating || channelTaken}>
              {creating ? "Recording…" : "Start conversation"}
            </Button>
          </div>
          {channelTaken ? (
            <p className="text-xs text-amber-600">
              An open {CHANNEL_LABELS[channel]} conversation already exists for this lead. Close it
              or pick another channel.
            </p>
          ) : null}
        </form>
      ) : null}
    </section>
  );
}
