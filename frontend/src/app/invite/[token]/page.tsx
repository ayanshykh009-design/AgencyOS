// Invite acceptance page: resolve a one-time token and create the account.
// This route is intentionally public (no session) — the invitee has no
// account yet. Backend contract (app/api/v1/endpoints/teams.py):
//   GET  /teams/public/{token}  → { email, full_name, role, organization_name }
//   POST /teams/accept          → { token, full_name, password }
"use client";

import { useEffect, use, useState } from "react";
import Link from "next/link";

import { Button, Field, Input, Spinner } from "@/components/ui";
import { ApiRequestError } from "@/lib/api-client";
import { ROUTES } from "@/lib/constants";
import { acceptInvite, lookupInvite, type InviteLookup } from "@/services/teams";

type Phase = "loading" | "error" | "form" | "success";

export function inviteError(err: unknown): string {
  if (err instanceof ApiRequestError) {
    switch (err.code) {
      case "team.invite_expired":
        return "This invite has expired. Ask your admin to send a new one.";
      case "team.invite_invalid":
        return err.message;
      case "team.user_exists":
        return "An account with that email already exists. Sign in or contact your admin.";
      case "network.error":
        return "Unable to reach the API. Please try again.";
      default:
        return err.message;
    }
  }
  return "Something went wrong. Please try again.";
}

export default function InviteAcceptPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);

  const [phase, setPhase] = useState<Phase>("loading");
  const [invite, setInvite] = useState<InviteLookup | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);

  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{
    full_name?: string;
    password?: string;
    confirm?: string;
  }>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    lookupInvite(token)
      .then((lookup) => {
        if (cancelled) return;
        setInvite(lookup);
        setFullName(lookup.full_name ?? "");
        setPhase("form");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLookupError(inviteError(err));
        setPhase("error");
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;

    const errors: typeof fieldErrors = {};
    if (!fullName.trim()) errors.full_name = "Full name is required";
    if (password.length < 8) errors.password = "Password must be at least 8 characters";
    if (confirmPassword !== password) errors.confirm = "Passwords do not match";
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSubmitError(null);
    setSubmitting(true);
    try {
      await acceptInvite({
        token,
        full_name: fullName.trim(),
        password,
      });
      setPhase("success");
    } catch (err) {
      setSubmitError(inviteError(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (phase === "loading") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
        <Spinner label="Checking invite…" />
      </main>
    );
  }

  if (phase === "error") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
        <div className="w-full max-w-sm rounded-lg border bg-white p-8 text-center shadow-sm">
          <h1 className="text-xl font-semibold">Invite unavailable</h1>
          <p role="alert" className="mt-2 text-sm text-gray-500">
            {lookupError}
          </p>
          <Link
            href={ROUTES.home}
            className="mt-6 inline-block text-sm font-medium text-gray-900 underline underline-offset-4"
          >
            Back to home
          </Link>
        </div>
      </main>
    );
  }

  if (phase === "success") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
        <div className="w-full max-w-sm rounded-lg border bg-white p-8 text-center shadow-sm">
          <h1 className="text-xl font-semibold">Welcome to AgencyOS</h1>
          <p className="mt-2 text-sm text-gray-500">
            Your account is ready. Sign in to start working in{" "}
            {invite?.organization_name ?? "your workspace"}.
          </p>
          <Link href={ROUTES.login} className="mt-6 inline-block">
            <Button>Sign in</Button>
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm rounded-lg border bg-white p-8 shadow-sm">
        <h1 className="text-xl font-semibold">Join AgencyOS</h1>
        {invite?.organization_name ? (
          <p className="mt-1 text-sm text-gray-500">{invite.organization_name} invited you</p>
        ) : null}

        <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
          <Field label="Email" htmlFor="invite-email">
            <Input id="invite-email" type="email" value={invite?.email ?? ""} readOnly disabled />
          </Field>

          <Field
            label="Full name"
            htmlFor="invite-full-name"
            required
            error={fieldErrors.full_name}
          >
            <Input
              id="invite-full-name"
              type="text"
              autoComplete="name"
              invalid={Boolean(fieldErrors.full_name)}
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Jane Smith"
            />
          </Field>

          <Field
            label="Password"
            htmlFor="invite-password"
            required
            error={fieldErrors.password}
            hint="At least 8 characters"
          >
            <Input
              id="invite-password"
              type="password"
              autoComplete="new-password"
              invalid={Boolean(fieldErrors.password)}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>

          <Field
            label="Confirm password"
            htmlFor="invite-confirm-password"
            required
            error={fieldErrors.confirm}
          >
            <Input
              id="invite-confirm-password"
              type="password"
              autoComplete="new-password"
              invalid={Boolean(fieldErrors.confirm)}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
          </Field>

          {submitError ? (
            <p role="alert" className="text-sm text-red-600">
              {submitError}
            </p>
          ) : null}

          <Button type="submit" disabled={submitting} className="mt-2">
            {submitting ? "Creating your account…" : "Create account"}
          </Button>
        </form>
      </div>
    </main>
  );
}
