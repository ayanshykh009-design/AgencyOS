// Password-reset request page (Sheet 2A screen 11). Always shows the same
// neutral confirmation — the backend never reveals whether an account exists,
// and neither does this page. A neutral disabled state is shown only when the
// backend reports that password reset is disabled for the environment.
// The actual reset confirmation page (/reset-password) is a separate batch.
"use client";

import Link from "next/link";
import { useState } from "react";

import { AuthShell } from "@/components/auth/auth-shell";
import { CoreOrbit } from "@/components/marketing/core-orbit";
import { Field, TextInput } from "@/components/marketing/form-fields";
import { ApiRequestError } from "@/lib/api-client";
import { ROUTES } from "@/lib/constants";
import { isPasswordResetDisabled, requestPasswordReset } from "@/services/auth";
import { validateForm, passwordResetRequestSchema } from "@/lib/validation/auth";

type Status = "form" | "confirmation" | "disabled";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [fieldError, setFieldError] = useState<string | undefined>(undefined);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<Status>("form");
  const [devUrl, setDevUrl] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    const errors = validateForm(passwordResetRequestSchema, { email });
    setFieldError(errors.email);
    setFormError(null);
    if (errors.email) return;

    setSubmitting(true);
    try {
      const result = await requestPasswordReset(email.trim());
      if (isPasswordResetDisabled(result.detail)) {
        setStatus("disabled");
        return;
      }
      // Enumeration-safe: any other backend answer renders the same generic
      // confirmation; only the local dev link differs.
      setDevUrl(result.dev_url ?? null);
      setStatus("confirmation");
    } catch (err) {
      // A failure must never flip to the success state.
      setFormError(
        err instanceof ApiRequestError
          ? err.message
          : "Unable to send the reset email. Please try again."
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (status === "confirmation") {
    return (
      <AuthShell>
        <div className="flex flex-col items-center text-center">
          <CoreOrbit size={56} />
          <h1 className="mt-4 font-display text-2xl font-semibold tracking-tight text-off-white">
            Check your email
          </h1>
          <p className="mt-4 w-full rounded-lg border border-success/40 bg-success/10 px-4 py-4 text-sm leading-6 text-off-white">
            If an account exists for that address, a reset link is on its way.
          </p>
          <p className="mt-3 text-xs text-muted">
            The message is identical for every email, so addresses are never revealed.
          </p>
          {devUrl ? (
            <p className="mt-3 w-full break-all rounded-md bg-deep-graphite p-2 text-left font-mono text-[11px] text-muted">
              Dev link:{" "}
              <a href={devUrl} className="underline hover:text-silver">
                {devUrl}
              </a>
            </p>
          ) : null}
          <Link
            href={ROUTES.login}
            className="mt-6 w-full rounded-lg border border-line bg-elevated px-4 py-3 text-center text-sm font-medium text-off-white transition-colors hover:bg-graphite focus:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver"
          >
            Back to sign in
          </Link>
        </div>
      </AuthShell>
    );
  }

  if (status === "disabled") {
    return (
      <AuthShell>
        <div className="flex flex-col items-center text-center">
          <CoreOrbit size={56} />
          <h1 className="mt-4 font-display text-2xl font-semibold tracking-tight text-off-white">
            Reset unavailable
          </h1>
          <p className="mt-4 w-full rounded-lg border border-line bg-elevated px-4 py-4 text-sm leading-6 text-soft-gray">
            Password reset is not enabled for this environment. Contact your administrator, or
            sign in if you still have access.
          </p>
          <Link
            href={ROUTES.login}
            className="mt-6 w-full rounded-lg border border-line bg-elevated px-4 py-3 text-center text-sm font-medium text-off-white transition-colors hover:bg-graphite focus:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver"
          >
            Back to sign in
          </Link>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      <div className="flex flex-col items-center text-center">
        <CoreOrbit size={56} />
        <h1 className="mt-4 font-display text-2xl font-semibold tracking-tight text-off-white">
          Reset Your Password
        </h1>
        <p className="mt-1 text-sm text-soft-gray">We will email you a reset link.</p>
      </div>

      <form onSubmit={handleSubmit} noValidate className="mt-6 flex flex-col gap-4">
        <Field label="Business email" id="email" error={fieldError}>
          <TextInput
            id="email"
            type="email"
            autoComplete="email"
            autoCapitalize="none"
            spellCheck={false}
            placeholder="ayesha@northwind.example"
            invalid={Boolean(fieldError)}
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
              setFieldError(undefined);
            }}
          />
        </Field>

        {formError ? (
          <p role="alert" className="text-sm text-danger">
            {formError}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-off-white px-4 py-3 text-sm font-semibold text-obsidian transition-colors hover:bg-white focus:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Sending…" : "Send reset link"}
        </button>
      </form>

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
