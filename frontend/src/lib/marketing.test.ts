// Content integrity tests for the Batch 1 public marketing pages.
import { describe, expect, it } from "vitest";

import { ROUTES } from "@/lib/constants";
import {
  COMPARISON_ROWS,
  MARKER_LABELS,
  PLANS,
  PRICING_FAQ,
  PRIVACY_SECTIONS,
  PUBLIC_FOOTER_LINKS,
  PUBLIC_NAV_ITEMS,
  TERMS_SECTIONS,
  type PlanMarker,
} from "@/lib/marketing";

describe("pricing plans", () => {
  it("has exactly the three designed plans", () => {
    expect(PLANS.map((plan) => plan.id)).toEqual(["starter", "professional", "enterprise"]);
  });

  it("never invents a price: every plan reads Contact for pricing", () => {
    for (const plan of PLANS) {
      expect(plan.price).toBe("Contact for pricing");
    }
  });

  it("highlights Professional as the recommended plan", () => {
    const recommended = PLANS.filter((plan) => plan.recommended === true);
    expect(recommended.map((plan) => plan.id)).toEqual(["professional"]);
  });

  it("routes every CTA to the contact or demo page (no checkout)", () => {
    const allowed = new Set<string>([ROUTES.contact, ROUTES.demo]);
    for (const plan of PLANS) {
      expect(allowed.has(plan.cta.href)).toBe(true);
      expect(["Contact Sales", "Book a Demo"]).toContain(plan.cta.label);
    }
  });

  it("lists the designed feature bullets for each plan", () => {
    expect(PLANS[0].features).toEqual([
      "CRM: leads, pipeline, tasks",
      "Global search and inbox",
      "AI research and drafts",
      "Owner-defined seat limit",
    ]);
    expect(PLANS[1].features).toContain("Everything in Starter");
    expect(PLANS[2].features).toContain("Everything in Professional");
  });
});

describe("pricing comparison", () => {
  it("compares the three designed capabilities", () => {
    expect(COMPARISON_ROWS.map((row) => row.capability)).toEqual([
      "CRM, pipeline & tasks",
      "Workflows & automation",
      "AI Agent & Assistant Actions",
    ]);
  });

  it("shows full CRM availability and Starter automation exclusion", () => {
    const crm = COMPARISON_ROWS[0].markers.every(
      (marker: PlanMarker) => marker === "included"
    );
    expect(crm).toBe(true);
    expect(COMPARISON_ROWS[1].markers).toEqual(["excluded", "included", "included"]);
    expect(COMPARISON_ROWS[2].markers).toEqual(["basic", "included", "included"]);
  });

  it("gives every marker an accessible label (never color alone)", () => {
    for (const marker of ["included", "basic", "excluded"] as const) {
      expect(MARKER_LABELS[marker].length).toBeGreaterThan(0);
    }
  });
});

describe("pricing FAQ", () => {
  it("preserves the three designed questions", () => {
    expect(PRICING_FAQ.map((item) => item.question)).toEqual([
      "Is there a free trial?",
      "How is AI usage handled?",
      "Can I change plans?",
    ]);
  });

  it("answers without invented prices, limits or guarantees", () => {
    for (const item of PRICING_FAQ) {
      expect(item.answer).not.toMatch(/\$\d/);
      expect(item.answer).not.toMatch(/guarantee/i);
      expect(item.answer.toLowerCase()).toMatch(/finaliz|not been decided|contact us/);
    }
  });
});

describe("public navigation links", () => {
  it("only links to routes that exist in the V1 route inventory", () => {
    const existingRoutes = new Set(Object.values(ROUTES) as string[]);
    const linked = [...PUBLIC_NAV_ITEMS, ...PUBLIC_FOOTER_LINKS]
      .map((item) => item.href)
      .filter((href): href is string => href !== undefined);
    expect(linked.length).toBeGreaterThan(0);
    for (const href of linked) {
      expect(existingRoutes.has(href)).toBe(true);
    }
  });

  it("keeps Product/Solutions/Resources/Company as non-link placeholders", () => {
    for (const label of ["Product", "Solutions", "Resources", "Company"]) {
      const item = PUBLIC_NAV_ITEMS.find((nav) => nav.label === label);
      expect(item?.href).toBeUndefined();
    }
  });

  it("links the footer to terms, privacy, contact and demo", () => {
    expect(PUBLIC_FOOTER_LINKS.map((link) => link.href)).toEqual([
      ROUTES.terms,
      ROUTES.privacy,
      ROUTES.contact,
      ROUTES.demo,
    ]);
  });
});

describe("legal page sections", () => {
  it("matches the designed terms outline", () => {
    expect(TERMS_SECTIONS.map((section) => section.title)).toEqual([
      "Acceptance of terms",
      "Accounts and access",
      "Acceptable use",
      "Customer data",
      "Service changes",
      "Termination",
      "Contact",
    ]);
  });

  it("matches the designed privacy outline", () => {
    expect(PRIVACY_SECTIONS.map((section) => section.title)).toEqual([
      "Data collection",
      "Account information",
      "Organization information",
      "Business data",
      "AI-processing information",
      "Retention",
      "Security",
      "User rights",
      "Privacy inquiries",
    ]);
  });

  it("uses unique, anchor-safe section ids", () => {
    for (const sections of [TERMS_SECTIONS, PRIVACY_SECTIONS]) {
      const ids = sections.map((section) => section.id);
      expect(new Set(ids).size).toBe(ids.length);
      for (const id of ids) {
        expect(id).toMatch(/^[a-z0-9-]+$/);
      }
    }
  });
});
