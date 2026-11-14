// AgencyOS Core Orbit mark, rendered as a static SVG.
// Geometry follows the brand board (Sheet 1 / Sheet 2A): a metallic core
// sphere inside two tick-marked rings with orbiting dots. Purely static —
// there is no animation, so reduced-motion preferences are respected.
import { cn } from "@/lib/utils";

interface CoreOrbitProps {
  className?: string;
  /** Pixel size of the square SVG. */
  size?: number;
}

const ORBIT_DOTS = [
  { cx: 32, cy: 5.5 },
  { cx: 58.5, cy: 32 },
  { cx: 5.5, cy: 32 },
  { cx: 48.6, cy: 48.6 },
];

export function CoreOrbit({ className, size = 32 }: CoreOrbitProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      aria-hidden="true"
      className={cn("shrink-0", className)}
    >
      {/* Outer faint dashed orbit */}
      <circle cx="32" cy="32" r="31" stroke="#2A2A2A" strokeWidth="1" strokeDasharray="2 3" />
      {/* Inner tick-marked ring */}
      <circle cx="32" cy="32" r="26.5" stroke="#A3A3A3" strokeWidth="2" />
      {/* Ticks */}
      {[0, 90, 180, 270].map((angle) => (
        <line
          key={angle}
          x1="32"
          y1="2.5"
          x2="32"
          y2="9.5"
          stroke="#A3A3A3"
          strokeWidth="3"
          transform={`rotate(${angle} 32 32)`}
        />
      ))}
      {/* Core: dark metallic housing + light sphere */}
      <circle cx="32" cy="32" r="14" fill="#111111" stroke="#C7C7C7" strokeWidth="1.5" />
      <circle cx="32" cy="32" r="9" fill="url(#core-orbit-sphere)" />
      {/* Orbiting dots */}
      {ORBIT_DOTS.map((dot, index) => (
        <circle key={index} cx={dot.cx} cy={dot.cy} r={index === 3 ? 2.5 : 3.5} fill="#F5F5F5" />
      ))}
      <defs>
        <radialGradient id="core-orbit-sphere" cx="0.35" cy="0.3" r="0.9">
          <stop offset="0%" stopColor="#FFFFFF" />
          <stop offset="55%" stopColor="#C7C7C7" />
          <stop offset="100%" stopColor="#5A5A5A" />
        </radialGradient>
      </defs>
    </svg>
  );
}
