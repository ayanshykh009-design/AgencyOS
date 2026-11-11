// Signup page: create a new organization and its owner account (Sheet 2A
// screen 06). Founder-approved: public self-service signup, no invitation.
// Each registration creates an isolated organization with the registering
// user as OWNER — tenant isolation, rate limits and email verification are
// enforced by the backend, never by the client.
"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { AuthShell } from "@/components/auth/auth-shell";
import { PasswordInput } from "@/components/auth/password-input";
import { Field, TextInput } from "@/components/marketing/form-fields";
import { ApiRequestError } from "@/lib/api-client";
import { ROUTES } from "@/lib/constants";
import { setPendingVerificationEmail } from "@/lib/pending-verification";
import {
  signupSchema,
  slugifyOrganization,
  validateForm,
  type FormErrors,
} from "@/lib/validation/auth";
import { register } from "@/services/auth";

export default function SignupPage() {
  const router = useRouter();
  const [values, setValues] = useState({
    fullName: "",
    email: "",
    password: "",
    confirmPassword: "",
    organizationName: "",
    organizationSlug: "",
    acceptTerms: false,
  });
  // Slug is auto-derived from the workspace name until the user edits it.
  const slugTouched = useRef(false);
  const [fieldErrors, setFieldErrors] = useState<FormErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function update<K extends keyof typeof values>(field: K, value: (typeof values)[K]) {
    setValues((current) => {
      const next = { ...current, [field]: value };
      if (field === "organizationName" && !slugTouched.current) {
        next.organizationSlug = slugifyOrganization(String(value));
      }
      return next;
    });
    setFieldErrors((current) => ({ ...current, [field]: undefined }));
  }

  const slugPreview = values.organizationSlug || "your-workspace";

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    const errors = validateForm(signupSchema, values);
    setFieldErrors(errors);
    setFormError(null);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    try {
      const result = await register({
        email: values.email,
        password: values.password,
        fullName: values.fullName.trim(),
        organizationName: values.organizationName.trim(),
        organizationSlug: values.organizationSlug,
      });
      if (result.email_verification_required) {
        // Keep the just-registered address for the resend form on the
        // verification screen (in-memory only; never persisted).
        setPendingVerificationEmail(result.user?.email ?? values.email);
        router.replace(`${ROUTES.verifyEmail}?registered=1`);
        return;
      }
      router.replace(ROUTES.dashboard);
      router.refresh();
    } catch (err) {
      if (err instanceof ApiRequestError) {
        if (err.code === "organization.slug_taken") {
          setFieldErrors((current) => ({
            ...current,
            organizationSlug: "That workspace slug is taken. Choose another.",
          }));
        } else if (err.code === "user.email_taken") {
          setFieldErrors((current) => ({
            ...current,
            email: "An account already exists for this email.",
          }));
        } else {
          setFormError(err.message);
        }
      } else {
        setFormError("Unable to create your account. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell wide>
      <h1 className="text-center font-display text-2xl font-semibold tracking-tight text-off-white">
        Create your workspace
      </h1>
      <p className="mt-1 text-center text-sm text-soft-gray">
        Set up your organization and owner account.
      </p>

      <form onSubmit={handleSubmit} noValidate className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Full name" id="full_name" error={fieldErrors.fullName}>
          <TextInput
            id="full_name"
            autoComplete="name"
            autoCapitalize="words"
            placeholder="Ayesha Khan"
            invalid={Boolean(fieldErrors.fullName)}
            value={values.fullName}
            onChange={(event) => update("fullName", event.target.value)}
          />
        </Field>

        <Field label="Business email" id="email" error={fieldErrors.email}>
          <TextInput
            id="email"
            type="email"
            autoComplete="email"
            autoCapitalize="none"
            spellCheck={false}
            placeholder="you@company.com"
            invalid={Boolean(fieldErrors.email)}
            value={values.email}
            onChange={(event) => update("email", event.target.value)}
          />
        </Field>

        <Field label="Password" id="password" error={fieldErrors.password} hint={fieldErrors.password ? undefined : "At least 8 characters."}>
          <PasswordInput
            id="password"
            autoComplete="new-password"
            invalid={Boolean(fieldErrors.password)}
            value={values.password}
            onChange={(event) => update("password", event.target.value)}
          />
        </Field>

        <Field label="Confirm password" id="confirm_password" error={fieldErrors.confirmPassword}>
          <PasswordInput
            id="confirm_password"
            autoComplete="new-password"
            invalid={Boolean(fieldErrors.confirmPassword)}
            value={values.confirmPassword}
            onChange={(event) => update("confirmPassword", event.target.value)}
          />
        </Field>

        <Field label="Workspace name" id="organization_name" error={fieldErrors.organizationName}>
          <TextInput
            id="organization_name"
            autoComplete="organization"
            placeholder="Northwind Studio"
            invalid={Boolean(fieldErrors.organizationName)}
            value={values.organizationName}
            onChange={(event) => update("organizationName", event.target.value)}
          />
        </Field>

        <Field
          label="Workspace slug"
          id="organization_slug"
          error={fieldErrors.organizationSlug}
          hint={fieldErrors.organizationSlug ? undefined : `${slugPreview}.agencyos.app`}
        >
          <TextInput
            id="organization_slug"
            autoCapitalize="none"
            spellCheck={false}
            autoComplete="off"
            placeholder="northwind"
            invalid={Boolean(fieldErrors.organizationSlug)}
            value={values.organizationSlug}
            onChange={(event) => {
              slugTouched.current = true;
              update("organizationSlug", event.target.value);
            }}
            className="font-mono"
          />
        </Field>

        <div className="sm:col-span-2">
          <label className="flex cursor-pointer items-start gap-3 text-sm leading-snug text-soft-gray">
            <input
              type="checkbox"
              checked={values.acceptTerms}
              onChange={(event) => update("acceptTerms", event.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 accent-success"
              aria-invalid={Boolean(fieldErrors.acceptTerms) || undefined}
              aria-describedby={fieldErrors.acceptTerms ? "acceptTerms-error" : undefined}
            />
            <span>
              I agree to the{" "}
              <Link
                href={ROUTES.terms}
                className="text-silver underline underline-offset-2 transition-colors hover:text-off-white"
              >
                Terms of Service
              </Link>{" "}
              and{" "}
              <Link
                href={ROUTES.privacy}
                className="text-silver underline underline-offset-2 transition-colors hover:text-off-white"
              >
                Privacy Policy
              </Link>
            </span>
          </label>
          {fieldErrors.acceptTerms ? (
            <p id="acceptTerms-error" role="alert" className="mt-1.5 text-xs text-danger">
              {fieldErrors.acceptTerms}
            </p>
          ) : null}
        </div>

        {formError ? (
          <p role="alert" className="text-sm text-danger sm:col-span-2">
            {formError}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-off-white px-4 py-3 text-sm font-semibold text-obsidian transition-colors hover:bg-white focus:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver disabled:cursor-not-allowed disabled:opacity-60 sm:col-span-2"
        >
          {submitting ? "Creating your workspace…" : "Create account"}
        </button>
      </form>

      <p className="mt-5 text-center text-sm text-soft-gray">
        Already have an account?{" "}
        <Link
          href={ROUTES.login}
          className="font-medium text-off-white underline-offset-2 transition-colors hover:underline focus:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver"
        >
          Sign in
        </Link>
      </p>
      <p className="mt-2 text-center text-xs text-muted">
        Email and password only. No social sign-in
      </p>
    </AuthShell>
  );
}
