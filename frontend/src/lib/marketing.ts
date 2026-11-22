// Static marketing content for the public pages (Batch 1 of Phase 6).
// Copy follows the approved Sheet 2A screens (AGENCYOS_ALL_IN_ONE.pdf).
// Everything marked "owner to supply" must stay a placeholder: pricing,
// legal text and contact details are owner-supplied content.

import { ROUTES } from "@/lib/constants";

// ---------------------------------------------------------------------
// Public header / footer navigation.
// Only destinations that exist in the V1 route inventory are links;
// the remaining items are rendered as non-interactive placeholders so
// the visual navigation matches the design without creating dead links.
// ---------------------------------------------------------------------
export type PublicNavItem = {
  label: string;
  href?: string;
};

export const PUBLIC_NAV_ITEMS: PublicNavItem[] = [
  { label: "Product" },
  { label: "Solutions" },
  { label: "Pricing", href: ROUTES.pricing },
  { label: "Resources" },
  { label: "Company" },
];

export const PUBLIC_FOOTER_LINKS: PublicNavItem[] = [
  { label: "Terms", href: ROUTES.terms },
  { label: "Privacy", href: ROUTES.privacy },
  { label: "Contact", href: ROUTES.contact },
  { label: "Demo", href: ROUTES.demo },
];

// ---------------------------------------------------------------------
// Pricing (/pricing) — Sheet 2A screen 01.
// ---------------------------------------------------------------------
export type PlanCard = {
  id: string;
  name: string;
  audience: string;
  price: string;
  features: string[];
  cta: { label: string; href: string };
  recommended?: boolean;
};

export const PLANS: PlanCard[] = [
  {
    id: "starter",
    name: "Starter",
    audience: "For small teams getting started",
    price: "Contact for pricing",
    features: [
      "CRM: leads, pipeline, tasks",
      "Global search and inbox",
      "AI research and drafts",
      "Owner-defined seat limit",
    ],
    cta: { label: "Contact Sales", href: ROUTES.contact },
  },
  {
    id: "professional",
    name: "Professional",
    audience: "For growing revenue teams",
    price: "Contact for pricing",
    features: [
      "Everything in Starter",
      "Workflows, triggers, deliveries",
      "Growth Intelligence",
      "Assistant Actions with approvals",
    ],
    cta: { label: "Book a Demo", href: ROUTES.demo },
    recommended: true,
  },
  {
    id: "enterprise",
    name: "Enterprise",
    audience: "For multi-team organizations",
    price: "Contact for pricing",
    features: [
      "Everything in Professional",
      "Advanced security review",
      "Custom onboarding",
      "Priority support channel",
    ],
    cta: { label: "Contact Sales", href: ROUTES.contact },
  },
];

export const PRICING_HEADLINE = "Simple Plans. Powerful Operations.";
export const PRICING_INTRO =
  "One AI Business Operating System for CRM, automation and intelligence. Talk to us to find the right plan.";

// Comparison matrix. Each marker is a label ("included", "basic",
// "excluded") plus the printed symbol; screens never rely on color alone.
export type PlanMarker = "included" | "basic" | "excluded";

export type ComparisonRow = {
  capability: string;
  markers: [PlanMarker, PlanMarker, PlanMarker];
};

export const COMPARISON_ROWS: ComparisonRow[] = [
  {
    capability: "CRM, pipeline & tasks",
    markers: ["included", "included", "included"],
  },
  {
    capability: "Workflows & automation",
    markers: ["excluded", "included", "included"],
  },
  {
    capability: "AI Agent & Assistant Actions",
    markers: ["basic", "included", "included"],
  },
];

export const PLAN_COLUMN_LABELS = ["Starter", "Professional", "Enterprise"] as const;

export const MARKER_SYMBOLS: Record<PlanMarker, string> = {
  included: "●",
  basic: "Basic",
  excluded: "—",
};

export const MARKER_LABELS: Record<PlanMarker, string> = {
  included: "Included",
  basic: "Basic",
  excluded: "Not included",
};

