// Thin API client wrapper around the FastAPI backend.
//
// All backend calls should route through this module (or src/services/) so
// base URL + auth headers are applied in one place. Failures are normalized
// into ApiRequestError using the backend's standard error envelope:
//   { "error": { "code": "...", "message": "...", "details": {...} } }
//
// A 401 on an authenticated request transparently triggers a single refresh
// (deduped across concurrent callers) and one retry of the original request.

import { env } from "@/lib/env";
import { clearSession, getAccessToken, getSession, setSession } from "@/lib/session";
import type { ApiError, AuthResponse } from "@/types";

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: Record<string, unknown> | null;

  constructor(
    status: number,
    code: string,
    message: string,
    details?: Record<string, unknown> | null
  ) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

interface ApiFetchOptions extends RequestInit {
  /** Attach the stored Bearer token (defaults to true). */
  auth?: boolean;
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { auth = true, headers, ...rest } = options;

  let res = await send(path, auth, headers, rest);
  if (res.status === 401 && auth) {
    if (await refreshSessionOnce()) {
      res = await send(path, auth, headers, rest);
    } else {
      // Refresh token missing/expired/revoked: drop the dead session so the app
      // falls back to the login flow.
      clearSession();
    }
  }

  if (!res.ok) {
    throw await toApiRequestError(res, path);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

async function send(
  path: string,
  auth: boolean,
  headers: HeadersInit | undefined,
  rest: RequestInit
): Promise<Response> {
  const token = auth ? getAccessToken() : null;
  try {
    return await fetch(`${env.NEXT_PUBLIC_API_URL}${path}`, {
      ...rest,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(headers ?? {}),
      },
    });
  } catch {
    throw new ApiRequestError(0, "network.error", "Unable to reach the API");
  }
}

// A single in-flight refresh shared by all concurrent 401s so a burst of
// requests rotates the refresh token exactly once.
let inFlightRefresh: Promise<boolean> | null = null;

function refreshSessionOnce(): Promise<boolean> {
  if (!inFlightRefresh) {
    inFlightRefresh = refreshSession().finally(() => {
      inFlightRefresh = null;
    });
  }
  return inFlightRefresh;
}

async function refreshSession(): Promise<boolean> {
  const session = getSession();
  if (!session?.refreshToken) {
    return false;
  }
  try {
    const res = await fetch(`${env.NEXT_PUBLIC_API_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: session.refreshToken }),
    });
    if (!res.ok) {
      return false;
    }
    const data = (await res.json()) as AuthResponse;
    setSession({
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      expiresIn: data.expires_in,
      user: data.user,
    });
    return true;
  } catch {
    return false;
  }
}

async function toApiRequestError(res: Response, path: string): Promise<ApiRequestError> {
  let code = "request.failed";
  let message = `API error ${res.status} on ${path}`;
  let details: Record<string, unknown> | null = null;
  try {
    const body = (await res.json()) as { error?: ApiError };
    if (body?.error) {
      code = body.error.code;
      message = body.error.message;
      details = body.error.details ?? null;
    }
  } catch {
    // Non-JSON error body; keep the generic message above.
  }
  return new ApiRequestError(res.status, code, message, details);
}
