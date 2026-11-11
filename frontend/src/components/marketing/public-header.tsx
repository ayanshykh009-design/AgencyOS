// Public marketing header (Sheet 2A navigation identity).
// Dark-first shell: AgencyOS orbit mark, center navigation and a Sign In
// button. Only destinations that exist in V1 are links; the other items
// are non-interactive placeholders so no broken links are created.
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { CoreOrbit } from "@/components/marketing/core-orbit";
import { ROUTES } from "@/lib/constants";
import { PUBLIC_NAV_ITEMS } from "@/lib/marketing";
import { cn } from "@/lib/utils";

export function PublicHeader() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="border-b border-line bg-obsidian/95">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        {/* Brand */}
        <Link
          href={ROUTES.home}
          className="flex items-center gap-2.5 text-off-white focus-visible:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver"
        >
          <CoreOrbit size={28} />
          <span className="font-display text-lg font-bold tracking-tight">AgencyOS</span>
        </Link>

        {/* Desktop navigation */}
        <nav aria-label="Public" className="hidden items-center gap-8 md:flex">
          {PUBLIC_NAV_ITEMS.map((item) => {
            const active = item.href !== undefined && pathname === item.href;
            if (item.href) {
              return (
                <Link
                  key={item.label}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "text-sm transition-colors duration-200 hover:text-off-white focus-visible:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver",
                    active ? "font-semibold text-off-white" : "text-soft-gray"
                  )}
                >
                  {item.label}
                </Link>
              );
            }
            // Placeholder item: no approved destination exists in V1 yet.
            return (
              <span
                key={item.label}
                aria-disabled="true"
                className="cursor-default text-sm text-muted"
              >
                {item.label}
              </span>
            );
          })}
        </nav>

        <div className="hidden md:block">
          <Link
            href={ROUTES.login}
            className="rounded-lg border border-line bg-graphite px-4 py-2 text-sm font-medium text-off-white transition-colors duration-200 hover:border-muted focus-visible:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver"
          >
            Sign In
          </Link>
        </div>

        {/* Mobile menu toggle */}
        <button
          type="button"
          className="rounded-lg border border-line bg-graphite p-2 text-off-white focus-visible:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver md:hidden"
          aria-expanded={menuOpen}
          aria-controls="public-mobile-menu"
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          onClick={() => setMenuOpen((open) => !open)}
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            {menuOpen ? (
              <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="1.5" />
            ) : (
              <path d="M3 6h14M3 10h14M3 14h14" stroke="currentColor" strokeWidth="1.5" />
            )}
          </svg>
        </button>
      </div>

      {/* Mobile navigation */}
      {menuOpen ? (
        <nav
          id="public-mobile-menu"
          aria-label="Public mobile"
          className="border-t border-line bg-obsidian px-4 py-3 md:hidden"
        >
          <ul className="flex flex-col gap-1">
            {PUBLIC_NAV_ITEMS.map((item) => (
              <li key={item.label}>
                {item.href ? (
                  <Link
                    href={item.href}
                    onClick={() => setMenuOpen(false)}
                    className="block rounded-md px-2 py-2 text-sm text-soft-gray hover:bg-graphite hover:text-off-white focus-visible:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver"
                  >
                    {item.label}
                  </Link>
                ) : (
                  <span aria-disabled="true" className="block px-2 py-2 text-sm text-muted">
                    {item.label}
                  </span>
                )}
              </li>
            ))}
            <li>
              <Link
                href={ROUTES.login}
                onClick={() => setMenuOpen(false)}
                className="mt-1 block rounded-md border border-line bg-graphite px-2 py-2 text-center text-sm font-medium text-off-white hover:border-muted focus-visible:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver"
              >
                Sign In
              </Link>
            </li>
          </ul>
        </nav>
      ) : null}
    </header>
  );
}