// FAQ answers are owner-reviewable drafts: they must not invent prices,
// limits, guarantees or contract terms.
export type FaqItem = { question: string; answer: string };

export const PRICING_FAQ: FaqItem[] = [
  {
    question: "Is there a free trial?",
    answer:
      "Trial availability has not been decided yet. Plans are quoted by our team, so the fastest way to evaluate AgencyOS is to book a demo or contact us.",
  },
  {
    question: "How is AI usage handled?",
    answer:
      "AI features are part of the product, not a separate add-on. How provider usage and any usage-based limits are billed is being finalized and will be published here once confirmed.",
  },
  {
    question: "Can I change plans?",
    answer:
      "Plan changes will be supported. The exact upgrade and downgrade process is being finalized; contact us and we will walk you through the current options.",
  },
];

// ---------------------------------------------------------------------
// Contact (/contact) — Sheet 2A screen 02.
// ---------------------------------------------------------------------
export const CONTACT_HEADLINE = "Let's Talk.";
export const CONTACT_INTRO_LINES = [
  "Tell us about your business and what you want AgencyOS to run.",
  "We will reply to the email you provide.",
];

export const CONTACT_INQUIRY_TYPES = [
  "Sales question",
  "Product question",
  "Partnership",
  "Other",
] as const;

// "Owner to supply" placeholders — never invent contact details.
export const CONTACT_REACH_ITEMS = [
  { icon: "mail" as const, label: "Email address", value: "Owner to supply" },
  { icon: "clock" as const, label: "Response times", value: "Owner to supply" },
  { icon: "social" as const, label: "Social links", value: "Owner to supply" },
];

// ---------------------------------------------------------------------
// Demo (/demo) — Sheet 2A screen 03.
// ---------------------------------------------------------------------
export const DEMO_HEADLINE = "See AgencyOS in Action.";
export const DEMO_INTRO =
  "A guided walkthrough of CRM, automation and the AI Agent on your use case.";

export const DEMO_TEAM_SIZES = ["1 – 10", "11 – 50", "51 – 200", "200+"] as const;

export const DEMO_USE_CASES = [
  "Lead management and follow-up automation",
  "Workflow automation",
  "AI research and drafting",
  "Growth intelligence",
  "Other",
] as const;

export const DEMO_CONTACT_WINDOWS = ["Weekday mornings", "Weekday afternoons", "Any time"] as const;

export const DEMO_NEXT_STEPS = [
  "We review your request",
  "We contact you using the details provided",
  "We tailor the walkthrough",
];

// ---------------------------------------------------------------------
// Legal pages (/terms, /privacy) — Sheet 2A screens 04 and 05.
// Layout ships now; legal text and claims are owner-supplied, so the
// reading column renders clearly-marked placeholder content.
// ---------------------------------------------------------------------
export type LegalSection = { id: string; title: string };

export const TERMS_SECTIONS: LegalSection[] = [
  { id: "acceptance", title: "Acceptance of terms" },
  { id: "accounts", title: "Accounts and access" },
  { id: "acceptable-use", title: "Acceptable use" },
  { id: "customer-data", title: "Customer data" },
  { id: "service-changes", title: "Service changes" },
  { id: "termination", title: "Termination" },
  { id: "contact", title: "Contact" },
];

export const PRIVACY_SECTIONS: LegalSection[] = [
  { id: "data-collection", title: "Data collection" },
  { id: "account-information", title: "Account information" },
  { id: "organization-information", title: "Organization information" },
  { id: "business-data", title: "Business data" },
  { id: "ai-processing", title: "AI-processing information" },
  { id: "retention", title: "Retention" },
  { id: "security", title: "Security" },
  { id: "user-rights", title: "User rights" },
  { id: "privacy-inquiries", title: "Privacy inquiries" },
];

export const LEGAL_DRAFT_NOTICE = "Layout only. Legal text and claims are supplied by the owner.";
