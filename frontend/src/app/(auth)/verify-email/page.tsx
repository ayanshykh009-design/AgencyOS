// Email-verification landing page: consumes the token from the emailed link.
"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import { ApiRequestError } from "@/lib/api-client";
import { ROUTES } from "@/lib/constants";
import { verifyEmail } from "@/services/auth";

type Status = "verifying" | "verified" | "failed";

function VerifyEmailInner() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<Status>(token ? "verifying" : "failed");
  const [error, setError] = useState<string | null>(token ? null : "Missing verification link");
  // The token is single-use; guard against double-invocation in StrictMode.
  const started = useRef(false);

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;
    verifyEmail(token)
      .then(() => setStatus("verified"))
      .catch((err) => {
        setError(
          err instanceof ApiRequestError
            ? err.message
            : "Unable to verify your email. Please try again."
        );
        setStatus("failed");
      });
  }, [token]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm rounded-lg border bg-white p-8 shadow-sm">
        <h1 className="text-xl font-semibold">AgencyOS</h1>
        <p className="mt-1 text-sm text-gray-500">Email verification</p>

        {status === "verifying" ? (
          <p className="mt-6 text-sm text-gray-600">Verifying your email address…</p>
        ) : null}

        {status === "verified" ? (
          <div className="mt-6">
            <p className="text-sm text-green-700">Your email is confirmed. You can sign in now.</p>
            <a
              href={ROUTES.login}
              className="mt-6 block rounded-md bg-black px-4 py-2 text-center text-sm font-medium text-white hover:bg-gray-800"
            >
              Continue to sign in
            </a>
          </div>
        ) : null}

        {status === "failed" ? (
          <div className="mt-6">
            <p role="alert" className="text-sm text-red-600">
              {error ?? "This verification link is invalid or has expired."}
            </p>
            <p className="mt-3 text-sm text-gray-500">
              Sign in and request a new link from your account settings.
            </p>
            <a
              href={ROUTES.login}
              className="mt-6 block rounded-md border border-gray-300 bg-white px-4 py-2 text-center text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Back to sign in
            </a>
          </div>
        ) : null}
      </div>
    </main>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailInner />
    </Suspense>
  );
}
