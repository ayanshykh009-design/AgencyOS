# Authentication

First-party session endpoints: registration, login, refresh, logout, and the
account-security flows added in the authentication hardening pass (email
verification, password reset, TOTP two-factor authentication).

All password hashing is Argon2id; access tokens are JWTs carrying a `tv`
(token-version) claim enforced server-side, and refresh tokens are opaque,
rotated, and grouped into reuse-detection families. Unless noted, endpoints
return the standard error envelope `{"error": {"code", "message", "details"?}}`.

## POST /api/v1/auth/register

Create an organization + owner account and return a session. When
`EMAIL_VERIFICATION_ENABLED` is on, the response sets
`email_verification_required: true` and a verification email is sent.

| Status | Body           | Meaning                     |
| ------ | -------------- | --------------------------- |
| `201`  | `AuthResponse` | Org + owner created         |
| `409`  | error envelope | Email or slug already taken |

## POST /api/v1/auth/login

Authenticate with email + password. Failures are throttled per-account
(`auth.too_many_attempts`, `429` with `Retry-After`) and timed to resist
account-enumeration. A correct password always succeeds.

| Status | Body           | Meaning                                             |
| ------ | -------------- | --------------------------------------------------- |
| `200`  | `AuthResponse` | Session issued                                      |
| `401`  | error envelope | `auth.invalid_credentials`                          |
| `403`  | error envelope | `auth.email_verification_required` (flag on, unverified) |
| `401`  | error envelope | `auth.mfa_required` with `details.mfa_token` (second factor needed) |

When `auth.mfa_required` is returned, submit the challenge to
`POST /auth/mfa/verify` (below) to finish the login.

## POST /api/v1/auth/refresh

Exchange a refresh token for a new pair (rotation). Replaying a rotated token
is treated as theft: the whole token family is revoked and the user's
`token_version` is bumped (`auth.refresh_token_reuse`, `401`), invalidating
outstanding access tokens.

## POST /api/v1/auth/logout

Revoke every outstanding refresh token and bump the access-token version
(sign out of all devices). Requires a session.

## GET /api/v1/auth/me

Return the authenticated user (`UserRead`).

## POST /api/v1/auth/change-password

Verify the current password, set a new one, and revoke all sessions. Requires
a session. `400 auth.wrong_password` on a bad current password.

## Email verification

Opt-in per deployment (`EMAIL_VERIFICATION_ENABLED`). Tokens are single-use,
hashed at rest (`auth_tokens`), and short-lived.

### POST /api/v1/auth/verify-email

Consume a verification token and mark the account verified. Pre-authentication.

| Status | Body | Meaning                                   |
| ------ | ---- | ----------------------------------------- |
| `204`  | —    | Email confirmed                           |
| `400`  | error envelope | `auth.invalid_verification_token` |

### POST /api/v1/auth/verify-email/resend

Pre-authentication resend: send a fresh verification link for an email
address. The body is `{"email": "..."}`; no session is required, so users
blocked by the verification gate can still request a new link. Any previous
token is invalidated. Enumeration-safe: always `202 MessageResponse` whether
or not the account exists, is already verified, or verification is enabled.
Rate-limited (`RATE_LIMIT_STRICT`).

A per-address cooldown (`EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS`) allows at
most one attempt per normalized address per window. It must be at least 60
seconds in every deployed environment (staging, QA, production); only explicit
development/test environments may set 0 to disable it. It is
enforced with an atomic `SET NX EX` against the shared Redis store and applies
before the account lookup, so unknown, verified, inactive and eligible
addresses consume the window identically. A suppressed request invalidates no
token, sends no email, and returns the same generic `202` body as any other
non-delivering resend. If the shared store is unavailable the endpoint fails
closed: it reports success generically but performs no resend. The Redis key is
a keyed HMAC digest of the normalized address — raw addresses are never stored.

The `dev_url` field (verification and password-reset responses) carries a raw
single-use link only in explicitly local `development`/`test` environments. In
every deployed environment — including `staging` — it is `null`, and a deployed
process refuses to boot without `REDIS_URL`, since the per-address cooldown and
the IP rate limiter both require shared state.

## Password reset

`PASSWORD_RESET_ENABLED` (default on). Reset is enumeration-safe: the request
endpoint always returns `202` whether or not the account exists. Completing a
reset revokes every existing session.

### POST /api/v1/auth/password-reset/request

| Status | Body              | Meaning                                  |
| ------ | ----------------- | ---------------------------------------- |
| `202`  | `MessageResponse` | Always; email sent only if the account exists |

### POST /api/v1/auth/password-reset/confirm

Set a new password with the emailed token and sign out all sessions.
Pre-authentication.

| Status | Body | Meaning                              |
| ------ | ---- | ------------------------------------ |
| `204`  | —    | Password updated, sessions revoked   |
| `400`  | error envelope | `auth.invalid_reset_token`    |

## Two-factor authentication (TOTP)

`MFA_ENABLED` (default off). Enrollment is two-step: `enroll` stores a *pending*
secret, and `activate` verifies a code before enabling MFA and issuing one-time
recovery codes (shown once, Argon2-hashed at rest).

| Endpoint                        | Auth  | Purpose                                        |
| ------------------------------- | ----- | ---------------------------------------------- |
| `POST /auth/mfa/enroll`         | Bearer| Start enrollment; returns `secret` + `otpauth_url` |
| `POST /auth/mfa/activate`       | Bearer| Confirm with a code; enables MFA, returns `recovery_codes` |
| `POST /auth/mfa/disable`        | Bearer| Turn off MFA after verifying a factor          |
| `POST /auth/mfa/verify`         | none  | Complete a MFA-gated login; returns `AuthResponse` |

The login challenge (`auth.mfa_required.details.mfa_token`) is a short-lived JWT
carrying `scope: "mfa"`; the API auth guard rejects that scope, so a challenge
token can never be used as an access token. `404 auth.mfa_unavailable` when the
feature is off.

| Error                          | Meaning                                         |
| ------------------------------ | ----------------------------------------------- |
| `401 auth.invalid_mfa_code`    | Bad TOTP / recovery code                        |
| `401 auth.invalid_mfa_token`   | Bad or expired MFA challenge                    |
| `429 auth.mfa_locked`          | Too many wrong codes (with `Retry-After`)       |
| `409 auth.mfa_already_enabled` | Enroll/activate while MFA is already on         |
| `409 auth.mfa_not_enrolled`    | Activate without a pending secret               |
| `409 auth.mfa_not_enabled`     | Disable while MFA is off                        |

## Configuration

Account-security behavior is driven by env vars (see `backend/.env.example`
and `app/core/config.py`): `EMAIL_VERIFICATION_ENABLED`,
`EMAIL_VERIFICATION_TOKEN_TTL_MINUTES`, `PASSWORD_RESET_ENABLED`,
`PASSWORD_RESET_TOKEN_TTL_MINUTES`, `MFA_ENABLED`, `MFA_ISSUER`,
`MFA_CHALLENGE_TTL_MINUTES`, `MFA_MAX_ATTEMPTS`, and the `SMTP_*` block.
Production validation fails to boot if a mail-dependent feature is enabled
without `SMTP_HOST`/`SMTP_FROM_EMAIL`.
