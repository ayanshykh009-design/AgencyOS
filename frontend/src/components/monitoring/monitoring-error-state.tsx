"use client";

// Shared error state for monitoring components.
//
// Ensures API failures are announced to assistive technology (role="alert"),
// are never silently rendered as valid zero-valued metrics, and expose a
// keyboard-accessible Retry control that refetches the SAME query key.

import { Button } from "@/components/ui/button";

interface MonitoringErrorStateProps {
  message: string;
  onRetry: () => void;
  retrying?: boolean;
}

export function MonitoringErrorState({ message, onRetry, retrying }: MonitoringErrorStateProps) {
  return (
    <div role="alert" className="flex flex-col items-center gap-3 py-8 text-destructive">
      <p>{message}</p>
      <Button
        variant="outline"
        onClick={onRetry}
        disabled={retrying}
        aria-label="Retry loading monitoring data"
      >
        {retrying ? "Retrying…" : "Retry"}
      </Button>
    </div>
  );
}
