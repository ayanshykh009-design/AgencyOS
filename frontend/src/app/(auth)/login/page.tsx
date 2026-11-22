// Login page: authenticate with email + password and enter the dashboard.
// Dark-first Core Orbit identity (Sheet 1). Social sign-in and "Remember me"
// from the artwork are intentionally not rendered: there is no OAuth backend
// and the session model is in-memory access token + HttpOnly refresh cookie.
"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";

import { AuthShell } from "@/components/auth/auth-shell";
import { PasswordInput } from "@/components/auth/password-input";
import { Field, TextInput } from "@/components/marketing/form-fields";
import { ApiRequestError } from "@/lib/api-client";
import { ROUTES } from "@/lib/constants";
import { loginSchema, validateForm, type FormErrors } from "@/lib/validation/auth";
import { login, mfaTokenFromError } from "@/services/auth";

export default function LoginPage() {
  const router = useRouter();
  const [values, setValues] = useState({ email: "", password: "" });
  const [fieldErrors, setFieldErrors] = useState<FormErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [verificationRequired, setVerificationRequired] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  function setField(field: "email" | "password") {
    return (event: React.ChangeEvent<HTMLInputElement>) => {
      const value = event.target.value;
      setValues((current) => ({ ...current, [field]: value }));
      if (fieldErrors[field]) {
        setFieldErrors((current) => ({ ...current, [field]: undefined }));
      }
    };
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    const errors = validateForm(loginSchema, values);
    setFieldErrors(errors);
    setError(null);
    setVerificationRequired(false);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    try {
      await login(values);
      router.replace(ROUTES.dashboard);
      router.refresh();
    } catch (err) {
      // A second factor is required: hand off to the challenge screen.
      const mfaToken = mfaTokenFromError(err);
      if (mfaToken) {
        router.push(`${ROUTES.mfa}?token=${encodeURIComponent(mfaToken)}`);
        return;
      }
      if (err instanceof ApiRequestError && err.code === "auth.email_verification_required") {
        setVerificationRequired(true);
        setError("Confirm your email address before signing in.");
      } else {
        setError(
          err instanceof ApiRequestError ? err.message : "Unable to log in. Please try again."
        );
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell>
      <h1 className="font-display text-2xl font-semibold tracking-tight text-off-white">
        Welcome back
      </h1>
      <p className="mt-1 text-sm text-soft-gray">Sign in to continue to AgencyOS</p>

      <form onSubmit={handleSubmit} noValidate className="mt-6 flex flex-col gap-4">
        <Field label="Email address" id="email" error={fieldErrors.email}>
          <TextInput
            id="email"
            type="email"
            invalid={Boolean(fieldErrors.email)}
            autoComplete="email"
            autoCapitalize="none"
            spellCheck={false}
            placeholder="you@company.com"
            value={values.email}
            onChange={setField("email")}
          />
        </Field>

        <Field label="Password" id="password" error={fieldErrors.password}>
          <PasswordInput
            id="password"
            invalid={Boolean(fieldErrors.password)}
            autoComplete="current-password"
            placeholder="Your password"
            value={values.password}
            onChange={setField("password")}
          />
        </Field>

        <div className="flex justify-end">
          <Link
            href={ROUTES.forgotPassword}
            className="text-xs text-soft-gray underline-offset-2 transition-colors hover:text-off-white hover:underline focus:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver"
          >
            Forgot password?
          </Link>
        </div>

        {error ? (
          <div role="alert" className="text-sm text-danger">
            <p>{error}</p>
            {verificationRequired ? (
              <Link
                href={ROUTES.verifyEmail}
                className="mt-1 inline-block text-silver underline underline-offset-2 hover:text-off-white"
              >
                Verify your email
              </Link>
            ) : null}
          </div>
        ) : null}

        <button
          type="submit"
          disabled={submitting}
          className="mt-1 w-full rounded-lg bg-off-white px-4 py-3 text-sm font-semibold text-obsidian transition-colors hover:bg-white focus:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Signing in…" : "Sign In"}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-soft-gray">
        Don&apos;t have an account?{" "}
        <Link
          href={ROUTES.signup}
          className="font-medium text-off-white underline-offset-2 transition-colors hover:underline focus:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver"
        >
          Create one
        </Link>
      </p>
    </AuthShell>
  );
}
