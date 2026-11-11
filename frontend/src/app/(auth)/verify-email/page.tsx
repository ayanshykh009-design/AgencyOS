// Email-verification landing page (Sheet 2A screen 10). The token in the
// emailed link is single-use; the "verified" state is only ever set after a
// real 204 from the API. Resend is enumeration-safe: the UI never reveals
// whether an address belongs to an account, and a neutral disabled state is
// shown only when the backend says email verification is disabled.
"use client";

import Link from "next/link";
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import { AuthShell } from "@/components/auth/auth-shell";
import { Field, TextInput } from "@/components/marketing/form-fields";
import { ApiRequestError } from "@/lib/api-client";
import { ROUTES } from "@/lib/constants";
import { getPendingVerificationEmail, setPendingVerificationEmail } from "@/lib/pending-verification";
import {
  isEmailVerificationDisabled,
  resendVerification,
  verifyEmail,
} from "@/services/auth";
import { isAuthenticated } from "@/lib/session";
import { validateForm, verificationResendSchema } from "@/lib/validation/auth";

type Status = "verifying" | "verified" | "expired" | "pending";

function EnvelopeIcon() {
  return (
    <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2.5" y="5" width="19" height="14" rx="2.5" />
      <path d="m3.5 7 8.5 6 8.5-6" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9.5" />
      <path d="m8.5 12.5 2.5 2.5 5-5.5" />
    </svg>
  );
}

function WarningIcon() {
  return (
    <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9.5" />
      <path d="M12 8v5" />
      <path d="M12 16.5h.01" />
    </svg>
  );
}

function VerifyEmailInner() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const justRegistered = searchParams.get("registered") === "1";

  const [status, setStatus] = useState<Status>(token ? "verifying" : "pending");
  const [verifyError, setVerifyError] = useState<string | null>(null);
  // Prefill the resend form with the just-registered address, if any.
  // In-memory only; never persisted, never logged.
  const [email, setEmail] = useState(() => getPendingVerificationEmail() ?? "");
  const [emailError, setEmailError] = useState<string | undefined>(undefined);
  const [resending, setResending] = useState(false);
  const [resendSent, setResendSent] = useState(false);
  const [resendDisabled, setResendDisabled] = useState(false);
  const [resendError, setResendError] = useState<string | null>(null);

  // The token is single-use; guard against double-invocation in StrictMode.
  const started = useRef(false);
  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;
    verifyEmail(token)
      .then(() => {
        setPendingVerificationEmail(null);
        setStatus("verified");
      })
      .catch((err) => {
        setVerifyError(
          err instanceof ApiRequestError
            ? err.message
            : "This verification link is invalid or has expired."
        );
        setStatus("expired");
      });
  }, [token]);

  async function handleResend(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (resending) return;
    const errors = validateForm(verificationResendSchema, { email });
    setEmailError(errors.email);
    if (errors.email) return;

    setResending(true);
    setResendError(null);
    try {
      const result = await resendVerification(email.trim());
      if (isEmailVerificationDisabled(result.detail)) {
        setResendDisabled(true);
      } else {
        setResendSent(true);
      }
    } catch (err) {
      // Enumeration-safe: a transport failure shows a neutral message, never
      // an account-existence signal.
      setResendError(
        err instanceof ApiRequestError ? err.message : "Unable to send the email. Please try again."
      );
    } finally {
      setResending(false);
    }
  }

  return (
    <AuthShell>
      {status === "verifying" ? (
        <div className="flex flex-col items-center py-6 text-center">
          <span className="h-8 w-8 animate-spin rounded-full border-2 border-line border-t-silver" aria-hidden="true" />
          <h1 className="mt-4 font-display text-xl font-semibold text-off-white">
            Verifying your email address…
          </h1>
        </div>
      ) : null}

      {status === "verified" ? (
        <div className="flex flex-col items-center text-center">
          <span className="text-success">
            <CheckIcon />
          </span>
          <h1 className="mt-4 font-display text-2xl font-semibold tracking-tight text-off-white">
            Email verified
          </h1>
          <p className="mt-1 text-sm text-soft-gray">
            Your email address is confirmed. You can continue to your workspace.
          </p>
          <Link
            href={isAuthenticated() ? ROUTES.dashboard : ROUTES.login}
            className="mt-6 w-full rounded-lg bg-off-white px-4 py-3 text-center text-sm font-semibold text-obsidian transition-colors hover:bg-white focus:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver"
          >
            Continue
          </Link>
        </div>
      ) : null}

      {status === "expired" ? (
        <div className="flex flex-col items-center text-center">
          <span className="text-danger">
            <WarningIcon />
          </span>
          <h1 className="mt-4 font-display text-2xl font-semibold tracking-tight text-off-white">
            Link expired
          </h1>
          <p className="mt-1 text-sm text-soft-gray">
            {verifyError ??
              "This verification link is no longer valid. Request a new one to continue."}
          </p>
          <ResendForm
            email={email}
            setEmail={setEmail}
            error={emailError}
            resending={resending}
            resendSent={resendSent}
            resendDisabled={resendDisabled}
            resendError={resendError}
            onSubmit={handleResend}
            primaryLabel="Send a new link"
          />
        </div>
      ) : null}

      {status === "pending" ? (
        <div className="flex flex-col items-center text-center">
          <span className="text-soft-gray">
            <EnvelopeIcon />
          </span>
          <h1 className="mt-4 font-display text-2xl font-semibold tracking-tight text-off-white">
            Verify Your Email
          </h1>
          <p className="mt-1 text-sm text-soft-gray">
            {justRegistered
              ? email
                ? `Your workspace is ready. We sent a verification link to ${email} — open it to activate your account.`
                : "Your workspace is ready. Check your inbox for a verification link — open it to activate your account."
              : "We sent a verification link to your email. Open it to activate your account."}
          </p>
          <ResendForm
            email={email}
            setEmail={setEmail}
            error={emailError}
            resending={resending}
            resendSent={resendSent}
            resendDisabled={resendDisabled}
            resendError={resendError}
            onSubmit={handleResend}
            primaryLabel="Resend verification email"
          />
          <p className="mt-4 text-xs text-muted">
            If resend is enabled, the response is the same whether or not an account exists.
          </p>
        </div>
      ) : null}

      <p className="mt-6 text-center text-sm text-muted">
        <Link
          href={ROUTES.login}
          className="underline-offset-2 transition-colors hover:text-silver hover:underline focus:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver"
        >
          Back to sign in
        </Link>
      </p>
    </AuthShell>
  );
}

