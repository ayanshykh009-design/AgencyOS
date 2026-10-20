// Auth service: login, logout, refresh, session persistence.
import { ApiRequestError, apiFetch, performRefresh } from "@/lib/api-client";
import { clearSession, setSession, type Session } from "@/lib/session";
import type {
  AuthResponse,
  MessageResponse,
  MfaActivateResponse,
  MfaEnrollResponse,
} from "@/types";

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

/** Rotate the refresh cookie and persist the new access token in memory. */
export async function refresh(): Promise<AuthResponse> {
  const result = await performRefresh();
  if (!result.ok) {
    throw new ApiRequestError(
      result.definitive ? 401 : 0,
      result.definitive ? "auth.invalid_refresh" : "auth.network_error",
      result.definitive ? "Refresh token invalid or expired" : "Unable to reach the API"
    );
  }
  return result.data;
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

// --- Email verification -----------------------------------------------------

/** Confirm an email address with a single-use verification token. */
export async function verifyEmail(token: string): Promise<void> {
  await apiFetch<void>("/auth/verify-email", {
    method: "POST",
    auth: false,
    body: JSON.stringify({ token }),
  });
}

/** Re-issue the verification link for the signed-in user. */
export async function resendVerification(): Promise<MessageResponse> {
  return apiFetch<MessageResponse>("/auth/verify-email/resend", { method: "POST" });
}

// --- Password reset ---------------------------------------------------------

/**
 * Request a password reset email. Always resolves (the backend never reveals
 * whether an account exists); inspect `dev_url` outside production only.
 */
export async function requestPasswordReset(email: string): Promise<MessageResponse> {
  return apiFetch<MessageResponse>("/auth/password-reset/request", {
    method: "POST",
    auth: false,
    body: JSON.stringify({ email }),
  });
}

/** Complete a password reset with a token and the new password. */
export async function confirmPasswordReset(token: string, newPassword: string): Promise<void> {
  await apiFetch<void>("/auth/password-reset/confirm", {
    method: "POST",
    auth: false,
    body: JSON.stringify({ token, new_password: newPassword }),
  });
}

// --- Two-factor authentication ----------------------------------------------

/** Start TOTP enrollment; returns a pending secret + otpauth URI. */
export async function mfaEnroll(): Promise<MfaEnrollResponse> {
  return apiFetch<MfaEnrollResponse>("/auth/mfa/enroll", { method: "POST" });
}

/** Confirm enrollment with a code; returns one-time recovery codes. */
export async function mfaActivate(code: string): Promise<MfaActivateResponse> {
  return apiFetch<MfaActivateResponse>("/auth/mfa/activate", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

/** Disable TOTP after verifying the current factor. */
export async function mfaDisable(code: string): Promise<void> {
  await apiFetch<void>("/auth/mfa/disable", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

/**
 * Complete a MFA-gated login. On success the resulting session is persisted
 * exactly like a password login.
 */
export async function mfaVerify(mfaToken: string, code: string): Promise<AuthResponse> {
  const result = await apiFetch<AuthResponse>("/auth/mfa/verify", {
    method: "POST",
    auth: false,
    body: JSON.stringify({ mfa_token: mfaToken, code }),
  });
  persist(result);
  return result;
}

/** The `mfa_token` a login attempt carries when a second factor is required. */
export function mfaTokenFromError(err: unknown): string | null {
  if (!(err instanceof ApiRequestError) || err.code !== "auth.mfa_required") {
    return null;
  }
  const token = err.details?.["mfa_token"];
  return typeof token === "string" ? token : null;
}

function persist(result: AuthResponse): void {
  const session: Session = {
    accessToken: result.access_token,
    expiresIn: result.expires_in,
    user: result.user,
  };
  setSession(session);
}
