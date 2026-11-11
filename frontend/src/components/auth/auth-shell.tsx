// Shared shell for the authentication screens (Sheet 1 login artwork and
// Sheet 2A screens 06/09/10/11): dark-first Obsidian scene, Core Orbit
// backdrop, AgencyOS wordmark and a centred card. The orbit drift is
// decorative, slow (120s) and disabled for reduced-motion users.
import Link from "next/link";

import { CoreOrbit } from "@/components/marketing/core-orbit";
import { cn } from "@/lib/utils";
import { ROUTES } from "@/lib/constants";

interface AuthShellProps {
  children: React.ReactNode;
  /** Wider card for multi-column forms (signup). */
  wide?: boolean;
}

export function AuthShell({ children, wide = false }: AuthShellProps) {
  return (
    <main className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-obsidian px-4 py-10">
      {/* Ambient glow */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(60% 50% at 50% 38%, rgba(24,24,24,0.95) 0%, rgba(5,5,5,0) 70%), radial-gradient(42% 36% at 50% 64%, rgba(42,42,42,0.4) 0%, rgba(5,5,5,0) 75%)",
        }}
      />

      {/* Core Orbit backdrop: two static tilted orbits (brand geometry) and a
          slow-rotating dashed comet ring. */}
      <svg
        aria-hidden="true"
        viewBox="0 0 1000 1000"
        fill="none"
        className="pointer-events-none absolute left-1/2 top-1/2 w-[150vmin] -translate-x-1/2 -translate-y-1/2 opacity-80"
      >
        <g transform="rotate(-18 500 500)" stroke="#2A2A2A">
          <ellipse cx="500" cy="500" rx="470" ry="300" strokeWidth="1.5" />
          <ellipse cx="500" cy="500" rx="345" ry="220" strokeWidth="1" strokeOpacity="0.7" />
        </g>
        <g className="auth-orbit">
          <circle
            cx="500"
            cy="500"
            r="385"
            stroke="#3A3A3A"
            strokeWidth="1"
            strokeDasharray="1 14"
            strokeLinecap="round"
          />
          <circle cx="500" cy="115" r="6.5" fill="#F5F5F5" />
          <circle cx="833.6" cy="692.5" r="4.5" fill="#C7C7C7" />
          <circle cx="166.4" cy="692.5" r="4.5" fill="#C7C7C7" />
        </g>
      </svg>

      <Link
        href={ROUTES.home}
        aria-label="AgencyOS — back to home"
        className="relative z-10 mb-6 flex items-center gap-3 rounded-lg focus:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver"
      >
        <CoreOrbit size={34} />
        <span className="font-display text-xl font-semibold tracking-tight text-off-white">
          AgencyOS
        </span>
      </Link>

      <div
        className={cn(
          "relative z-10 w-full rounded-2xl border border-line bg-graphite p-6 shadow-[0_24px_80px_rgba(0,0,0,0.65)] sm:p-8",
          wide ? "max-w-[620px]" : "max-w-[400px]"
        )}
      >
        {children}
      </div>
    </main>
  );
}