interface ResendFormProps {
  email: string;
  setEmail: (value: string) => void;
  error: string | undefined;
  resending: boolean;
  resendSent: boolean;
  resendDisabled: boolean;
  resendError: string | null;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  primaryLabel: string;
}

function ResendForm({
  email,
  setEmail,
  error,
  resending,
  resendSent,
  resendDisabled,
  resendError,
  onSubmit,
  primaryLabel,
}: ResendFormProps) {
  if (resendDisabled) {
    return (
      <p className="mt-6 w-full rounded-lg border border-line bg-elevated px-4 py-3 text-sm text-soft-gray">
        Email verification is not enabled for this environment. You can keep using AgencyOS once
        you sign in.
      </p>
    );
  }
  if (resendSent) {
    return (
      <p role="status" className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg border border-success/40 bg-success/10 px-4 py-3 text-sm text-success">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="m4.5 12.5 5 5L19.5 7" />
        </svg>
        If an account exists and is unverified, we&apos;ve sent a new link.
      </p>
    );
  }
  return (
    <form onSubmit={onSubmit} noValidate className="mt-6 flex w-full flex-col gap-3">
      <Field label="Business email" id="resend_email" error={error} className="text-left">
        <TextInput
          id="resend_email"
          type="email"
          autoComplete="email"
          autoCapitalize="none"
          spellCheck={false}
          placeholder="you@company.com"
          invalid={Boolean(error)}
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </Field>
      {resendError ? (
        <p role="alert" className="text-sm text-danger">
          {resendError}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={resending}
        className="w-full rounded-lg bg-off-white px-4 py-3 text-sm font-semibold text-obsidian transition-colors hover:bg-white focus:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver disabled:cursor-not-allowed disabled:opacity-60"
      >
        {resending ? "Sending…" : primaryLabel}
      </button>
    </form>
  );
}

function VerifyEmailFallback() {
  return (
    <AuthShell>
      <div className="flex flex-col items-center py-8 text-center" role="status" aria-label="Loading the verification screen">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-line border-t-silver" aria-hidden="true" />
        <p className="mt-4 text-sm text-soft-gray">Loading…</p>
      </div>
    </AuthShell>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<VerifyEmailFallback />}>
      <VerifyEmailInner />
    </Suspense>
  );
}
