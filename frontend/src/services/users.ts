// Users service: list org members and update roles/status (admin).
import { apiFetch } from "@/lib/api-client";
import type { Page, User, UserRole } from "@/types";

export async function listUsers(limit = 100, offset = 0): Promise<Page<User>> {
  return apiFetch<Page<User>>(`/users?limit=${limit}&offset=${offset}`);
}

export async function getUser(userId: string): Promise<User> {
  return apiFetch<User>(`/users/${userId}`);
}

export interface UserUpdateInput {
  role?: UserRole;
  is_active?: boolean;
  full_name?: string;
}

export async function updateUser(userId: string, patch: UserUpdateInput): Promise<User> {
  return apiFetch<User>(`/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}
