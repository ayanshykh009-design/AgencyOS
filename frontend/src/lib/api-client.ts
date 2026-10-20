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
import { clearSession, getAccessToken, setSession } from "@/lib/session";
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
    const result = await performRefresh();
    if (result.ok) {
      res = await send(path, auth, headers, rest);
    } else if (result.definitive) {
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
      credentials: "include",
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

// A single in-flight refresh shared by all callers (bootstrap + 401 retries)
// so a burst of requests rotates the refresh token exactly once.
export type RefreshResult = { ok: true; data: AuthResponse } | { ok: false; definitive: boolean };

let inFlightRefresh: Promise<RefreshResult> | null = null;

export function performRefresh(): Promise<RefreshResult> {
  if (!inFlightRefresh) {
    inFlightRefresh = doRefresh().finally(() => {
      inFlightRefresh = null;
    });
  }
  return inFlightRefresh;
}

async function doRefresh(): Promise<RefreshResult> {
  try {
    const res = await fetch(`${env.NEXT_PUBLIC_API_URL}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
    });
    if (!res.ok) {
      const definitive = res.status === 401 || res.status === 403;
      if (definitive) {
        clearSession();
      }
      return { ok: false, definitive };
    }
    const data = (await res.json()) as AuthResponse;
    setSession({
      accessToken: data.access_token,
      expiresIn: data.expires_in,
      user: data.user,
    });
    return { ok: true, data };
  } catch {
    // Network failure: not definitive; leave session state untouched.
    return { ok: false, definitive: false };
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
