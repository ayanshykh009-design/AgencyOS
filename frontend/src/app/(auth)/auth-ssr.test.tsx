// Server-render smoke tests for the five authentication screens.
// These render the real page components to static markup (no DOM needed)
// and assert the honest initial states: no fake success copy ever renders
// before a backend confirms it, and the core layout/copy is present.
// Interactive/hydration behavior is covered neither here nor by any local
// browser automation in this repo.
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(""),
  usePathname: () => "/",
}));

import LoginPage from "@/app/(auth)/login/page";
import SignupPage from "@/app/(auth)/signup/page";
import MfaChallengePage from "@/app/(auth)/mfa/page";
import VerifyEmailPage from "@/app/(auth)/verify-email/page";
import ForgotPasswordPage from "@/app/(auth)/forgot-password/page";

describe("authentication screens — initial render", () => {
  it("login renders the designed layout and no fake success state", () => {
    const html = renderToStaticMarkup(<LoginPage />);
    expect(html).toContain("Welcome back");
    expect(html).toContain("Sign in to continue to AgencyOS");
    expect(html).toContain('href="/forgot-password"');
    expect(html).toContain('href="/signup"');
    expect(html).not.toContain("Email verified");
    expect(html).not.toContain("Check your email");
  });

  it("signup renders the workspace card, consent and terms links", () => {
    const html = renderToStaticMarkup(<SignupPage />);
    expect(html).toContain("Create your workspace");
    expect(html).toContain("Workspace slug");
    expect(html).toContain("Create account");
    expect(html).toContain('href="/terms"');
    expect(html).toContain('href="/privacy"');
    expect(html).toContain("No social sign-in");
    expect(html).not.toContain("Check your email");
  });

  it("mfa renders the challenge and the missing-challenge error without a token", () => {
    const html = renderToStaticMarkup(<MfaChallengePage />);
    expect(html).toContain("Verify Your Identity");
    expect(html).toContain("Authenticator (TOTP) only");
    expect(html).toContain("Missing challenge");
    expect(html).not.toContain("Email verified");
  });

  it("verify-email renders the pending state with a resend control", () => {
    const html = renderToStaticMarkup(<VerifyEmailPage />);
    expect(html).toContain("Verify Your Email");
    expect(html).toContain("Resend verification email");
    expect(html).toContain("Back to sign in");
    expect(html).not.toContain("Email verified");
    expect(html).not.toContain("Check your email");
  });

  it("forgot-password renders the request state with the enumeration-safe copy absent until submit", () => {
    const html = renderToStaticMarkup(<ForgotPasswordPage />);
    expect(html).toContain("Reset Your Password");
    expect(html).toContain("Send reset link");
    // The confirmation copy must not appear before a real 202 response.
    expect(html).not.toContain("If an account exists for that address");
    expect(html).not.toContain("Check your email");
  });
});
