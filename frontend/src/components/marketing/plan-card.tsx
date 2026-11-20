// Pricing plan card (Sheet 2A screen 01).
// Starter/Enterprise: thin Line Gray border. Professional: silver outline
// with the white RECOMMENDED badge and a white primary CTA.
import Link from "next/link";

import type { PlanCard as PlanCardData } from "@/lib/marketing";
import { cn } from "@/lib/utils";

interface PlanCardProps {
  plan: PlanCardData;
}

export function PlanCard({ plan }: PlanCardProps) {
  const recommended = plan.recommended === true;
  return (
    <article
      className={cn(
        "flex flex-col rounded-xl border bg-graphite p-6 transition-colors duration-200",
        recommended ? "border-silver/70" : "border-line"
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-display text-xl font-semibold text-off-white">{plan.name}</h3>
        {recommended ? (
          <span className="rounded-full bg-off-white px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-obsidian">
            Recommended
          </span>
        ) : null}
      </div>
      <p className="mt-1 text-sm text-soft-gray">{plan.audience}</p>

      <p className="mt-4 font-display text-lg font-semibold text-off-white">{plan.price}</p>

      <ul className="mt-4 flex flex-col gap-2.5">
        {plan.features.map((feature) => (
          <li key={feature} className="flex items-start gap-2.5 text-sm text-off-white/90">
            <svg
              width="14"
              height="14"
              viewBox="0 0 16 16"
              fill="none"
              aria-hidden="true"
              className="mt-1 shrink-0 text-success"
            >
              <path
                d="M2.5 8.5 6 12l7.5-8"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span>{feature}</span>
          </li>
        ))}
      </ul>

      <div className="mt-6 pt-2 mt-auto">
        <Link
          href={plan.cta.href}
          className={cn(
            "block rounded-lg px-4 py-2.5 text-center text-sm font-medium transition-colors duration-200 focus-visible:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver",
            recommended
              ? "bg-off-white text-obsidian hover:bg-silver"
              : "border border-line bg-elevated text-off-white hover:border-muted"
          )}
        >
          {plan.cta.label}
        </Link>
      </div>
    </article>
  );
}
