// Security settings: manage TOTP two-factor authentication for the account.
"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/lib/api-client";
import { mfaActivate, mfaDisable, mfaEnroll } from "@/services/auth";

type Phase = "idle" | "enrolling" | "active" | "disabling";

export default function SecuritySettingsPage() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [secret, setSecret] = useState<string | null>(null);
  const [otpauthUri, setOtpauthUri] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleEnroll() {
    setBusy(true);
    setError(null);
    try {
      const result = await mfaEnroll();
      setSecret(result.secret);
      setOtpauthUri(result.otpauth_url);
      setPhase("enrolling");
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Unable to start enrollment.");
    } finally {
      setBusy(false);
    }
  }

  async function handleActivate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await mfaActivate(code);
      setRecoveryCodes(result.recovery_codes);
      setPhase("active");
      setCode("");
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Invalid code. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDisable(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await mfaDisable(code);
      setPhase("idle");
      setSecret(null);
      setOtpauthUri(null);
      setRecoveryCodes(null);
      setCode("");
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Invalid code. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg">
      <h1 className="text-xl font-semibold">Security</h1>
      <p className="mt-1 text-sm text-gray-500">
        Protect your account with two-factor authentication (TOTP).
      </p>

      <div className="mt-6 rounded-lg border bg-white p-6 shadow-sm">
        {phase === "idle" ? (
          <div>
            <p className="text-sm text-gray-600">
              Two-factor authentication is currently off. When enabled you will need a code from
              your authenticator app each time you sign in.
            </p>
            <Button onClick={handleEnroll} disabled={busy} className="mt-4">
              {busy ? "Starting…" : "Enable two-factor"}
            </Button>
          </div>
        ) : null}

        {phase === "enrolling" ? (
          <div>
            <p className="text-sm text-gray-600">
              Scan this secret into your authenticator app, then confirm with a code.
            </p>
            <p className="mt-3 break-all rounded-md bg-gray-50 p-3 font-mono text-xs">{secret}</p>
            {otpauthUri ? (
              <p className="mt-2 break-all text-xs text-gray-500">{otpauthUri}</p>
            ) : null}
            <form onSubmit={handleActivate} className="mt-4 flex flex-col gap-3">
              <input
                type="text"
                required
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="6-digit code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black"
              />
              <Button type="submit" disabled={busy}>
                {busy ? "Confirming…" : "Confirm and enable"}
              </Button>
            </form>
          </div>
        ) : null}

        {phase === "active" && recoveryCodes ? (
          <div>
            <p className="text-sm text-green-700">Two-factor authentication is on.</p>
            <p className="mt-3 text-sm text-gray-600">
              Save these recovery codes somewhere safe. Each works once if you lose access to your
              authenticator app. They are shown only now.
            </p>
            <ul className="mt-3 grid grid-cols-2 gap-1 rounded-md bg-gray-50 p-3 font-mono text-sm">
              {recoveryCodes.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
            <Button variant="outline" className="mt-4" onClick={() => setPhase("disabling")}>
              Disable two-factor
            </Button>
          </div>
        ) : null}

        {phase === "disabling" ? (
          <form onSubmit={handleDisable} className="flex flex-col gap-3">
            <p className="text-sm text-gray-600">
              Enter a current code or a recovery code to turn off two-factor authentication.
            </p>
            <input
              type="text"
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black"
            />
            <div className="flex gap-2">
              <Button type="submit" variant="danger" disabled={busy}>
                {busy ? "Disabling…" : "Disable"}
              </Button>
              <Button type="button" variant="outline" onClick={() => setPhase("active")}>
                Cancel
              </Button>
            </div>
          </form>
        ) : null}

        {error ? (
          <p role="alert" className="mt-4 text-sm text-red-600">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}
