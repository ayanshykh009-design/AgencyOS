// Client-side validation for the authentication screens.
// Constraints mirror the real backend schemas in backend/app/schemas/auth.py
// (password 8–128, names 1–255, slug ^[a-z0-9][a-z0-9-]*$ up to 63 chars) so
// the UI never invents stricter rules than the API enforces.

import { z } from "zod";

const REQUIRED_MESSAGE = "This field is required";
const EMAIL_MESSAGE = "Enter a full email address";
const PASSWORD_SHORT_MESSAGE = "Password must be at least 8 characters";
const PASSWORD_LONG_MESSAGE = "Password must be at most 128 characters";

const email = z.string().trim().min(1, REQUIRED_MESSAGE).email(EMAIL_MESSAGE).max(255);
const password = z
  .string()
  .min(8, PASSWORD_SHORT_MESSAGE)
  .max(128, PASSWORD_LONG_MESSAGE);

export const loginSchema = z.object({
  email,
  password,
});

export const SLUG_PATTERN = /^[a-z0-9][a-z0-9-]{0,62}$/;
const SLUG_MESSAGE = "Use lowercase letters, numbers and hyphens; start with a letter or number";

export const signupSchema = z
  .object({
    fullName: z.string().trim().min(1, REQUIRED_MESSAGE).max(255),
    email,
    password,
    confirmPassword: z.string().min(1, REQUIRED_MESSAGE),
    organizationName: z.string().trim().min(1, REQUIRED_MESSAGE).max(255),
    organizationSlug: z
      .string()
      .trim()
      .min(1, REQUIRED_MESSAGE)
      .max(63)
      .regex(SLUG_PATTERN, SLUG_MESSAGE),
    acceptTerms: z
      .boolean()
      .refine((value) => value, "You must agree to the Terms of Service and Privacy Policy"),
  })
  .superRefine((values, ctx) => {
    if (values.confirmPassword !== values.password) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["confirmPassword"],
        message: "Passwords do not match",
      });
    }
  });

/** Derive a backend-legal slug candidate from a workspace name. */
export function slugifyOrganization(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-")
    .slice(0, 63);
}

export const passwordResetRequestSchema = z.object({ email });

export const verificationResendSchema = z.object({ email });

/** Six-digit TOTP code from an authenticator app. */
export const totpCodeSchema = z
  .string()
  .trim()
  .regex(/^\d{6}$/, "Enter the 6-digit code from your authenticator app");

/** Recovery codes issued at MFA activation; opaque, single-use, up to 64 chars. */
export const recoveryCodeSchema = z
  .string()
  .trim()
  .min(1, "Enter a recovery code")
  .max(64, "Recovery codes are at most 64 characters");

export type LoginValues = z.infer<typeof loginSchema>;
export type SignupValues = z.infer<typeof signupSchema>;
export type FormErrors = Record<string, string | undefined>;

export function validateForm(schema: z.ZodTypeAny, values: unknown): FormErrors {
  const result = schema.safeParse(values);
  if (result.success) return {};
  const errors: FormErrors = {};
  for (const issue of result.error.issues) {
    const key = String(issue.path[0] ?? "");
    if (!(key in errors)) errors[key] = issue.message;
  }
  return errors;
}
