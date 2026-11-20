import { apiFetch } from "./client";

export type NotificationCategory =
  | "loan"
  | "repayment"
  | "contribution"
  | "account"
  | "system";

/** One in-app notice for the signed-in account. */
export interface Notification {
  id: string;
  category: NotificationCategory;
  title: string;
  body: string | null;
  link_path: string | null;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

/** The bell needs the page and the badge in one request. */
export interface NotificationPage {
  items: Notification[];
  total: number;
  unread_count: number;
}

export async function getNotifications(params: { skip?: number; limit?: number } = {}) {
  return apiFetch<NotificationPage>("/api/notifications", {
    searchParams: {
      skip: params.skip !== undefined ? String(params.skip) : undefined,
      limit: params.limit !== undefined ? String(params.limit) : undefined,
    },
  });
}

export async function markNotificationRead(id: string): Promise<Notification> {
  return apiFetch<Notification>(`/api/notifications/${id}/read`, { method: "POST" });
}

export async function markAllNotificationsRead(): Promise<{ updated: number }> {
  return apiFetch<{ updated: number }>("/api/notifications/read-all", { method: "POST" });
}
