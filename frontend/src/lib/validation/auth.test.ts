import { describe, expect, it } from "vitest";

import {
  loginSchema,
  passwordResetRequestSchema,
  recoveryCodeSchema,
  slugifyOrganization,
  signupSchema,
  totpCodeSchema,
  validateForm,
  SLUG_PATTERN,
} from "@/lib/validation/auth";

const validSignup = {
  fullName: "Ayesha Khan",
  email: "ayesha@northwind.example",
  password: "correct-horse-battery-staple",
  confirmPassword: "correct-horse-battery-staple",
  organizationName: "Northwind Studio",
  organizationSlug: "northwind",
  acceptTerms: true,
};

describe("loginSchema", () => {
  it("accepts a valid email and password", () => {
    const result = loginSchema.safeParse({ email: "a@b.example", password: "password1" });
    expect(result.success).toBe(true);
  });

  it("rejects an invalid email", () => {
    const result = loginSchema.safeParse({ email: "bad@", password: "password1" });
    expect(result.success).toBe(false);
  });

  it("rejects a password shorter than the backend minimum (8)", () => {
    const result = loginSchema.safeParse({ email: "a@b.example", password: "short" });
    expect(result.success).toBe(false);
  });
});

describe("signupSchema", () => {
  it("accepts the designed happy path", () => {
    expect(signupSchema.safeParse(validSignup).success).toBe(true);
  });

  it("rejects a password shorter than 8 characters (backend rule)", () => {
    const result = signupSchema.safeParse({
      ...validSignup,
      password: "abc1234",
      confirmPassword: "abc1234",
    });
    expect(result.success).toBe(false);
  });

  it("rejects a password longer than 128 characters (backend rule)", () => {
    const long = "x".repeat(129);
    const result = signupSchema.safeParse({
      ...validSignup,
      password: long,
      confirmPassword: long,
    });
    expect(result.success).toBe(false);
  });

  it("rejects mismatched confirmation", () => {
    const result = signupSchema.safeParse({
      ...validSignup,
      confirmPassword: "different-password",
    });
    expect(result.success).toBe(false);
    const errors = validateForm(signupSchema, {
      ...validSignup,
      confirmPassword: "different-password",
    });
    expect(errors.confirmPassword).toBe("Passwords do not match");
  });

  it("rejects a slug with uppercase, spaces or a leading hyphen", () => {
    for (const slug of ["Northwind", "north wind", "-northwind", "northwind!"]) {
      const result = signupSchema.safeParse({ ...validSignup, organizationSlug: slug });
      expect(result.success, `slug ${slug} should fail`).toBe(false);
    }
  });

  it("accepts a slug matching the backend pattern", () => {
    expect(SLUG_PATTERN.test("northwind-12")).toBe(true);
    expect(
      signupSchema.safeParse({ ...validSignup, organizationSlug: "northwind-12" }).success
    ).toBe(true);
  });

  it("requires explicit Terms and Privacy consent", () => {
    const result = signupSchema.safeParse({ ...validSignup, acceptTerms: false });
    expect(result.success).toBe(false);
    const errors = validateForm(signupSchema, { ...validSignup, acceptTerms: false });
    expect(errors.acceptTerms).toBeDefined();
  });

  it("rejects blank required fields", () => {
    const result = signupSchema.safeParse({ ...validSignup, organizationName: "   " });
    expect(result.success).toBe(false);
  });
});

describe("slugifyOrganization", () => {
  it("derives a backend-legal slug from a workspace name", () => {
    expect(slugifyOrganization("Northwind Studio")).toBe("northwind-studio");
    expect(slugifyOrganization("  A  &  B! ")).toBe("a-b");
    expect(slugifyOrganization("--lead--trail--")).toBe("lead-trail");
    expect(slugifyOrganization("")).toBe("");
  });

  it("keeps the slug within 63 characters and always starts with alphanumerics", () => {
    const slug = slugifyOrganization("x".repeat(200));
    expect(slug.length).toBeLessThanOrEqual(63);
    expect(SLUG_PATTERN.test(slug)).toBe(true);
  });
});

describe("passwordResetRequestSchema", () => {
  it("accepts an email and rejects non-emails", () => {
    expect(passwordResetRequestSchema.safeParse({ email: "a@b.example" }).success).toBe(true);
    expect(passwordResetRequestSchema.safeParse({ email: "not-an-email" }).success).toBe(false);
  });
});

describe("mfa code schemas", () => {
  it("accepts exactly six digits for TOTP", () => {
    expect(totpCodeSchema.safeParse("123456").success).toBe(true);
    expect(totpCodeSchema.safeParse("12345").success).toBe(false);
    expect(totpCodeSchema.safeParse("12345a").success).toBe(false);
  });

  it("accepts an opaque recovery code up to 64 characters", () => {
    expect(recoveryCodeSchema.safeParse("abcd-efgh-ijkl").success).toBe(true);
    expect(recoveryCodeSchema.safeParse("x".repeat(65)).success).toBe(false);
    expect(recoveryCodeSchema.safeParse("   ").success).toBe(false);
  });
});
