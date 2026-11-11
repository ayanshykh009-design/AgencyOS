// "ON THIS PAGE" table of contents for the legal pages.
// Highlights the section currently in view via IntersectionObserver;
// without observation support it falls back to a plain link list.
"use client";

import { useEffect, useState } from "react";

import type { LegalSection } from "@/lib/marketing";
import { cn } from "@/lib/utils";

export function LegalToc({ sections }: { sections: LegalSection[] }) {
  const [activeId, setActiveId] = useState<string>(sections[0]?.id ?? "");

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActiveId(entry.target.id);
        }
      },
      { rootMargin: "-20% 0px -70% 0px" }
    );
    const elements = sections
      .map((section) => document.getElementById(section.id))
      .filter((element): element is HTMLElement => element !== null);
    for (const element of elements) observer.observe(element);
    return () => observer.disconnect();
  }, [sections]);

  return (
    <nav aria-label="On this page" className="rounded-xl border border-line bg-graphite p-4">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">On this page</p>
      <ul className="mt-3 flex flex-col gap-0.5">
        {sections.map((section) => (
          <li key={section.id}>
            <a
              href={`#${section.id}`}
              aria-current={activeId === section.id ? "location" : undefined}
              className={cn(
                "block rounded-md px-3 py-2 text-sm transition-colors duration-200 focus-visible:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver",
                activeId === section.id
                  ? "bg-elevated text-off-white"
                  : "text-soft-gray hover:bg-elevated hover:text-off-white"
              )}
            >
              {section.title}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
