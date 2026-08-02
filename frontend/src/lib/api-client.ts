// Thin API client wrapper around the FastAPI backend.
//
// All backend calls should route through this module (or src/services/) so
// base URL + auth headers are applied in one place. Failures are normalized
// into ApiRequestError using the backend's standard error envelope:
//   { "error": { "code": "...", "message": "...", "details": {...} } }

import { env } from "@/lib/env";
import { getAccessToken } from "@/lib/session";
import type { ApiError } from "@/types";

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
  const token = auth ? getAccessToken() : null;

  let res: Response;
  try {
    res = await fetch(`${env.NEXT_PUBLIC_API_URL}${path}`, {
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

  if (!res.ok) {
    throw await toApiRequestError(res, path);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
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
