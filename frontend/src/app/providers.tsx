// Client-side providers for the app (React Query).
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { refresh } from "@/services/auth";
import { installPrincipalIsolation } from "@/lib/principal-cache";

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

  // Tenant/session isolation: cached query data must never survive a logout
  // or a principal change into another user's/org's session. The isolation
  // helper scopes the cache by composite identity (organization_id : user_id)
  // and clears it on any change — including logout. Workspace pages hold
  // their data in component state and remount on navigation or lead/principal
  // change (see the leads/[id] page keys).
  useEffect(() => {
    return installPrincipalIsolation(queryClient);
  }, [queryClient]);

  useEffect(() => {
    // Bootstrap the in-memory access token from the HttpOnly refresh cookie.
    void refresh().catch(() => {
      // Unauthenticated or expired; leave the app in the signed-out state.
    });
  }, []);

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
