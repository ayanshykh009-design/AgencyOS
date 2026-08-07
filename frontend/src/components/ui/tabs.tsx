// Minimal Tabs primitive (no Radix) with context-driven active state.
"use client";

import { createContext, useContext, useState } from "react";

import { cn } from "@/lib/utils";

interface TabsContextValue {
  value: string;
  setValue: (value: string) => void;
}

const TabsContext = createContext<TabsContextValue | null>(null);

function useTabsContext(): TabsContextValue {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error("Tabs components must be used within a <Tabs>");
  return ctx;
}

interface TabsProps {
  defaultValue: string;
  className?: string;
  children: React.ReactNode;
}

export function Tabs({ defaultValue, className, children }: TabsProps) {
  const [value, setValue] = useState(defaultValue);
  return (
    <TabsContext.Provider value={{ value, setValue }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  );
}

interface TabsListProps {
  className?: string;
  children: React.ReactNode;
}

export function TabsList({ className, children }: TabsListProps) {
  return <div className={cn("flex flex-wrap gap-1 border-b", className)}>{children}</div>;
}

interface TabsTriggerProps {
  value: string;
  className?: string;
  children: React.ReactNode;
}

export function TabsTrigger({ value, className, children }: TabsTriggerProps) {
  const { value: active, setValue } = useTabsContext();
  const isActive = active === value;
  return (
    <button
      type="button"
      className={cn(
        "px-3 py-1.5 text-sm font-medium rounded-t-md border-b-2",
        isActive
          ? "border-gray-900 text-gray-900"
          : "border-transparent text-gray-500 hover:text-gray-900",
        className
      )}
      onClick={() => setValue(value)}
    >
      {children}
    </button>
  );
}

interface TabsContentProps {
  value: string;
  className?: string;
  children: React.ReactNode;
}

export function TabsContent({ value, className, children }: TabsContentProps) {
  const { value: active } = useTabsContext();
  if (active !== value) return null;
  return <div className={cn("pt-4", className)}>{children}</div>;
}
