// Select primitive with composable sub-components.
import { cn } from "@/lib/utils";
import * as React from "react";

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean;
}

export function Select({
  className,
  invalid,
  children,
  ...props
}: SelectProps & { children?: React.ReactNode }) {
  return (
    <select
      className={cn(
        "w-full rounded-md border bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900 disabled:opacity-50",
        invalid ? "border-red-400" : "border-gray-300",
        className
      )}
      {...props}
    >
      {children}
    </select>
  );
}

export function SelectTrigger({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLButtonElement> & { children?: React.ReactNode }) {
  return (
    <button
      className={cn(
        "w-full rounded-md border bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900 disabled:opacity-50 text-left",
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function SelectContent({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { children?: React.ReactNode }) {
  return (
    <div
      className={cn(
        "relative z-50 max-h-96 overflow-y-auto overflow-x-hidden rounded-md border bg-white py-1 text-sm shadow-md",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function SelectItem({
  className,
  value,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { value: string }) {
  return (
    <div
      className={cn(
        "relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none focus:bg-gray-100 focus:text-gray-900 data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
        className
      )}
      role="option"
      aria-selected="false"
      data-value={value}
      {...props}
    >
      {children}
    </div>
  );
}

export function SelectValue({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn("truncate", className)} {...props} />;
}
