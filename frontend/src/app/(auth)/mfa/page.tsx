// MFA challenge: complete a second factor (TOTP authenticator code, or a
// single-use recovery code) after a password login. Recovery codes are only
// supported because the backend issues and accepts them at activation; the
// page does not manage or invent any other recovery flow.
"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AuthShell } from "@/components/auth/auth-shell";
import { CodeBoxes } from "@/components/auth/code-boxes";
import { CoreOrbit } from "@/components/marketing/core-orbit";
import { Field, TextInput } from "@/components/marketing/form-fields";
import { ApiRequestError } from "@/lib/api-client";
import { ROUTES } from "@/lib/constants";
import { mfaVerify } from "@/services/auth";

type Mode = "totp" | "recovery";

function MfaChallengeInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const mfaToken = searchParams.get("token");

  const [mode, setMode] = useState<Mode>("totp");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(mfaToken ? null : "Missing challenge");
  const [invalidCode, setInvalidCode] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const ready =
    mfaToken !== null && (mode === "totp" ? /^\d{6}$/.test(code) : code.trim().length > 0);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting || !mfaToken || !ready) return;
    setError(null);
    setInvalidCode(false);
    setSubmitting(true);
    try {
      await mfaVerify(mfaToken, code.trim());
      router.replace(ROUTES.dashboard);
      router.refresh();
    } catch (err) {
      if (err instanceof ApiRequestError) {
        if (err.code === "auth.invalid_mfa_code") {
          // Backend rejected the factor; mark the boxes red (screen 09).
          setInvalidCode(true);
          setError("That code did not work. Try again.");
        } else {
          setError(err.message);
        }
      } else {
        setError("Unable to verify the code. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  function switchMode(next: Mode) {
    setMode(next);
    setCode("");
    setError(null);
    setInvalidCode(false);
  }

  return (
    <AuthShell>
      <div className="flex flex-col items-center text-center">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-info/40 bg-info/10 px-3 py-1 text-[11px] font-medium text-info">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          Authenticator (TOTP) only
        </span>

        <CoreOrbit size={56} className="mt-4" />
        <h1 className="mt-4 font-display text-2xl font-semibold tracking-tight text-off-white">
          Verify Your Identity
        </h1>
        <p className="mt-1 text-sm text-soft-gray">
          {mode === "totp"
            ? "Enter the 6-digit code from your authenticator app."
            : "Enter one of your single-use recovery codes."}
        </p>
      </div>

      <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4" noValidate>
        {mode === "totp" ? (
          <CodeBoxes
            value={code}
            onChange={(next) => {
              setCode(next);
              setInvalidCode(false);
              if (error) setError(null);
            }}
            invalid={invalidCode}
            disabled={submitting}
            autoFocus
            aria-label="Six-digit authenticator code"
          />
        ) : (
          <Field label="Recovery code" id="recovery_code">
            <TextInput
              id="recovery_code"
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              placeholder="xxxx-xxxx-xxxx"
              value={code}
              onChange={(event) => {
                setCode(event.target.value);
                setInvalidCode(false);
                if (error) setError(null);
              }}
              className="font-mono"
            />
          </Field>
        )}

        {error ? (
          <p role="alert" className="text-center text-sm text-danger">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={submitting || !ready}
          className="w-full rounded-lg bg-off-white px-4 py-3 text-sm font-semibold text-obsidian transition-colors hover:bg-white focus:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Verifying…" : "Verify"}
        </button>

        <button
          type="button"
          onClick={() => switchMode(mode === "totp" ? "recovery" : "totp")}
          className="mx-auto text-xs text-muted underline-offset-2 transition-colors hover:text-silver hover:underline focus:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver"
        >
          {mode === "totp" ? "Use a recovery code instead" : "Use your authenticator app instead"}
        </button>
      </form>

      <p className="mt-5 text-center text-sm text-muted">
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

function MfaFallback() {
  return (
    <AuthShell>
      <div className="flex flex-col items-center py-8 text-center" role="status" aria-label="Loading the challenge screen">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-line border-t-silver" aria-hidden="true" />
        <p className="mt-4 text-sm text-soft-gray">Loading…</p>
      </div>
    </AuthShell>
  );
}

export default function MfaChallengePage() {
  return (
    <Suspense fallback={<MfaFallback />}>
      <MfaChallengeInner />
    </Suspense>
  );
}
