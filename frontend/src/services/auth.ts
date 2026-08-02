// Auth service: login, logout, session persistence.
import { apiFetch } from "@/lib/api-client";
import { clearSession, setSession, type Session } from "@/lib/session";
import type { AuthResponse } from "@/types";

export interface LoginInput {
  email: string;
  password: string;
}

export async function login(input: LoginInput): Promise<AuthResponse> {
  const result = await apiFetch<AuthResponse>("/auth/login", {
    method: "POST",
    auth: false,
    body: JSON.stringify(input),
  });
  persist(result);
  return result;
}

export async function logout(): Promise<void> {
  try {
    await apiFetch<void>("/auth/logout", { method: "POST" });
  } catch {
    // Best-effort server-side revocation; local sign-out always proceeds.
  } finally {
    clearSession();
  }
}

export async function fetchCurrentUser(): Promise<AuthResponse["user"]> {
  return apiFetch<AuthResponse["user"]>("/auth/me");
}

function persist(result: AuthResponse): void {
  const session: Session = {
    accessToken: result.access_token,
    refreshToken: result.refresh_token,
    expiresIn: result.expires_in,
    user: result.user,
  };
  setSession(session);
}
