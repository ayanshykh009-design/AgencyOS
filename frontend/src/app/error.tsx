"use client";

import { Button } from "@/components/ui/button";

/**
 * Global error boundary (root layout).
 * Catches render errors anywhere in the app and offers a recovery action.
 * Logging can be wired to the observability stack here.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  // TODO: report `error.digest`/`error.message` to the error-tracking service.
  console.error(error);

  return (
    <html lang="en">
      <body className="flex min-h-screen items-center justify-center">
        <main className="flex flex-col items-center gap-4 text-center">
          <h1 className="text-2xl font-semibold">Something went wrong</h1>
          <p className="max-w-sm text-sm text-muted-foreground">
            An unexpected error occurred. Please try again.
          </p>
          <Button type="button" onClick={() => reset()}>
            Try again
          </Button>
        </main>
      </body>
    </html>
  );
}
