// MFA challenge: complete a second-factor (TOTP or recovery code) after login.
"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/lib/api-client";
import { ROUTES } from "@/lib/constants";
import { mfaVerify } from "@/services/auth";

function MfaChallengeInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const mfaToken = searchParams.get("token");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(mfaToken ? null : "Missing challenge");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting || !mfaToken) return;
    setError(null);
    setSubmitting(true);
    try {
      await mfaVerify(mfaToken, code);
      router.replace(ROUTES.dashboard);
      router.refresh();
    } catch (err) {
      setError(
        err instanceof ApiRequestError
          ? err.message
          : "Unable to verify the code. Please try again."
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm rounded-lg border bg-white p-8 shadow-sm">
        <h1 className="text-xl font-semibold">AgencyOS</h1>
        <p className="mt-1 text-sm text-gray-500">
          Enter the 6-digit code from your authenticator app, or a recovery code.
        </p>

        <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
          <label className="flex flex-col gap-1 text-sm">
            Authentication code
            <input
              type="text"
              required
              autoComplete="one-time-code"
              inputMode="numeric"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black"
            />
          </label>

          {error ? (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          ) : null}

          <Button type="submit" disabled={submitting || !mfaToken} className="mt-2">
            {submitting ? "Verifying…" : "Verify"}
          </Button>
        </form>

        <p className="mt-4 text-center text-sm">
          <a href={ROUTES.login} className="text-gray-500 hover:underline">
            Back to sign in
          </a>
        </p>
      </div>
    </main>
  );
}

export default function MfaChallengePage() {
  return (
    <Suspense fallback={null}>
      <MfaChallengeInner />
    </Suspense>
  );
}
