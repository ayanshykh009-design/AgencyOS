// Password-reset request page: always reports success (enumeration-safe).
"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ROUTES } from "@/lib/constants";
import { requestPasswordReset } from "@/services/auth";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [devUrl, setDevUrl] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    try {
      const result = await requestPasswordReset(email);
      setDevUrl(result.dev_url ?? null);
      setSent(true);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm rounded-lg border bg-white p-8 shadow-sm">
        <h1 className="text-xl font-semibold">AgencyOS</h1>
        <p className="mt-1 text-sm text-gray-500">Reset your password</p>

        {sent ? (
          <div className="mt-6">
            <p className="text-sm text-gray-600">
              If an account exists for that address, a reset link has been sent.
            </p>
            {devUrl ? (
              <p className="mt-3 break-all rounded-md bg-gray-50 p-2 text-xs text-gray-500">
                Dev link: <a href={devUrl}>{devUrl}</a>
              </p>
            ) : null}
            <a
              href={ROUTES.login}
              className="mt-6 block rounded-md border border-gray-300 bg-white px-4 py-2 text-center text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Back to sign in
            </a>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
            <label className="flex flex-col gap-1 text-sm">
              Email
              <input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black"
              />
            </label>

            <Button type="submit" disabled={submitting} className="mt-2">
              {submitting ? "Sending…" : "Send reset link"}
            </Button>
          </form>
        )}
      </div>
    </main>
  );
}
