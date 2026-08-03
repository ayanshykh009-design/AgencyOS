// Textarea primitive (presentational, props-driven).
import { cn } from "@/lib/utils";

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
}

export function Textarea({ className, invalid, ...props }: TextareaProps) {
  return (
    <textarea
      className={cn(
        "w-full rounded-md border bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-900 disabled:opacity-50",
        invalid ? "border-red-400" : "border-gray-300",
        className
      )}
      {...props}
    />
  );
}
