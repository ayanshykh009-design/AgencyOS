"use client";

// Six single-digit code boxes (Sheet 2A screen 09). Auto-advances, supports
// backspace and full-code paste, and exposes an invalid (red) visual state.
import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

const LENGTH = 6;

interface CodeBoxesProps {
  value: string;
  onChange: (value: string) => void;
  invalid?: boolean;
  disabled?: boolean;
  autoFocus?: boolean;
  "aria-label"?: string;
}

const BOX_BASE =
  "h-12 w-10 rounded-lg border bg-deep-graphite text-center font-mono text-xl text-off-white caret-transparent transition-colors focus:outline-none focus-visible:ring-[1.4px] focus-visible:ring-silver sm:h-14 sm:w-12 sm:text-2xl";

export function CodeBoxes({
  value,
  onChange,
  invalid = false,
  disabled = false,
  autoFocus = true,
  "aria-label": ariaLabel = "Verification code",
}: CodeBoxesProps) {
  const refs = useRef<Array<HTMLInputElement | null>>([]);
  const digits = Array.from({ length: LENGTH }, (_, index) => value[index] ?? "");

  useEffect(() => {
    if (autoFocus) refs.current[0]?.focus();
  }, [autoFocus]);

  const commit = (next: string) => onChange(next.slice(0, LENGTH));

  function handleChange(index: number, raw: string) {
    const picked = raw.replace(/\D/g, "");
    if (picked.length === 0) {
      // Deletion inside a filled box: clear it.
      commit(value.slice(0, index) + value.slice(index + 1));
      return;
    }
    const merged = (value.slice(0, index) + picked + value.slice(index)).replace(/\D/g, "");
    commit(merged);
    const nextIndex = Math.min(index + picked.length, LENGTH - 1);
    refs.current[nextIndex]?.focus();
  }

  function handleKeyDown(index: number, event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Backspace" && !digits[index] && index > 0) {
      event.preventDefault();
      commit(value.slice(0, index - 1) + value.slice(index));
      refs.current[index - 1]?.focus();
    } else if (event.key === "ArrowLeft" && index > 0) {
      event.preventDefault();
      refs.current[index - 1]?.focus();
    } else if (event.key === "ArrowRight" && index < LENGTH - 1) {
      event.preventDefault();
      refs.current[index + 1]?.focus();
    }
  }

  function handlePaste(event: React.ClipboardEvent<HTMLInputElement>) {
    const pasted = event.clipboardData.getData("text").replace(/\D/g, "").slice(0, LENGTH);
    if (pasted) {
      event.preventDefault();
      commit(pasted);
      refs.current[Math.min(pasted.length, LENGTH - 1)]?.focus();
    }
  }

  return (
    <div className="flex justify-center gap-2 sm:gap-3" role="group" aria-label={ariaLabel}>
      {digits.map((digit, index) => (
        <input
          key={index}
          ref={(node) => {
            refs.current[index] = node;
          }}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={1}
          autoComplete={index === 0 ? "one-time-code" : "off"}
          aria-label={`Digit ${index + 1}`}
          aria-invalid={invalid || undefined}
          disabled={disabled}
          value={digit}
          onChange={(event) => handleChange(index, event.target.value)}
          onKeyDown={(event) => handleKeyDown(index, event)}
          onPaste={handlePaste}
          className={cn(
            BOX_BASE,
            invalid ? "border-danger" : "border-line",
            digit && !invalid && "border-soft-gray",
            disabled && "cursor-not-allowed opacity-60"
          )}
        />
      ))}
    </div>
  );
}
