// Inbox: per-user in-app notifications.
"use client";

import { useCallback, useEffect, useState } from "react";

import {
  Badge,
  Button,
  EmptyState,
  PageHeader,
  Spinner,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TRow,
} from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { NOTIFICATION_TYPE_LABELS, formatDateTime, notificationTypeTone } from "@/lib/format";
import { listNotifications, markNotificationRead } from "@/services/notifications";
import type { Notification } from "@/types";

export function inboxErrorMessage(err: unknown): string {
  return err instanceof ApiRequestError ? err.message : "Failed to load notifications";
}

export default function InboxPage() {
  const session = useAuth();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [onlyUnread, setOnlyUnread] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback((unreadOnly: boolean) => {
    listNotifications({ onlyUnread: unreadOnly, limit: 100 })
      .then((page) => {
        setNotifications(page.items);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(inboxErrorMessage(err));
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load(onlyUnread);
  }, [load, onlyUnread]);

  if (!session) return null;

  const markRead = (notification: Notification) => {
    if (notification.is_read) return;
    setBusyId(notification.id);
    markNotificationRead(notification.id)
      .then(() => load(onlyUnread))
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Failed to update notification");
      })
      .finally(() => setBusyId(null));
  };

  const unread = notifications.filter((n) => !n.is_read).length;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Inbox"
        description={`Notifications for you${onlyUnread ? ` · ${unread} unread` : ""}.`}
        actions={
          <Button variant="outline" onClick={() => setOnlyUnread((v) => !v)}>
            {onlyUnread ? "Show all" : "Unread only"}
          </Button>
        }
      />

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {loading ? (
        <Spinner label="Loading notifications…" />
      ) : notifications.length === 0 ? (
        <EmptyState
          title="No notifications"
          description="Workflow, approval, and agent events will land here."
        />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Type</TH>
              <TH>Message</TH>
              <TH>Received</TH>
              <TH />
            </tr>
          </THead>
          <TBody>
            {notifications.map((notification) => (
              <TRow key={notification.id}>
                <TD>
                  <Badge tone={notificationTypeTone(notification.type)}>
                    {NOTIFICATION_TYPE_LABELS[notification.type]}
                  </Badge>
                </TD>
                <TD className="max-w-xl">
                  <p className="font-medium">
                    {notification.title}
                    {!notification.is_read ? (
                      <span className="ml-2 inline-block h-2 w-2 rounded-full bg-blue-500 align-middle" />
                    ) : null}
                  </p>
                  <p className="truncate text-sm text-gray-500">{notification.body}</p>
                </TD>
                <TD className="text-xs text-gray-400">{formatDateTime(notification.created_at)}</TD>
                <TD className="text-right">
                  <div className="flex items-center justify-end gap-2">
                    {notification.action_url ? (
                      <a
                        href={notification.action_url}
                        className="text-sm font-medium text-blue-600 hover:underline"
                      >
                        Open
                      </a>
                    ) : null}
                    {!notification.is_read ? (
                      <Button
                        variant="ghost"
                        disabled={busyId === notification.id}
                        onClick={() => markRead(notification)}
                      >
                        Mark read
                      </Button>
                    ) : null}
                  </div>
                </TD>
              </TRow>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}
