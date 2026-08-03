// Text input primitive (presentational, props-driven).
import { cn } from "@/lib/utils";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

export function Input({ className, invalid, ...props }: InputProps) {
  return (
    <input
      className={cn(
        "w-full rounded-md border bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-900 focus:ring-offset-0 disabled:opacity-50",
        invalid ? "border-red-400" : "border-gray-300",
        className
      )}
      {...props}
    />
  );
}
