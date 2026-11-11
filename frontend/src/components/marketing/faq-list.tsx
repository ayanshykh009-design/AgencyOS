// Pricing FAQ disclosure row (Sheet 2A screen 01).
// Desktop shows the three questions in a single row, as designed;
// answers expand in a panel beneath the row. Buttons carry
// aria-expanded/aria-controls for keyboard and screen-reader access.
"use client";

import { useState } from "react";

import type { FaqItem } from "@/lib/marketing";
import { cn } from "@/lib/utils";

function faqId(question: string): string {
  return `faq-${question.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

export function FaqList({ items }: { items: FaqItem[] }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const openItem = items.find((item) => faqId(item.question) === openId);

  return (
    <div>
      {/* Question row: wraps to a column on small screens */}
      <ul className="flex flex-col gap-1 md:flex-row md:items-center md:gap-8">
        {items.map((item) => {
          const id = faqId(item.question);
          const open = openId === id;
          return (
            <li key={id}>
              <button
                type="button"
                aria-expanded={open}
                aria-controls={`${id}-panel`}
                onClick={() => setOpenId(open ? null : id)}
                className="flex items-center gap-2 py-3 text-left text-sm transition-colors duration-200 focus-visible:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver md:py-1"
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 16 16"
                  fill="none"
                  aria-hidden="true"
                  className={cn(
                    "shrink-0 text-muted transition-transform duration-200",
                    open ? "rotate-90 text-off-white" : "rotate-0"
                  )}
                >
                  <path d="M6 3.5 10.5 8 6 12.5" stroke="currentColor" strokeWidth="1.5" />
                </svg>
                <span
                  className={cn(
                    "transition-colors duration-200",
                    open ? "font-medium text-off-white" : "text-soft-gray hover:text-off-white"
                  )}
                >
                  {item.question}
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      {/* Answer panel beneath the row */}
      <div id={openItem ? `${faqId(openItem.question)}-panel` : undefined} className="min-h-[3.5rem] pt-3">
        {openItem ? (
          <p className="max-w-2xl text-sm leading-relaxed text-soft-gray">{openItem.answer}</p>
        ) : null}
      </div>
    </div>
  );
}
