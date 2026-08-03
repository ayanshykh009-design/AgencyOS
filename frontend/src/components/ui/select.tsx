// Select primitive (presentational, props-driven).
import { cn } from "@/lib/utils";

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean;
}

export function Select({ className, invalid, ...props }: SelectProps) {
  return (
    <select
      className={cn(
        "w-full rounded-md border bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900 disabled:opacity-50",
        invalid ? "border-red-400" : "border-gray-300",
        className
      )}
      {...props}
    />
  );
}
