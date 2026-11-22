// Auth service: register, login, logout, refresh, session persistence.
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

/** Self-service organization signup (founder-approved: public signup is open). */
export interface RegisterInput {
  email: string;
  password: string;
  fullName: string;
  organizationName: string;
  organizationSlug: string;
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

/**
 * Register a new organization and its owner account. The backend creates the
 * organization with the registering user as OWNER, isolates it as its own
 * tenant, enforces the same rate limits as login, and (when email
 * verification is enabled) flags the account until the address is confirmed.
 * On success the refresh cookie is set and the session is persisted in
 * memory exactly like a password login.
 */
export async function register(input: RegisterInput): Promise<AuthResponse> {
  const result = await apiFetch<AuthResponse>("/auth/register", {
    method: "POST",
    auth: false,
    body: JSON.stringify({
      email: input.email,
      password: input.password,
      full_name: input.fullName,
      organization_name: input.organizationName,
      organization_slug: input.organizationSlug,
    }),
  });
  persist(result);
  return result;
}

/**
 * The backend cannot expose its feature flags to the browser, so the
 * disabled/feature-off states are derived from the exact `detail` the API
 * returns when a flag is off (app/api/v1/endpoints/auth.py). The UI shows a
 * neutral disabled state only from this real signal — never from a guess.
 */
export const PASSWORD_RESET_DISABLED_DETAIL = "Password reset is not enabled";

export const EMAIL_VERIFICATION_DISABLED_DETAIL = "Email verification is not enabled";

export function isPasswordResetDisabled(detail: string | null | undefined): boolean {
  return detail === PASSWORD_RESET_DISABLED_DETAIL;
}

export function isEmailVerificationDisabled(detail: string | null | undefined): boolean {
  return detail === EMAIL_VERIFICATION_DISABLED_DETAIL;
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

/** Re-send the verification link for an email address (pre-authentication). */
export async function resendVerification(email: string): Promise<MessageResponse> {
  return apiFetch<MessageResponse>("/auth/verify-email/resend", {
    method: "POST",
    auth: false,
    body: JSON.stringify({ email }),
  });
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
