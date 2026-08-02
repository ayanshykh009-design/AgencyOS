// React hook exposing the current auth session with reactive updates.
"use client";

import { useEffect, useState } from "react";

import { getSession, subscribe, type Session } from "@/lib/session";

export function useAuth(): Session | null {
  const [session, setSessionState] = useState<Session | null>(() => getSession());

  useEffect(() => {
    return subscribe(() => setSessionState(getSession()));
  }, []);

  return session;
}
