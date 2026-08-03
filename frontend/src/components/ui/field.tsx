// Form field wrapper (label + error + children).
import { cn } from "@/lib/utils";

interface FieldProps {
  label?: string;
  htmlFor?: string;
  error?: string | null;
  hint?: string;
  required?: boolean;
  className?: string;
  children: React.ReactNode;
}

export function Field({ label, htmlFor, error, hint, required, className, children }: FieldProps) {
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      {label ? (
        <label htmlFor={htmlFor} className="text-sm text-gray-600">
          {label}
          {required ? <span className="ml-0.5 text-red-500">*</span> : null}
        </label>
      ) : null}
      {children}
      {hint && !error ? <p className="text-xs text-gray-400">{hint}</p> : null}
      {error ? <p className="text-xs text-red-600">{error}</p> : null}
    </div>
  );
}
