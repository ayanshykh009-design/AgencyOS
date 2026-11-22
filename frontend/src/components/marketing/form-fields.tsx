// Dark-first form field primitives for the public marketing pages.
// Visual system follows Sheet 2C: 1px Line Gray borders, radius 8px,
// silver focus ring, red error state with helper text below the control.
// The authenticated pages keep using components/ui/* (light styling).
import { cn } from "@/lib/utils";

const BASE_CONTROL =
  "w-full rounded-lg border bg-deep-graphite px-3 py-2.5 text-sm text-off-white placeholder:text-muted focus:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver disabled:cursor-not-allowed disabled:opacity-50";

interface FieldProps {
  /** Visible label text. */
  label: string;
  /** Unique id shared by label, control and error text. */
  id: string;
  error?: string;
  hint?: string;
  className?: string;
  children: React.ReactNode;
}

export function Field({ label, id, error, hint, className, children }: FieldProps) {
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-xs font-medium text-soft-gray">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-xs text-muted">
          {hint}
        </p>
      ) : null}
      {/* describedBy is resolved here to keep aria wiring next to the error text */}
      <span className="hidden">{describedBy}</span>
    </div>
  );
}

interface TextInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

export function TextInput({ invalid, className, ...props }: TextInputProps) {
  return (
    <input
      aria-invalid={invalid || undefined}
      className={cn(BASE_CONTROL, invalid ? "border-danger" : "border-line", className)}
      {...props}
    />
  );
}

interface SelectInputProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean;
  children: React.ReactNode;
}

export function SelectInput({ invalid, className, children, ...props }: SelectInputProps) {
  return (
    <div className="relative">
      <select
        aria-invalid={invalid || undefined}
        className={cn(
          BASE_CONTROL,
          "appearance-none pr-9",
          invalid ? "border-danger" : "border-line",
          className
        )}
        {...props}
      >
        {children}
      </select>
      <svg
        width="16"
        height="16"
        viewBox="0 0 16 16"
        fill="none"
        aria-hidden="true"
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted"
      >
        <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    </div>
  );
}

interface TextAreaInputProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
}

export function TextAreaInput({ invalid, className, ...props }: TextAreaInputProps) {
  return (
    <textarea
      aria-invalid={invalid || undefined}
      className={cn(
        BASE_CONTROL,
        "min-h-[96px] resize-y",
        invalid ? "border-danger" : "border-line",
        className
      )}
      {...props}
    />
  );
}
