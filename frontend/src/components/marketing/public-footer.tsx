// Public marketing footer (Sheet 2A): brand on the left, legal/contact
// links on the right, separated by a thin top border.
import Link from "next/link";

import { CoreOrbit } from "@/components/marketing/core-orbit";
import { ROUTES } from "@/lib/constants";
import { PUBLIC_FOOTER_LINKS } from "@/lib/marketing";

export function PublicFooter() {
  return (
    <footer className="border-t border-line bg-obsidian">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 py-6 sm:px-6 md:flex-row">
        <Link
          href={ROUTES.home}
          className="flex items-center gap-2 text-off-white focus-visible:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver"
        >
          <CoreOrbit size={22} />
          <span className="font-display text-base font-bold tracking-tight">AgencyOS</span>
        </Link>
        <nav aria-label="Footer">
          <ul className="flex items-center gap-6">
            {PUBLIC_FOOTER_LINKS.map((link) => (
              <li key={link.label}>
                <Link
                  href={link.href ?? ROUTES.home}
                  className="text-sm text-muted transition-colors duration-200 hover:text-soft-gray focus-visible:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver"
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </footer>
  );
}
