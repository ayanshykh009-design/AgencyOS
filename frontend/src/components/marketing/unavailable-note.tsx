// Amber "not available yet" note used on the public pages where a
// capability is intentionally unavailable in V1 (no submission backend,
// no checkout). Matches the amber annotation style of Sheet 2A.
import { cn } from "@/lib/utils";

interface UnavailableNoteProps {
  children: React.ReactNode;
  className?: string;
}

export function UnavailableNote({ children, className }: UnavailableNoteProps) {
  return (
    <p
      className={cn(
        "flex items-start gap-2 rounded-lg border border-warning/60 bg-warning/10 px-3 py-2 text-xs text-warning",
        className
      )}
      role="note"
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 16 16"
        fill="none"
        aria-hidden="true"
        className="mt-0.5 shrink-0"
      >
        <path
          d="M8 1.5 15 14H1L8 1.5Z"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinejoin="round"
        />
        <path d="M8 6v4" stroke="currentColor" strokeWidth="1.2" />
        <circle cx="8" cy="12" r="0.8" fill="currentColor" />
      </svg>
      <span>{children}</span>
    </p>
  );
}
