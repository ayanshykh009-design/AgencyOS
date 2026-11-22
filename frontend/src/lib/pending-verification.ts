// Holds the email address captured at signup while email verification is
// pending. In-memory only (module singleton): it is never written to
// storage, URLs or logs, survives client-side navigation within the session,
// and is cleared on successful verification, sign-out, or an explicit reset.
// Reloading the page loses it by design — the verify-email screen then
// renders a blank, editable email field instead.
let pendingEmail: string | null = null;

export function setPendingVerificationEmail(email: string | null): void {
  pendingEmail = email && email.trim() ? email.trim() : null;
}

export function getPendingVerificationEmail(): string | null {
  return pendingEmail;
}
