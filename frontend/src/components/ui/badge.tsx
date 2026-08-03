// Badge primitive for status/label chips.
import { cn } from "@/lib/utils";
import type { BadgeTone } from "@/lib/format";

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
}

const TONES: Record<BadgeTone, string> = {
  gray: "bg-gray-100 text-gray-600",
  green: "bg-green-100 text-green-800",
  red: "bg-red-100 text-red-800",
  amber: "bg-amber-100 text-amber-800",
  blue: "bg-blue-100 text-blue-800",
  purple: "bg-purple-100 text-purple-800",
};

export function Badge({ tone = "gray", className, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium capitalize",
        TONES[tone],
        className
      )}
      {...props}
    />
  );
}
