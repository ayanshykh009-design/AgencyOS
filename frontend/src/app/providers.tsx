// Client-side providers for the app (React Query).
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect } from "react";
import { useState } from "react";

import { refresh } from "@/services/auth";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      })
  );

  useEffect(() => {
    // Bootstrap the in-memory access token from the HttpOnly refresh cookie.
    void refresh().catch(() => {
      // Unauthenticated or expired; leave the app in the signed-out state.
    });
  }, []);

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
