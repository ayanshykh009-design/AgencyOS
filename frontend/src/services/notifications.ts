// Notifications service: per-user in-app inbox.
import { apiFetch } from "@/lib/api-client";
import type { Notification, NotificationType, Page } from "@/types";

export interface NotificationQuery {
  onlyUnread?: boolean;
  limit?: number;
  offset?: number;
}

export interface UnreadCount {
  count: number;
}

export interface NotificationTypeCounts {
  counts: Record<NotificationType, number>;
}

export async function listNotifications(
  query: NotificationQuery = {}
): Promise<Page<Notification>> {
  const params = new URLSearchParams();
  if (query.onlyUnread) params.set("only_unread", "true");
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();
  return apiFetch<Page<Notification>>(`/notifications${qs ? `?${qs}` : ""}`);
}

export async function getNotification(notificationId: string): Promise<Notification> {
  return apiFetch<Notification>(`/notifications/${notificationId}`);
}

export async function getUnreadCount(): Promise<UnreadCount> {
  return apiFetch<UnreadCount>("/notifications/unread-count");
}

export async function getNotificationTypeCounts(): Promise<NotificationTypeCounts> {
  return apiFetch<NotificationTypeCounts>("/notifications/counts");
}

export async function markNotificationRead(notificationId: string): Promise<Notification> {
  return apiFetch<Notification>(`/notifications/${notificationId}/read`, {
    method: "POST",
  });
}

export async function setNotificationRead(
  notificationId: string,
  isRead: boolean
): Promise<Notification> {
  return apiFetch<Notification>(`/notifications/${notificationId}`, {
    method: "PATCH",
    body: JSON.stringify({ is_read: isRead }),
  });
}
