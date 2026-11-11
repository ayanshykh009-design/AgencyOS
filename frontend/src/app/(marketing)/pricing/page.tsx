// Pricing page (Sheet 2A screen 01): headline, three plan cards,
// capability comparison and FAQ. Informational only — there is no
// checkout or billing backend in V1, so every price reads
// "Contact for pricing" and CTAs route to /contact or /demo.
import type { Metadata } from "next";

import { ComparisonTable } from "@/components/marketing/comparison-table";
import { FaqList } from "@/components/marketing/faq-list";
import { PlanCard } from "@/components/marketing/plan-card";
import { UnavailableNote } from "@/components/marketing/unavailable-note";
import { PLANS, PRICING_FAQ, PRICING_HEADLINE, PRICING_INTRO } from "@/lib/marketing";

export const metadata: Metadata = {
  title: "Pricing · AgencyOS",
  description:
    "Simple plans for the AgencyOS AI Business Operating System. Contact us to find the right plan.",
};

export default function PricingPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 pb-20 pt-14 sm:px-6">
      {/* Headline */}
      <header className="mx-auto max-w-3xl text-center">
        <h1 className="font-display text-4xl font-semibold tracking-tight text-off-white sm:text-5xl">
          {PRICING_HEADLINE}
        </h1>
        <p className="mt-4 text-sm text-soft-gray sm:text-base">{PRICING_INTRO}</p>
      </header>

      {/* Plan cards */}
      <div className="mt-12 grid gap-6 md:grid-cols-3">
        {PLANS.map((plan) => (
          <PlanCard key={plan.id} plan={plan} />
        ))}
      </div>

      {/* Comparison */}
      <section aria-labelledby="compare-heading" className="mt-16">
        <h2 id="compare-heading" className="text-xs font-semibold uppercase tracking-wider text-muted">
          Compare capabilities
        </h2>
        <div className="mt-4">
          <ComparisonTable />
        </div>
      </section>

      {/* FAQ */}
      <section aria-labelledby="faq-heading" className="mt-14 border-t border-line pt-8">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:gap-10">
          <h2
            id="faq-heading"
            className="font-display text-xl font-semibold text-off-white md:w-48 md:shrink-0"
          >
            FAQ
          </h2>
          <div className="flex-1">
            <FaqList items={PRICING_FAQ} />
          </div>
        </div>
        <UnavailableNote className="mt-8">
          No checkout in V1: CTAs route to /contact or /demo.
        </UnavailableNote>
      </section>
    </div>
  );
}
